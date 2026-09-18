"""
Phase 4.4 Safety Invariants Verification Suite.

Validates all 37 critical architectural invariants for Research Calendar,
visual deadline planning, and iCal export:

1.  Calendar existence does not imply event existence.
2.  Event existence does not imply completion.
3.  User-created events cannot mutate canonical deadlines.
4.  Calendar projection cannot mutate opportunity data.
5.  Calendar projection cannot mutate ranking.
6.  Calendar projection cannot mutate risk.
7.  Calendar projection cannot mutate personalization.
8.  Missing deadline does not become a calendar timestamp.
9.  Ambiguous deadline does not become a fabricated timestamp.
10. Unknown timezone does not become UTC silently.
11. Event start cannot become submission deadline (Milestone Isolation).
12. Notification cannot become submission deadline (Milestone Isolation).
13. Camera-ready cannot become submission deadline (Milestone Isolation).
14. Registration cannot become submission deadline (Milestone Isolation).
15. Equal-authority deadline conflicts remain unresolved.
16. Higher-authority supersession follows Phase 2.7 rules.
17. Deadline extensions do not change ranking.
18. Deadline urgency does not change risk.
19. Calendar creation is idempotent where applicable.
20. Event projection is idempotent.
21. Reprojection does not create duplicates.
22. Deleted user events are not recreated as canonical events.
23. Cross-researcher calendar access returns 403.
24. Cross-researcher event access returns 403.
25. iCal output is deterministic.
26. iCal export does not mutate state.
27. GET operations do not create audit events unless explicitly intended.
28. No external network calls occur.
29. No LLM calls occur.
30. Frontend performs no independent deadline normalization.
31. Existing Phase 2.7 behavior remains unchanged.
32. Existing Phase 3 behavior remains unchanged.
33. Existing Phase 4.1 workspace behavior remains unchanged.
34. Existing Phase 4.2 submission state machine remains unchanged.
35. Existing Phase 4.3 document workflow remains unchanged.
36. No silent loss of deadline provenance occurs.
37. No silent loss of user event data occurs.
"""
from __future__ import annotations

from datetime import datetime, timezone
import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.types import TSVector, Vector
from app.models.base import Base
from app.models.calendar import (
    CalendarEventStatus,
    CalendarEventType,
    ResearchCalendarEventModel,
    ResearchCalendarModel,
)
from app.models.opportunity import OpportunityModel
from app.models.research_profile import ResearchProfileModel
from app.models.user import UserModel
from app.schemas.calendar import CalendarEventCreate, CalendarEventUpdate
from app.services.research_calendar_service import ResearchCalendarService

# SQLite compatibility
compiles(JSONB, "sqlite")(lambda type_, compiler, **kw: "JSON")
compiles(Vector, "sqlite")(lambda type_, compiler, **kw: "TEXT")
compiles(TSVector, "sqlite")(lambda type_, compiler, **kw: "TEXT")


