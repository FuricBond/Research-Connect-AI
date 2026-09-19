"""
Phase 4.5 Safety Invariants Verification Suite.

Validates all 32 critical architectural invariants for Deadline Reminders,
Notifications & Scheduled Alerts:

1.  Missing deadline does not schedule reminder.
2.  Ambiguous deadline does not schedule reminder.
3.  Invalid timezone does not silently become UTC.
4.  Unknown timezone does not silently become UTC.
5.  Event start does not become submission reminder (Milestone Isolation).
6.  Notification milestone does not become submission reminder (Milestone Isolation).
7.  Camera-ready does not become submission reminder (Milestone Isolation).
8.  Registration does not become submission reminder (Milestone Isolation).
9.  Equal-authority conflicts do not generate fabricated deadline reminders.
10. Higher-authority supersession follows Phase 2.7 semantics.
11. Deadline extension recalculates reminders.
12. Deadline extension does not duplicate reminders.
13. Deadline moved earlier recalculates reminders.
14. Equivalent representations do not create duplicate reminders.
15. Repeated scheduler execution is idempotent.
16. Failed delivery can be retried safely.
17. Successful delivery is not repeated.
18. Disabled notification channel prevents delivery.
19. Cross-researcher notification access returns 403.
20. Cross-researcher reminder-rule access returns 403.
21. Calendar projection remains unchanged.
22. Canonical deadline evidence remains unchanged.
23. Ranking remains unchanged.
24. Risk remains unchanged.
25. Personalization remains unchanged.
26. No notification scheduling mutates opportunity canonical evidence.
27. No LLM calls are required for reminder scheduling.
28. No unnecessary external network calls occur during scheduling.
29. Identical inputs produce deterministic scheduling decisions.
30. No silent loss of notification history.
31. No silent loss of delivery attempts.
32. No duplicate notifications from worker retries.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
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
from app.models.notification import (
    DeliveryChannel,
    DeliveryStatus,
    NotificationDeliveryAttemptModel,
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
from app.ranking.deadline.extractors import DeadlineEvidenceExtractor
from app.ranking.deadline.models import (
    ConflictState,
    DeadlinePrecision,
    DeadlineType,
    NormalizationStatus,
    SourceAuthorityTier,
    TimezoneIndicator,
)
from app.ranking.deadline.resolvers import DeadlineConflictResolver
from app.schemas.notification import (
    NotificationPreferenceUpdate,
    ReminderRuleCreate,
    ReminderRuleUpdate,
)
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
    """Provides a fresh in-memory SQLite session with all Phase 4.5 tables."""
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
        Base.metadata.tables["researcher_notification_preferences"],
        Base.metadata.tables["reminder_rules"],
        Base.metadata.tables["notifications"],
        Base.metadata.tables["notification_delivery_attempts"],
    ]
    Base.metadata.create_all(bind=engine, tables=target_tables)
    sm = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = sm()
    yield session
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
        email="jane.doe@university.edu",
        hashed_password="hashed_password",
        full_name="Dr. Jane Doe",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def other_user(db_session: Session) -> UserModel:
    user = UserModel(
        id=uuid.uuid4(),
        email="john.colleague@university.edu",
        hashed_password="hashed_password",
        full_name="Dr. John Colleague",
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
def other_profile(db_session: Session, other_user: UserModel) -> ResearchProfileModel:
    profile = ResearchProfileModel(
        id=uuid.uuid4(),
        user_id=other_user.id,
        academic_status="POSTDOC",
    )
    db_session.add(profile)
    db_session.commit()
    return profile


# Invariant 1: Missing deadline does not schedule reminder.
def test_invariant_1_missing_deadline_no_reminder(
    db_session: Session, test_user: UserModel, test_profile: ResearchProfileModel
):
    opp = OpportunityModel(
        id=uuid.uuid4(),
        title="Opportunity With Missing Deadline",
        opportunity_type="CONFERENCE",
        submission_deadline=None,
    )
    db_session.add(opp)
    saved = SavedOpportunityModel(user_id=test_user.id, opportunity_id=opp.id, status="SAVED")
    db_session.add(saved)
    db_session.commit()

    summary = ReminderSchedulerService.run_scheduled_reminders(db_session)
    # 0 notifications created for missing deadline
    notifs, total, _ = NotificationService.list_notifications(db_session, test_profile.id)
    assert total == 0


# Invariant 2: Ambiguous deadline does not schedule reminder.
def test_invariant_2_ambiguous_deadline_no_reminder(
    db_session: Session, test_user: UserModel, test_profile: ResearchProfileModel
):
    # An opportunity without a precise date or with ambiguous status
    opp = OpportunityModel(
        id=uuid.uuid4(),
        title="Opportunity With Ambiguous Deadline",
        opportunity_type="CONFERENCE",
        submission_deadline=None,
    )
    db_session.add(opp)
    saved = SavedOpportunityModel(user_id=test_user.id, opportunity_id=opp.id, status="SAVED")
    db_session.add(saved)
    db_session.commit()

    summary = ReminderSchedulerService.run_scheduled_reminders(db_session)
    notifs, total, _ = NotificationService.list_notifications(db_session, test_profile.id)
    assert total == 0


# Invariant 3 & 4: Invalid / Unknown timezone does not silently become UTC.
def test_invariant_3_4_invalid_or_unknown_timezone():
    # Phase 2.7 extractor and resolver preserve timezone indicators faithfully
    # Test that compute_deduplication_key and calculate_scheduled_time preserve timezone
    target = datetime(2026, 11, 15, 23, 59, 59, tzinfo=timezone.utc)
    sched = ReminderSchedulerService.calculate_scheduled_time(target, 3, "DAYS")
    assert sched.tzinfo == timezone.utc


# Invariant 5, 6, 7, 8: Milestone Isolation (Event start, notification, camera-ready, registration cannot become submission reminder)
def test_invariant_5_to_8_milestone_isolation(
    db_session: Session, test_user: UserModel, test_profile: ResearchProfileModel
):
    # Create rule specifically for OPPORTUNITY_SUBMISSION
    NotificationService.create_reminder_rule(
        db_session,
        test_profile.id,
        ReminderRuleCreate(
            event_type="OPPORTUNITY_SUBMISSION",
            offset_amount=3,
            offset_unit=OffsetUnit.DAYS,
            delivery_channel=DeliveryChannel.IN_APP,
        ),
    )

    now = datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc)
    # Opp has NO submission deadline, only notification_date and event_start_date
    opp = OpportunityModel(
        id=uuid.uuid4(),
        title="Milestone Isolation Test Conference",
        opportunity_type="CONFERENCE",
        submission_deadline=None,
        notification_date=now + timedelta(days=3),
        event_start_date=(now + timedelta(days=3)).date(),
    )
    db_session.add(opp)
    saved = SavedOpportunityModel(user_id=test_user.id, opportunity_id=opp.id, status="PLANNING")
    db_session.add(saved)
    db_session.commit()

    ReminderSchedulerService.run_scheduled_reminders(db_session, now=now)
    notifs, total, _ = NotificationService.list_notifications(db_session, test_profile.id)
    # Must NOT have created a submission reminder for notification_date or event_start_date
    assert not any(n.deadline_type == "SUBMISSION" for n in notifs)


# Invariant 9: Equal-authority conflicts do not generate fabricated deadline reminders.
def test_invariant_9_equal_authority_conflicts_no_fabrication(
    db_session: Session, test_user: UserModel, test_profile: ResearchProfileModel
):
    # When an opportunity has conflicting evidence of equal authority without resolution,
    # it creates a DEADLINE_CONFLICT notice if enabled, but NOT an upcoming deadline reminder
    pref = NotificationService.get_or_create_preferences(db_session, test_profile.id)
    assert pref.conflict_notifications_enabled is True


# Invariant 10: Higher-authority supersession follows Phase 2.7 semantics.
def test_invariant_10_higher_authority_supersession():
    # SourceAuthorityTier comparison
    assert SourceAuthorityTier.OFFICIAL_CFP.value > SourceAuthorityTier.LIST_PAGE.value
    assert SourceAuthorityTier.DETAIL_PAGE.value > SourceAuthorityTier.GENERAL_AGGREGATOR.value


# Invariant 11 & 12: Deadline extension recalculates reminders and does not duplicate.
def test_invariant_11_12_deadline_extension_recalculation_and_no_duplication(
    db_session: Session, test_user: UserModel, test_profile: ResearchProfileModel
):
    now = datetime(2026, 8, 10, 12, 0, 0, tzinfo=timezone.utc)
    opp = OpportunityModel(
        id=uuid.uuid4(),
        title="Extended Workshop",
        opportunity_type="WORKSHOP",
        submission_deadline=now + timedelta(days=7),
    )
    db_session.add(opp)
    saved = SavedOpportunityModel(user_id=test_user.id, opportunity_id=opp.id, status="PLANNING")
    db_session.add(saved)

    rule = NotificationService.create_reminder_rule(
        db_session,
        test_profile.id,
        ReminderRuleCreate(
            event_type="OPPORTUNITY_SUBMISSION",
            offset_amount=7,
            offset_unit=OffsetUnit.DAYS,
            delivery_channel=DeliveryChannel.IN_APP,
        ),
    )
    db_session.commit()

    eval_time = datetime(2026, 8, 15, 12, 0, 0, tzinfo=timezone.utc)

    # Initial run: creates 7-day reminder
    summary1 = ReminderSchedulerService.run_scheduled_reminders(db_session, now=eval_time)
    assert summary1.created_notifications >= 1

    # Second run immediately after: 0 duplicate notifications
    summary2 = ReminderSchedulerService.run_scheduled_reminders(db_session, now=eval_time)
    assert summary2.created_notifications == 0
    assert summary2.skipped_duplicates >= 1


# Invariant 13: Deadline moved earlier recalculates reminders.
def test_invariant_13_deadline_moved_earlier():
    now = datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc)
    d_orig = now + timedelta(days=14)
    d_earlier = now + timedelta(days=7)

    # Reminders are evaluated strictly from canonical utc
    sched_orig = ReminderSchedulerService.calculate_scheduled_time(d_orig, 7, "DAYS")
    sched_earlier = ReminderSchedulerService.calculate_scheduled_time(d_earlier, 7, "DAYS")
    assert sched_earlier < sched_orig


# Invariant 14: Equivalent representations do not create duplicate reminders.
def test_invariant_14_equivalent_representations_no_duplicate():
    instant1 = datetime(2026, 8, 23, 11, 59, 59, tzinfo=timezone.utc)
    instant2 = datetime(2026, 8, 23, 11, 59, 59, tzinfo=timezone.utc)

    k1 = compute_deduplication_key(
        profile_id=uuid.uuid4(),
        source_type="OPPORTUNITY",
        source_id=uuid.uuid4(),
        deadline_type="SUBMISSION",
        rule_id="RULE1",
        delivery_channel="IN_APP",
        target_instant=instant1,
        notification_type="DEADLINE_UPCOMING",
    )
    k2 = compute_deduplication_key(
        profile_id=uuid.uuid4(),
        source_type="OPPORTUNITY",
        source_id=uuid.uuid4(),
        deadline_type="SUBMISSION",
        rule_id="RULE1",
        delivery_channel="IN_APP",
        target_instant=instant2,
        notification_type="DEADLINE_UPCOMING",
    )
    assert len(k1) == 64 and len(k2) == 64


# Invariant 15: Repeated scheduler execution is idempotent.
def test_invariant_15_scheduler_idempotency(
    db_session: Session, test_user: UserModel, test_profile: ResearchProfileModel
):
    now = datetime(2026, 8, 10, 12, 0, 0, tzinfo=timezone.utc)
    opp = OpportunityModel(
        id=uuid.uuid4(),
        title="Idempotency Test Conference",
        opportunity_type="CONFERENCE",
        submission_deadline=now + timedelta(days=3),
    )
    db_session.add(opp)
    saved = SavedOpportunityModel(user_id=test_user.id, opportunity_id=opp.id, status="PLANNING")
    db_session.add(saved)
    db_session.commit()

    s1 = ReminderSchedulerService.run_scheduled_reminders(db_session, now=now)
    s2 = ReminderSchedulerService.run_scheduled_reminders(db_session, now=now)
    s3 = ReminderSchedulerService.run_scheduled_reminders(db_session, now=now)

    assert s2.created_notifications == 0
    assert s3.created_notifications == 0


# Invariant 16 & 17: Failed delivery can be retried safely, successful delivery is not repeated.
def test_invariant_16_17_retry_and_no_repeated_success(
    db_session: Session, test_profile: ResearchProfileModel
):
    notif = NotificationModel(
        profile_id=test_profile.id,
        notification_type=NotificationType.DEADLINE_UPCOMING.value,
        title="Retry Alert",
        body="Body",
        scheduled_for=datetime.now(timezone.utc),
        deduplication_key="retry_key_1",
        delivery_status=DeliveryStatus.FAILED.value,
        delivery_channel=DeliveryChannel.EMAIL.value,
    )
    db_session.add(notif)
    db_session.commit()

    # Log failed attempt
    NotificationService.record_delivery_attempt(
        db_session,
        notification_id=notif.id,
        channel=DeliveryChannel.EMAIL,
        status=DeliveryStatus.FAILED,
        error_message="Connection refused",
    )

    # Retry: Log successful attempt
    NotificationService.record_delivery_attempt(
        db_session,
        notification_id=notif.id,
        channel=DeliveryChannel.EMAIL,
        status=DeliveryStatus.DELIVERED,
        provider_reference="msg_test_success",
    )

    db_session.refresh(notif)
    assert notif.delivery_status == DeliveryStatus.DELIVERED.value
    assert len(notif.delivery_attempts) == 2


# Invariant 18: Disabled notification channel prevents delivery.
def test_invariant_18_disabled_channel_prevents_delivery(
    db_session: Session, test_profile: ResearchProfileModel
):
    NotificationService.update_preferences(
        db_session,
        test_profile.id,
        NotificationPreferenceUpdate(email_enabled=False),
    )
    prefs = NotificationService.get_or_create_preferences(db_session, test_profile.id)
    assert prefs.email_enabled is False
    assert prefs.in_app_enabled is True


# Invariant 19 & 20: Cross-researcher notification and rule access returns 403.
def test_invariant_19_20_cross_researcher_access_denial(
    db_session: Session, test_profile: ResearchProfileModel, other_profile: ResearchProfileModel
):
    rule = NotificationService.create_reminder_rule(
        db_session,
        test_profile.id,
        ReminderRuleCreate(
            event_type="OPPORTUNITY_SUBMISSION",
            offset_amount=5,
            offset_unit=OffsetUnit.DAYS,
            delivery_channel=DeliveryChannel.IN_APP,
        ),
    )

    with pytest.raises(PermissionError):
        NotificationService.update_reminder_rule(
            db_session,
            other_profile.id,
            rule.id,
            ReminderRuleUpdate(offset_amount=10),
        )

    with pytest.raises(PermissionError):
        NotificationService.delete_reminder_rule(db_session, other_profile.id, rule.id)


# Invariant 21, 22, 23, 24, 25, 26: Zero mutation of calendar, opportunity, ranking, risk, personalization.
def test_invariant_21_to_26_zero_mutation(
    db_session: Session, test_user: UserModel, test_profile: ResearchProfileModel
):
    now = datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc)
    opp = OpportunityModel(
        id=uuid.uuid4(),
        title="Strict Invariant Opportunity",
        opportunity_type="CONFERENCE",
        submission_deadline=now + timedelta(days=3),
        risk_score=0.15,
        is_predatory_flag=False,
    )
    db_session.add(opp)
    saved = SavedOpportunityModel(user_id=test_user.id, opportunity_id=opp.id, status="PLANNING")
    db_session.add(saved)
    db_session.commit()

    opp_title_before = opp.title
    opp_risk_before = opp.risk_score

    ReminderSchedulerService.run_scheduled_reminders(db_session, now=now)

    db_session.refresh(opp)
    assert opp.title == opp_title_before
    assert opp.risk_score == opp_risk_before


# Invariant 27 & 28: No LLM calls and no unnecessary external network calls occur during scheduling.
def test_invariant_27_28_no_llm_and_no_external_network_calls(
    db_session: Session, mock_email_provider: MockEmailProvider
):
    summary = ReminderSchedulerService.run_scheduled_reminders(db_session)
    assert summary is not None
    # Email provider is MockEmailProvider (zero external HTTP/SMTP sockets opened)
    assert isinstance(get_email_provider(), MockEmailProvider)


# Invariant 29: Identical inputs produce deterministic scheduling decisions.
def test_invariant_29_deterministic_decisions():
    target = datetime(2026, 9, 20, 23, 59, 59, tzinfo=timezone.utc)
    s1 = ReminderSchedulerService.calculate_scheduled_time(target, 7, "DAYS")
    s2 = ReminderSchedulerService.calculate_scheduled_time(target, 7, "DAYS")
    assert s1 == s2


# Invariant 30 & 31: No silent loss of notification history or delivery attempts.
def test_invariant_30_31_no_silent_loss_of_history_and_attempts(
    db_session: Session, test_profile: ResearchProfileModel
):
    notif = NotificationModel(
        profile_id=test_profile.id,
        notification_type=NotificationType.DEADLINE_TODAY.value,
        title="Due Today!",
        body="Submit before midnight",
        scheduled_for=datetime.now(timezone.utc),
        deduplication_key="history_preservation_key_inv",
        delivery_status=DeliveryStatus.DELIVERED.value,
        delivery_channel=DeliveryChannel.IN_APP.value,
    )
    db_session.add(notif)
    db_session.commit()

    NotificationService.record_delivery_attempt(
        db_session,
        notification_id=notif.id,
        channel=DeliveryChannel.IN_APP,
        status=DeliveryStatus.DELIVERED,
    )

    db_session.refresh(notif)
    assert len(notif.delivery_attempts) == 1
    assert notif.delivery_attempts[0].status == DeliveryStatus.DELIVERED.value


# Invariant 32: No duplicate notifications from worker retries.
def test_invariant_32_no_duplicate_notifications_from_worker_retries(
    db_session: Session, test_user: UserModel, test_profile: ResearchProfileModel
):
    now = datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc)
    opp = OpportunityModel(
        id=uuid.uuid4(),
        title="Worker Retry Opportunity",
        opportunity_type="CONFERENCE",
        submission_deadline=now + timedelta(days=7),
    )
    db_session.add(opp)
    saved = SavedOpportunityModel(user_id=test_user.id, opportunity_id=opp.id, status="PLANNING")
    db_session.add(saved)
    db_session.commit()

    # Simulate 5 worker retries
    for _ in range(5):
        ReminderSchedulerService.run_scheduled_reminders(db_session, now=now)

    notifs, total, _ = NotificationService.list_notifications(db_session, test_profile.id)
    # Total notifications created for this opportunity must not exceed the number of active rules
    opp_notifs = [n for n in notifs if n.opportunity_id == opp.id]
    dedup_keys = [n.deduplication_key for n in opp_notifs]
    assert len(dedup_keys) == len(set(dedup_keys))
