"""
Phase 4.2 — REST API Integration Tests for /api/v1/submissions and workspace integration.

Tests cover:
  1. POST /api/v1/submissions - Create submission (201 Created)
  2. POST /api/v1/submissions - Non-existent workspace item rejection (404 Not Found)
  3. POST /api/v1/submissions - Cross-researcher workspace attachment rejection (403 Forbidden)
  4. GET /api/v1/submissions - List submissions with status/type/search filtering (200 OK)
  5. GET /api/v1/submissions/summary - Summary metrics across lifecycle stages (200 OK)
  6. GET /api/v1/submissions/{id} - Retrieve single submission with allowed transitions and deadline context (200 OK)
  7. GET /api/v1/submissions/{id} - Non-existent submission rejection (404 Not Found)
  8. GET /api/v1/submissions/{id} - Cross-researcher access rejection (403 Forbidden)
  9. PATCH /api/v1/submissions/{id} - Update draft metadata (200 OK)
 10. PATCH /api/v1/submissions/{id} - Cross-researcher update rejection (403 Forbidden)
 11. POST /api/v1/submissions/{id}/transition - Valid lifecycle transition (200 OK)
 12. POST /api/v1/submissions/{id}/transition - Invalid transition rejection (400 Bad Request)
 13. POST /api/v1/submissions/{id}/transition - Cross-researcher transition rejection (403 Forbidden)
 14. DELETE /api/v1/submissions/{id} - Delete draft submission (204 No Content)
 15. DELETE /api/v1/submissions/{id} - Reject deleting active submitted submission (400 Bad Request)
 16. DELETE /api/v1/submissions/{id} - Cross-researcher deletion rejection (403 Forbidden)
 17. GET /api/v1/workspace/{item_id}/submissions - List workspace-linked submissions (200 OK)
 18. GET /api/v1/workspace/{item_id}/submissions - Cross-researcher workspace rejection (403 Forbidden)
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
from app.models.research_submission import SubmissionStatus, SubmissionType
from app.models.saved_opportunity import SavedOpportunityModel, WorkspacePriority, WorkspaceStatus
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
        Base.metadata.tables["research_submission_documents"],
        Base.metadata.tables["research_submission_document_versions"],
        Base.metadata.tables["research_submission_events"],
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
def sample_data(db_session: Session) -> dict[str, Any]:
    """Sets up two researchers, opportunities, and workspace items."""
    u1 = UserModel(
        id=uuid.uuid4(),
        email="alice@university.edu",
        hashed_password="dummy_hash_1",
        full_name="Dr. Alice Chen",
        role="FACULTY",
    )
    u2 = UserModel(
        id=uuid.uuid4(),
        email="bob@university.edu",
        hashed_password="dummy_hash_2",
        full_name="Dr. Bob Martin",
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

    p1 = ResearchProfileModel(id=uuid.uuid4(), user_id=u1.id, academic_status="FACULTY")
    p2 = ResearchProfileModel(id=uuid.uuid4(), user_id=u2.id, academic_status="FACULTY")
    db_session.add_all([p1, p2])
    db_session.flush()

    ws1 = SavedOpportunityModel(
        id=uuid.uuid4(),
        user_id=u1.id,
        opportunity_id=opp1.id,
        status=WorkspaceStatus.PLANNING,
        priority=WorkspacePriority.HIGH,
    )
    ws2 = SavedOpportunityModel(
        id=uuid.uuid4(),
        user_id=u2.id,
        opportunity_id=opp2.id,
        status=WorkspaceStatus.PLANNING,
        priority=WorkspacePriority.MEDIUM,
    )
    db_session.add_all([ws1, ws2])
    db_session.commit()

    return {
        "user1": u1,
        "user2": u2,
        "opp1": opp1,
        "opp2": opp2,
        "ws1": ws1,
        "ws2": ws2,
    }


def test_api_create_submission_success(client: TestClient, sample_data: dict[str, Any]):
    u1 = sample_data["user1"]
    ws1 = sample_data["ws1"]

    payload = {
        "workspace_item_id": str(ws1.id),
        "title": "A Novel Graph Foundation Model",
        "abstract": "Self-supervised graph representation with high scalability.",
        "submission_type": "FULL_PAPER",
        "venue": "NeurIPS Main Track",
        "external_submission_id": "OPENREVIEW-9912",
        "submission_url": "https://openreview.net/forum?id=9912",
        "notes": "Targeting 9 pages + references.",
    }

    res = client.post(
        "/api/v1/submissions",
        json=payload,
        headers={"X-User-ID": str(u1.id)},
    )
    assert res.status_code == 201
    body = res.json()
    assert body["title"] == "A Novel Graph Foundation Model"
    assert body["status"] == "DRAFT"
    assert body["submission_type"] == "FULL_PAPER"
    assert body["venue"] == "NeurIPS Main Track"
    assert body["external_submission_id"] == "OPENREVIEW-9912"
    assert body["workspace_item_id"] == str(ws1.id)
    assert body["workspace_status"] == "PLANNING"
    assert "READY" in body["allowed_transitions"]
    assert "WITHDRAWN" in body["allowed_transitions"]
    assert body["deadline_context"]["submission_deadline"] is not None


def test_api_create_submission_errors(client: TestClient, sample_data: dict[str, Any]):
    u1 = sample_data["user1"]
    u2 = sample_data["user2"]
    ws1 = sample_data["ws1"]

    # 404 on non-existent workspace item
    res_404 = client.post(
        "/api/v1/submissions",
        json={"workspace_item_id": str(uuid.uuid4()), "title": "Orphan"},
        headers={"X-User-ID": str(u1.id)},
    )
    assert res_404.status_code == 404

    # 403 when User 2 tries to create submission for User 1's workspace item
    res_403 = client.post(
        "/api/v1/submissions",
        json={"workspace_item_id": str(ws1.id), "title": "Sneaky Paper"},
        headers={"X-User-ID": str(u2.id)},
    )
    assert res_403.status_code == 403


def test_api_list_and_summary_submissions(client: TestClient, sample_data: dict[str, Any]):
    u1 = sample_data["user1"]
    ws1 = sample_data["ws1"]

    # Create 2 submissions for user 1
    s1 = client.post(
        "/api/v1/submissions",
        json={"workspace_item_id": str(ws1.id), "title": "Paper One", "submission_type": "FULL_PAPER"},
        headers={"X-User-ID": str(u1.id)},
    ).json()

    s2 = client.post(
        "/api/v1/submissions",
        json={"workspace_item_id": str(ws1.id), "title": "Paper Two", "submission_type": "SHORT_PAPER"},
        headers={"X-User-ID": str(u1.id)},
    ).json()

    # Transition s1 to READY
    client.post(
        f"/api/v1/submissions/{s1['id']}/transition",
        json={"target_status": "READY"},
        headers={"X-User-ID": str(u1.id)},
    )

    # List all
    list_res = client.get("/api/v1/submissions", headers={"X-User-ID": str(u1.id)})
    assert list_res.status_code == 200
    list_body = list_res.json()
    assert list_body["total_count"] == 2
    assert len(list_body["items"]) == 2

    # Filter by status
    filter_res = client.get(
        "/api/v1/submissions?status=READY",
        headers={"X-User-ID": str(u1.id)},
    )
    assert filter_res.status_code == 200
    filter_body = filter_res.json()
    assert filter_body["total_count"] == 1
    assert filter_body["items"][0]["id"] == s1["id"]

    # Search filter
    search_res = client.get(
        "/api/v1/submissions?search=Two",
        headers={"X-User-ID": str(u1.id)},
    )
    assert search_res.status_code == 200
    search_body = search_res.json()
    assert search_body["total_count"] == 1
    assert search_body["items"][0]["id"] == s2["id"]

    # Summary
    summary_res = client.get("/api/v1/submissions/summary", headers={"X-User-ID": str(u1.id)})
    assert summary_res.status_code == 200
    summary_body = summary_res.json()
    assert summary_body["total_submissions"] == 2
    assert summary_body["active_submissions"] == 2
    assert summary_body["counts_by_status"]["READY"] == 1
    assert summary_body["counts_by_status"]["DRAFT"] == 1


def test_api_get_and_patch_submission(client: TestClient, sample_data: dict[str, Any]):
    u1 = sample_data["user1"]
    u2 = sample_data["user2"]
    ws1 = sample_data["ws1"]

    created = client.post(
        "/api/v1/submissions",
        json={"workspace_item_id": str(ws1.id), "title": "Original Paper Title"},
        headers={"X-User-ID": str(u1.id)},
    ).json()
    sub_id = created["id"]

    # GET single
    get_res = client.get(f"/api/v1/submissions/{sub_id}", headers={"X-User-ID": str(u1.id)})
    assert get_res.status_code == 200
    assert get_res.json()["title"] == "Original Paper Title"

    # PATCH metadata
    patch_res = client.patch(
        f"/api/v1/submissions/{sub_id}",
        json={
            "title": "Refined Paper Title",
            "abstract": "New experimental results added.",
            "venue": "NeurIPS Poster Track",
            "external_submission_id": "TRACK-456",
        },
        headers={"X-User-ID": str(u1.id)},
    )
    assert patch_res.status_code == 200
    patch_body = patch_res.json()
    assert patch_body["title"] == "Refined Paper Title"
    assert patch_body["abstract"] == "New experimental results added."
    assert patch_body["venue"] == "NeurIPS Poster Track"
    assert patch_body["external_submission_id"] == "TRACK-456"

    # Cross-researcher isolation
    cross_get = client.get(f"/api/v1/submissions/{sub_id}", headers={"X-User-ID": str(u2.id)})
    assert cross_get.status_code == 403

    cross_patch = client.patch(
        f"/api/v1/submissions/{sub_id}",
        json={"title": "Malicious Modification"},
        headers={"X-User-ID": str(u2.id)},
    )
    assert cross_patch.status_code == 403


def test_api_status_transition_lifecycle_and_promotion(client: TestClient, sample_data: dict[str, Any]):
    u1 = sample_data["user1"]
    u2 = sample_data["user2"]
    ws1 = sample_data["ws1"]

    sub = client.post(
        "/api/v1/submissions",
        json={"workspace_item_id": str(ws1.id), "title": "Lifecycle Paper"},
        headers={"X-User-ID": str(u1.id)},
    ).json()
    sub_id = sub["id"]

    # Invalid transition directly to SUBMITTED
    invalid_res = client.post(
        f"/api/v1/submissions/{sub_id}/transition",
        json={"target_status": "SUBMITTED"},
        headers={"X-User-ID": str(u1.id)},
    )
    assert invalid_res.status_code == 400
    assert "Invalid submission lifecycle transition" in invalid_res.json()["detail"]

    # Valid: DRAFT -> READY
    t1 = client.post(
        f"/api/v1/submissions/{sub_id}/transition",
        json={"target_status": "READY", "notes": "Ready for submission portal"},
        headers={"X-User-ID": str(u1.id)},
    )
    assert t1.status_code == 200
    assert t1.json()["status"] == "READY"

    # Valid: READY -> SUBMITTED (Promotes workspace to APPLIED)
    t2 = client.post(
        f"/api/v1/submissions/{sub_id}/transition",
        json={"target_status": "SUBMITTED", "notes": "Submitted via OpenReview"},
        headers={"X-User-ID": str(u1.id)},
    )
    assert t2.status_code == 200
    assert t2.json()["status"] == "SUBMITTED"
    assert t2.json()["submitted_at"] is not None
    assert t2.json()["workspace_status"] == "APPLIED"

    # Verify workspace item itself is promoted
    ws_res = client.get(f"/api/v1/workspace/{ws1.id}", headers={"X-User-ID": str(u1.id)})
    assert ws_res.status_code == 200
    assert ws_res.json()["status"] == "APPLIED"

    # Cross-researcher transition rejected
    cross_t = client.post(
        f"/api/v1/submissions/{sub_id}/transition",
        json={"target_status": "UNDER_REVIEW"},
        headers={"X-User-ID": str(u2.id)},
    )
    assert cross_t.status_code == 403


def test_api_deletion_lifecycle_constraints(client: TestClient, sample_data: dict[str, Any]):
    u1 = sample_data["user1"]
    u2 = sample_data["user2"]
    ws1 = sample_data["ws1"]

    sub = client.post(
        "/api/v1/submissions",
        json={"workspace_item_id": str(ws1.id), "title": "Delete Candidate"},
        headers={"X-User-ID": str(u1.id)},
    ).json()
    sub_id = sub["id"]

    # Cross-researcher delete rejected (403)
    cross_del = client.delete(f"/api/v1/submissions/{sub_id}", headers={"X-User-ID": str(u2.id)})
    assert cross_del.status_code == 403

    # Move to READY -> SUBMITTED
    client.post(
        f"/api/v1/submissions/{sub_id}/transition",
        json={"target_status": "READY"},
        headers={"X-User-ID": str(u1.id)},
    )
    client.post(
        f"/api/v1/submissions/{sub_id}/transition",
        json={"target_status": "SUBMITTED"},
        headers={"X-User-ID": str(u1.id)},
    )

    # Cannot delete active SUBMITTED submission (400 Bad Request)
    bad_del = client.delete(f"/api/v1/submissions/{sub_id}", headers={"X-User-ID": str(u1.id)})
    assert bad_del.status_code == 400

    # Withdraw submission -> Deletion permitted (204 No Content)
    client.post(
        f"/api/v1/submissions/{sub_id}/transition",
        json={"target_status": "WITHDRAWN"},
        headers={"X-User-ID": str(u1.id)},
    )
    good_del = client.delete(f"/api/v1/submissions/{sub_id}", headers={"X-User-ID": str(u1.id)})
    assert good_del.status_code == 204

    # Confirmed deleted (404)
    confirm_get = client.get(f"/api/v1/submissions/{sub_id}", headers={"X-User-ID": str(u1.id)})
    assert confirm_get.status_code == 404


def test_api_workspace_item_submissions_endpoint(client: TestClient, sample_data: dict[str, Any]):
    u1 = sample_data["user1"]
    u2 = sample_data["user2"]
    ws1 = sample_data["ws1"]

    client.post(
        "/api/v1/submissions",
        json={"workspace_item_id": str(ws1.id), "title": "Workspace Sub 1"},
        headers={"X-User-ID": str(u1.id)},
    )
    client.post(
        "/api/v1/submissions",
        json={"workspace_item_id": str(ws1.id), "title": "Workspace Sub 2"},
        headers={"X-User-ID": str(u1.id)},
    )

    # GET /api/v1/workspace/{item_id}/submissions
    ws_subs_res = client.get(
        f"/api/v1/workspace/{ws1.id}/submissions",
        headers={"X-User-ID": str(u1.id)},
    )
    assert ws_subs_res.status_code == 200
    subs_body = ws_subs_res.json()
    assert subs_body["total_count"] == 2
    assert len(subs_body["items"]) == 2

    # Cross-researcher access to workspace submissions rejected (403)
    cross_res = client.get(
        f"/api/v1/workspace/{ws1.id}/submissions",
        headers={"X-User-ID": str(u2.id)},
    )
    assert cross_res.status_code == 403