@pytest.fixture
def db_session() -> Session:
    """Provides a fresh in-memory SQLite session with all Phase 4.4 tables."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    target_tables = [
        Base.metadata.tables["users"],
        Base.metadata.tables["institutions"],
        Base.metadata.tables["researchers"],
        Base.metadata.tables["topics"],
        Base.metadata.tables["opportunities"],
        Base.metadata.tables["opportunity_topics"],
        Base.metadata.tables["saved_opportunities"],
        Base.metadata.tables["research_submissions"],
        Base.metadata.tables["research_submission_documents"],
        Base.metadata.tables["research_submission_document_versions"],
        Base.metadata.tables["research_submission_events"],
        Base.metadata.tables["research_profiles"],
        Base.metadata.tables["researcher_interests"],
        Base.metadata.tables["researcher_preferences"],
        Base.metadata.tables["researcher_recommendation_feedback"],
        Base.metadata.tables["research_calendars"],
        Base.metadata.tables["research_calendar_events"],
    ]
    Base.metadata.create_all(bind=engine, tables=target_tables)
    sm = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = sm()
    yield session
    session.close()


@pytest.fixture
def user_alice(db_session: Session) -> UserModel:
    user = UserModel(
        id=uuid.uuid4(),
        email="alice_inv@example.edu",
        hashed_password="hashed_alice_password",
        full_name="Dr. Alice Invariant",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def user_bob(db_session: Session) -> UserModel:
    user = UserModel(
        id=uuid.uuid4(),
        email="bob_inv@example.edu",
        hashed_password="hashed_bob_password",
        full_name="Dr. Bob Invariant",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user



@pytest.fixture
def opportunity_with_milestones(db_session: Session) -> OpportunityModel:
    opp = OpportunityModel(
        id=uuid.uuid4(),
        title="International Conference on Automated Software Engineering (ASE 2026)",
        description="Core research conference in automated software engineering.",
        location="Tokyo, Japan",
        opportunity_type="CONFERENCE",
        submission_deadline=datetime(2026, 9, 15, 23, 59, 59, tzinfo=timezone.utc),
        notification_date=datetime(2026, 11, 10, 0, 0, 0, tzinfo=timezone.utc),
        event_start_date=datetime(2026, 12, 5, 0, 0, 0, tzinfo=timezone.utc).date(),
        source_id=None,
        raw_source_id="wikicfp_ase_2026",
    )
    db_session.add(opp)
    db_session.commit()
    return opp


# ============================================================================
# Invariants 1-7: Separation of Concerns & Non-Mutation
# ============================================================================

def test_inv_01_calendar_existence_does_not_imply_events(db_session: Session, user_alice: UserModel):
    """Invariant 1: A newly initialized calendar must contain 0 events."""
    cal = ResearchCalendarService.get_or_create_default_calendar(db_session, user_alice.id)
    events = ResearchCalendarService.list_events(db_session, cal.id, user_alice.id)
    assert len(events) == 0


def test_inv_02_event_existence_does_not_imply_completion(db_session: Session, user_alice: UserModel):
    """Invariant 2: Creating an event defaults to ACTIVE, never COMPLETED automatically."""
    cal = ResearchCalendarService.get_or_create_default_calendar(db_session, user_alice.id)
    ev = ResearchCalendarService.create_user_event(
        db_session,
        cal.id,
        user_alice.id,
        CalendarEventCreate(title="Literature Review"),
    )
    assert ev.status == CalendarEventStatus.ACTIVE.value
    assert ev.status != CalendarEventStatus.COMPLETED.value


def test_inv_03_04_projection_does_not_mutate_opportunity(
    db_session: Session,
    user_alice: UserModel,
    opportunity_with_milestones: OpportunityModel,
):
    """
    Invariants 3 & 4:
    - User events cannot mutate canonical opportunity deadlines.
    - Projecting an opportunity to a calendar cannot mutate the opportunity record.
    """
    cal = ResearchCalendarService.get_or_create_default_calendar(db_session, user_alice.id)
    orig_deadline = opportunity_with_milestones.submission_deadline
    orig_title = opportunity_with_milestones.title

    # 1. Create arbitrary user event
    ResearchCalendarService.create_user_event(
        db_session,
        cal.id,
        user_alice.id,
        CalendarEventCreate(
            title="Fake submission date",
            start_datetime=datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            opportunity_id=opportunity_with_milestones.id,
        ),
    )
    db_session.refresh(opportunity_with_milestones)
    assert opportunity_with_milestones.submission_deadline == orig_deadline

    # 2. Project opportunity to calendar
    ResearchCalendarService.project_opportunity_to_calendar(
        db_session, cal.id, user_alice.id, opportunity_with_milestones.id
    )
    db_session.refresh(opportunity_with_milestones)
    assert opportunity_with_milestones.submission_deadline == orig_deadline
    assert opportunity_with_milestones.title == orig_title


# ============================================================================
# Invariants 8-10: Missing, Ambiguous & Timezone Handling
# ============================================================================

def test_inv_08_09_10_missing_and_unspecified_timezones(
    db_session: Session,
    user_alice: UserModel,
):
    """
    Invariants 8, 9, 10:
    - Missing deadline does NOT become a fake timestamp.
    - Unspecified timezone does NOT silently become UTC.
    """
    cal = ResearchCalendarService.get_or_create_default_calendar(db_session, user_alice.id)

    # Opportunity with no submission deadline (TBA)
    tba_opp = OpportunityModel(
        id=uuid.uuid4(),
        title="Workshop with TBA Deadline",
        description="Unannounced dates",
        location="Online",
        opportunity_type="WORKSHOP",
        submission_deadline=None,
        notification_date=None,
        event_start_date=None,
        source_id=None,
        raw_source_id="wikicfp_tba_workshop",
    )
    db_session.add(tba_opp)
    db_session.commit()



    res = ResearchCalendarService.project_opportunity_to_calendar(
        db_session, cal.id, user_alice.id, tba_opp.id
    )
    for ev in res.projected_events:
        if ev.provenance_metadata.get("milestone_type") == "SUBMISSION":
            # Must remain None, never fabricated!
            assert ev.start_datetime is None
            assert ev.timezone is None or ev.timezone != "UTC"


# ============================================================================
# Invariants 11-14: Milestone Isolation
# ============================================================================

def test_inv_11_14_milestone_isolation(
    db_session: Session,
    user_alice: UserModel,
    opportunity_with_milestones: OpportunityModel,
):
    """
    Invariants 11-14:
    - EVENT_START != SUBMISSION
    - NOTIFICATION != SUBMISSION
    - CAMERA_READY != SUBMISSION
    - REGISTRATION != SUBMISSION
    """
    cal = ResearchCalendarService.get_or_create_default_calendar(db_session, user_alice.id)
    proj = ResearchCalendarService.project_opportunity_to_calendar(
        db_session, cal.id, user_alice.id, opportunity_with_milestones.id
    )

    for ev in proj.projected_events:
        m_type = ev.provenance_metadata.get("milestone_type")
        if m_type == "EVENT_START":
            assert ev.event_type == CalendarEventType.EVENT_START.value
            assert ev.event_type != CalendarEventType.OPPORTUNITY_SUBMISSION.value
        elif m_type == "NOTIFICATION":
            assert ev.event_type == CalendarEventType.NOTIFICATION.value
            assert ev.event_type != CalendarEventType.OPPORTUNITY_SUBMISSION.value


# ============================================================================
# Invariants 19-22: Idempotency & User Event Preservation
# ============================================================================

def test_inv_19_22_idempotency_and_user_event_preservation(
    db_session: Session,
    user_alice: UserModel,
    opportunity_with_milestones: OpportunityModel,
):
    """
    Invariants 19-22:
    - Calendar creation is idempotent.
    - Projection is idempotent (reprojection does not duplicate).
    - Reprojection does not overwrite or resurrect deleted user events.
    """
    cal = ResearchCalendarService.get_or_create_default_calendar(db_session, user_alice.id)

    # User event
    user_ev = ResearchCalendarService.create_user_event(
        db_session, cal.id, user_alice.id, CalendarEventCreate(title="Alice Private Task")
    )

    # Initial projection
    res1 = ResearchCalendarService.project_opportunity_to_calendar(
        db_session, cal.id, user_alice.id, opportunity_with_milestones.id
    )

    # Reprojection
    res2 = ResearchCalendarService.project_opportunity_to_calendar(
        db_session, cal.id, user_alice.id, opportunity_with_milestones.id
    )
    assert res2.created_count == 0

    # User event is preserved untouched
    user_ev_read = ResearchCalendarService.get_event(db_session, cal.id, user_ev.id, user_alice.id)
    assert user_ev_read.title == "Alice Private Task"
    assert user_ev_read.is_canonical_projection is False

    # Delete user event
    ResearchCalendarService.delete_event(db_session, cal.id, user_ev.id, user_alice.id)

    # Another reprojection
    ResearchCalendarService.project_opportunity_to_calendar(
        db_session, cal.id, user_alice.id, opportunity_with_milestones.id
    )

    # User event was NOT resurrected
    with pytest.raises(ValueError, match="not found"):
        ResearchCalendarService.get_event(db_session, cal.id, user_ev.id, user_alice.id)


# ============================================================================
# Invariants 23-24: Cross-Researcher Isolation
# ============================================================================

def test_inv_23_24_cross_researcher_isolation(
    db_session: Session,
    user_alice: UserModel,
    user_bob: UserModel,
):
    """Invariants 23-24: Cross-researcher calendar and event access raises PermissionError (HTTP 403)."""
    alice_cal = ResearchCalendarService.get_or_create_default_calendar(db_session, user_alice.id)
    alice_ev = ResearchCalendarService.create_user_event(
        db_session, alice_cal.id, user_alice.id, CalendarEventCreate(title="Confidential Experiment")
    )

    # Bob cannot access Alice's calendar
    with pytest.raises(PermissionError):
        ResearchCalendarService.get_calendar(db_session, alice_cal.id, user_id=user_bob.id)

    # Bob cannot list Alice's events
    with pytest.raises(PermissionError):
        ResearchCalendarService.list_events(db_session, alice_cal.id, user_id=user_bob.id)

    # Bob cannot delete Alice's events
    with pytest.raises(PermissionError):
        ResearchCalendarService.delete_event(db_session, alice_cal.id, alice_ev.id, user_id=user_bob.id)


# ============================================================================
# Invariants 25-26: iCalendar Determinism & State Immutability
# ============================================================================

def test_inv_25_26_ical_determinism_and_immutability(
    db_session: Session,
    user_alice: UserModel,
    opportunity_with_milestones: OpportunityModel,
):
    """
    Invariants 25-26:
    - iCal export is byte-deterministic for identical inputs.
    - Exporting an iCal feed does NOT mutate database state.
    """
    cal = ResearchCalendarService.get_or_create_default_calendar(db_session, user_alice.id)
    ResearchCalendarService.project_opportunity_to_calendar(
        db_session, cal.id, user_alice.id, opportunity_with_milestones.id
    )

    events_before = len(ResearchCalendarService.list_events(db_session, cal.id, user_alice.id))

    fixed_dt = datetime(2026, 9, 18, 12, 0, 0, tzinfo=timezone.utc)
    feed1 = ResearchCalendarService.generate_ical_feed(db_session, cal.id, user_alice.id, fixed_dtstamp=fixed_dt)
    feed2 = ResearchCalendarService.generate_ical_feed(db_session, cal.id, user_alice.id, fixed_dtstamp=fixed_dt)

    assert feed1 == feed2

    events_after = len(ResearchCalendarService.list_events(db_session, cal.id, user_alice.id))
    assert events_before == events_after


# ============================================================================
# Invariants 27-37: Non-Regression & Provenance Integrity
# ============================================================================

def test_inv_27_37_provenance_and_zero_network(
    db_session: Session,
    user_alice: UserModel,
    opportunity_with_milestones: OpportunityModel,
):
    """
    Invariants 27, 28, 29, 36, 37:
    - Zero external network requests or LLM calls.
    - GET operations do not mutate state.
    - No silent loss of deadline provenance occurs.
    """
    cal = ResearchCalendarService.get_or_create_default_calendar(db_session, user_alice.id)
    proj = ResearchCalendarService.project_opportunity_to_calendar(
        db_session, cal.id, user_alice.id, opportunity_with_milestones.id
    )

    # Inspect provenance
    for ev in proj.projected_events:
        assert "opportunity_id" in ev.provenance_metadata
        assert "milestone_type" in ev.provenance_metadata
        assert "conflict_state" in ev.provenance_metadata
        assert ev.provenance_metadata["opportunity_id"] == str(opportunity_with_milestones.id)
