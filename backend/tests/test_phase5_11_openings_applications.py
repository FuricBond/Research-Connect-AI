"""
Phase 5.11 — Research Internships, RA Openings & the Application Workflow.

An application is jointly owned, and these tests exist mainly to pin that split down:

  Eligibility   Applications are accepted only for an OPEN structured opening that handles
                applications on-platform and whose deadline has not passed. Each refusal is
                distinct, because "closed" and "handled off-platform" need different actions.
  Role split    Review decisions belong to the posting's author; withdrawal and the response to
                an offer belong to the applicant. Neither side can perform the other's move.
  Privacy       The author's reviewer note is never returned to the applicant, and applicants
                cannot enumerate rival applications.
  Audit         The status history is append-only and identical for both sides, so a recorded
                decision cannot be silently revised.
  Idempotence   One application per researcher per posting; re-applying after withdrawal reuses
                the record rather than creating a competing submission.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from app.db.session import get_db
from app.db.types import TSVector, Vector
from app.main import app
from app.models.base import Base
from app.models.notification import NotificationModel, NotificationType
from app.models.research_posting import PostingStatus, PostingType, ResearchPostingModel
from app.models.research_posting_application import (
    ApplicationStatus,
    CompensationType,
    ResearchPostingApplicationModel,
)
from app.models.research_profile import ResearchProfileModel
from app.models.user import UserModel
from app.schemas.research_posting import ResearchPostingCreate
from app.schemas.research_posting_application import ApplicationCreate, OpeningTermsUpdate
from app.services.research_posting_application_service import (
    APPLICANT_TRANSITIONS,
    AUTHOR_TRANSITIONS,
    ApplicationNotAcceptedError,
    ApplicationNotFoundError,
    ApplicationPermissionError,
    DuplicateApplicationError,
    InvalidApplicationTransitionError,
    ResearchPostingApplicationService,
)
from app.services.research_posting_service import ResearchPostingService

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


def _make_account(db: Session, email: str, role: str, full_name: str):
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
        institution="Test University",
        department="Computer Science",
    )
    db.add(profile)
    db.commit()
    return user, profile


@pytest.fixture
def faculty(db_session: Session):
    return _make_account(db_session, "supervisor@university.edu", "FACULTY", "Dr. Amara Okafor")


@pytest.fixture
def applicant(db_session: Session):
    return _make_account(db_session, "applicant@university.edu", "STUDENT", "Priya Raghavan")


@pytest.fixture
def other_applicant(db_session: Session):
    return _make_account(db_session, "rival@university.edu", "STUDENT", "Rival Candidate")


def _open_opening(
    db: Session,
    faculty_pair,
    *,
    posting_type: PostingType = PostingType.RESEARCH_ASSISTANTSHIP,
    accepts_applications: bool = True,
    deadline_days: int | None = 30,
    publish: bool = True,
) -> ResearchPostingModel:
    """Creates and (by default) publishes a structured opening that accepts applications."""
    user, profile = faculty_pair
    payload = ResearchPostingCreate(
        title=f"Funded {posting_type.value.lower()} in information retrieval",
        posting_type=posting_type,
        description="A funded appointment working on dense retrieval evaluation for one year.",
        application_deadline=(
            datetime.now(timezone.utc) + timedelta(days=deadline_days)
            if deadline_days is not None
            else None
        ),
        opening_terms=OpeningTermsUpdate(
            compensation_type=CompensationType.STIPEND,
            compensation_amount=2200,
            compensation_currency="USD",
            compensation_period="MONTH",
            duration_months=12,
            hours_per_week=20,
            accepts_applications=accepts_applications,
        ),
    )
    posting = ResearchPostingService.create_posting(db, profile, user, payload)
    if publish:
        ResearchPostingService.transition_status(db, posting.id, user, PostingStatus.OPEN)
        db.refresh(posting)
    return posting


def _apply(db: Session, posting, applicant_pair, **fields):
    user, profile = applicant_pair
    return ResearchPostingApplicationService.submit_application(
        db, posting.id, profile, user, ApplicationCreate(**fields)
    )


# ===========================================================================
# Opening terms
# ===========================================================================


def test_opening_terms_are_persisted_and_exposed(db_session: Session, faculty):
    posting = _open_opening(db_session, faculty)
    read = ResearchPostingService.build_posting_read(posting)

    assert read.opening_terms.compensation_type == CompensationType.STIPEND
    assert read.opening_terms.compensation_amount == 2200.0
    assert read.opening_terms.compensation_currency == "USD"
    assert read.opening_terms.compensation_period == "MONTH"
    assert read.opening_terms.duration_months == 12
    assert read.opening_terms.is_structured_opening is True
    assert read.opening_terms.accepts_applications is True


def test_supervisor_led_posting_cannot_accept_on_platform_applications(db_session: Session, faculty):
    """
    Enabling applications on a Phase 5.10 category would advertise a workflow the service
    refuses, so the flag is forced off rather than accepted and later contradicted.
    """
    posting = _open_opening(
        db_session, faculty, posting_type=PostingType.THESIS_TOPIC, accepts_applications=True
    )
    read = ResearchPostingService.build_posting_read(posting)

    assert read.opening_terms.is_structured_opening is False
    assert read.opening_terms.accepts_applications is False


def test_phase_5_10_posting_defaults_to_unspecified_compensation(db_session: Session, faculty):
    user, profile = faculty
    posting = ResearchPostingService.create_posting(
        db_session,
        profile,
        user,
        ResearchPostingCreate(
            title="Open collaboration on retrieval evaluation",
            posting_type=PostingType.COLLABORATION,
            description="An open invitation to collaborate on shared retrieval benchmarks.",
        ),
    )
    read = ResearchPostingService.build_posting_read(posting)
    assert read.opening_terms.compensation_type == CompensationType.UNSPECIFIED
    assert read.opening_terms.accepts_applications is False


# ===========================================================================
# Eligibility
# ===========================================================================


def test_apply_to_open_opening(db_session: Session, faculty, applicant):
    posting = _open_opening(db_session, faculty)
    application = _apply(db_session, posting, applicant, cover_note="I would like to apply.")

    assert application.status == ApplicationStatus.SUBMITTED.value
    assert application.applicant_profile_id == applicant[1].id
    assert len(application.status_history) == 1
    assert application.status_history[0]["to_status"] == ApplicationStatus.SUBMITTED.value
    assert application.status_history[0]["actor_role"] == "APPLICANT"

    db_session.refresh(posting)
    assert posting.application_count == 1


def test_cannot_apply_to_draft_posting(db_session: Session, faculty, applicant):
    posting = _open_opening(db_session, faculty, publish=False)
    with pytest.raises(ApplicationNotAcceptedError, match="not open"):
        _apply(db_session, posting, applicant)


def test_cannot_apply_to_supervisor_led_posting(db_session: Session, faculty, applicant):
    posting = _open_opening(db_session, faculty, posting_type=PostingType.PROJECT)
    with pytest.raises(ApplicationNotAcceptedError, match="supervisor-led"):
        _apply(db_session, posting, applicant)


def test_cannot_apply_when_author_handles_applications_off_platform(
    db_session: Session, faculty, applicant
):
    posting = _open_opening(db_session, faculty, accepts_applications=False)
    with pytest.raises(ApplicationNotAcceptedError, match="off-platform"):
        _apply(db_session, posting, applicant)


def test_cannot_apply_after_deadline(db_session: Session, faculty, applicant):
    posting = _open_opening(db_session, faculty)
    posting.application_deadline = datetime.now(timezone.utc) - timedelta(days=1)
    db_session.commit()

    with pytest.raises(ApplicationNotAcceptedError, match="deadline"):
        _apply(db_session, posting, applicant)


def test_open_ended_opening_accepts_applications(db_session: Session, faculty, applicant):
    posting = _open_opening(db_session, faculty, deadline_days=None)
    application = _apply(db_session, posting, applicant)
    assert application.status == ApplicationStatus.SUBMITTED.value


def test_author_cannot_apply_to_own_posting(db_session: Session, faculty):
    posting = _open_opening(db_session, faculty)
    with pytest.raises(ApplicationPermissionError, match="you authored"):
        _apply(db_session, posting, faculty)


def test_duplicate_application_is_rejected(db_session: Session, faculty, applicant):
    posting = _open_opening(db_session, faculty)
    _apply(db_session, posting, applicant)
    with pytest.raises(DuplicateApplicationError, match="already applied"):
        _apply(db_session, posting, applicant)


def test_reapplying_after_withdrawal_reuses_the_record(db_session: Session, faculty, applicant):
    """
    The author should see one continuous history per person, not two competing submissions.
    """
    posting = _open_opening(db_session, faculty)
    first = _apply(db_session, posting, applicant, cover_note="First attempt")
    ResearchPostingApplicationService.transition_application(
        db_session, first.id, applicant[0], ApplicationStatus.WITHDRAWN
    )

    second = _apply(db_session, posting, applicant, cover_note="Second attempt")
    assert second.id == first.id, "re-application must reuse the same record"
    assert second.status == ApplicationStatus.SUBMITTED.value
    assert second.cover_note == "Second attempt"
    assert second.withdrawn_at is None
    # SUBMITTED, WITHDRAWN, SUBMITTED — the whole sequence is preserved.
    assert [e["to_status"] for e in second.status_history] == ["SUBMITTED", "WITHDRAWN", "SUBMITTED"]

    total = db_session.execute(
        select(ResearchPostingApplicationModel).where(
            ResearchPostingApplicationModel.posting_id == posting.id
        )
    ).scalars().all()
    assert len(total) == 1

    db_session.refresh(posting)
    assert posting.application_count == 1, "re-application must not double-count"


# ===========================================================================
# Role-partitioned lifecycle
# ===========================================================================


def test_author_review_progression(db_session: Session, faculty, applicant):
    posting = _open_opening(db_session, faculty)
    application = _apply(db_session, posting, applicant)

    for target in (
        ApplicationStatus.UNDER_REVIEW,
        ApplicationStatus.SHORTLISTED,
        ApplicationStatus.OFFERED,
    ):
        application = ResearchPostingApplicationService.transition_application(
            db_session, application.id, faculty[0], target
        )
        assert application.status == target.value

    assert application.decided_at is not None


def test_applicant_accepts_offer(db_session: Session, faculty, applicant):
    posting = _open_opening(db_session, faculty)
    application = _apply(db_session, posting, applicant)
    # An offer is reached through review, matching the author's real path.
    ResearchPostingApplicationService.transition_application(
        db_session, application.id, faculty[0], ApplicationStatus.UNDER_REVIEW
    )
    ResearchPostingApplicationService.transition_application(
        db_session, application.id, faculty[0], ApplicationStatus.OFFERED
    )
    accepted = ResearchPostingApplicationService.transition_application(
        db_session, application.id, applicant[0], ApplicationStatus.ACCEPTED
    )
    assert accepted.status == ApplicationStatus.ACCEPTED.value


def test_applicant_cannot_shortlist_themselves(db_session: Session, faculty, applicant):
    posting = _open_opening(db_session, faculty)
    application = _apply(db_session, posting, applicant)

    with pytest.raises(InvalidApplicationTransitionError, match="belongs to the posting's author"):
        ResearchPostingApplicationService.transition_application(
            db_session, application.id, applicant[0], ApplicationStatus.SHORTLISTED
        )


def test_author_cannot_accept_an_offer_for_the_applicant(db_session: Session, faculty, applicant):
    posting = _open_opening(db_session, faculty)
    application = _apply(db_session, posting, applicant)
    ResearchPostingApplicationService.transition_application(
        db_session, application.id, faculty[0], ApplicationStatus.UNDER_REVIEW
    )
    ResearchPostingApplicationService.transition_application(
        db_session, application.id, faculty[0], ApplicationStatus.OFFERED
    )

    with pytest.raises(InvalidApplicationTransitionError, match="belongs to the applicant"):
        ResearchPostingApplicationService.transition_application(
            db_session, application.id, faculty[0], ApplicationStatus.ACCEPTED
        )


def test_applicant_may_withdraw_at_any_live_stage(db_session: Session, faculty, applicant):
    for stage in (ApplicationStatus.SUBMITTED, ApplicationStatus.UNDER_REVIEW, ApplicationStatus.SHORTLISTED):
        posting = _open_opening(db_session, faculty)
        application = _apply(db_session, posting, applicant)
        if stage != ApplicationStatus.SUBMITTED:
            ResearchPostingApplicationService.transition_application(
                db_session, application.id, faculty[0], ApplicationStatus.UNDER_REVIEW
            )
        if stage == ApplicationStatus.SHORTLISTED:
            ResearchPostingApplicationService.transition_application(
                db_session, application.id, faculty[0], ApplicationStatus.SHORTLISTED
            )
        withdrawn = ResearchPostingApplicationService.transition_application(
            db_session, application.id, applicant[0], ApplicationStatus.WITHDRAWN
        )
        assert withdrawn.status == ApplicationStatus.WITHDRAWN.value
        assert withdrawn.withdrawn_at is not None


def test_terminal_application_cannot_change(db_session: Session, faculty, applicant):
    posting = _open_opening(db_session, faculty)
    application = _apply(db_session, posting, applicant)
    ResearchPostingApplicationService.transition_application(
        db_session, application.id, faculty[0], ApplicationStatus.REJECTED
    )

    with pytest.raises(InvalidApplicationTransitionError, match="already REJECTED"):
        ResearchPostingApplicationService.transition_application(
            db_session, application.id, faculty[0], ApplicationStatus.OFFERED
        )


def test_rejection_and_declining_remain_distinguishable(db_session: Session, faculty, applicant, other_applicant):
    """A single CLOSED state would erase whether the author or the candidate said no."""
    posting = _open_opening(db_session, faculty)

    rejected = _apply(db_session, posting, applicant)
    ResearchPostingApplicationService.transition_application(
        db_session, rejected.id, faculty[0], ApplicationStatus.REJECTED
    )

    declined = _apply(db_session, posting, other_applicant)
    ResearchPostingApplicationService.transition_application(
        db_session, declined.id, faculty[0], ApplicationStatus.UNDER_REVIEW
    )
    ResearchPostingApplicationService.transition_application(
        db_session, declined.id, faculty[0], ApplicationStatus.OFFERED
    )
    ResearchPostingApplicationService.transition_application(
        db_session, declined.id, other_applicant[0], ApplicationStatus.DECLINED
    )

    db_session.refresh(rejected)
    db_session.refresh(declined)
    assert rejected.status == ApplicationStatus.REJECTED.value
    assert declined.status == ApplicationStatus.DECLINED.value


def test_transition_tables_do_not_overlap():
    """
    No status may be moved to the same target by both sides, or the audit trail could not
    attribute a decision to whoever actually made it.
    """
    for status in set(APPLICANT_TRANSITIONS) | set(AUTHOR_TRANSITIONS):
        applicant_targets = APPLICANT_TRANSITIONS.get(status, frozenset())
        author_targets = AUTHOR_TRANSITIONS.get(status, frozenset())
        assert not (applicant_targets & author_targets), (
            f"{status.value} is ambiguously transitionable by both roles"
        )


# ===========================================================================
# Privacy and access
# ===========================================================================


def test_reviewer_note_is_withheld_from_the_applicant(db_session: Session, faculty, applicant):
    posting = _open_opening(db_session, faculty)
    application = _apply(db_session, posting, applicant)
    ResearchPostingApplicationService.transition_application(
        db_session,
        application.id,
        faculty[0],
        ApplicationStatus.UNDER_REVIEW,
        decision_reason="Shortlisting for interview",
        reviewer_note="Weaker publication record than the other candidate",
    )

    author_view = ResearchPostingApplicationService.build_application_read(
        application, faculty[0], "AUTHOR"
    )
    applicant_view = ResearchPostingApplicationService.build_application_read(
        application, applicant[0], "APPLICANT"
    )

    assert author_view.reviewer_note == "Weaker publication record than the other candidate"
    assert applicant_view.reviewer_note is None
    # The reason meant for the applicant is shared with both.
    assert applicant_view.decision_reason == "Shortlisting for interview"


def test_applicant_supplied_reviewer_note_is_ignored(db_session: Session, faculty, applicant):
    """An applicant must not be able to write into the author's private assessment."""
    posting = _open_opening(db_session, faculty)
    application = _apply(db_session, posting, applicant)
    ResearchPostingApplicationService.transition_application(
        db_session,
        application.id,
        applicant[0],
        ApplicationStatus.WITHDRAWN,
        reviewer_note="Injected by the applicant",
    )
    db_session.refresh(application)
    assert application.reviewer_note is None


