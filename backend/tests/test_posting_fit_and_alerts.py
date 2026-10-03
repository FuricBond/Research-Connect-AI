"""
Phase 5.15 — Posting fit for students, and "notify me when a new posting matches".

  Scorer     Deterministic, bounded 0-100, reasons in a stable order. A topic match outranks a
             skills-only match; an EXCLUDED preference caps the score at 20; a student with no
             signals gets no score, only guidance; a post-doc needs a doctorate.
  Reads      Students only. Visibility follows the posting; its author gets 403. Nothing is
             written and no profile is created.
  Batch      Only OPEN postings, in request order, at most 100 ids.
  Alerts     Sent once, on the first publish, only to opted-in students with in-app
             notifications on and a fit at or above their own threshold. Never the author.
             Reopening never alerts again, and an alert failure never blocks publishing.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from app.db.session import get_db
from app.db.types import TSVector, Vector
from app.main import app
from app.models.base import Base
from app.models.notification import NotificationModel, NotificationPreferenceModel
from app.models.research_posting import PostingStatus, PostingType, ResearchPostingModel
from app.models.research_profile import ResearchProfileModel
from app.models.researcher_interest import ResearcherInterestModel
from app.models.researcher_preference import ResearcherPreferenceModel
from app.models.topic import TopicModel
from app.models.user import UserModel
from app.schemas.research_posting import ResearchPostingCreate
from app.services import posting_match_alert_service
from app.services.posting_fit_service import (
    EXCLUDED_LABEL,
    NO_SIGNALS_GAP,
    PostingFitService,
)
from app.services.research_posting_service import ResearchPostingService

compiles(JSONB, "sqlite")(lambda type_, compiler, **kw: "JSON")
compiles(Vector, "sqlite")(lambda type_, compiler, **kw: "TEXT")
compiles(TSVector, "sqlite")(lambda type_, compiler, **kw: "TEXT")

NOW = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)


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


# ── Fixture helpers (from the Phase 5.10 tests) ─────────────────────────────


def _make_account(
    db: Session,
    email: str,
    role: str,
    *,
    full_name: str = "Dr. Test",
    institution: str = "Test University",
    academic_status: str | None = None,
    keywords: list[str] | None = None,
    is_active: bool = True,
    with_profile: bool = True,
) -> tuple[UserModel, ResearchProfileModel | None]:
    user = UserModel(
        id=uuid.uuid4(),
        email=email,
        hashed_password="hashed",
        full_name=full_name,
        role=role,
        is_active=is_active,
    )
    db.add(user)
    db.flush()
    profile = None
    if with_profile:
        profile = ResearchProfileModel(
            id=uuid.uuid4(),
            user_id=user.id,
            academic_status=academic_status or ("FACULTY" if role == "FACULTY" else "POSTGRADUATE"),
            institution=institution,
            department="Computer Science",
            keywords=keywords or [],
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


def _topic(db: Session, slug: str) -> TopicModel:
    topic = db.execute(select(TopicModel).where(TopicModel.slug == slug)).scalar_one_or_none()
    if topic is None:
        topic = TopicModel(id=uuid.uuid4(), name=slug.replace("-", " ").title(), slug=slug)
        db.add(topic)
        db.commit()
    return topic


def _create_posting(
    db: Session,
    faculty_pair,
    *,
    topics: tuple[str, ...] = ("information-retrieval",),
    publish: bool = True,
    **overrides,
) -> ResearchPostingModel:
    user, profile = faculty_pair
    data = {
        "title": "Doctoral position in neural information retrieval",
        "posting_type": PostingType.PROJECT,
        "description": "We are seeking a doctoral researcher to work on dense retrieval models.",
        "required_skills": ["Python", "PyTorch"],
        "positions_available": 2,
        "application_deadline": datetime.now(timezone.utc) + timedelta(days=45),
        "topic_ids": [_topic(db, slug).id for slug in topics],
    }
    data.update(overrides)
    posting = ResearchPostingService.create_posting(db, profile, user, ResearchPostingCreate(**data))
    if publish:
        posting = ResearchPostingService.transition_status(db, posting.id, user, PostingStatus.OPEN)
    return posting


def _interest(db: Session, profile: ResearchProfileModel, slug: str, confidence: float = 1.0) -> None:
    topic = _topic(db, slug)
    db.add(
        ResearcherInterestModel(
            id=uuid.uuid4(),
            profile_id=profile.id,
            topic_id=topic.id,
            topic_name=topic.name,
            topic_slug=slug,
            strength=0.9,
            confidence=confidence,
            evidence_count=3,
            classification="PRIMARY_EXPERTISE",
            is_primary_expertise=False,
            source="TEST",
        )
    )
    db.commit()


def _preference(
    db: Session,
    profile: ResearchProfileModel,
    category: str,
    value: str,
    *,
    preference_type: str = "PREFERRED",
    canonical_id: uuid.UUID | None = None,
) -> None:
    db.add(
        ResearcherPreferenceModel(
            id=uuid.uuid4(),
            profile_id=profile.id,
            category=category,
            preference_type=preference_type,
            preference_key=category.lower(),
            preference_value=value,
            display_label=value,
            canonical_id=canonical_id,
            strength=1.0,
            confidence=0.95,
            source="EXPLICIT",
            is_active=True,
        )
    )
    db.commit()


def _student(db: Session, name: str, **kwargs) -> tuple[UserModel, ResearchProfileModel]:
    email = f"{name.lower().replace(' ', '.')}.{uuid.uuid4().hex[:6]}@university.edu"
    return _make_account(db, email, "STUDENT", full_name=name, **kwargs)


def _fit(db: Session, posting: ResearchPostingModel, profile: ResearchProfileModel):
    signals = PostingFitService.load_signals(db, [profile])[profile.id]
    return PostingFitService.score(posting, signals, now=NOW)


def _headers(user: UserModel) -> dict[str, str]:
    return {"X-User-ID": str(user.id)}


# ===========================================================================
# Scorer
# ===========================================================================


def test_scorer_is_deterministic_bounded_and_orders_reasons_by_contribution(db_session, faculty):
    posting = _create_posting(
        db_session,
        faculty,
        topics=("information-retrieval", "machine-learning"),
        required_skills=["Python", "PyTorch", "Information Retrieval"],
    )
    _, student = _student(db_session, "Sam Student", keywords=["python"])
    _interest(db_session, student, "information-retrieval", confidence=0.9)

    first = _fit(db_session, posting, student)
    second = _fit(db_session, posting, student)

    assert first == second
    assert 0 <= first.score <= 100
    # topic 0.9 / 1.9 of 0.50, skills 2 of 3 of 0.30, opening 0.5 of 0.20.
    assert first.score == 54
    assert first.band == "Good"
    assert [r.code for r in first.reasons] == ["TOPIC", "SKILLS", "OPENING"]
    assert first.reasons[0].matched == ["Information Retrieval"]
    assert first.reasons[1].matched == ["Python", "Information Retrieval"]
    assert first.gaps == ["PyTorch"]
    assert sum(r.weight for r in first.reasons) == pytest.approx(1.0)


def test_reasons_with_equal_contribution_are_ordered_by_code(db_session, faculty):
    posting = _create_posting(db_session, faculty, topics=("robotics",), required_skills=["ROS"])
    _, student = _student(db_session, "Sam Student", keywords=["poetry"])

    fit = _fit(db_session, posting, student)

    # Opening contributes; skills and topic contribute nothing and tie, so code decides.
    assert [r.code for r in fit.reasons] == ["OPENING", "SKILLS", "TOPIC"]
    assert fit.score == 10
    assert fit.band == "Low"


def test_a_topic_match_outranks_a_skills_only_match(db_session, faculty):
    posting = _create_posting(db_session, faculty, required_skills=["Python"])
    _, by_topic = _student(db_session, "Topic Student")
    _interest(db_session, by_topic, "information-retrieval")
    _, by_skill = _student(db_session, "Skill Student", keywords=["Python"])

    topic_fit = _fit(db_session, posting, by_topic)
    skill_fit = _fit(db_session, posting, by_skill)

    assert topic_fit.score == 60
    assert skill_fit.score == 40
    assert topic_fit.score > skill_fit.score


def test_an_excluded_topic_or_type_caps_the_score_at_20(db_session, faculty):
    posting = _create_posting(
        db_session, faculty, topics=("information-retrieval", "robotics"), required_skills=["Python"]
    )
    _, student = _student(db_session, "Sam Student", keywords=["python"])
    _interest(db_session, student, "information-retrieval")
    uncapped = _fit(db_session, posting, student).score
    assert uncapped > 20

    _preference(
        db_session, student, "TOPIC", "robotics",
        preference_type="EXCLUDED", canonical_id=_topic(db_session, "robotics").id,
    )
    capped = _fit(db_session, posting, student)

    assert capped.score == 20
    excluded = next(r for r in capped.reasons if r.code == "EXCLUDED")
    assert excluded.label == EXCLUDED_LABEL
    assert excluded.matched == ["Robotics"]

    _, other = _student(db_session, "Type Excluder", keywords=["python"])
    _interest(db_session, other, "information-retrieval")
    _preference(db_session, other, "OPPORTUNITY_TYPE", "PROJECT", preference_type="EXCLUDED")
    assert _fit(db_session, posting, other).score == 20


def test_no_signals_gives_no_score_and_guidance(db_session, faculty):
    posting = _create_posting(db_session, faculty)
    _, student = _student(db_session, "Blank Student")

    fit = _fit(db_session, posting, student)

    assert fit.score is None
    assert fit.band is None
    assert fit.gaps == [NO_SIGNALS_GAP]


def test_postdoc_needs_a_doctorate(db_session, faculty):
    posting = _create_posting(
        db_session, faculty, posting_type=PostingType.POSTDOC, topics=(), required_skills=[]
    )
    _, masters = _student(db_session, "Masters Student", academic_status="POSTGRADUATE", keywords=["ir"])
    _, doctor = _student(db_session, "Doctoral Student", academic_status="PHD", keywords=["ir"])

    masters_fit = _fit(db_session, posting, masters)
    doctor_fit = _fit(db_session, posting, doctor)

    # Only the opening part is present: type 0.5, stage 0 or 1, placement 0.5.
    assert masters_fit.score == 33
    assert doctor_fit.score == 67
    assert masters_fit.reasons[0].label == "Post-doctoral positions need a completed PhD"


def test_internships_suit_students_and_preferences_raise_the_opening(db_session, faculty):
    posting = _create_posting(
        db_session, faculty, posting_type=PostingType.INTERNSHIP, topics=(), required_skills=[],
        work_mode="REMOTE",
    )
    _, student = _student(db_session, "Intern Student", academic_status="UNDERGRADUATE")
    _preference(db_session, student, "OPPORTUNITY_TYPE", "INTERNSHIP")

    fit = _fit(db_session, posting, student)

    assert fit.score == 100
    assert fit.band == "Strong"
    assert fit.reasons[0].matched == ["a type of opening you prefer", "suited to your career stage", "remote"]


def test_a_passed_deadline_is_noted(db_session, faculty):
    posting = _create_posting(db_session, faculty)
    posting.application_deadline = NOW - timedelta(days=1)
    db_session.commit()
    _, student = _student(db_session, "Late Student", keywords=["python"])

    fit = _fit(db_session, posting, student)

    assert any(r.code == "DEADLINE_PASSED" and r.label == "Applications closed" for r in fit.reasons)


# ===========================================================================
# GET /postings/{id}/fit
# ===========================================================================


def test_fit_for_a_student(client, db_session, faculty):
    posting = _create_posting(db_session, faculty)
    user, profile = _student(db_session, "Sam Student", keywords=["python"])
    _interest(db_session, profile, "information-retrieval")

    res = client.get(f"/api/v1/postings/{posting.id}/fit", headers=_headers(user))

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["posting_id"] == str(posting.id)
    # topic 1.0 of 0.50, skills 1 of 2 of 0.30, opening 0.5 of 0.20.
    assert body["score"] == 75
    assert body["band"] == "Strong"
    assert body["gaps"] == ["PyTorch"]
    assert {r["code"] for r in body["reasons"]} == {"TOPIC", "SKILLS", "OPENING"}


def test_fit_access_rules(client, db_session, faculty, other_faculty):
    posting = _create_posting(db_session, faculty)
    draft = _create_posting(db_session, other_faculty, publish=False)
    student, _ = _student(db_session, "Sam Student")
    url = f"/api/v1/postings/{posting.id}/fit"

    assert client.get(url).status_code == 401
    assert client.get(url, headers=_headers(other_faculty[0])).status_code == 403
    assert client.get(url, headers=_headers(faculty[0])).status_code == 403, "the author is faculty"
    assert client.get(f"/api/v1/postings/{draft.id}/fit", headers=_headers(student)).status_code == 404

    # A student-role author still gets 403 for their own posting.
    posting.author_user_id = student.id
    db_session.commit()
    assert client.get(url, headers=_headers(student)).status_code == 403


def test_reading_fit_writes_nothing_and_creates_no_profile(client, db_session, faculty):
    posting = _create_posting(db_session, faculty)
    user, _ = _student(db_session, "No Profile", with_profile=False)
    user_id, posting_id = user.id, posting.id
    profiles_before = db_session.execute(select(func.count()).select_from(ResearchProfileModel)).scalar_one()

    statements: list[str] = []
    engine = db_session.get_bind()
    listener = lambda conn, cursor, statement, *args: statements.append(statement.lstrip().split()[0].upper())  # noqa: E731
    event.listen(engine, "before_cursor_execute", listener)
    try:
        single = client.get(f"/api/v1/postings/{posting_id}/fit", headers={"X-User-ID": str(user_id)})
        batch = client.post(
            "/api/v1/postings/fit-scores",
            json={"posting_ids": [str(posting_id)]},
            headers={"X-User-ID": str(user_id)},
        )
    finally:
        event.remove(engine, "before_cursor_execute", listener)

    assert single.status_code == 200 and batch.status_code == 200
    assert single.json()["score"] is None
    assert single.json()["gaps"] == [NO_SIGNALS_GAP]
    assert set(statements) == {"SELECT"}
    profiles_after = db_session.execute(select(func.count()).select_from(ResearchProfileModel)).scalar_one()
    assert profiles_after == profiles_before


def test_the_public_posting_read_carries_no_fit(client, db_session, faculty):
    posting = _create_posting(db_session, faculty)
    user, _ = _student(db_session, "Sam Student", keywords=["python"])

    one = client.get(f"/api/v1/postings/{posting.id}", headers=_headers(user)).json()
    listed = client.get("/api/v1/postings", headers=_headers(user)).json()

    assert "score" not in one and "fit" not in one
    assert all("fit" not in item and "score" not in item for item in listed["postings"])


# ===========================================================================
# POST /postings/fit-scores
# ===========================================================================


def test_batch_keeps_request_order_and_drops_invisible_postings(client, db_session, faculty, other_faculty):
    first = _create_posting(db_session, faculty, title="First open posting here")
    second = _create_posting(db_session, other_faculty, title="Second open posting here")
    draft = _create_posting(db_session, faculty, title="A draft posting here", publish=False)
    closed = _create_posting(db_session, faculty, title="A closed posting here")
    ResearchPostingService.transition_status(db_session, closed.id, faculty[0], PostingStatus.CLOSED)
    user, profile = _student(db_session, "Sam Student", keywords=["python"])

    res = client.post(
        "/api/v1/postings/fit-scores",
        json={"posting_ids": [str(second.id), str(draft.id), str(uuid.uuid4()), str(closed.id), str(first.id)]},
        headers=_headers(user),
    )

    assert res.status_code == 200, res.text
    assert [f["posting_id"] for f in res.json()["fits"]] == [str(second.id), str(first.id)]


def test_batch_rules(client, db_session, faculty):
    posting = _create_posting(db_session, faculty)
    user, _ = _student(db_session, "Sam Student")
    body = {"posting_ids": [str(posting.id)]}

    assert client.post("/api/v1/postings/fit-scores", json=body).status_code == 401
    assert client.post("/api/v1/postings/fit-scores", json=body, headers=_headers(faculty[0])).status_code == 403
    too_many = {"posting_ids": [str(uuid.uuid4()) for _ in range(101)]}
    assert client.post("/api/v1/postings/fit-scores", json=too_many, headers=_headers(user)).status_code == 422
    hundred = {"posting_ids": [str(uuid.uuid4()) for _ in range(99)] + [str(posting.id)]}
    res = client.post("/api/v1/postings/fit-scores", json=hundred, headers=_headers(user))
    assert res.status_code == 200
    assert len(res.json()["fits"]) == 1


def test_batch_route_is_not_captured_by_the_posting_id_routes(client, db_session, faculty):
    """A POST to /postings/fit-scores reaches the batch handler, not a /{posting_id} route."""
    user, _ = _student(db_session, "Sam Student")
    res = client.post("/api/v1/postings/fit-scores", json={"posting_ids": []}, headers=_headers(user))
    assert res.status_code == 200
    assert res.json() == {"fits": []}


# ===========================================================================
# Match alerts
# ===========================================================================


def _opt_in(db: Session, profile: ResearchProfileModel, *, min_score: int = 60, enabled: bool = True,
            in_app: bool = True) -> None:
    db.add(
        NotificationPreferenceModel(
            id=uuid.uuid4(),
            profile_id=profile.id,
            in_app_enabled=in_app,
            posting_match_alerts_enabled=enabled,
            posting_match_min_score=min_score,
        )
    )
    db.commit()


def _matching_student(db: Session, name: str, *, skills: bool = True, **kwargs) -> tuple[UserModel, ResearchProfileModel]:
    user, profile = _student(db, name, keywords=["python", "pytorch"] if skills else [], **kwargs)
    _interest(db, profile, "information-retrieval")
    return user, profile


def _alerts(db: Session) -> list[NotificationModel]:
    return list(
        db.execute(
            select(NotificationModel).where(NotificationModel.notification_type == "POSTING_MATCH")
        ).scalars()
    )


def test_first_publish_alerts_only_opted_in_students_at_or_above_threshold(db_session, faculty, other_faculty):
    _, strong = _matching_student(db_session, "Strong Match")  # fit 90
    _opt_in(db_session, strong, min_score=60)
    _, edge = _matching_student(db_session, "Edge Match", skills=False)  # fit 60
    _opt_in(db_session, edge, min_score=60)
    _, picky = _matching_student(db_session, "Picky Match", skills=False)  # fit 60 < 80
    _opt_in(db_session, picky, min_score=80)
    _, opted_out = _matching_student(db_session, "Opted Out")
    _opt_in(db_session, opted_out, enabled=False)
    _, quiet = _matching_student(db_session, "In App Off")
    _opt_in(db_session, quiet, in_app=False)
    _, inactive = _matching_student(db_session, "Inactive Student", is_active=False)
    _opt_in(db_session, inactive)
    _, no_prefs = _matching_student(db_session, "No Preferences Row")
    _opt_in(db_session, other_faculty[1])
    _interest(db_session, other_faculty[1], "information-retrieval")
    _opt_in(db_session, faculty[1])

    posting = _create_posting(db_session, faculty)

    alerts = _alerts(db_session)
    assert sorted(a.profile_id for a in alerts) == sorted([strong.id, edge.id])
    alert = next(a for a in alerts if a.profile_id == strong.id)
    assert alert.title == "New posting matches your interests"
    assert alert.body == f"“{posting.title}” — 90% fit"
    assert alert.source_type == "RESEARCH_POSTING"
    assert alert.source_id == posting.id
    assert alert.delivery_status == "DELIVERED" and alert.delivery_channel == "IN_APP"
    assert alert.metadata_json["posting_id"] == str(posting.id)
    assert alert.metadata_json["fit_score"] == 90
    assert alert.metadata_json["band"] == "Strong"
    assert len(alert.metadata_json["reasons"]) == 3
    assert "@" not in alert.body and "@" not in str(alert.metadata_json), "no contact email"


def test_reopening_and_repeating_never_alert_twice(db_session, faculty):
    _, student = _matching_student(db_session, "Strong Match")
    _opt_in(db_session, student)
    posting = _create_posting(db_session, faculty)
    assert len(_alerts(db_session)) == 1

    ResearchPostingService.transition_status(db_session, posting.id, faculty[0], PostingStatus.CLOSED)
    ResearchPostingService.transition_status(db_session, posting.id, faculty[0], PostingStatus.OPEN)
    assert len(_alerts(db_session)) == 1, "reopening is not a first publish"

    assert posting_match_alert_service.notify_matching_students(db_session, posting, NOW) == 0
    db_session.commit()
    assert len(_alerts(db_session)) == 1, "the deduplication key carries no timestamp"


def test_an_alert_failure_does_not_block_publishing(db_session, faculty, monkeypatch):
    _, student = _matching_student(db_session, "Strong Match")
    _opt_in(db_session, student)

    def failing(db, posting, now):
        raise RuntimeError("alerting is down")

    monkeypatch.setattr(posting_match_alert_service, "notify_matching_students", failing)
    posting = _create_posting(db_session, faculty)

    assert posting.status == PostingStatus.OPEN.value
    assert posting.published_at is not None
    assert _alerts(db_session) == []


def test_a_failure_after_writing_rolls_back_only_the_alerts(db_session, faculty, monkeypatch):
    _, student = _matching_student(db_session, "Strong Match")
    _opt_in(db_session, student)
    original = posting_match_alert_service.notify_matching_students

    def half_done(db, posting, now):
        original(db, posting, now)
        raise RuntimeError("failed after flushing an alert")

    monkeypatch.setattr(posting_match_alert_service, "notify_matching_students", half_done)
    posting = _create_posting(db_session, faculty)

    db_session.expire_all()
    stored = db_session.get(ResearchPostingModel, posting.id)
    assert stored.status == PostingStatus.OPEN.value
    assert stored.published_at is not None
    assert _alerts(db_session) == [], "the savepoint discarded the partial alerts"


def test_alert_query_count_does_not_grow_with_students(db_session, faculty):
    posting = _create_posting(db_session, faculty, publish=False)
    for index in range(2):
        _, profile = _matching_student(db_session, f"Student {index}")
        _opt_in(db_session, profile)

    def count_queries() -> int:
        engine = db_session.get_bind()
        count = 0

        def _listener(*args, **kwargs):
            nonlocal count
            count += 1

        event.listen(engine, "before_cursor_execute", _listener)
        try:
            posting_match_alert_service.notify_matching_students(db_session, posting, NOW)
        finally:
            event.remove(engine, "before_cursor_execute", _listener)
        db_session.rollback()
        return count

    few = count_queries()
    for index in range(2, 10):
        _, profile = _matching_student(db_session, f"Student {index}")
        _opt_in(db_session, profile)
    many = count_queries()

    assert few == many, f"query count grew with students: {few} -> {many}"
