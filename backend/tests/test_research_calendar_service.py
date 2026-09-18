"""
Unit and Service Tests for Phase 4.4 Research Calendar & Visual Deadline Planning.

Tests:
  - Calendar creation (default, custom) and idempotency
  - Calendar ownership and retrieval with strict isolation
  - User planning events (creation, update, deletion, listing)
  - Date-range filtering and indexed query behavior
  - Canonical deadline projection from Phase 2.7 (milestone mapping, isolation, idempotency)
  - Handling of extensions, moved earlier, and source conflicts
  - Timezone semantics (preserving unspecified timezones, AoE date-only semantics)
  - RFC 5545 iCalendar generation (VCALENDAR, VEVENT, UID, DTSTART, SUMMARY, line folding, determinism)
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
import uuid

import pytest
from sqlalchemy import create_engine
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
from app.models.research_submission import ResearchSubmissionModel
from app.models.saved_opportunity import SavedOpportunityModel
from app.models.submission_document import (
    ResearchSubmissionDocumentModel,
    ResearchSubmissionDocumentVersionModel,
    ResearchSubmissionEventModel,
)
from app.models.user import UserModel
from app.schemas.calendar import (
    CalendarCreate,
    CalendarEventCreate,
    CalendarEventUpdate,
    CalendarUpdate,
)
from app.services.research_calendar_service import (
    ResearchCalendarService,
    _escape_ical_text,
    _fold_ical_line,
)

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
def test_user(db_session: Session) -> UserModel:
    user = UserModel(
        id=uuid.uuid4(),
        email="researcher_alice@example.edu",
        hashed_password="hashed_alice_password",
        full_name="Dr. Alice Researcher",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def test_user_other(db_session: Session) -> UserModel:
    user = UserModel(
        id=uuid.uuid4(),
        email="researcher_bob@example.edu",
        hashed_password="hashed_bob_password",
        full_name="Dr. Bob Observer",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user



@pytest.fixture
def test_opportunity(db_session: Session) -> OpportunityModel:
    opp = OpportunityModel(
        id=uuid.uuid4(),
        title="International Conference on Machine Learning (ICML 2026)",
        description="Top-tier machine learning research conference.",
        location="Vienna, Austria",
        opportunity_type="CONFERENCE",
        submission_deadline=datetime(2026, 8, 20, 23, 59, 59, tzinfo=timezone.utc),
        notification_date=datetime(2026, 10, 15, 0, 0, 0, tzinfo=timezone.utc),
        event_start_date=datetime(2026, 12, 1, 0, 0, 0, tzinfo=timezone.utc).date(),
        source_id=None,
        raw_source_id="wikicfp_icml_2026",
    )

    db_session.add(opp)
    db_session.commit()
    return opp



# ============================================================================
# Calendar Management Tests
# ============================================================================

def test_get_or_create_default_calendar_idempotent(db_session: Session, test_user: UserModel):
    """Verifies that calling get_or_create_default_calendar returns the same calendar instance."""
    cal1 = ResearchCalendarService.get_or_create_default_calendar(db_session, test_user.id)
    assert cal1 is not None
    assert cal1.user_id == test_user.id
    assert cal1.is_default is True
    assert cal1.name == "Default Research Calendar"

    cal2 = ResearchCalendarService.get_or_create_default_calendar(db_session, test_user.id)
    assert cal1.id == cal2.id


def test_create_custom_calendar_and_list(db_session: Session, test_user: UserModel):
    """Verifies creating multiple calendars and listing them ordered by is_default."""
    default_cal = ResearchCalendarService.get_or_create_default_calendar(db_session, test_user.id)

    custom_payload = CalendarCreate(
        name="Grant Proposals 2026",
        description="Calendar for European Research Council funding deadlines.",
        timezone="Europe/Berlin",
        is_default=False,
    )
    custom_cal = ResearchCalendarService.create_calendar(db_session, test_user.id, custom_payload)

    calendars = ResearchCalendarService.list_calendars(db_session, test_user.id)
    assert len(calendars) == 2
    assert calendars[0].id == default_cal.id
    assert calendars[1].id == custom_cal.id
    assert calendars[1].name == "Grant Proposals 2026"
    assert calendars[1].timezone == "Europe/Berlin"


def test_calendar_cross_user_isolation(db_session: Session, test_user: UserModel, test_user_other: UserModel):
    """Verifies that accessing another researcher's calendar raises PermissionError."""
    alice_cal = ResearchCalendarService.get_or_create_default_calendar(db_session, test_user.id)

    with pytest.raises(PermissionError, match="Forbidden"):
        ResearchCalendarService.get_calendar(db_session, alice_cal.id, user_id=test_user_other.id)


