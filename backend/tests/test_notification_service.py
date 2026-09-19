from __future__ import annotations

from datetime import datetime, timezone
import uuid
import pytest

from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR as TSVector
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from pgvector.sqlalchemy import Vector

from app.models.base import Base
from app.models.notification import (
    DeliveryChannel,
    DeliveryStatus,
    NotificationModel,
    NotificationPreferenceModel,
    OffsetUnit,
    ReminderRuleModel,
)
from app.models.research_profile import ResearchProfileModel
from app.models.user import UserModel
from app.schemas.notification import (
    NotificationPreferenceUpdate,
    ReminderRuleCreate,
    ReminderRuleUpdate,
)
from app.services.notification_service import NotificationService

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
def test_user(db_session: Session) -> UserModel:
    user = UserModel(
        id=uuid.uuid4(),
        email="alice_notif@example.edu",
        hashed_password="hashed_test_password",
        full_name="Dr. Alice Observer",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def test_user_bob(db_session: Session) -> UserModel:
    user = UserModel(
        id=uuid.uuid4(),
        email="bob_notif@example.edu",
        hashed_password="hashed_test_password",
        full_name="Dr. Bob Observer",
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
def test_profile_bob(db_session: Session, test_user_bob: UserModel) -> ResearchProfileModel:
    profile = ResearchProfileModel(
        id=uuid.uuid4(),
        user_id=test_user_bob.id,
        academic_status="POSTDOC",
    )
    db_session.add(profile)
    db_session.commit()
    return profile


# ============================================================================
# Preferences Tests
# ============================================================================

def test_get_or_create_preferences_bootstraps_defaults(
    db_session: Session,
    test_profile: ResearchProfileModel,
):
    prefs = NotificationService.get_or_create_preferences(db_session, test_profile.id)
    assert prefs.profile_id == test_profile.id
    assert prefs.email_enabled is True
    assert prefs.in_app_enabled is True
    assert prefs.deadline_reminders_enabled is True
    assert prefs.extension_notifications_enabled is True
    assert prefs.conflict_notifications_enabled is True
    assert prefs.calendar_event_reminders_enabled is True

    # Calling again returns same row
    prefs2 = NotificationService.get_or_create_preferences(db_session, test_profile.id)
    assert prefs2.id == prefs.id


def test_update_preferences(
    db_session: Session,
    test_profile: ResearchProfileModel,
):
    NotificationService.get_or_create_preferences(db_session, test_profile.id)
    updated = NotificationService.update_preferences(
        db_session,
        test_profile.id,
        NotificationPreferenceUpdate(
            email_enabled=False,
            conflict_notifications_enabled=False,
        ),
    )
    assert updated.email_enabled is False
    assert updated.conflict_notifications_enabled is False
    assert updated.in_app_enabled is True  # untouched


# ============================================================================
# Reminder Rules Tests
# ============================================================================

def test_reminder_rules_lifecycle_and_defaults(
    db_session: Session,
    test_profile: ResearchProfileModel,
):
    # Bootstrapping defaults
    rules = NotificationService.bootstrap_default_reminder_rules(db_session, test_profile.id)
    assert len(rules) == 4
    offsets = [r.offset_amount for r in rules]
    assert 14 in offsets
    assert 7 in offsets
    assert 3 in offsets
    assert 24 in offsets

    # Create custom rule
    new_rule = NotificationService.create_reminder_rule(
        db_session,
        test_profile.id,
        ReminderRuleCreate(
            event_type="OPPORTUNITY_SUBMISSION",
            offset_amount=5,
            offset_unit=OffsetUnit.DAYS,
            delivery_channel=DeliveryChannel.EMAIL,
        ),
    )
    assert new_rule.offset_amount == 5
    assert new_rule.delivery_channel == "EMAIL"

    # Update rule
    updated_rule = NotificationService.update_reminder_rule(
        db_session,
        test_profile.id,
        new_rule.id,
        ReminderRuleUpdate(offset_amount=6),
    )
    assert updated_rule.offset_amount == 6

    # Delete rule
    NotificationService.delete_reminder_rule(db_session, test_profile.id, new_rule.id)
    all_rules = NotificationService.list_reminder_rules(db_session, test_profile.id)
    assert new_rule.id not in [r.id for r in all_rules]


def test_reminder_rules_ownership_isolation(
    db_session: Session,
    test_profile: ResearchProfileModel,
    test_profile_bob: ResearchProfileModel,
):
    rule = NotificationService.create_reminder_rule(
        db_session,
        test_profile.id,
        ReminderRuleCreate(
            offset_amount=10,
            offset_unit=OffsetUnit.DAYS,
            delivery_channel=DeliveryChannel.IN_APP,
        ),
    )

    # Bob cannot update or delete Alice's rule
    with pytest.raises(PermissionError):
        NotificationService.update_reminder_rule(
            db_session,
            test_profile_bob.id,
            rule.id,
            ReminderRuleUpdate(offset_amount=12),
        )

    with pytest.raises(PermissionError):
        NotificationService.delete_reminder_rule(
            db_session,
            test_profile_bob.id,
            rule.id,
        )


# ============================================================================
# Notification Read State & Delivery Attempt Tests
# ============================================================================

def test_notification_read_state(
    db_session: Session,
    test_profile: ResearchProfileModel,
    test_profile_bob: ResearchProfileModel,
):
    notif1 = NotificationModel(
        profile_id=test_profile.id,
        notification_type="DEADLINE_UPCOMING",
        title="Upcoming Deadline: ICML 2026",
        body="Submission deadline in 7 days.",
        scheduled_for=datetime(2026, 8, 14, 12, 0, 0, tzinfo=timezone.utc),
        delivery_status=DeliveryStatus.DELIVERED.value,
        delivery_channel=DeliveryChannel.IN_APP.value,
        deduplication_key="dedup-1",
        metadata_json={},
    )
    notif2 = NotificationModel(
        profile_id=test_profile.id,
        notification_type="DEADLINE_TODAY",
        title="Deadline Today: NeurIPS 2026",
        body="Submission deadline today!",
        scheduled_for=datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc),
        delivery_status=DeliveryStatus.DELIVERED.value,
        delivery_channel=DeliveryChannel.IN_APP.value,
        deduplication_key="dedup-2",
        metadata_json={},
    )
    db_session.add_all([notif1, notif2])
    db_session.commit()

    assert NotificationService.get_unread_count(db_session, test_profile.id) == 2

    # Mark notif1 as read
    marked = NotificationService.mark_as_read(db_session, test_profile.id, notif1.id)
    assert marked.read_at is not None
    assert NotificationService.get_unread_count(db_session, test_profile.id) == 1

    # Bob cannot mark Alice's notification as read
    with pytest.raises(PermissionError):
        NotificationService.mark_as_read(db_session, test_profile_bob.id, notif2.id)

    # Mark all as read
    count = NotificationService.mark_all_as_read(db_session, test_profile.id)
    assert count == 1
    assert NotificationService.get_unread_count(db_session, test_profile.id) == 0


def test_record_delivery_attempt(
    db_session: Session,
    test_profile: ResearchProfileModel,
):
    notif = NotificationModel(
        profile_id=test_profile.id,
        notification_type="DEADLINE_UPCOMING",
        title="Test Notification",
        body="Test message body",
        scheduled_for=datetime(2026, 8, 14, 12, 0, 0, tzinfo=timezone.utc),
        delivery_status=DeliveryStatus.PENDING.value,
        delivery_channel=DeliveryChannel.EMAIL.value,
        deduplication_key="dedup-attempt-1",
        metadata_json={},
    )
    db_session.add(notif)
    db_session.commit()

    attempt = NotificationService.record_delivery_attempt(
        db=db_session,
        notification_id=notif.id,
        channel=DeliveryChannel.EMAIL.value,
        status="SUCCESS",
        attempt_number=1,
        provider_reference="email-msg-999",
    )
    assert attempt.notification_id == notif.id
    assert attempt.status == "SUCCESS"
    assert attempt.provider_reference == "email-msg-999"
