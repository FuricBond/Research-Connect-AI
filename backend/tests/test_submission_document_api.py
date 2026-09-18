"""
Integration and API Tests for Phase 4.3 Research Submission Document & Readiness Management.

Endpoints tested:
  - POST   /api/v1/submissions/{id}/documents
  - GET    /api/v1/submissions/{id}/documents
  - GET    /api/v1/submissions/{id}/documents/{doc_id}
  - PATCH  /api/v1/submissions/{id}/documents/{doc_id}
  - DELETE /api/v1/submissions/{id}/documents/{doc_id}
  - GET    /api/v1/submissions/{id}/documents/{doc_id}/versions
  - GET    /api/v1/submissions/{id}/readiness
  - GET    /api/v1/submissions/{id}/history
  - Cross-researcher isolation (HTTP 403 Forbidden)
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
from app.models.opportunity import OpportunityModel
from app.models.research_profile import ResearchProfileModel
from app.models.research_submission import (
    ResearchSubmissionModel,
    SubmissionStatus,
    SubmissionType,
)
from app.models.saved_opportunity import SavedOpportunityModel, WorkspacePriority, WorkspaceStatus
from app.models.submission_document import (
    DocumentStatus,
    DocumentType,
    ResearchSubmissionDocumentModel,
    ResearchSubmissionDocumentVersionModel,
    ResearchSubmissionEventModel,
)
from app.models.user import UserModel
from app.services.research_submission_service import ResearchSubmissionService

# SQLite compatibility
compiles(JSONB, "sqlite")(lambda type_, compiler, **kw: "JSON")
compiles(Vector, "sqlite")(lambda type_, compiler, **kw: "TEXT")
compiles(TSVector, "sqlite")(lambda type_, compiler, **kw: "TEXT")


@pytest.fixture
def db_session() -> Session:
    """Provides a fresh in-memory SQLite session with all Phase 4.3 tables."""
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
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def test_users(db_session: Session) -> tuple[UserModel, UserModel]:
    """Creates two distinct researchers."""
    u1 = UserModel(
        id=uuid.uuid4(),
        email="author1@institution.edu",
        hashed_password="hash_author1",
        full_name="Dr. Author One",
        role="FACULTY",
    )
    u2 = UserModel(
        id=uuid.uuid4(),
        email="author2@institution.edu",
        hashed_password="hash_author2",
        full_name="Dr. Author Two",
        role="FACULTY",
    )
    db_session.add_all([u1, u2])
    db_session.flush()

    p1 = ResearchProfileModel(id=uuid.uuid4(), user_id=u1.id, academic_status="FACULTY")
    p2 = ResearchProfileModel(id=uuid.uuid4(), user_id=u2.id, academic_status="FACULTY")
    db_session.add_all([p1, p2])
    db_session.commit()
    return u1, u2


@pytest.fixture
def test_submission(
    db_session: Session,
    test_users: tuple[UserModel, UserModel],
) -> ResearchSubmissionModel:
    """Creates a sample opportunity and submission for researcher u1."""
    u1, _ = test_users
    opp = OpportunityModel(
        id=uuid.uuid4(),
        title="NeurIPS 2027",
        opportunity_type="CONFERENCE",
        submission_deadline=datetime(2027, 5, 20, 23, 59, 59, tzinfo=timezone.utc),
        organizer="NeurIPS",
    )
    db_session.add(opp)
    db_session.commit()

    ws_item = SavedOpportunityModel(
        id=uuid.uuid4(),
        user_id=u1.id,
        opportunity_id=opp.id,
        status=WorkspaceStatus.PLANNING.value,
        priority=WorkspacePriority.HIGH.value,
    )
    db_session.add(ws_item)
    db_session.commit()

    submission = ResearchSubmissionModel(
        id=uuid.uuid4(),
        workspace_item_id=ws_item.id,
        title="Scaling Transformers with Sparse Attention",
        abstract="Novel architecture for sub-quadratic sequence modeling.",
        submission_type=SubmissionType.FULL_PAPER.value,
        status=SubmissionStatus.DRAFT.value,
        venue="NeurIPS 2027",
    )
    db_session.add(submission)
    db_session.commit()
    return submission


# ── Document Endpoints Integration Tests ──────────────────────────────────────


def test_create_and_get_document_api(
    client: TestClient,
    test_users: tuple[UserModel, UserModel],
    test_submission: ResearchSubmissionModel,
):
    """POST /api/v1/submissions/{id}/documents & GET /{id}/documents/{doc_id}."""
    u1, _ = test_users
    headers = {"X-User-ID": str(u1.id)}

    create_resp = client.post(
        f"/api/v1/submissions/{test_submission.id}/documents",
        json={
            "document_type": "FULL_PAPER",
            "title": "Camera-ready Paper",
            "description": "Full 10 pages manuscript",
            "is_required": True,
            "status": "DRAFT",
            "file_metadata": {"filename": "main.pdf", "size_bytes": 500000},
            "storage_reference": "storage/neurips27/main.pdf",
        },
        headers=headers,
    )
    assert create_resp.status_code == 201
    data = create_resp.json()
    assert data["title"] == "Camera-ready Paper"
    assert data["document_type"] == "FULL_PAPER"
    assert data["is_required"] is True
    assert data["current_version"] == 1
    doc_id = data["id"]

    # Get single document
    get_resp = client.get(
        f"/api/v1/submissions/{test_submission.id}/documents/{doc_id}",
        headers=headers,
    )
    assert get_resp.status_code == 200
    get_data = get_resp.json()
    assert get_data["id"] == doc_id
    assert get_data["versions_count"] == 1


def test_list_documents_api(
    client: TestClient,
    test_users: tuple[UserModel, UserModel],
    test_submission: ResearchSubmissionModel,
):
    """GET /api/v1/submissions/{id}/documents with filtering."""
    u1, _ = test_users
    headers = {"X-User-ID": str(u1.id)}

    # Create 2 documents
    client.post(
        f"/api/v1/submissions/{test_submission.id}/documents",
        json={"document_type": "ABSTRACT", "title": "Abstract Text", "is_required": True, "status": "READY"},
        headers=headers,
    )
    client.post(
        f"/api/v1/submissions/{test_submission.id}/documents",
        json={"document_type": "CODE", "title": "PyTorch Implementation", "is_required": False, "status": "DRAFT"},
        headers=headers,
    )

    # List all
    resp = client.get(f"/api/v1/submissions/{test_submission.id}/documents", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_count"] == 2
    assert "counts_by_status" in data
    assert "counts_by_type" in data

    # Filter by required
    req_resp = client.get(f"/api/v1/submissions/{test_submission.id}/documents?is_required=true", headers=headers)
    assert req_resp.status_code == 200
    assert req_resp.json()["total_count"] == 1


def test_update_document_and_version_api(
    client: TestClient,
    test_users: tuple[UserModel, UserModel],
    test_submission: ResearchSubmissionModel,
):
    """PATCH /api/v1/submissions/{id}/documents/{doc_id} with create_new_version."""
    u1, _ = test_users
    headers = {"X-User-ID": str(u1.id)}

    # Create
    create_resp = client.post(
        f"/api/v1/submissions/{test_submission.id}/documents",
        json={"document_type": "FULL_PAPER", "title": "Draft v1", "status": "DRAFT"},
        headers=headers,
    )
    doc_id = create_resp.json()["id"]

    # Update with new version
    patch_resp = client.patch(
        f"/api/v1/submissions/{test_submission.id}/documents/{doc_id}",
        json={
            "title": "Draft v2 - Addressed Reviewers",
            "status": "READY",
            "create_new_version": True,
        },
        headers=headers,
    )
    assert patch_resp.status_code == 200
    updated = patch_resp.json()
    assert updated["current_version"] == 2
    assert updated["title"] == "Draft v2 - Addressed Reviewers"
    assert updated["status"] == "READY"
    assert updated["completed_at"] is not None

    # Get versions
    versions_resp = client.get(
        f"/api/v1/submissions/{test_submission.id}/documents/{doc_id}/versions",
        headers=headers,
    )
    assert versions_resp.status_code == 200
    versions = versions_resp.json()
    assert len(versions) == 2
    assert versions[0]["version_number"] == 2


def test_delete_document_api(
    client: TestClient,
    test_users: tuple[UserModel, UserModel],
    test_submission: ResearchSubmissionModel,
):
    """DELETE /api/v1/submissions/{id}/documents/{doc_id} returns 204."""
    u1, _ = test_users
    headers = {"X-User-ID": str(u1.id)}

    create_resp = client.post(
        f"/api/v1/submissions/{test_submission.id}/documents",
        json={"document_type": "OTHER", "title": "Temporary Notes", "status": "DRAFT"},
        headers=headers,
    )
    doc_id = create_resp.json()["id"]

    del_resp = client.delete(
        f"/api/v1/submissions/{test_submission.id}/documents/{doc_id}",
        headers=headers,
    )
    assert del_resp.status_code == 204

    # Verify 404
    get_resp = client.get(
        f"/api/v1/submissions/{test_submission.id}/documents/{doc_id}",
        headers=headers,
    )
    assert get_resp.status_code == 404


# ── Readiness & History Endpoints ─────────────────────────────────────────────


def test_evaluate_readiness_api(
    client: TestClient,
    test_users: tuple[UserModel, UserModel],
    test_submission: ResearchSubmissionModel,
):
    """GET /api/v1/submissions/{id}/readiness returns readiness assessment."""
    u1, _ = test_users
    headers = {"X-User-ID": str(u1.id)}

    resp = client.get(f"/api/v1/submissions/{test_submission.id}/readiness", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "overall_readiness" in data
    assert "can_mark_submission_ready" in data
    assert "readiness_percentage" in data
    assert "blocking_issues" in data
    assert "warnings" in data
    assert "metadata_completeness" in data


def test_get_submission_history_api(
    client: TestClient,
    test_users: tuple[UserModel, UserModel],
    test_submission: ResearchSubmissionModel,
):
    """GET /api/v1/submissions/{id}/history returns audit trail events."""
    u1, _ = test_users
    headers = {"X-User-ID": str(u1.id)}

    # Add a document to generate an audit event
    client.post(
        f"/api/v1/submissions/{test_submission.id}/documents",
        json={"document_type": "FIGURES", "title": "Figure 1", "status": "DRAFT"},
        headers=headers,
    )

    resp = client.get(f"/api/v1/submissions/{test_submission.id}/history", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_count"] >= 1
    assert len(data["items"]) >= 1
    assert data["items"][0]["event_type"] in ["DOCUMENT_ADDED", "SUBMISSION_CREATED"]


# ── Cross-Researcher Isolation Tests ──────────────────────────────────────────


def test_cross_researcher_api_forbidden(
    client: TestClient,
    test_users: tuple[UserModel, UserModel],
    test_submission: ResearchSubmissionModel,
):
    """Verifies that researcher B receives HTTP 403 when trying to access researcher A's endpoints."""
    _, u2 = test_users
    headers_u2 = {"X-User-ID": str(u2.id)}

    # Try to create doc
    resp1 = client.post(
        f"/api/v1/submissions/{test_submission.id}/documents",
        json={"document_type": "OTHER", "title": "Unauthorized Doc"},
        headers=headers_u2,
    )
    assert resp1.status_code == 403

    # Try to list docs
    resp2 = client.get(f"/api/v1/submissions/{test_submission.id}/documents", headers=headers_u2)
    assert resp2.status_code == 403

    # Try to get readiness
    resp3 = client.get(f"/api/v1/submissions/{test_submission.id}/readiness", headers=headers_u2)
    assert resp3.status_code == 403

    # Try to get history
    resp4 = client.get(f"/api/v1/submissions/{test_submission.id}/history", headers=headers_u2)
    assert resp4.status_code == 403