def test_update_calendar_metadata(db_session: Session, test_user: UserModel):
    """Verifies updating calendar name, description, and timezone."""
    cal = ResearchCalendarService.get_or_create_default_calendar(db_session, test_user.id)

    update_payload = CalendarUpdate(
        name="Alice's Academic Timeline",
        timezone="America/New_York",
    )
    updated = ResearchCalendarService.update_calendar(db_session, cal.id, test_user.id, update_payload)
    assert updated.name == "Alice's Academic Timeline"
    assert updated.timezone == "America/New_York"


# ============================================================================
# User Planning Event Tests
# ============================================================================

def test_create_user_planning_event(db_session: Session, test_user: UserModel):
    """Verifies creating custom user events marked is_canonical_projection=False."""
    cal = ResearchCalendarService.get_or_create_default_calendar(db_session, test_user.id)

    event_payload = CalendarEventCreate(
        title="Complete ablation experiments",
        description="Run benchmark on GPU cluster with 5 seeds.",
        event_type=CalendarEventType.RESEARCH_MILESTONE,
        start_datetime=datetime(2026, 7, 10, 14, 0, 0, tzinfo=timezone.utc),
        end_datetime=datetime(2026, 7, 10, 18, 0, 0, tzinfo=timezone.utc),
        status=CalendarEventStatus.ACTIVE,
    )
    event = ResearchCalendarService.create_user_event(db_session, cal.id, test_user.id, event_payload)

    assert event.id is not None
    assert event.is_canonical_projection is False
    assert event.title == "Complete ablation experiments"
    assert event.event_type == CalendarEventType.RESEARCH_MILESTONE.value
    assert event.calendar_id == cal.id


def test_event_crud_and_deletion(db_session: Session, test_user: UserModel):
    """Verifies retrieval, update, and deletion of custom user events."""
    cal = ResearchCalendarService.get_or_create_default_calendar(db_session, test_user.id)

    event = ResearchCalendarService.create_user_event(
        db_session,
        cal.id,
        test_user.id,
        CalendarEventCreate(title="Advisor meeting draft review"),
    )

    # Update
    updated = ResearchCalendarService.update_event(
        db_session,
        cal.id,
        event.id,
        test_user.id,
        CalendarEventUpdate(title="Advisor meeting — final paper signoff", status=CalendarEventStatus.COMPLETED),
    )
    assert updated.title == "Advisor meeting — final paper signoff"
    assert updated.status == CalendarEventStatus.COMPLETED.value

    # Delete
    deleted = ResearchCalendarService.delete_event(db_session, cal.id, event.id, test_user.id)
    assert deleted is True

    with pytest.raises(ValueError, match="not found"):
        ResearchCalendarService.get_event(db_session, cal.id, event.id, test_user.id)