def test_unrelated_researcher_cannot_read_an_application(
    db_session: Session, faculty, applicant, other_applicant
):
    posting = _open_opening(db_session, faculty)
    application = _apply(db_session, posting, applicant)

    with pytest.raises(ApplicationNotFoundError):
        ResearchPostingApplicationService.get_application(
            db_session, application.id, other_applicant[0]
        )


def test_applicant_cannot_enumerate_rival_applications(
    db_session: Session, faculty, applicant, other_applicant
):
    posting = _open_opening(db_session, faculty)
    _apply(db_session, posting, applicant)
    _apply(db_session, posting, other_applicant)

    with pytest.raises(ApplicationPermissionError, match="author"):
        ResearchPostingApplicationService.list_applications_for_posting(
            db_session, posting.id, applicant[0]
        )

    authored = ResearchPostingApplicationService.list_applications_for_posting(
        db_session, posting.id, faculty[0]
    )
    assert authored.total == 2


def test_my_applications_is_scoped_to_the_applicant(
    db_session: Session, faculty, applicant, other_applicant
):
    posting = _open_opening(db_session, faculty)
    mine = _apply(db_session, posting, applicant)
    _apply(db_session, posting, other_applicant)

    listed = ResearchPostingApplicationService.list_my_applications(
        db_session, applicant[1].id, applicant[0]
    )
    assert [a.id for a in listed.applications] == [mine.id]
    assert all(a.reviewer_note is None for a in listed.applications)


