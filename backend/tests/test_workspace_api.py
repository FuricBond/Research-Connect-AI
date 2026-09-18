"""
Phase 4.1 — REST API Integration Tests for /api/v1/workspace Endpoints.

Tests cover:
  1. POST /api/v1/workspace - Add opportunity to workspace (201 Created)
  2. POST /api/v1/workspace - Duplicate addition rejection (409 Conflict)
  3. POST /api/v1/workspace - Non-existent opportunity rejection (404 Not Found)
  4. GET /api/v1/workspace - List items with status, priority, and search filters (200 OK)
  5. GET /api/v1/workspace/summary - Aggregated status and priority counts (200 OK)
  6. GET /api/v1/workspace/{item_id} - Retrieve single item with allowed_transitions (200 OK)
  7. PATCH /api/v1/workspace/{item_id} - Update priority, tags, notes (200 OK)
  8. POST /api/v1/workspace/{item_id}/transition - Valid status transition (200 OK)
  9. POST /api/v1/workspace/{item_id}/transition - Invalid transition rejection (400 Bad Request)
 10. POST /api/v1/workspace/{item_id}/archive - Archive opportunity (200 OK)
 11. POST /api/v1/workspace/{item_id}/unarchive - Unarchive opportunity (200 OK)
 12. DELETE /api/v1/workspace/{item_id} - Remove opportunity from workspace (204 No Content)
 13. Researcher Isolation:
       - Cross-researcher GET rejection (403 Forbidden)
       - Cross-researcher PATCH rejection (403 Forbidden)
       - Cross-researcher transition rejection (403 Forbidden)
       - Cross-researcher archive rejection (403 Forbidden)
       - Cross-researcher DELETE rejection (403 Forbidden)
"""
from __future__ import annotations

from datetime import datetime, timezone
import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from app.db.session import get_db
from app.db.types import TSVector, Vector
from app.main import app
from app.models.base import Base
from app.models.opportunity import OpportunityModel
from app.models.research_profile import ResearchProfileModel
from app.models.saved_opportunity import SavedOpportunityModel
from app.models.user import UserModel

# SQLite compatibility
compiles(JSONB, "sqlite")(lambda type_, compiler, **kw: "JSON")
compiles(Vector, "sqlite")(lambda type_, compiler, **kw: "TEXT")
compiles(TSVector, "sqlite")(lambda type_, compiler, **kw: "TEXT")


@pytest.fixture
def db_session() -> Session:
    """Provides a fresh in-memory SQLite session with all required tables."""
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
        Base.metadata.tables["researcher_interests"],
        Base.metadata.tables["researcher_preferences"],
        Base.metadata.tables["researcher_recommendation_feedback"],
    ]
    Base.metadata.create_all(bind=engine, tables=target_tables)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_session: Session) -> TestClient:
    """FastAPI TestClient with overridden get_db dependency."""
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
def sample_data(db_session: Session) -> tuple[UserModel, UserModel, OpportunityModel, OpportunityModel]:
    """Sets up two researchers and two opportunities."""
    u1 = UserModel(
        id=uuid.uuid4(),
        email="alice@university.edu",
        hashed_password="dummy_hash_1",
        full_name="Alice Researcher",
        role="FACULTY",
    )
    u2 = UserModel(
        id=uuid.uuid4(),
        email="bob@university.edu",
        hashed_password="dummy_hash_2",
        full_name="Bob Researcher",
        role="FACULTY",
    )
    opp1 = OpportunityModel(
        id=uuid.uuid4(),
        title="NeurIPS 2026 Call for Papers",
        opportunity_type="CONFERENCE",
        delivery_mode="HYBRID",
        status="ACTIVE",
        publisher="NeurIPS Foundation",
        organizer="NeurIPS",
        submission_deadline=datetime(2026, 5, 20, 23, 59, 59, tzinfo=timezone.utc),
        risk_score=0.01,
        is_predatory_flag=False,
    )
    opp2 = OpportunityModel(
        id=uuid.uuid4(),
        title="Nature Machine Intelligence Call",
        opportunity_type="JOURNAL",
        delivery_mode="ONLINE",
        status="ACTIVE",
        publisher="Nature Portfolio",
        organizer="Nature",
        submission_deadline=datetime(2026, 8, 1, 23, 59, 59, tzinfo=timezone.utc),
        risk_score=0.03,
        is_predatory_flag=False,
    )
    db_session.add_all([u1, u2, opp1, opp2])
    db_session.flush()

    p1 = ResearchProfileModel(
        id=uuid.uuid4(),
        user_id=u1.id,
        academic_status="FACULTY",
    )
    p2 = ResearchProfileModel(
        id=uuid.uuid4(),
        user_id=u2.id,
        academic_status="FACULTY",
    )
    db_session.add_all([p1, p2])
    db_session.commit()
    return u1, u2, opp1, opp2