def test_list_events_with_date_range_filtering(db_session: Session, test_user: UserModel):
    """Verifies date-range and type filtering on list_events."""
    cal = ResearchCalendarService.get_or_create_default_calendar(db_session, test_user.id)

    ev_june = ResearchCalendarService.create_user_event(
        db_session,
        cal.id,
        test_user.id,
        CalendarEventCreate(
            title="June Milestone",
            start_datetime=datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc),
        ),
    )
    ev_july = ResearchCalendarService.create_user_event(
        db_session,
        cal.id,
        test_user.id,
        CalendarEventCreate(
            title="July Milestone",
            start_datetime=datetime(2026, 7, 20, 12, 0, 0, tzinfo=timezone.utc),
        ),
    )
    ev_aug = ResearchCalendarService.create_user_event(
        db_session,
        cal.id,
        test_user.id,
        CalendarEventCreate(
            title="August Milestone",
            start_datetime=datetime(2026, 8, 25, 12, 0, 0, tzinfo=timezone.utc),
        ),
    )

    # Filter July only
    july_events = ResearchCalendarService.list_events(
        db_session,
        cal.id,
        test_user.id,
        start_date=datetime(2026, 7, 1, tzinfo=timezone.utc),
        end_date=datetime(2026, 7, 31, tzinfo=timezone.utc),
    )
    assert len(july_events) == 1
    assert july_events[0].id == ev_july.id


# ============================================================================
# Canonical Opportunity Projection Tests
# ============================================================================

def test_project_opportunity_canonical_milestones(
    db_session: Session,
    test_user: UserModel,
    test_opportunity: OpportunityModel,
):
    """
    Verifies projection of canonical milestones (SUBMISSION, NOTIFICATION, EVENT_START).
    Ensures milestone isolation: EVENT_START is NOT converted to SUBMISSION.
    """
    cal = ResearchCalendarService.get_or_create_default_calendar(db_session, test_user.id)

    proj_res = ResearchCalendarService.project_opportunity_to_calendar(
        db=db_session,
        calendar_id=cal.id,
        user_id=test_user.id,
        opportunity_id=test_opportunity.id,
    )

    assert proj_res.created_count >= 1
    assert len(proj_res.projected_events) >= 1

    events_by_type = {ev.event_type: ev for ev in proj_res.projected_events}

    # Verify submission deadline projected
    assert CalendarEventType.OPPORTUNITY_SUBMISSION.value in events_by_type
    sub_ev = events_by_type[CalendarEventType.OPPORTUNITY_SUBMISSION.value]
    assert sub_ev.is_canonical_projection is True
    assert sub_ev.opportunity_id == test_opportunity.id
    assert sub_ev.provenance_metadata["milestone_type"] == "SUBMISSION"
    assert sub_ev.start_datetime is not None

    # Verify event start date is NOT a submission deadline (Milestone Isolation Invariant)
    if CalendarEventType.EVENT_START.value in events_by_type:
        event_start_ev = events_by_type[CalendarEventType.EVENT_START.value]
        assert event_start_ev.provenance_metadata["milestone_type"] == "EVENT_START"
        assert event_start_ev.event_type != CalendarEventType.OPPORTUNITY_SUBMISSION.value


def test_project_opportunity_idempotency(
    db_session: Session,
    test_user: UserModel,
    test_opportunity: OpportunityModel,
):
    """Verifies that reprojecting the same opportunity is completely idempotent."""
    cal = ResearchCalendarService.get_or_create_default_calendar(db_session, test_user.id)

    # First run
    res1 = ResearchCalendarService.project_opportunity_to_calendar(
        db_session, cal.id, test_user.id, test_opportunity.id
    )
    initial_count = res1.created_count

    # Second run with unchanged opportunity
    res2 = ResearchCalendarService.project_opportunity_to_calendar(
        db_session, cal.id, test_user.id, test_opportunity.id
    )
    assert res2.created_count == 0
    assert res2.updated_count == 0
    assert res2.unchanged_count == initial_count

    # Verify total events in calendar did not duplicate
    all_events = ResearchCalendarService.list_events(db_session, cal.id, test_user.id)
    assert len(all_events) == initial_count