def test_application_summary_counts_active_separately(db_session: Session, faculty, applicant):
    first = _open_opening(db_session, faculty)
    second = _open_opening(db_session, faculty)

    live = _apply(db_session, first, applicant)
    withdrawn = _apply(db_session, second, applicant)
    ResearchPostingApplicationService.transition_application(
        db_session, withdrawn.id, applicant[0], ApplicationStatus.WITHDRAWN
    )

    summary = ResearchPostingApplicationService.summarize_my_applications(db_session, applicant[1].id)
    assert summary.total == 2
    assert summary.active == 1
    assert summary.by_status[ApplicationStatus.SUBMITTED.value] == 1
    assert summary.by_status[ApplicationStatus.WITHDRAWN.value] == 1
    assert live.status == ApplicationStatus.SUBMITTED.value


# ===========================================================================
# Notifications
# ===========================================================================


def test_author_is_notified_of_a_new_application(db_session: Session, faculty, applicant):
    posting = _open_opening(db_session, faculty)
    _apply(db_session, posting, applicant)

    notifications = db_session.execute(
        select(NotificationModel).where(NotificationModel.profile_id == faculty[1].id)
    ).scalars().all()
    assert len(notifications) == 1
    assert notifications[0].source_type == "RESEARCH_POSTING"
    assert "application" in notifications[0].title.lower()


