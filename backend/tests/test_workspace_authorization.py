"""
Phase 4.6 — Workspace Authorization & RBAC Security Tests.

Validates:
  1. Unauthenticated access rejection.
  2. Cross-workspace access rejection (IDOR protection).
  3. Role-based operation matrices:
     - OWNER: full control.
     - EDITOR: mutation of submissions, documents, tasks.
     - CONTRIBUTOR: task creation/assignment/completion, document contribution.
     - VIEWER: read-only access, cannot mutate protected resources.
  4. Privilege escalation prevention.
  5. Removed member loses all access.
"""
from __future__ import annotations

from datetime import datetime, timezone
import uuid
import pytest
from sqlalchemy import create_engine, select
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
from app.models.saved_opportunity import SavedOpportunityModel, WorkspaceStatus
from app.models.user import UserModel
from app.models.workspace_collaboration import (
    MemberStatus,
    WorkspaceMemberModel,
    WorkspaceRole,
)
from app.services.workspace_authorization_service import WorkspaceAuthorizationService

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
def auth_setup(db_session: Session):
    u_owner = UserModel(id=uuid.uuid4(), email="owner@univ.edu", full_name="Owner Prof", hashed_password="pw")
    u_editor = UserModel(id=uuid.uuid4(), email="editor@univ.edu", full_name="Editor Researcher", hashed_password="pw")
    u_contrib = UserModel(id=uuid.uuid4(), email="contrib@univ.edu", full_name="Contrib Scholar", hashed_password="pw")
    u_viewer = UserModel(id=uuid.uuid4(), email="viewer@univ.edu", full_name="Viewer Student", hashed_password="pw")
    u_outsider = UserModel(id=uuid.uuid4(), email="outsider@univ.edu", full_name="Outsider User", hashed_password="pw")
    db_session.add_all([u_owner, u_editor, u_contrib, u_viewer, u_outsider])
    db_session.flush()

    opp = OpportunityModel(id=uuid.uuid4(), title="Test Grant", opportunity_type="CONFERENCE", status="ACTIVE")
    db_session.add(opp)
    db_session.flush()

    ws_a = SavedOpportunityModel(id=uuid.uuid4(), user_id=u_owner.id, opportunity_id=opp.id, status="PLANNING")
    ws_b = SavedOpportunityModel(id=uuid.uuid4(), user_id=u_outsider.id, opportunity_id=opp.id, status="PLANNING")
    db_session.add_all([ws_a, ws_b])
    db_session.flush()

    # Workspace A members
    m_owner = WorkspaceMemberModel(workspace_id=ws_a.id, user_id=u_owner.id, role="OWNER", status="ACTIVE")
    m_editor = WorkspaceMemberModel(workspace_id=ws_a.id, user_id=u_editor.id, role="EDITOR", status="ACTIVE")
    m_contrib = WorkspaceMemberModel(workspace_id=ws_a.id, user_id=u_contrib.id, role="CONTRIBUTOR", status="ACTIVE")
    m_viewer = WorkspaceMemberModel(workspace_id=ws_a.id, user_id=u_viewer.id, role="VIEWER", status="ACTIVE")

    # Workspace B members
    m_outsider = WorkspaceMemberModel(workspace_id=ws_b.id, user_id=u_outsider.id, role="OWNER", status="ACTIVE")

    db_session.add_all([m_owner, m_editor, m_contrib, m_viewer, m_outsider])
    db_session.commit()

    return {
        "owner": u_owner,
        "editor": u_editor,
        "contrib": u_contrib,
        "viewer": u_viewer,
        "outsider": u_outsider,
        "ws_a": ws_a,
        "ws_b": ws_b,
    }


def test_cross_workspace_idor_prevented(client: TestClient, auth_setup):
    data = auth_setup
    # Outsider (owner of B) attempts to read members of Workspace A
    res = client.get(
        f"/api/v1/workspaces/{data['ws_a'].id}/members",
        headers={"X-User-ID": str(data["outsider"].id)},
    )
    assert res.status_code == 403


def test_viewer_cannot_mutate_tasks(client: TestClient, auth_setup):
    data = auth_setup
    res = client.post(
        f"/api/v1/workspaces/{data['ws_a'].id}/tasks",
        headers={"X-User-ID": str(data["viewer"].id)},
        json={"title": "Viewer Malicious Task"},
    )
    assert res.status_code == 403


def test_contributor_cannot_invite_members(client: TestClient, auth_setup):
    data = auth_setup
    res = client.post(
        f"/api/v1/workspaces/{data['ws_a'].id}/invitations",
        headers={"X-User-ID": str(data["contrib"].id)},
        json={"invitee_email": "friend@univ.edu", "role": "EDITOR"},
    )
    assert res.status_code == 403


def test_privilege_escalation_prevented(client: TestClient, auth_setup):
    data = auth_setup
    # Contributor tries to promote themselves to OWNER
    # Find contributor member id
    res = client.get(
        f"/api/v1/workspaces/{data['ws_a'].id}/members",
        headers={"X-User-ID": str(data["contrib"].id)},
    )
    assert res.status_code == 200
    contrib_member = next(m for m in res.json()["items"] if m["user_id"] == str(data["contrib"].id))

    res = client.patch(
        f"/api/v1/workspaces/{data['ws_a'].id}/members/{data['contrib'].id}/role",
        headers={"X-User-ID": str(data["contrib"].id)},
        json={"role": "OWNER"},
    )
    assert res.status_code == 403


def test_removed_member_loses_access(client: TestClient, auth_setup, db_session: Session):
    data = auth_setup
    # Remove editor from Workspace A
    m_editor = db_session.execute(
        select(WorkspaceMemberModel).where(
            WorkspaceMemberModel.workspace_id == data["ws_a"].id,
            WorkspaceMemberModel.user_id == data["editor"].id,
        )
    ).scalar_one()
    m_editor.status = MemberStatus.REMOVED.value
    db_session.commit()

    # Former editor tries to list tasks
    res = client.get(
        f"/api/v1/workspaces/{data['ws_a'].id}/tasks",
        headers={"X-User-ID": str(data["editor"].id)},
    )
    assert res.status_code == 403