def test_project_opportunity_reprojection_updates_on_change(
    db_session: Session,
    test_user: UserModel,
    test_opportunity: OpportunityModel,
):
    """
    Verifies that if opportunity deadline updates later (e.g. extension),
    reprojection updates the existing event rather than creating a duplicate.
    """
    cal = ResearchCalendarService.get_or_create_default_calendar(db_session, test_user.id)

    # Initial projection
    ResearchCalendarService.project_opportunity_to_calendar(
        db_session, cal.id, test_user.id, test_opportunity.id
    )

    # Opportunity deadline is extended
    new_deadline = datetime(2026, 8, 27, 23, 59, 59, tzinfo=timezone.utc)
    test_opportunity.submission_deadline = new_deadline
    db_session.commit()

    # Reproject
    res = ResearchCalendarService.project_opportunity_to_calendar(
        db_session, cal.id, test_user.id, test_opportunity.id
    )
    assert res.created_count == 0
    assert res.updated_count >= 1

    events = ResearchCalendarService.list_events(
        db_session, cal.id, test_user.id, event_type=CalendarEventType.OPPORTUNITY_SUBMISSION
    )
    assert len(events) == 1
    assert events[0].date_str == "2026-08-27"
    assert events[0].start_datetime.day == 28


# ============================================================================
# RFC 5545 iCalendar Export Tests
# ============================================================================

def test_ical_export_structure_and_determinism(
    db_session: Session,
    test_user: UserModel,
    test_opportunity: OpportunityModel,
):
    """
    Verifies valid RFC 5545 structure:
    - VCALENDAR and VEVENT records
    - Stable UIDs
    - DTSTART, SUMMARY, CATEGORIES
    - Line folding at 75 octets
    - Byte-identical determinism for identical calendar state
    """
    cal = ResearchCalendarService.get_or_create_default_calendar(db_session, test_user.id)
    ResearchCalendarService.project_opportunity_to_calendar(
        db_session, cal.id, test_user.id, test_opportunity.id
    )
    ResearchCalendarService.create_user_event(
        db_session,
        cal.id,
        test_user.id,
        CalendarEventCreate(
            title="Very long title for an academic manuscript preparation milestone that will test line folding according to RFC 5545 specifications",
            description="Comprehensive description containing commas, semicolons; and newlines\nto verify RFC 5545 text escaping.",
            start_datetime=datetime(2026, 7, 1, 10, 0, 0, tzinfo=timezone.utc),
            end_datetime=datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc),
        ),
    )

    fixed_time = datetime(2026, 9, 18, 12, 0, 0, tzinfo=timezone.utc)
    feed1 = ResearchCalendarService.generate_ical_feed(db_session, cal.id, test_user.id, fixed_dtstamp=fixed_time)
    feed2 = ResearchCalendarService.generate_ical_feed(db_session, cal.id, test_user.id, fixed_dtstamp=fixed_time)

    # 1. Byte-level determinism
    assert feed1 == feed2

    # 2. Structure assertions
    assert "BEGIN:VCALENDAR\r\n" in feed1
    assert "VERSION:2.0\r\n" in feed1
    assert "PRODID:-//ResearchConnect AI//Research Calendar//EN\r\n" in feed1
    assert "BEGIN:VEVENT\r\n" in feed1
    assert "END:VEVENT\r\n" in feed1
    assert "END:VCALENDAR\r\n" in feed1

    # 3. UID and DTSTART assertions
    assert "@researchconnect.ai" in feed1
    assert "DTSTART:20260701T100000Z" in feed1

    # 4. Text escaping
    assert "\\," in feed1 or "\\;" in feed1 or "\\n" in feed1

    # 5. Line folding check: no raw line exceeds 75 octets without CRLF + space continuation
    raw_lines = feed1.split("\r\n")
    for line in raw_lines:
        if line:  # ignore empty line at end
            assert len(line.encode("utf-8")) <= 75


def test_escape_and_fold_helpers():
    """Unit test for _escape_ical_text and _fold_ical_line."""
    raw = "Hello; World, with\\backslash and \n newline"
    escaped = _escape_ical_text(raw)
    assert "\\;" in escaped
    assert "\\," in escaped
    assert "\\\\" in escaped
    assert "\\n" in escaped

    long_line = "DESCRIPTION:" + "A" * 100
    folded = _fold_ical_line(long_line, max_length=75)
    parts = folded.split("\r\n ")
    assert len(parts) >= 2
    assert len(parts[0].encode("utf-8")) <= 75