def test_applicant_is_notified_of_a_decision(db_session: Session, faculty, applicant):
    posting = _open_opening(db_session, faculty)
    application = _apply(db_session, posting, applicant)
    ResearchPostingApplicationService.transition_application(
        db_session, application.id, faculty[0], ApplicationStatus.SHORTLISTED
    )

    notifications = db_session.execute(
        select(NotificationModel).where(NotificationModel.profile_id == applicant[1].id)
    ).scalars().all()
    assert len(notifications) == 1
    assert "shortlisted" in notifications[0].title.lower()


def test_notifications_are_deduplicated(db_session: Session, faculty, applicant):
    """A retried request must not produce two identical alerts."""
    posting = _open_opening(db_session, faculty)
    application = _apply(db_session, posting, applicant)
    now = datetime.now(timezone.utc)

    for _ in range(3):
        ResearchPostingApplicationService._notify(
            db_session,
            recipient_user_id=applicant[0].id,
            notification_type=NotificationType.SYSTEM,
            title="Repeated",
            body="Repeated",
            source_id=posting.id,
            metadata={"application_id": str(application.id), "status": "SUBMITTED"},
            reference_time=now,
        )
    db_session.commit()

    repeated = db_session.execute(
        select(NotificationModel).where(
            NotificationModel.profile_id == applicant[1].id,
            NotificationModel.title == "Repeated",
        )
    ).scalars().all()
    assert len(repeated) == 1


