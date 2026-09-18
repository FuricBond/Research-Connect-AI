"""
Integration and API Tests for Phase 4.4 Research Calendar & Visual Deadline Planning.

Endpoints tested:
  - POST   /api/v1/calendar
  - GET    /api/v1/calendar
  - GET    /api/v1/calendar/default
  - GET    /api/v1/calendar/{calendar_id}
  - PATCH  /api/v1/calendar/{calendar_id}
  - POST   /api/v1/calendar/{calendar_id}/events
  - GET    /api/v1/calendar/{calendar_id}/events
  - GET    /api/v1/calendar/{calendar_id}/events/{event_id}
  - PATCH  /api/v1/calendar/{calendar_id}/events/{event_id}
  - DELETE /api/v1/calendar/{calendar_id}/events/{event_id}
  - POST   /api/v1/calendar/{calendar_id}/opportunities/{opportunity_id}/project
  - GET    /api/v1/calendar/{calendar_id}/export.ics
  - GET    /api/v1/researchers/{researcher_id}/calendar
  - GET    /api/v1/researchers/{researcher_id}/calendar.ics
  - Strict tenant isolation (HTTP 403 on cross-user operations)
"""
from __future__ import annotations

from datetime import datetime, timezone
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
from app.models.opportunity import OpportunityModel
from app.models.research_profile import ResearchProfileModel
from app.models.user import UserModel
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
def opportunity(db_session: Session) -> OpportunityModel:
    opp = OpportunityModel(
        id=uuid.uuid4(),
        title="NeurIPS 2026 — Annual Conference on Neural Information Processing Systems",
        description="Premier conference in machine learning and computational neuroscience.",
        location="New Orleans, USA",
        opportunity_type="CONFERENCE",
        submission_deadline=datetime(2026, 9, 22, 23, 59, 59, tzinfo=timezone.utc),
        notification_date=datetime(2026, 11, 20, 0, 0, 0, tzinfo=timezone.utc),
        event_start_date=datetime(2026, 12, 10, 0, 0, 0, tzinfo=timezone.utc).date(),
        source_id=None,
        raw_source_id="wikicfp_neurips_2026",
    )

    db_session.add(opp)
    db_session.commit()
    return opp



# ============================================================================
# Calendar API Tests
# ============================================================================

def test_get_or_create_default_calendar_api(client: TestClient, alice: UserModel):
    """Verifies GET /api/v1/calendar/default lazily initializes calendar."""
    res = client.get("/api/v1/calendar/default", headers={"X-User-ID": str(alice.id)})
    assert res.status_code == 200
    data = res.json()
    assert data["user_id"] == str(alice.id)
    assert data["is_default"] is True
    assert data["name"] == "Default Research Calendar"


def test_create_and_list_calendars_api(client: TestClient, alice: UserModel):
    """Verifies POST /api/v1/calendar and GET /api/v1/calendar."""
    payload = {
        "name": "NSF Grants 2026",
        "description": "National Science Foundation funding timeline",
        "timezone": "America/New_York",
        "is_default": False,
    }
    create_res = client.post(
        "/api/v1/calendar",
        json=payload,
        headers={"X-User-ID": str(alice.id)},
    )
    assert create_res.status_code == 201
    created_data = create_res.json()
    assert created_data["name"] == "NSF Grants 2026"
    assert created_data["timezone"] == "America/New_York"

    list_res = client.get("/api/v1/calendar", headers={"X-User-ID": str(alice.id)})
    assert list_res.status_code == 200
    list_data = list_res.json()
    assert list_data["total"] >= 1
    assert any(c["id"] == created_data["id"] for c in list_data["items"])


def test_calendar_cross_user_isolation_api(client: TestClient, alice: UserModel, bob: UserModel):
    """Verifies that accessing Alice's calendar as Bob returns HTTP 403 Forbidden."""
    # Alice creates a calendar
    alice_cal = client.post(
        "/api/v1/calendar",
        json={"name": "Alice Private Calendar"},
        headers={"X-User-ID": str(alice.id)},
    ).json()

    # Bob attempts to get Alice's calendar
    get_res = client.get(
        f"/api/v1/calendar/{alice_cal['id']}",
        headers={"X-User-ID": str(bob.id)},
    )
    assert get_res.status_code == 403
    assert "Forbidden" in get_res.json()["detail"]


# ============================================================================
# Event API Tests
# ============================================================================

