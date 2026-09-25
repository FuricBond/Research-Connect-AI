"""
Phase 6 / Audit Resolution — P0 Security Regression Test Suite.

Verifies the probe matrix from Section 8.2 and Section E (P0-SEC-1..4) of the audit:
  1. Anonymous requests to protected routers return 401 Unauthorized (no fallback identity).
  2. Anonymous PATCH to researcher profile is rejected with 401 Unauthorized.
  3. System-wide reminder trigger requires ADMIN role (401 for anon, 403 for non-admin, 200 for admin).
  4. Cross-user requests return 403 Forbidden.
  5. JWT Bearer authentication works end-to-end (register -> token -> authenticated calls).
  6. Disabling dev identity mode rejects raw X-User-ID headers in production.
"""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.db.types import TSVector, Vector
from app.main import app
from app.models import Base
from app.models.research_profile import AcademicStatus, ResearchProfileModel
from app.models.user import UserModel
from app.services.researcher_profile_service import ResearcherProfileService

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
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
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
def user_a(db_session: Session) -> UserModel:
    user = UserModel(
        id=uuid.uuid4(),
        email="alice@institution.edu",
        hashed_password=hash_password("AliceSecurePass123!"),
        full_name="Alice Researcher",
        role="FACULTY",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def profile_a(db_session: Session, user_a: UserModel) -> ResearchProfileModel:
    profile = ResearchProfileModel(
        id=uuid.uuid4(),
        user_id=user_a.id,
        academic_status="FACULTY",
        institution="University of Excellence",
        department="Computer Science",
    )
    db_session.add(profile)
    db_session.commit()
    return profile


@pytest.fixture
def user_b(db_session: Session) -> UserModel:
    user = UserModel(
        id=uuid.uuid4(),
        email="bob@institution.edu",
        hashed_password=hash_password("BobSecurePass123!"),
        full_name="Bob Researcher",
        role="STUDENT",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def profile_b(db_session: Session, user_b: UserModel) -> ResearchProfileModel:
    profile = ResearchProfileModel(
        id=uuid.uuid4(),
        user_id=user_b.id,
        academic_status="STUDENT",
        institution="University of Excellence",
        department="Physics",
    )
    db_session.add(profile)
    db_session.commit()
    return profile


@pytest.fixture
def admin_user(db_session: Session) -> UserModel:
    user = UserModel(
        id=uuid.uuid4(),
        email="admin@institution.edu",
        hashed_password=hash_password("AdminSecurePass123!"),
        full_name="Platform Admin",
        role="ADMIN",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


# ============================================================================
# 1. P0-SEC-1: Anonymous Access Rejected (No Fallback Identity)
# ============================================================================

def test_p0_sec_1_anonymous_workspace_rejected(client: TestClient, user_a: UserModel):
    """Anonymous callers cannot access workspace or assume oldest user identity."""
    res = client.get("/api/v1/workspace")
    assert res.status_code == 401
    assert "Authentication required" in res.json()["detail"]


def test_p0_sec_1_anonymous_calendar_rejected(client: TestClient, user_a: UserModel):
    """Anonymous callers cannot access default calendar or assume oldest user identity."""
    res = client.get("/api/v1/calendar/default")
    assert res.status_code == 401


def test_p0_sec_1_anonymous_notifications_rejected(client: TestClient, user_a: UserModel):
    """Anonymous callers cannot access notifications."""
    res = client.get("/api/v1/notifications")
    assert res.status_code == 401


def test_p0_sec_1_anonymous_submissions_rejected(client: TestClient, user_a: UserModel):
    """Anonymous callers cannot list submissions."""
    res = client.get("/api/v1/submissions")
    assert res.status_code == 401


# ============================================================================
# 2. P0-SEC-2: Researcher Routes Require Authentication
# ============================================================================

def test_p0_sec_2_anonymous_profile_patch_rejected(client: TestClient, profile_a: ResearchProfileModel):
    """Anonymous PATCH to researcher profile must return 401 Unauthorized."""
    res = client.patch(
        f"/api/v1/researchers/{profile_a.id}",
        json={"bio": "HIJACKED by anonymous"},
    )
    assert res.status_code == 401


def test_p0_sec_2_anonymous_profile_get_rejected(client: TestClient, profile_a: ResearchProfileModel):
    """Anonymous GET to researcher profile must return 401 Unauthorized."""
    res = client.get(f"/api/v1/researchers/{profile_a.id}")
    assert res.status_code == 401


def test_p0_sec_2_anonymous_preferences_get_rejected(client: TestClient, profile_a: ResearchProfileModel):
    """Anonymous GET to researcher preferences must return 401 Unauthorized."""
    res = client.get(f"/api/v1/researchers/{profile_a.id}/preferences")
    assert res.status_code == 401


def test_p0_sec_2_anonymous_preference_intelligence_rejected(client: TestClient, profile_a: ResearchProfileModel):
    """Anonymous GET to preference-intelligence must return 401 Unauthorized."""
    res = client.get(f"/api/v1/researchers/{profile_a.id}/preference-intelligence")
    assert res.status_code == 401


def test_p0_sec_2_anonymous_profile_completeness_rejected(client: TestClient, profile_a: ResearchProfileModel):
    """Anonymous GET to profile completeness must return 401 Unauthorized."""
    res = client.get(f"/api/v1/researchers/{profile_a.id}/completeness")
    assert res.status_code == 401


# ============================================================================
# 3. P0-SEC-3: Reminder Trigger Requires Admin Role
# ============================================================================

def test_p0_sec_3_anonymous_reminder_trigger_rejected(client: TestClient):
    """Anonymous trigger must be rejected with 401."""
    res = client.post("/api/v1/notifications/trigger-reminders")
    assert res.status_code == 401


def test_p0_sec_3_non_admin_reminder_trigger_forbidden(client: TestClient, user_a: UserModel):
    """Regular user (FACULTY/STUDENT) trigger must be forbidden with 403."""
    res = client.post(
        "/api/v1/notifications/trigger-reminders",
        headers={"X-User-ID": str(user_a.id)},
    )
    assert res.status_code == 403


def test_p0_sec_3_admin_reminder_trigger_allowed(client: TestClient, admin_user: UserModel):
    """ADMIN role caller can trigger reminders."""
    res = client.post(
        "/api/v1/notifications/trigger-reminders",
        headers={"X-User-ID": str(admin_user.id)},
    )
    assert res.status_code == 200


# ============================================================================
# 4. Cross-User Authorization (403 Forbidden)
# ============================================================================

def test_cross_user_researcher_profile_forbidden(
    client: TestClient,
    profile_a: ResearchProfileModel,
    user_b: UserModel,
):
    """User B cannot view or modify User A's profile."""
    res_get = client.get(
        f"/api/v1/researchers/{profile_a.id}",
        headers={"X-User-ID": str(user_b.id)},
    )
    assert res_get.status_code == 403

    res_patch = client.patch(
        f"/api/v1/researchers/{profile_a.id}",
        json={"bio": "Tampered by Bob"},
        headers={"X-User-ID": str(user_b.id)},
    )
    assert res_patch.status_code == 403


def test_cross_user_preferences_forbidden(
    client: TestClient,
    profile_a: ResearchProfileModel,
    user_b: UserModel,
):
    """User B cannot view User A's preferences."""
    res = client.get(
        f"/api/v1/researchers/{profile_a.id}/preferences",
        headers={"X-User-ID": str(user_b.id)},
    )
    assert res.status_code == 403


# ============================================================================
# 5. Owner Authorization (200 OK)
# ============================================================================

def test_owner_access_profile_and_preferences(
    client: TestClient,
    profile_a: ResearchProfileModel,
    user_a: UserModel,
):
    """Owner accessing their own profile and preferences succeeds."""
    res_get = client.get(
        f"/api/v1/researchers/{profile_a.id}",
        headers={"X-User-ID": str(user_a.id)},
    )
    assert res_get.status_code == 200
    assert res_get.json()["id"] == str(profile_a.id)

    res_pref = client.get(
        f"/api/v1/researchers/{profile_a.id}/preferences",
        headers={"X-User-ID": str(user_a.id)},
    )
    assert res_pref.status_code == 200


# ============================================================================
# 6. P0-SEC-4: JWT Bearer Authentication & Production Mode
# ============================================================================

def test_jwt_bearer_authentication_flow(client: TestClient, db_session: Session):
    """Test user registration and subsequent authenticated request via JWT Bearer."""
    # 1. Register a new user
    reg_payload = {
        "email": "carol@institution.edu",
        "password": "CarolSecurePassword123!",
        "full_name": "Carol Researcher",
        "role": "FACULTY",
        "department": "Biochemistry",
        "institution_name": "Carol Lab",
    }
    reg_res = client.post("/api/v1/auth/register", json=reg_payload)
    assert reg_res.status_code == 201
    reg_data = reg_res.json()
    token = reg_data["access_token"]
    assert token
    profile_id = reg_data["user"]["profile_id"]

    # 2. Access /auth/me with Bearer token
    me_res = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_res.status_code == 200
    assert me_res.json()["email"] == "carol@institution.edu"

    # 3. Access profile with Bearer token
    prof_res = client.get(
        f"/api/v1/researchers/{profile_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert prof_res.status_code == 200
    assert prof_res.json()["id"] == profile_id

    # 4. Invalid Bearer token
    bad_token_res = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer invalid.jwt.token"},
    )
    assert bad_token_res.status_code == 401


def test_production_mode_rejects_raw_x_user_id(
    client: TestClient,
    profile_a: ResearchProfileModel,
    user_a: UserModel,
    monkeypatch,
):
    """When auth_dev_identity_enabled is False, raw X-User-ID is ignored (requires Bearer)."""
    monkeypatch.setattr(settings, "auth_dev_identity_enabled", False)

    res = client.get(
        f"/api/v1/researchers/{profile_a.id}",
        headers={"X-User-ID": str(user_a.id)},
    )
    assert res.status_code == 401
    assert "Authentication required" in res.json()["detail"]