# ===========================================================================
# REST API
# ===========================================================================


def test_api_full_application_journey(client: TestClient, db_session: Session, faculty, applicant):
    posting = _open_opening(db_session, faculty)
    applicant_headers = {"X-User-ID": str(applicant[0].id)}
    author_headers = {"X-User-ID": str(faculty[0].id)}

    submitted = client.post(
        f"/api/v1/postings/{posting.id}/applications",
        headers=applicant_headers,
        json={"cover_note": "I am keen to work on retrieval evaluation.", "contact_email": "me@uni.edu"},
    )
    assert submitted.status_code == 201, submitted.text
    body = submitted.json()
    application_id = body["id"]
    assert body["status"] == "SUBMITTED"
    assert body["is_applicant"] is True
    assert body["reviewer_note"] is None
    assert "WITHDRAWN" in body["allowed_transitions"]

    reviewed = client.get(f"/api/v1/postings/{posting.id}/applications", headers=author_headers)
    assert reviewed.status_code == 200
    assert reviewed.json()["total"] == 1

    # The applicant cannot review the posting's applications.
    assert client.get(
        f"/api/v1/postings/{posting.id}/applications", headers=applicant_headers
    ).status_code == 403

    offered = client.post(
        f"/api/v1/postings/applications/{application_id}/transition",
        headers=author_headers,
        json={"target_status": "OFFERED", "decision_reason": "Strong fit", "reviewer_note": "private"},
    )
    assert offered.status_code == 400, "OFFERED must be reached via review, not directly from SUBMITTED"

    client.post(
        f"/api/v1/postings/applications/{application_id}/transition",
        headers=author_headers,
        json={"target_status": "UNDER_REVIEW"},
    )
    offer = client.post(
        f"/api/v1/postings/applications/{application_id}/transition",
        headers=author_headers,
        json={"target_status": "OFFERED", "decision_reason": "Strong fit", "reviewer_note": "private note"},
    )
    assert offer.status_code == 200
    assert offer.json()["reviewer_note"] == "private note"

    # The applicant sees the shared reason but never the private note.
    applicant_view = client.get(
        f"/api/v1/postings/applications/{application_id}", headers=applicant_headers
    )
    assert applicant_view.status_code == 200
    assert applicant_view.json()["decision_reason"] == "Strong fit"
    assert applicant_view.json()["reviewer_note"] is None

    accepted = client.post(
        f"/api/v1/postings/applications/{application_id}/transition",
        headers=applicant_headers,
        json={"target_status": "ACCEPTED"},
    )
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "ACCEPTED"
    assert [e["to_status"] for e in accepted.json()["status_history"]] == [
        "SUBMITTED",
        "UNDER_REVIEW",
        "OFFERED",
        "ACCEPTED",
    ]