def test_user_event_lifecycle_api(client: TestClient, alice: UserModel):
    """Verifies POST, GET, PATCH, and DELETE /api/v1/calendar/{id}/events."""
    cal = client.get("/api/v1/calendar/default", headers={"X-User-ID": str(alice.id)}).json()

    # Create event
    event_payload = {
        "title": "Complete experiment runs",
        "description": "Evaluate cross-validation scores on dataset A",
        "event_type": "RESEARCH_MILESTONE",
        "start_datetime": "2026-08-01T10:00:00Z",
        "status": "ACTIVE",
    }
    create_res = client.post(
        f"/api/v1/calendar/{cal['id']}/events",
        json=event_payload,
        headers={"X-User-ID": str(alice.id)},
    )
    assert create_res.status_code == 201
    ev_data = create_res.json()
    assert ev_data["title"] == "Complete experiment runs"
    assert ev_data["is_canonical_projection"] is False

    # List events
    list_res = client.get(
        f"/api/v1/calendar/{cal['id']}/events",
        headers={"X-User-ID": str(alice.id)},
    )
    assert list_res.status_code == 200
    assert list_res.json()["total"] == 1

    # Update event
    patch_res = client.patch(
        f"/api/v1/calendar/{cal['id']}/events/{ev_data['id']}",
        json={"title": "Complete experiment runs — Phase 2", "status": "COMPLETED"},
        headers={"X-User-ID": str(alice.id)},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["title"] == "Complete experiment runs — Phase 2"
    assert patch_res.json()["status"] == "COMPLETED"

    # Delete event
    del_res = client.delete(
        f"/api/v1/calendar/{cal['id']}/events/{ev_data['id']}",
        headers={"X-User-ID": str(alice.id)},
    )
    assert del_res.status_code == 204

    # Confirm deletion
    get_after = client.get(
        f"/api/v1/calendar/{cal['id']}/events/{ev_data['id']}",
        headers={"X-User-ID": str(alice.id)},
    )
    assert get_after.status_code == 404


def test_project_opportunity_api(
    client: TestClient,
    alice: UserModel,
    opportunity: OpportunityModel,
):
    """Verifies POST /api/v1/calendar/{calendar_id}/opportunities/{opportunity_id}/project."""
    cal = client.get("/api/v1/calendar/default", headers={"X-User-ID": str(alice.id)}).json()

    proj_res = client.post(
        f"/api/v1/calendar/{cal['id']}/opportunities/{opportunity.id}/project",
        headers={"X-User-ID": str(alice.id)},
    )
    assert proj_res.status_code == 200
    proj_data = proj_res.json()
    assert proj_data["opportunity_id"] == str(opportunity.id)
    assert proj_data["created_count"] >= 1
    assert len(proj_data["projected_events"]) >= 1


def test_export_calendar_ics_api(
    client: TestClient,
    alice: UserModel,
    opportunity: OpportunityModel,
):
    """Verifies GET /api/v1/calendar/{calendar_id}/export.ics returns standard text/calendar."""
    cal = client.get("/api/v1/calendar/default", headers={"X-User-ID": str(alice.id)}).json()

    # Project opportunity
    client.post(
        f"/api/v1/calendar/{cal['id']}/opportunities/{opportunity.id}/project",
        headers={"X-User-ID": str(alice.id)},
    )

    export_res = client.get(
        f"/api/v1/calendar/{cal['id']}/export.ics",
        headers={"X-User-ID": str(alice.id)},
    )
    assert export_res.status_code == 200
    assert "text/calendar" in export_res.headers["content-type"]
    assert "attachment; filename=" in export_res.headers["content-disposition"]
    body = export_res.text
    assert "BEGIN:VCALENDAR" in body
    assert "BEGIN:VEVENT" in body
    assert "END:VCALENDAR" in body


def test_researcher_calendar_view_api(
    client: TestClient,
    db_session: Session,
    alice: UserModel,
    opportunity: OpportunityModel,
):
    """Verifies GET /api/v1/researchers/{researcher_id}/calendar."""
    profile = ResearchProfileModel(
        id=uuid.uuid4(),
        user_id=alice.id,
        academic_status="FACULTY",
    )
    db_session.add(profile)
    db_session.commit()

    # Project opportunity
    cal = ResearchCalendarService.get_or_create_default_calendar(db_session, alice.id)
    ResearchCalendarService.project_opportunity_to_calendar(
        db_session, cal.id, alice.id, opportunity.id
    )

    res = client.get(
        f"/api/v1/researchers/{profile.id}/calendar",
        headers={"X-User-ID": str(alice.id)},
    )
    assert res.status_code == 200
    data = res.json()
    assert "calendar" in data
    assert "events" in data
    assert data["total_events"] >= 1
    assert data["upcoming_deadlines_count"] >= 1


def test_researcher_calendar_ics_api(
    client: TestClient,
    db_session: Session,
    alice: UserModel,
):
    """Verifies GET /api/v1/researchers/{researcher_id}/calendar.ics."""
    profile = ResearchProfileModel(
        id=uuid.uuid4(),
        user_id=alice.id,
        academic_status="FACULTY",
    )
    db_session.add(profile)
    db_session.commit()


    res = client.get(
        f"/api/v1/researchers/{profile.id}/calendar.ics",
        headers={"X-User-ID": str(alice.id)},
    )
    assert res.status_code == 200
    assert "text/calendar" in res.headers["content-type"]
    assert "BEGIN:VCALENDAR" in res.text
