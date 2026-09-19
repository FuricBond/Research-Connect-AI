from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid
import pytest

from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR as TSVector
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from pgvector.sqlalchemy import Vector

from app.models.base import Base
from app.models.calendar import CalendarEventType, ResearchCalendarEventModel, ResearchCalendarModel
from app.models.notification import (
    DeliveryChannel,
    DeliveryStatus,
    NotificationModel,
    NotificationPreferenceModel,
    NotificationType,
    OffsetUnit,
    ReminderRuleModel,
)
from app.models.opportunity import OpportunityModel
from app.models.research_profile import ResearchProfileModel
from app.models.saved_opportunity import SavedOpportunityModel
from app.models.user import UserModel
from app.ranking.deadline.models import (
    ConflictState,
    DeadlineObservation,
    DeadlinePrecision,
    DeadlineType,
    NormalizationStatus,
    NormalizedDeadline,
    SourceAuthorityTier,
    TimezoneIndicator,
)
from app.schemas.notification import ReminderRuleCreate
from app.services.notification_service import NotificationService
from app.services.reminder_scheduler_service import (
    MockEmailProvider,
    ReminderSchedulerService,
    compute_deduplication_key,
    get_email_provider,
    set_email_provider,
)

# SQLite compatibility
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
    target_tables = [
        Base.metadata.tables["users"],
        Base.metadata.tables["institutions"],
        Base.metadata.tables["researchers"],
        Base.metadata.tables["topics"],
        Base.metadata.tables["opportunities"],
        Base.metadata.tables["opportunity_topics"],
        Base.metadata.tables["saved_opportunities"],
        Base.metadata.tables["research_submissions"],
        Base.metadata.tables["research_profiles"],
        Base.metadata.tables["research_calendars"],
        Base.metadata.tables["research_calendar_events"],
        Base.metadata.tables["researcher_notification_preferences"],
        Base.metadata.tables["reminder_rules"],
        Base.metadata.tables["notifications"],
        Base.metadata.tables["notification_delivery_attempts"],
    ]
    Base.metadata.create_all(bind=engine, tables=target_tables)
    sm = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = sm()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def mock_email_provider() -> MockEmailProvider:
    provider = MockEmailProvider()
    set_email_provider(provider)
    yield provider
    provider.clear()


@pytest.fixture
def test_user(db_session: Session) -> UserModel:
    user = UserModel(
        id=uuid.uuid4(),
        email="researcher_alice@example.edu",
        hashed_password="hashed_test_password",
        full_name="Dr. Alice Observer",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def test_profile(db_session: Session, test_user: UserModel) -> ResearchProfileModel:
    profile = ResearchProfileModel(
        id=uuid.uuid4(),
        user_id=test_user.id,
        academic_status="FACULTY",
    )
    db_session.add(profile)
    db_session.commit()
    return profile


@pytest.fixture
def test_opportunity(db_session: Session) -> OpportunityModel:
    opp = OpportunityModel(
        id=uuid.uuid4(),
        title="International Conference on Machine Learning (ICML 2026)",
        description="Premier machine learning conference.",
        location="Vienna, Austria",
        opportunity_type="CONFERENCE",
        submission_deadline=datetime(2026, 8, 20, 23, 59, 59, tzinfo=timezone.utc),
        event_start_date=datetime(2026, 12, 1, 0, 0, 0, tzinfo=timezone.utc).date(),
        source_id=None,
        raw_source_id="icml_2026_test",
    )
    db_session.add(opp)
    db_session.commit()
    return opp


# ============================================================================
# Unit Tests
# ============================================================================

def test_calculate_scheduled_time():
    target = datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc)

    # 14 days before
    sched_14d = ReminderSchedulerService.calculate_scheduled_time(target, 14, OffsetUnit.DAYS.value)
    assert sched_14d == datetime(2026, 8, 6, 12, 0, 0, tzinfo=timezone.utc)

    # 24 hours before
    sched_24h = ReminderSchedulerService.calculate_scheduled_time(target, 24, OffsetUnit.HOURS.value)
    assert sched_24h == datetime(2026, 8, 19, 12, 0, 0, tzinfo=timezone.utc)

    # 30 minutes before
    sched_30m = ReminderSchedulerService.calculate_scheduled_time(target, 30, OffsetUnit.MINUTES.value)
    assert sched_30m == datetime(2026, 8, 20, 11, 30, 0, tzinfo=timezone.utc)