def test_api_my_applications_and_summary(client: TestClient, db_session: Session, faculty, applicant):
    posting = _open_opening(db_session, faculty)
    _apply(db_session, posting, applicant)
    headers = {"X-User-ID": str(applicant[0].id)}

    listed = client.get("/api/v1/postings/applications/mine", headers=headers)
    assert listed.status_code == 200, listed.text
    assert listed.json()["total"] == 1

    summary = client.get("/api/v1/postings/applications/mine/summary", headers=headers)
    assert summary.status_code == 200
    assert summary.json()["active"] == 1


def test_api_literal_routes_are_not_shadowed_by_the_id_route(client: TestClient, applicant):
    """
    `/postings/applications/mine` must not be captured by `/postings/{posting_id}`; a 422 on a
    UUID parse would mean the literal path had been shadowed.
    """
    headers = {"X-User-ID": str(applicant[0].id)}
    for path in ("/api/v1/postings/applications/mine", "/api/v1/postings/applications/mine/summary"):
        res = client.get(path, headers=headers)
        assert res.status_code == 200, f"{path} -> {res.status_code}: {res.text[:160]}"


def test_api_anonymous_cannot_apply(client: TestClient, db_session: Session, faculty):
    posting = _open_opening(db_session, faculty)
    res = client.post(f"/api/v1/postings/{posting.id}/applications", json={})
    assert res.status_code == 401