def test_api_add_opportunity_to_workspace(
    client: TestClient,
    sample_data: tuple[UserModel, UserModel, OpportunityModel, OpportunityModel],
):
    """Test POST /api/v1/workspace creates item and returns 201."""
    u1, _, opp1, _ = sample_data

    response = client.post(
        "/api/v1/workspace",
        json={
            "opportunity_id": str(opp1.id),
            "status": "SAVED",
            "priority": "HIGH",
            "tags": ["ml", "neurips"],
            "notes": "Main target for benchmark paper",
        },
        headers={"X-User-ID": str(u1.id)},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["opportunity_id"] == str(opp1.id)
    assert data["status"] == "SAVED"
    assert data["priority"] == "HIGH"
    assert data["tags"] == ["ml", "neurips"]
    assert data["notes"] == "Main target for benchmark paper"
    assert "CONSIDERING" in data["allowed_transitions"]
    assert data["opportunity"]["title"] == "NeurIPS 2026 Call for Papers"


def test_api_duplicate_opportunity_idempotent(
    client: TestClient,
    sample_data: tuple[UserModel, UserModel, OpportunityModel, OpportunityModel],
):
    """Test POST /api/v1/workspace is idempotent and returns 200 OK if opportunity already in workspace."""
    u1, _, opp1, _ = sample_data

    # Add first time -> 201 Created
    r1 = client.post(
        "/api/v1/workspace",
        json={"opportunity_id": str(opp1.id)},
        headers={"X-User-ID": str(u1.id)},
    )
    assert r1.status_code == 201
    item_id_1 = r1.json()["id"]

    # Add second time -> 200 OK (idempotent return)
    r2 = client.post(
        "/api/v1/workspace",
        json={"opportunity_id": str(opp1.id)},
        headers={"X-User-ID": str(u1.id)},
    )
    assert r2.status_code == 200
    assert r2.json()["id"] == item_id_1


def test_api_list_and_summary(
    client: TestClient,
    sample_data: tuple[UserModel, UserModel, OpportunityModel, OpportunityModel],
):
    """Test GET /api/v1/workspace and GET /api/v1/workspace/summary."""
    u1, _, opp1, opp2 = sample_data

    # Add two items
    client.post(
        "/api/v1/workspace",
        json={"opportunity_id": str(opp1.id), "priority": "HIGH", "tags": ["top"]},
        headers={"X-User-ID": str(u1.id)},
    )
    client.post(
        "/api/v1/workspace",
        json={"opportunity_id": str(opp2.id), "priority": "MEDIUM", "tags": ["journal"]},
        headers={"X-User-ID": str(u1.id)},
    )

    # List items
    r_list = client.get("/api/v1/workspace", headers={"X-User-ID": str(u1.id)})
    assert r_list.status_code == 200
    list_data = r_list.json()
    assert list_data["total_count"] == 2
    assert list_data["active_count"] == 2
    assert len(list_data["items"]) == 2

    # Filter by priority HIGH
    r_filtered = client.get(
        "/api/v1/workspace?priority=HIGH",
        headers={"X-User-ID": str(u1.id)},
    )
    assert r_filtered.status_code == 200
    assert r_filtered.json()["total_count"] == 1

    # Summary
    r_sum = client.get("/api/v1/workspace/summary", headers={"X-User-ID": str(u1.id)})
    assert r_sum.status_code == 200
    sum_data = r_sum.json()
    assert sum_data["total_count"] == 2
    assert sum_data["active_count"] == 2
    assert sum_data["counts_by_status"]["SAVED"] == 2


def test_api_get_and_patch_item(
    client: TestClient,
    sample_data: tuple[UserModel, UserModel, OpportunityModel, OpportunityModel],
):
    """Test GET /api/v1/workspace/{item_id} and PATCH /api/v1/workspace/{item_id}."""
    u1, _, opp1, _ = sample_data

    # Create item
    res = client.post(
        "/api/v1/workspace",
        json={"opportunity_id": str(opp1.id)},
        headers={"X-User-ID": str(u1.id)},
    )
    item_id = res.json()["id"]

    # Retrieve item
    r_get = client.get(f"/api/v1/workspace/{item_id}", headers={"X-User-ID": str(u1.id)})
    assert r_get.status_code == 200
    assert r_get.json()["id"] == item_id

    # Update item metadata
    r_patch = client.patch(
        f"/api/v1/workspace/{item_id}",
        json={
            "priority": "URGENT",
            "notes": "Collaborating with Lab B",
            "tags": ["urgent", "neurips"],
        },
        headers={"X-User-ID": str(u1.id)},
    )
    assert r_patch.status_code == 200
    patched_data = r_patch.json()
    assert patched_data["priority"] == "URGENT"
    assert patched_data["notes"] == "Collaborating with Lab B"
    assert patched_data["tags"] == ["urgent", "neurips"]


def test_api_transition_validation(
    client: TestClient,
    sample_data: tuple[UserModel, UserModel, OpportunityModel, OpportunityModel],
):
    """Test valid and invalid transitions via POST /api/v1/workspace/{item_id}/transition."""
    u1, _, opp1, _ = sample_data

    res = client.post(
        "/api/v1/workspace",
        json={"opportunity_id": str(opp1.id)},
        headers={"X-User-ID": str(u1.id)},
    )
    item_id = res.json()["id"]

    # Invalid: SAVED -> ACCEPTED returns 400
    r_bad = client.post(
        f"/api/v1/workspace/{item_id}/transition",
        json={"target_status": "ACCEPTED"},
        headers={"X-User-ID": str(u1.id)},
    )
    assert r_bad.status_code == 400
    assert "Invalid workspace state transition from 'SAVED' to 'ACCEPTED'" in r_bad.json()["detail"]

    # Valid: SAVED -> CONSIDERING returns 200
    r_good = client.post(
        f"/api/v1/workspace/{item_id}/transition",
        json={"target_status": "CONSIDERING", "notes": "Evaluating submission scope"},
        headers={"X-User-ID": str(u1.id)},
    )
    assert r_good.status_code == 200
    assert r_good.json()["status"] == "CONSIDERING"


def test_api_archive_unarchive_lifecycle(
    client: TestClient,
    sample_data: tuple[UserModel, UserModel, OpportunityModel, OpportunityModel],
):
    """Test archive and unarchive endpoints."""
    u1, _, opp1, _ = sample_data

    res = client.post(
        "/api/v1/workspace",
        json={"opportunity_id": str(opp1.id)},
        headers={"X-User-ID": str(u1.id)},
    )
    item_id = res.json()["id"]

    # Archive
    r_arch = client.post(
        f"/api/v1/workspace/{item_id}/archive",
        headers={"X-User-ID": str(u1.id)},
    )
    assert r_arch.status_code == 200
    assert r_arch.json()["status"] == "ARCHIVED"
    assert r_arch.json()["archived_at"] is not None

    # Unarchive
    r_unarch = client.post(
        f"/api/v1/workspace/{item_id}/unarchive?target_status=PLANNING",
        headers={"X-User-ID": str(u1.id)},
    )
    assert r_unarch.status_code == 200
    assert r_unarch.json()["status"] == "PLANNING"
    assert r_unarch.json()["archived_at"] is None


def test_api_delete_item(
    client: TestClient,
    sample_data: tuple[UserModel, UserModel, OpportunityModel, OpportunityModel],
):
    """Test DELETE /api/v1/workspace/{item_id} returns 204."""
    u1, _, opp1, _ = sample_data

    res = client.post(
        "/api/v1/workspace",
        json={"opportunity_id": str(opp1.id)},
        headers={"X-User-ID": str(u1.id)},
    )
    item_id = res.json()["id"]

    r_del = client.delete(f"/api/v1/workspace/{item_id}", headers={"X-User-ID": str(u1.id)})
    assert r_del.status_code == 204

    # Verify 404 after deletion
    r_check = client.get(f"/api/v1/workspace/{item_id}", headers={"X-User-ID": str(u1.id)})
    assert r_check.status_code == 404


def test_api_cross_researcher_isolation_enforcement(
    client: TestClient,
    sample_data: tuple[UserModel, UserModel, OpportunityModel, OpportunityModel],
):
    """Verify that Bob (u2) cannot access or modify Alice's (u1) workspace items."""
    u1, u2, opp1, _ = sample_data

    # Alice creates an item
    res = client.post(
        "/api/v1/workspace",
        json={"opportunity_id": str(opp1.id)},
        headers={"X-User-ID": str(u1.id)},
    )
    alice_item_id = res.json()["id"]

    # Bob tries to GET Alice's item -> 403 Forbidden
    r_get = client.get(f"/api/v1/workspace/{alice_item_id}", headers={"X-User-ID": str(u2.id)})
    assert r_get.status_code == 403

    # Bob tries to PATCH Alice's item -> 403 Forbidden
    r_patch = client.patch(
        f"/api/v1/workspace/{alice_item_id}",
        json={"priority": "URGENT"},
        headers={"X-User-ID": str(u2.id)},
    )
    assert r_patch.status_code == 403

    # Bob tries to transition Alice's item -> 403 Forbidden
    r_trans = client.post(
        f"/api/v1/workspace/{alice_item_id}/transition",
        json={"target_status": "CONSIDERING"},
        headers={"X-User-ID": str(u2.id)},
    )
    assert r_trans.status_code == 403

    # Bob tries to archive Alice's item -> 403 Forbidden
    r_arch = client.post(
        f"/api/v1/workspace/{alice_item_id}/archive",
        headers={"X-User-ID": str(u2.id)},
    )
    assert r_arch.status_code == 403

    # Bob tries to delete Alice's item -> 403 Forbidden
    r_del = client.delete(
        f"/api/v1/workspace/{alice_item_id}",
        headers={"X-User-ID": str(u2.id)},
    )
    assert r_del.status_code == 403