def test_compute_deduplication_key_determinism():
    pid = uuid.uuid4()
    opp_id = uuid.uuid4()
    rule_id = uuid.uuid4()
    instant = datetime(2026, 8, 21, 11, 59, 59, tzinfo=timezone.utc)

    k1 = compute_deduplication_key(
        profile_id=pid,
        source_type="OPPORTUNITY",
        source_id=opp_id,
        deadline_type="SUBMISSION",
        rule_id=rule_id,
        delivery_channel="IN_APP",
        target_instant=instant,
        notification_type="DEADLINE_UPCOMING",
    )
    k2 = compute_deduplication_key(
        profile_id=pid,
        source_type="OPPORTUNITY",
        source_id=opp_id,
        deadline_type="SUBMISSION",
        rule_id=rule_id,
        delivery_channel="IN_APP",
        target_instant=instant,
        notification_type="DEADLINE_UPCOMING",
    )
    assert k1 == k2
    assert len(k1) == 64  # sha256 hex


# ============================================================================
# Scheduler Execution & Idempotency Tests
# ============================================================================

def test_run_scheduled_reminders_and_idempotency(
    db_session: Session,
    test_user: UserModel,
    test_profile: ResearchProfileModel,
    test_opportunity: OpportunityModel,
    mock_email_provider: MockEmailProvider,
):
    # Track opportunity in workspace
    saved = SavedOpportunityModel(
        user_id=test_user.id,
        opportunity_id=test_opportunity.id,
        status="PLANNING",
    )
    db_session.add(saved)
    db_session.commit()

    # Rule: 7 days before
    NotificationService.create_reminder_rule(
        db_session,
        test_profile.id,
        ReminderRuleCreate(
            event_type="OPPORTUNITY_SUBMISSION",
            offset_amount=7,
            offset_unit=OffsetUnit.DAYS,
            delivery_channel=DeliveryChannel.IN_APP,
        ),
    )

    # Eval time: 6 days before deadline (so 7-day reminder is due)
    eval_time = datetime(2026, 8, 15, 12, 0, 0, tzinfo=timezone.utc)

    summary1 = ReminderSchedulerService.run_scheduled_reminders(db_session, now=eval_time)
    assert summary1.created_notifications >= 1
    assert summary1.delivered_notifications >= 1

    # Verify notification created
    notifs, total, unread = NotificationService.list_notifications(db_session, test_profile.id)
    assert total >= 1
    assert any("ICML 2026" in n.title for n in notifs)

    # Re-run scheduler with identical state (Idempotency)
    summary2 = ReminderSchedulerService.run_scheduled_reminders(db_session, now=eval_time)
    assert summary2.created_notifications == 0
    assert summary2.skipped_duplicates >= 1

    # Verify still only 1 notification
    _, total2, _ = NotificationService.list_notifications(db_session, test_profile.id)
    assert total2 == total


def test_email_notification_delivery_channel(
    db_session: Session,
    test_user: UserModel,
    test_profile: ResearchProfileModel,
    test_opportunity: OpportunityModel,
    mock_email_provider: MockEmailProvider,
):
    saved = SavedOpportunityModel(
        user_id=test_user.id,
        opportunity_id=test_opportunity.id,
        status="PLANNING",
    )
    db_session.add(saved)

    # Email rule
    NotificationService.create_reminder_rule(
        db_session,
        test_profile.id,
        ReminderRuleCreate(
            event_type="OPPORTUNITY_SUBMISSION",
            offset_amount=7,
            offset_unit=OffsetUnit.DAYS,
            delivery_channel=DeliveryChannel.EMAIL,
        ),
    )
    db_session.commit()

    eval_time = datetime(2026, 8, 15, 12, 0, 0, tzinfo=timezone.utc)
    summary = ReminderSchedulerService.run_scheduled_reminders(db_session, now=eval_time)
    assert summary.delivered_notifications >= 1

    # Check mock email was sent
    assert len(mock_email_provider.sent_emails) == 1
    sent = mock_email_provider.sent_emails[0]
    assert sent["to"] == test_user.email
    assert "ICML 2026" in sent["subject"]


def test_calendar_planning_event_reminder(
    db_session: Session,
    test_user: UserModel,
    test_profile: ResearchProfileModel,
):
    cal = ResearchCalendarModel(
        user_id=test_user.id,
        profile_id=test_profile.id,
        name="Test Calendar",
        timezone="UTC",
        is_default=True,
    )
    db_session.add(cal)
    db_session.commit()

    # Create user planning milestone for tomorrow
    base_time = datetime(2026, 9, 20, 10, 0, 0, tzinfo=timezone.utc)
    ev = ResearchCalendarEventModel(
        calendar_id=cal.id,
        title="Complete Literature Review",
        event_type=CalendarEventType.RESEARCH_MILESTONE.value,
        start_datetime=base_time,
        is_canonical_projection=False,
    )
    db_session.add(ev)
    db_session.commit()

    # Eval time: 12 hours before event (within 24h reminder window)
    eval_time = base_time - timedelta(hours=12)

    summary = ReminderSchedulerService.run_scheduled_reminders(db_session, now=eval_time)
    assert summary.created_notifications >= 1

    notifs, _, _ = NotificationService.list_notifications(db_session, test_profile.id)
    assert any("Literature Review" in n.title for n in notifs)