def test_api_unrelated_researcher_gets_404_for_an_application(
    client: TestClient, db_session: Session, faculty, applicant, other_applicant
):
    posting = _open_opening(db_session, faculty)
    application = _apply(db_session, posting, applicant)
    res = client.get(
        f"/api/v1/postings/applications/{application.id}",
        headers={"X-User-ID": str(other_applicant[0].id)},
    )
    assert res.status_code == 404


def test_api_applying_to_supervisor_led_posting_is_refused(
    client: TestClient, db_session: Session, faculty, applicant
):
    posting = _open_opening(db_session, faculty, posting_type=PostingType.THESIS_TOPIC)
    res = client.post(
        f"/api/v1/postings/{posting.id}/applications",
        headers={"X-User-ID": str(applicant[0].id)},
        json={},
    )
    assert res.status_code == 400
    assert "supervisor-led" in res.json()["detail"]


def test_api_posting_read_exposes_opening_terms(client: TestClient, db_session: Session, faculty):
    posting = _open_opening(db_session, faculty)
    res = client.get(f"/api/v1/postings/{posting.id}")
    assert res.status_code == 200
    terms = res.json()["opening_terms"]
    assert terms["compensation_type"] == "STIPEND"
    assert terms["is_structured_opening"] is True
    assert terms["accepts_applications"] is True


def test_api_posting_read_reports_the_readers_own_application(
    client: TestClient, db_session: Session, faculty, applicant, other_applicant
):
    """
    The detail page must know the reader already applied, so it can show the status instead of
    offering an Apply button that would be refused as a duplicate.
    """
    posting = _open_opening(db_session, faculty)
    application = _apply(db_session, posting, applicant)

    own = client.get(
        f"/api/v1/postings/{posting.id}", headers={"X-User-ID": str(applicant[0].id)}
    ).json()
    assert own["viewer_application_id"] == str(application.id)
    assert own["viewer_application_status"] == "SUBMITTED"

    # Another researcher's application must not be reported as the reader's own.
    stranger = client.get(
        f"/api/v1/postings/{posting.id}", headers={"X-User-ID": str(other_applicant[0].id)}
    ).json()
    assert stranger["viewer_application_id"] is None
    assert stranger["viewer_application_status"] is None

    anonymous = client.get(f"/api/v1/postings/{posting.id}").json()
    assert anonymous["viewer_application_id"] is None
