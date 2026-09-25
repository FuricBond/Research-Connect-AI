"""
Phase 5.10 — Faculty Research Opportunities & Project Postings.

Covers the invariants that make a posting trustworthy to the researchers reading it:

  Authorship    Only FACULTY and ADMIN accounts may author postings; only the author (or an
                administrator) may modify one.
  Visibility    Only OPEN postings are publicly discoverable. An unpublished draft is not
                merely hidden — its existence is not disclosed, so probing an id cannot
                distinguish "no such posting" from "someone else's draft".
  Lifecycle     Every transition is explicitly enumerated. An outcome state (FILLED,
                CANCELLED) cannot be quietly reopened under the same posting.
  Isolation     One author's postings never appear in another author's own-postings view.
  Performance   Listing is bounded in query count regardless of how many postings exist.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from app.db.session import get_db
from app.db.types import TSVector, Vector
from app.main import app
from app.models.base import Base
from app.models.research_posting import PostingStatus, PostingType, ResearchPostingModel
from app.models.research_profile import ResearchProfileModel
from app.models.topic import TopicModel
from app.models.user import UserModel
from app.schemas.research_posting import ResearchPostingCreate, ResearchPostingUpdate
from app.services.research_posting_service import (
    InvalidPostingTransitionError,
    PostingNotFoundError,
    PostingPermissionError,
    ResearchPostingService,
    VALID_TRANSITIONS,
)

compiles(JSONB, "sqlite")(lambda type_, compiler, **kw: "JSON")
compiles(Vector, "sqlite")(lambda type_, compiler, **kw: "TEXT")
compiles(TSVector, "sqlite")(lambda type_, compiler, **kw: "TEXT")


@pytest.fixture
def db_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_session: Session) -> TestClient:
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _make_account(
    db: Session,
    email: str,
    role: str,
    *,
    full_name: str = "Dr. Test",
    institution: str = "Test University",
) -> tuple[UserModel, ResearchProfileModel]:
    user = UserModel(
        id=uuid.uuid4(),
        email=email,
        hashed_password="hashed",
        full_name=full_name,
        role=role,
        is_active=True,
    )
    db.add(user)
    db.flush()
    profile = ResearchProfileModel(
        id=uuid.uuid4(),
        user_id=user.id,
        academic_status="FACULTY" if role == "FACULTY" else "POSTGRADUATE",
        institution=institution,
        department="Computer Science",
    )
    db.add(profile)
    db.commit()
    return user, profile


@pytest.fixture
def faculty(db_session: Session):
    return _make_account(db_session, "faculty@university.edu", "FACULTY", full_name="Dr. Amara Okafor")


@pytest.fixture
def other_faculty(db_session: Session):
    return _make_account(db_session, "other.faculty@university.edu", "FACULTY", full_name="Dr. Lin Wei")


@pytest.fixture
def student(db_session: Session):
    return _make_account(db_session, "student@university.edu", "STUDENT", full_name="Priya Raghavan")


@pytest.fixture
def admin(db_session: Session):
    return _make_account(db_session, "admin@university.edu", "ADMIN", full_name="Sam Whitfield")


def _create_payload(**overrides) -> ResearchPostingCreate:
    data = {
        "title": "Doctoral position in neural information retrieval",
        "posting_type": PostingType.PROJECT,
        "description": "We are seeking a doctoral researcher to work on dense retrieval models.",
        "required_skills": ["Python", "PyTorch"],
        "positions_available": 2,
        "application_deadline": datetime.now(timezone.utc) + timedelta(days=45),
    }
    data.update(overrides)
    return ResearchPostingCreate(**data)


def _create_posting(db: Session, faculty_pair, **overrides) -> ResearchPostingModel:
    user, profile = faculty_pair
    return ResearchPostingService.create_posting(db, profile, user, _create_payload(**overrides))


# ===========================================================================
# Authorship
# ===========================================================================


def test_faculty_can_author_posting(db_session: Session, faculty):
    posting = _create_posting(db_session, faculty)

    assert posting.status == PostingStatus.DRAFT.value, "a new posting must start unpublished"
    assert posting.author_user_id == faculty[0].id
    assert posting.author_profile_id == faculty[1].id
    # Placement defaults to the author's affiliation rather than making them retype it.
    assert posting.institution == "Test University"
    assert posting.department == "Computer Science"


def test_admin_can_author_posting(db_session: Session, admin):
    posting = _create_posting(db_session, admin)
    assert posting.status == PostingStatus.DRAFT.value


def test_student_cannot_author_posting(db_session: Session, student):
    user, profile = student
    with pytest.raises(PostingPermissionError, match="FACULTY and ADMIN"):
        ResearchPostingService.create_posting(db_session, profile, user, _create_payload())


def test_non_author_cannot_modify_posting(db_session: Session, faculty, other_faculty):
    posting = _create_posting(db_session, faculty)
    with pytest.raises(PostingPermissionError):
        ResearchPostingService.update_posting(
            db_session, posting.id, other_faculty[0], ResearchPostingUpdate(title="Hijacked title here")
        )


def test_administrator_may_moderate_another_authors_posting(db_session: Session, faculty, admin):
    """Administrators need to be able to take down a posting they did not write."""
    posting = _create_posting(db_session, faculty)
    updated = ResearchPostingService.update_posting(
        db_session, posting.id, admin[0], ResearchPostingUpdate(summary="Moderated by administrator")
    )
    assert updated.summary == "Moderated by administrator"


# ===========================================================================
# Visibility
# ===========================================================================


def test_draft_is_visible_to_its_author(db_session: Session, faculty):
    posting = _create_posting(db_session, faculty)
    loaded = ResearchPostingService.get_posting(db_session, posting.id, requesting_user=faculty[0])
    assert loaded.id == posting.id


def test_draft_existence_is_not_disclosed_to_others(db_session: Session, faculty, other_faculty):
    """
    A draft must not be distinguishable from a nonexistent posting, otherwise an id probe
    reveals that a competitor is preparing a position.
    """
    posting = _create_posting(db_session, faculty)

    with pytest.raises(PostingNotFoundError):
        ResearchPostingService.get_posting(db_session, posting.id, requesting_user=other_faculty[0])
    with pytest.raises(PostingNotFoundError):
        ResearchPostingService.get_posting(db_session, posting.id, requesting_user=None)

    missing_id = uuid.uuid4()
    with pytest.raises(PostingNotFoundError) as draft_err:
        ResearchPostingService.get_posting(db_session, posting.id, requesting_user=None)
    with pytest.raises(PostingNotFoundError) as absent_err:
        ResearchPostingService.get_posting(db_session, missing_id, requesting_user=None)
    assert str(draft_err.value).replace(str(posting.id), "X") == str(absent_err.value).replace(
        str(missing_id), "X"
    ), "the two errors must be indistinguishable apart from the id"


def test_only_open_postings_are_publicly_listed(db_session: Session, faculty):
    draft = _create_posting(db_session, faculty, title="Draft posting about retrieval systems")
    published = _create_posting(db_session, faculty, title="Published posting about retrieval")
    ResearchPostingService.transition_status(db_session, published.id, faculty[0], PostingStatus.OPEN)

    public = ResearchPostingService.list_postings(db_session)
    ids = {p.id for p in public.postings}
    assert published.id in ids
    assert draft.id not in ids
    assert public.total == 1


def test_author_can_list_own_drafts(db_session: Session, faculty):
    draft = _create_posting(db_session, faculty)
    listed = ResearchPostingService.list_postings(
        db_session,
        requesting_user=faculty[0],
        author_profile_id=faculty[1].id,
        include_own_drafts=True,
    )
    assert draft.id in {p.id for p in listed.postings}


def test_own_postings_view_is_isolated_between_authors(db_session: Session, faculty, other_faculty):
    mine = _create_posting(db_session, faculty)
    theirs = _create_posting(db_session, other_faculty)

    listed = ResearchPostingService.list_postings(
        db_session,
        requesting_user=faculty[0],
        author_profile_id=faculty[1].id,
        include_own_drafts=True,
    )
    ids = {p.id for p in listed.postings}
    assert mine.id in ids
    assert theirs.id not in ids


# ===========================================================================
# Lifecycle state machine
# ===========================================================================


def test_publishing_records_published_at(db_session: Session, faculty):
    posting = _create_posting(db_session, faculty)
    assert posting.published_at is None

    published = ResearchPostingService.transition_status(
        db_session, posting.id, faculty[0], PostingStatus.OPEN
    )
    assert published.status == PostingStatus.OPEN.value
    assert published.published_at is not None


def test_republishing_preserves_original_published_at(db_session: Session, faculty):
    """`published_at` is a first-publication fact, so closing and reopening must not reset it."""
    posting = _create_posting(db_session, faculty)
    ResearchPostingService.transition_status(db_session, posting.id, faculty[0], PostingStatus.OPEN)
    first_published = posting.published_at

    ResearchPostingService.transition_status(db_session, posting.id, faculty[0], PostingStatus.CLOSED)
    reopened = ResearchPostingService.transition_status(
        db_session, posting.id, faculty[0], PostingStatus.OPEN
    )
    assert reopened.published_at == first_published
    assert reopened.closed_at is None, "reopening must clear the stale closure timestamp"


def test_filled_posting_cannot_be_reopened(db_session: Session, faculty):
    """
    Reopening a filled search under the same posting would mislead applicants who were
    already rejected against it, so FILLED only leads to ARCHIVED.
    """
    posting = _create_posting(db_session, faculty)
    ResearchPostingService.transition_status(db_session, posting.id, faculty[0], PostingStatus.OPEN)
    ResearchPostingService.transition_status(db_session, posting.id, faculty[0], PostingStatus.FILLED)

    with pytest.raises(InvalidPostingTransitionError, match="FILLED"):
        ResearchPostingService.transition_status(db_session, posting.id, faculty[0], PostingStatus.OPEN)

    assert ResearchPostingService.get_allowed_transitions(PostingStatus.FILLED) == [
        PostingStatus.ARCHIVED
    ]


def test_archived_is_terminal_and_uneditable(db_session: Session, faculty):
    posting = _create_posting(db_session, faculty)
    ResearchPostingService.transition_status(db_session, posting.id, faculty[0], PostingStatus.CANCELLED)
    ResearchPostingService.transition_status(db_session, posting.id, faculty[0], PostingStatus.ARCHIVED)

    assert ResearchPostingService.get_allowed_transitions(PostingStatus.ARCHIVED) == []
    with pytest.raises(InvalidPostingTransitionError, match="archived"):
        ResearchPostingService.update_posting(
            db_session, posting.id, faculty[0], ResearchPostingUpdate(title="Edited after archival")
        )


def test_transition_to_current_status_is_idempotent(db_session: Session, faculty):
    posting = _create_posting(db_session, faculty)
    unchanged = ResearchPostingService.transition_status(
        db_session, posting.id, faculty[0], PostingStatus.DRAFT
    )
    assert unchanged.status == PostingStatus.DRAFT.value


def test_every_status_has_an_explicit_transition_set():
    """A status missing from the table would silently become a dead end."""
    for status in PostingStatus:
        assert status in VALID_TRANSITIONS, f"{status.value} has no declared transitions"
    # Every declared target must itself be a known status.
    for targets in VALID_TRANSITIONS.values():
        for target in targets:
            assert isinstance(target, PostingStatus)


def test_archived_is_reachable_from_every_other_status():
    """Any posting must be able to reach a resting state without being deleted."""
    reachable_to_archived = set()
    for status, targets in VALID_TRANSITIONS.items():
        if PostingStatus.ARCHIVED in targets or status == PostingStatus.ARCHIVED:
            reachable_to_archived.add(status)
    # OPEN reaches ARCHIVED indirectly via CLOSED/FILLED/CANCELLED.
    assert PostingStatus.OPEN not in reachable_to_archived
    assert VALID_TRANSITIONS[PostingStatus.OPEN] & {
        PostingStatus.CLOSED,
        PostingStatus.FILLED,
        PostingStatus.CANCELLED,
    }
    for status in PostingStatus:
        if status in (PostingStatus.OPEN,):
            continue
        assert status in reachable_to_archived, f"{status.value} cannot reach ARCHIVED"


# ===========================================================================
# Deletion
# ===========================================================================


def test_draft_can_be_deleted(db_session: Session, faculty):
    posting = _create_posting(db_session, faculty)
    ResearchPostingService.delete_posting(db_session, posting.id, faculty[0])
    assert db_session.get(ResearchPostingModel, posting.id) is None


def test_published_posting_cannot_be_deleted(db_session: Session, faculty):
    """Deleting a published posting would erase something applicants may have acted on."""
    posting = _create_posting(db_session, faculty)
    ResearchPostingService.transition_status(db_session, posting.id, faculty[0], PostingStatus.OPEN)
    with pytest.raises(InvalidPostingTransitionError, match="DRAFT"):
        ResearchPostingService.delete_posting(db_session, posting.id, faculty[0])


# ===========================================================================
# Derived fields, topics and filtering
# ===========================================================================


def test_derived_deadline_fields(db_session: Session, faculty):
    posting = _create_posting(
        db_session, faculty, application_deadline=datetime.now(timezone.utc) + timedelta(days=10)
    )
    ResearchPostingService.transition_status(db_session, posting.id, faculty[0], PostingStatus.OPEN)

    read = ResearchPostingService.build_posting_read(posting, requesting_user=faculty[0])
    assert read.is_accepting_applications is True
    assert read.days_until_deadline in (9, 10)
    assert read.is_owner is True


def test_draft_is_never_accepting_applications(db_session: Session, faculty):
    posting = _create_posting(db_session, faculty)
    read = ResearchPostingService.build_posting_read(posting)
    assert read.is_accepting_applications is False


def test_expired_deadline_stops_accepting_applications(db_session: Session, faculty):
    posting = _create_posting(db_session, faculty)
    ResearchPostingService.transition_status(db_session, posting.id, faculty[0], PostingStatus.OPEN)
    # Set the deadline into the past directly: the create schema rightly refuses past dates.
    posting.application_deadline = datetime.now(timezone.utc) - timedelta(days=1)
    db_session.commit()

    read = ResearchPostingService.build_posting_read(posting)
    assert read.is_accepting_applications is False
    assert read.days_until_deadline is not None and read.days_until_deadline < 0


def test_topic_links_and_filtering(db_session: Session, faculty):
    topic = TopicModel(id=uuid.uuid4(), name="Information Retrieval", slug="information-retrieval")
    other_topic = TopicModel(id=uuid.uuid4(), name="Computer Vision", slug="computer-vision")
    db_session.add_all([topic, other_topic])
    db_session.commit()

    posting = _create_posting(db_session, faculty, topic_ids=[topic.id])
    ResearchPostingService.transition_status(db_session, posting.id, faculty[0], PostingStatus.OPEN)

    read = ResearchPostingService.build_posting_read(posting)
    assert [t.slug for t in read.topics] == ["information-retrieval"]
    assert read.topics[0].is_primary is True

    matched = ResearchPostingService.list_postings(db_session, topic_id=topic.id)
    assert matched.total == 1
    unmatched = ResearchPostingService.list_postings(db_session, topic_id=other_topic.id)
    assert unmatched.total == 0


def test_unknown_topic_ids_are_ignored_rather_than_rejected(db_session: Session, faculty):
    """A stale topic id from a client must not block an otherwise valid posting."""
    posting = _create_posting(db_session, faculty, topic_ids=[uuid.uuid4()])
    read = ResearchPostingService.build_posting_read(posting)
    assert read.topics == []


def test_updating_topics_replaces_the_previous_set(db_session: Session, faculty):
    first = TopicModel(id=uuid.uuid4(), name="Topic One", slug="topic-one")
    second = TopicModel(id=uuid.uuid4(), name="Topic Two", slug="topic-two")
    db_session.add_all([first, second])
    db_session.commit()

    posting = _create_posting(db_session, faculty, topic_ids=[first.id])
    updated = ResearchPostingService.update_posting(
        db_session, posting.id, faculty[0], ResearchPostingUpdate(topic_ids=[second.id])
    )
    read = ResearchPostingService.build_posting_read(updated)
    assert [t.slug for t in read.topics] == ["topic-two"]


def test_search_and_type_filters(db_session: Session, faculty):
    a = _create_posting(
        db_session, faculty, title="Thesis topic in graph learning", posting_type=PostingType.THESIS_TOPIC
    )
    b = _create_posting(
        db_session, faculty, title="Collaboration on retrieval evaluation", posting_type=PostingType.COLLABORATION
    )
    for posting in (a, b):
        ResearchPostingService.transition_status(db_session, posting.id, faculty[0], PostingStatus.OPEN)

    by_type = ResearchPostingService.list_postings(db_session, posting_type=PostingType.THESIS_TOPIC)
    assert {p.id for p in by_type.postings} == {a.id}

    by_search = ResearchPostingService.list_postings(db_session, search="retrieval evaluation")
    assert {p.id for p in by_search.postings} == {b.id}


def test_author_summary_aggregates_by_status_and_type(db_session: Session, faculty):
    open_posting = _create_posting(db_session, faculty)
    ResearchPostingService.transition_status(db_session, open_posting.id, faculty[0], PostingStatus.OPEN)
    _create_posting(db_session, faculty, posting_type=PostingType.THESIS_TOPIC)

    summary = ResearchPostingService.get_author_summary(db_session, faculty[1].id)
    assert summary.total == 2
    assert summary.by_status[PostingStatus.OPEN.value] == 1
    assert summary.by_status[PostingStatus.DRAFT.value] == 1
    assert summary.by_type[PostingType.THESIS_TOPIC.value] == 1
    assert summary.open_accepting_applications == 1


def test_listing_query_count_is_bounded(db_session: Session, faculty):
    """Query count must not grow with the number of postings returned."""
    for i in range(25):
        posting = _create_posting(db_session, faculty, title=f"Open research posting number {i}")
        ResearchPostingService.transition_status(db_session, posting.id, faculty[0], PostingStatus.OPEN)

    engine = db_session.get_bind()
    count = 0

    def _listener(*args, **kwargs):
        nonlocal count
        count += 1

    event.listen(engine, "before_cursor_execute", _listener)
    try:
        result = ResearchPostingService.list_postings(db_session, limit=25)
    finally:
        event.remove(engine, "before_cursor_execute", _listener)

    assert len(result.postings) == 25
    assert count <= 4, f"expected a bounded query count, executed {count}"


# ===========================================================================
# REST API
# ===========================================================================


def test_api_author_publish_and_discover(client: TestClient, faculty):
    user, _ = faculty
    headers = {"X-User-ID": str(user.id)}

    created = client.post(
        "/api/v1/postings",
        headers=headers,
        json={
            "title": "Research assistant for retrieval benchmarking",
            "posting_type": "PROJECT",
            "description": "Assist with building and running retrieval benchmarks for a year.",
            "required_skills": ["Python"],
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["status"] == "DRAFT"
    assert body["is_owner"] is True
    assert "OPEN" in body["allowed_transitions"]
    posting_id = body["id"]

    # Not discoverable while it is a draft.
    assert client.get("/api/v1/postings").json()["total"] == 0

    published = client.post(
        f"/api/v1/postings/{posting_id}/transition",
        headers=headers,
        json={"target_status": "OPEN", "note": "Funding confirmed"},
    )
    assert published.status_code == 200
    assert published.json()["status"] == "OPEN"

    discovered = client.get("/api/v1/postings")
    assert discovered.status_code == 200
    assert discovered.json()["total"] == 1


def test_api_student_cannot_author(client: TestClient, student):
    user, _ = student
    res = client.post(
        "/api/v1/postings",
        headers={"X-User-ID": str(user.id)},
        json={
            "title": "Unauthorized posting attempt by a student",
            "posting_type": "PROJECT",
            "description": "This should be refused because students do not supervise research.",
        },
    )
    assert res.status_code == 403


def test_api_anonymous_cannot_author(client: TestClient, faculty):
    res = client.post(
        "/api/v1/postings",
        json={
            "title": "Anonymous posting attempt without credentials",
            "posting_type": "PROJECT",
            "description": "This must be refused because no identity was supplied.",
        },
    )
    assert res.status_code == 401


def test_api_cross_author_update_forbidden(client: TestClient, db_session: Session, faculty, other_faculty):
    posting = _create_posting(db_session, faculty)
    res = client.patch(
        f"/api/v1/postings/{posting.id}",
        headers={"X-User-ID": str(other_faculty[0].id)},
        json={"title": "Attempted hijack of another author's posting"},
    )
    assert res.status_code == 403


def test_api_draft_returns_404_for_non_author(client: TestClient, db_session: Session, faculty, other_faculty):
    posting = _create_posting(db_session, faculty)
    res = client.get(f"/api/v1/postings/{posting.id}", headers={"X-User-ID": str(other_faculty[0].id)})
    assert res.status_code == 404


def test_api_invalid_transition_returns_400(client: TestClient, db_session: Session, faculty):
    posting = _create_posting(db_session, faculty)
    res = client.post(
        f"/api/v1/postings/{posting.id}/transition",
        headers={"X-User-ID": str(faculty[0].id)},
        json={"target_status": "FILLED"},
    )
    assert res.status_code == 400
    assert "DRAFT" in res.json()["detail"]


def test_api_mine_and_summary(client: TestClient, db_session: Session, faculty):
    _create_posting(db_session, faculty)
    headers = {"X-User-ID": str(faculty[0].id)}

    mine = client.get("/api/v1/postings/mine", headers=headers)
    assert mine.status_code == 200
    assert mine.json()["total"] == 1

    summary = client.get("/api/v1/postings/mine/summary", headers=headers)
    assert summary.status_code == 200
    assert summary.json()["by_status"]["DRAFT"] == 1


def test_api_delete_draft(client: TestClient, db_session: Session, faculty):
    posting = _create_posting(db_session, faculty)
    res = client.delete(f"/api/v1/postings/{posting.id}", headers={"X-User-ID": str(faculty[0].id)})
    assert res.status_code == 204
    assert db_session.get(ResearchPostingModel, posting.id) is None


def test_api_rejects_past_application_deadline(client: TestClient, faculty):
    res = client.post(
        "/api/v1/postings",
        headers={"X-User-ID": str(faculty[0].id)},
        json={
            "title": "Posting with an already expired deadline",
            "posting_type": "PROJECT",
            "description": "The deadline supplied here is in the past and must be refused.",
            "application_deadline": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
        },
    )
    assert res.status_code == 422


def test_api_account_without_profile_gets_actionable_error(client: TestClient, db_session: Session):
    user = UserModel(
        id=uuid.uuid4(),
        email="profileless@university.edu",
        hashed_password="hashed",
        full_name="No Profile",
        role="FACULTY",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    res = client.post(
        "/api/v1/postings",
        headers={"X-User-ID": str(user.id)},
        json={
            "title": "Posting attempted without a researcher profile",
            "posting_type": "PROJECT",
            "description": "A posting is authored by an academic identity, which is missing here.",
        },
    )
    assert res.status_code == 409
    assert "profile" in res.json()["detail"].lower()
