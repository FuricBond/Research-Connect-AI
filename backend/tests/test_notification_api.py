"""
Integration and API Tests for Phase 4.5 Deadline Reminders, Notifications & Scheduled Alerts.

Endpoints tested:
  - GET    /api/v1/notifications
  - GET    /api/v1/notifications/unread-count
  - POST   /api/v1/notifications/{notification_id}/read
  - POST   /api/v1/notifications/read-all
  - GET    /api/v1/notifications/preferences
  - PATCH  /api/v1/notifications/preferences
  - GET    /api/v1/notifications/rules
  - POST   /api/v1/notifications/rules
  - PATCH  /api/v1/notifications/rules/{rule_id}
  - DELETE /api/v1/notifications/rules/{rule_id}
  - POST   /api/v1/notifications/trigger-reminders
  - GET    /api/v1/researchers/{researcher_id}/notifications
  - POST   /api/v1/researchers/{researcher_id}/notifications/{notification_id}/read
  - POST   /api/v1/researchers/{researcher_id}/notifications/read-all
  - GET    /api/v1/researchers/{researcher_id}/notification-preferences
  - PATCH  /api/v1/researchers/{researcher_id}/notification-preferences
  - GET    /api/v1/researchers/{researcher_id}/reminder-rules
  - POST   /api/v1/researchers/{researcher_id}/reminder-rules
  - PATCH  /api/v1/researchers/{researcher_id}/reminder-rules/{rule_id}
  - DELETE /api/v1/researchers/{researcher_id}/reminder-rules/{rule_id}
  - Strict tenant isolation (HTTP 403 on cross-user operations)
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
import uuid

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import get_db
from app.db.types import TSVector, Vector
from app.main import app
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
    NotificationModel,
    NotificationPreferenceModel,
    NotificationType,
    OffsetUnit,
    ReminderRuleModel,
)
from app.models.opportunity import OpportunityModel
from app.models.research_profile import ResearchProfileModel
from app.models.user import UserModel
from app.schemas.notification import ReminderRuleCreate
from app.services.notification_service import NotificationService

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
def client(db_session: Session) -> TestClient:
    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def alice(db_session: Session) -> UserModel:
    user = UserModel(
        id=uuid.uuid4(),
        email="alice@example.edu",
        hashed_password="hashed_alice_password",
        full_name="Dr. Alice Smith",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def bob(db_session: Session) -> UserModel:
    user = UserModel(
        id=uuid.uuid4(),
        email="bob@example.edu",
        hashed_password="hashed_bob_password",
        full_name="Dr. Bob Jones",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def alice_profile(db_session: Session, alice: UserModel) -> ResearchProfileModel:
    profile = ResearchProfileModel(
        id=uuid.uuid4(),
        user_id=alice.id,
        academic_status="FACULTY",
    )
    db_session.add(profile)
    db_session.commit()
    return profile


@pytest.fixture
def bob_profile(db_session: Session, bob: UserModel) -> ResearchProfileModel:
    profile = ResearchProfileModel(
        id=uuid.uuid4(),
        user_id=bob.id,
        academic_status="POSTDOC",
    )
    db_session.add(profile)
    db_session.commit()
    return profile


def test_notification_preferences_get_and_update(client: TestClient, alice: UserModel):
    # GET preferences (auto-bootstrapped)
    resp = client.get("/api/v1/notifications/preferences", headers={"X-User-ID": str(alice.id)})
    assert resp.status_code == 200
    data = resp.json()
    assert data["email_enabled"] is True
    assert data["in_app_enabled"] is True
    assert data["deadline_reminders_enabled"] is True

    # PATCH preferences
    patch_resp = client.patch(
        "/api/v1/notifications/preferences",
        headers={"X-User-ID": str(alice.id)},
        json={"email_enabled": False, "conflict_notifications_enabled": False},
    )
    assert patch_resp.status_code == 200
    updated = patch_resp.json()
    assert updated["email_enabled"] is False
    assert updated["conflict_notifications_enabled"] is False
    assert updated["in_app_enabled"] is True


def test_reminder_rules_crud(client: TestClient, alice: UserModel):
    # GET rules (default rules bootstrapped)
    resp = client.get("/api/v1/notifications/rules", headers={"X-User-ID": str(alice.id)})
    assert resp.status_code == 200
    rules_data = resp.json()
    assert rules_data["total"] >= 4
    assert len(rules_data["rules"]) >= 4

    # POST new rule
    create_resp = client.post(
        "/api/v1/notifications/rules",
        headers={"X-User-ID": str(alice.id)},
        json={
            "event_type": "OPPORTUNITY_SUBMISSION",
            "offset_amount": 10,
            "offset_unit": "DAYS",
            "delivery_channel": "IN_APP",
        },
    )
    assert create_resp.status_code == 201
    new_rule = create_resp.json()
    assert new_rule["offset_amount"] == 10
    rule_id = new_rule["id"]

    # PATCH rule
    patch_resp = client.patch(
        f"/api/v1/notifications/rules/{rule_id}",
        headers={"X-User-ID": str(alice.id)},
        json={"offset_amount": 12, "is_active": False},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["offset_amount"] == 12
    assert patch_resp.json()["is_active"] is False

    # DELETE rule
    del_resp = client.delete(
        f"/api/v1/notifications/rules/{rule_id}",
        headers={"X-User-ID": str(alice.id)},
    )
    assert del_resp.status_code == 204

    # Verify deleted
    get_after = client.get("/api/v1/notifications/rules", headers={"X-User-ID": str(alice.id)})
    rule_ids = [r["id"] for r in get_after.json()["rules"]]
    assert rule_id not in rule_ids


def test_notifications_listing_and_read_state(
    client: TestClient,
    db_session: Session,
    alice: UserModel,
    alice_profile: ResearchProfileModel,
):
    n1 = NotificationModel(
        profile_id=alice_profile.id,
        notification_type=NotificationType.DEADLINE_UPCOMING.value,
        title="ICML Submission Due Soon",
        body="Deadline in 3 days",
        scheduled_for=datetime.now(timezone.utc),
        deduplication_key="dedup_alice_1",
        delivery_status=DeliveryStatus.DELIVERED.value,
        delivery_channel=DeliveryChannel.IN_APP.value,
    )
    n2 = NotificationModel(
        profile_id=alice_profile.id,
        notification_type=NotificationType.DEADLINE_EXTENDED.value,
        title="NeurIPS Deadline Extended",
        body="Deadline extended by 7 days",
        scheduled_for=datetime.now(timezone.utc),
        deduplication_key="dedup_alice_2",
        delivery_status=DeliveryStatus.DELIVERED.value,
        delivery_channel=DeliveryChannel.IN_APP.value,
    )
    db_session.add_all([n1, n2])
    db_session.commit()

    # Check unread count
    resp = client.get("/api/v1/notifications/unread-count", headers={"X-User-ID": str(alice.id)})
    assert resp.status_code == 200
    assert resp.json()["unread_count"] == 2

    # List notifications
    list_resp = client.get("/api/v1/notifications", headers={"X-User-ID": str(alice.id)})
    assert list_resp.status_code == 200
    items = list_resp.json()["notifications"]
    assert len(items) == 2

    # Mark one as read
    read_resp = client.post(
        f"/api/v1/notifications/{n1.id}/read",
        headers={"X-User-ID": str(alice.id)},
    )
    assert read_resp.status_code == 200
    assert read_resp.json()["read_at"] is not None

    # Check unread count is now 1
    resp2 = client.get("/api/v1/notifications/unread-count", headers={"X-User-ID": str(alice.id)})
    assert resp2.json()["unread_count"] == 1

    # Mark all read
    all_read_resp = client.post(
        "/api/v1/notifications/read-all",
        headers={"X-User-ID": str(alice.id)},
    )
    assert all_read_resp.status_code == 200
    assert all_read_resp.json()["marked_read_count"] == 1

    # Check unread count is now 0
    resp3 = client.get("/api/v1/notifications/unread-count", headers={"X-User-ID": str(alice.id)})
    assert resp3.json()["unread_count"] == 0


def test_researcher_scoped_endpoints_and_cross_tenant_isolation(
    client: TestClient,
    db_session: Session,
    alice: UserModel,
    bob: UserModel,
    alice_profile: ResearchProfileModel,
    bob_profile: ResearchProfileModel,
):
    rule_alice = NotificationService.create_reminder_rule(
        db_session,
        alice_profile.id,
        ReminderRuleCreate(
            event_type="OPPORTUNITY_SUBMISSION",
            offset_amount=5,
            offset_unit=OffsetUnit.DAYS,
            delivery_channel=DeliveryChannel.IN_APP,
        ),
    )
    notif_alice = NotificationModel(
        profile_id=alice_profile.id,
        notification_type=NotificationType.DEADLINE_UPCOMING.value,
        title="Alice Exclusive Alert",
        body="Secret submission due",
        scheduled_for=datetime.now(timezone.utc),
        deduplication_key="alice_unique_key_999",
        delivery_status=DeliveryStatus.DELIVERED.value,
        delivery_channel=DeliveryChannel.IN_APP.value,
    )
    db_session.add(notif_alice)
    db_session.commit()

    # Alice can access her researcher-scoped endpoints
    res_notifs = client.get(
        f"/api/v1/researchers/{alice_profile.id}/notifications",
        headers={"X-User-ID": str(alice.id)},
    )
    assert res_notifs.status_code == 200
    assert len(res_notifs.json()["notifications"]) == 1

    # Bob attempting to access Alice's researcher notifications must return 403 Forbidden
    bob_cross_notifs = client.get(
        f"/api/v1/researchers/{alice_profile.id}/notifications",
        headers={"X-User-ID": str(bob.id)},
    )
    assert bob_cross_notifs.status_code == 403
    assert "Forbidden" in bob_cross_notifs.json()["detail"]

    # Bob attempting to access Alice's notification preferences must return 403
    bob_cross_prefs = client.get(
        f"/api/v1/researchers/{alice_profile.id}/notification-preferences",
        headers={"X-User-ID": str(bob.id)},
    )
    assert bob_cross_prefs.status_code == 403

    # Bob attempting to access Alice's reminder rules must return 403
    bob_cross_rules = client.get(
        f"/api/v1/researchers/{alice_profile.id}/reminder-rules",
        headers={"X-User-ID": str(bob.id)},
    )
    assert bob_cross_rules.status_code == 403

    # Bob attempting to mark Alice's notification as read must return 403
    bob_cross_read = client.post(
        f"/api/v1/researchers/{alice_profile.id}/notifications/{notif_alice.id}/read",
        headers={"X-User-ID": str(bob.id)},
    )
    assert bob_cross_read.status_code == 403

    # Bob attempting to patch Alice's reminder rule must return 403
    bob_cross_patch_rule = client.patch(
        f"/api/v1/researchers/{alice_profile.id}/reminder-rules/{rule_alice.id}",
        headers={"X-User-ID": str(bob.id)},
        json={"offset_amount": 99},
    )
    assert bob_cross_patch_rule.status_code == 403


def test_schedule_run_api_endpoint(client: TestClient, alice: UserModel):
    # Alice triggers scheduler run
    resp = client.post(
        "/api/v1/notifications/trigger-reminders",
        headers={"X-User-ID": str(alice.id)},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "discovered_reminders" in data
    assert "created_notifications" in data
    assert "delivered_notifications" in data
    assert "errors" in data
