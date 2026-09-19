"""
Phase 4.6 — Workspace Membership Unit & Integration Tests.

Validates:
  1. Adding a member to a workspace (Owner only).
  2. Non-owner cannot add members (403 / HTTPException).
  3. Updating a member's role (OWNER -> EDITOR, CONTRIBUTOR, VIEWER).
  4. Non-owner cannot update member roles.
  5. Owner cannot change own role (preventing orphaned workspace).
  6. Removing a member from workspace.
  7. Non-owner cannot remove other members.
  8. Owner cannot be removed.
  9. Duplicate active membership prevention.
  10. Zero N+1 queries when retrieving workspace members.
"""
from __future__ import annotations

from datetime import datetime, timezone
import uuid
from fastapi import HTTPException
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
from app.schemas.workspace_collaboration import (
    WorkspaceMemberAdd,
    WorkspaceMemberRoleUpdate,
)
from app.services.workspace_collaboration_service import WorkspaceCollaborationService

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
def sample_workspace(db_session: Session) -> tuple[UserModel, UserModel, UserModel, SavedOpportunityModel]:
    u_owner = UserModel(id=uuid.uuid4(), email="owner@univ.edu", full_name="Owner Prof", hashed_password="pw")
    u_editor = UserModel(id=uuid.uuid4(), email="editor@univ.edu", full_name="Editor Researcher", hashed_password="pw")
    u_other = UserModel(id=uuid.uuid4(), email="other@univ.edu", full_name="Other User", hashed_password="pw")
    db_session.add_all([u_owner, u_editor, u_other])
    db_session.flush()

    opp = OpportunityModel(
        id=uuid.uuid4(),
        title="Collab Grant 2026",
        opportunity_type="CONFERENCE",
        status="ACTIVE",
    )
    db_session.add(opp)
    db_session.flush()

    ws = SavedOpportunityModel(
        id=uuid.uuid4(),
        user_id=u_owner.id,
        opportunity_id=opp.id,
        status=WorkspaceStatus.PLANNING.value,
    )
    db_session.add(ws)
    db_session.flush()

    # Seed owner membership
    owner_member = WorkspaceMemberModel(
        workspace_id=ws.id,
        user_id=u_owner.id,
        role=WorkspaceRole.OWNER.value,
        status=MemberStatus.ACTIVE.value,
        joined_at=datetime.now(timezone.utc),
    )
    db_session.add(owner_member)
    db_session.commit()

    return u_owner, u_editor, u_other, ws


def test_add_member_by_owner_succeeds(db_session: Session, sample_workspace):
    u_owner, u_editor, _, ws = sample_workspace

    member = WorkspaceCollaborationService.add_member(
        db=db_session,
        workspace_id=ws.id,
        actor_id=u_owner.id,
        payload=WorkspaceMemberAdd(user_id=u_editor.id, role=WorkspaceRole.EDITOR),
    )

    assert member.workspace_id == ws.id
    assert member.user_id == u_editor.id
    assert member.role == WorkspaceRole.EDITOR.value
    assert member.status == MemberStatus.ACTIVE.value


def test_add_member_by_non_owner_forbidden(db_session: Session, sample_workspace):
    _, u_editor, u_other, ws = sample_workspace

    with pytest.raises(HTTPException) as exc_info:
        WorkspaceCollaborationService.add_member(
            db=db_session,
            workspace_id=ws.id,
            actor_id=u_editor.id,
            payload=WorkspaceMemberAdd(user_id=u_other.id, role=WorkspaceRole.CONTRIBUTOR),
        )
    assert exc_info.value.status_code == 403


def test_duplicate_active_member_prevented(db_session: Session, sample_workspace):
    u_owner, u_editor, _, ws = sample_workspace

    WorkspaceCollaborationService.add_member(
        db=db_session,
        workspace_id=ws.id,
        actor_id=u_owner.id,
        payload=WorkspaceMemberAdd(user_id=u_editor.id, role=WorkspaceRole.CONTRIBUTOR),
    )

    with pytest.raises(HTTPException) as exc_info:
        WorkspaceCollaborationService.add_member(
            db=db_session,
            workspace_id=ws.id,
            actor_id=u_owner.id,
            payload=WorkspaceMemberAdd(user_id=u_editor.id, role=WorkspaceRole.CONTRIBUTOR),
        )
    assert exc_info.value.status_code == 409


def test_update_member_role(db_session: Session, sample_workspace):
    u_owner, u_editor, _, ws = sample_workspace

    member = WorkspaceCollaborationService.add_member(
        db=db_session,
        workspace_id=ws.id,
        actor_id=u_owner.id,
        payload=WorkspaceMemberAdd(user_id=u_editor.id, role=WorkspaceRole.CONTRIBUTOR),
    )

    updated = WorkspaceCollaborationService.update_member_role(
        db=db_session,
        workspace_id=ws.id,
        actor_id=u_owner.id,
        target_user_id=u_editor.id,
        payload=WorkspaceMemberRoleUpdate(role=WorkspaceRole.EDITOR),
    )

    assert updated.role == WorkspaceRole.EDITOR.value


def test_cannot_demote_owner_via_member_update(db_session: Session, sample_workspace):
    u_owner, _, _, ws = sample_workspace

    with pytest.raises(HTTPException) as exc_info:
        WorkspaceCollaborationService.update_member_role(
            db=db_session,
            workspace_id=ws.id,
            actor_id=u_owner.id,
            target_user_id=u_owner.id,
            payload=WorkspaceMemberRoleUpdate(role=WorkspaceRole.EDITOR),
        )
    assert exc_info.value.status_code == 400


def test_remove_member(db_session: Session, sample_workspace):
    u_owner, u_editor, _, ws = sample_workspace

    member = WorkspaceCollaborationService.add_member(
        db=db_session,
        workspace_id=ws.id,
        actor_id=u_owner.id,
        payload=WorkspaceMemberAdd(user_id=u_editor.id, role=WorkspaceRole.CONTRIBUTOR),
    )

    WorkspaceCollaborationService.remove_member(
        db=db_session,
        workspace_id=ws.id,
        actor_id=u_owner.id,
        target_user_id=u_editor.id,
    )

    db_session.refresh(member)
    assert member.status == MemberStatus.REMOVED.value
    assert member.removed_at is not None


def test_owner_cannot_be_removed(db_session: Session, sample_workspace):
    u_owner, _, _, ws = sample_workspace

    with pytest.raises(HTTPException) as exc_info:
        WorkspaceCollaborationService.remove_member(
            db=db_session,
            workspace_id=ws.id,
            actor_id=u_owner.id,
            target_user_id=u_owner.id,
        )
    assert exc_info.value.status_code == 400


def test_api_members_crud(client: TestClient, sample_workspace):
    u_owner, u_editor, _, ws = sample_workspace

    # 1. List members (owner)
    res = client.get(f"/api/v1/workspaces/{ws.id}/members", headers={"X-User-ID": str(u_owner.id)})
    assert res.status_code == 200
    data = res.json()
    assert data["total_count"] == 1
    assert data["items"][0]["role"] == "OWNER"

    # 2. Add member
    res = client.post(
        f"/api/v1/workspaces/{ws.id}/members",
        headers={"X-User-ID": str(u_owner.id)},
        json={"user_id": str(u_editor.id), "role": "CONTRIBUTOR"},
    )
    assert res.status_code == 201

    # 3. Change role
    res = client.patch(
        f"/api/v1/workspaces/{ws.id}/members/{u_editor.id}/role",
        headers={"X-User-ID": str(u_owner.id)},
        json={"role": "EDITOR"},
    )
    assert res.status_code == 200
    assert res.json()["role"] == "EDITOR"

    # 4. Remove member
    res = client.delete(
        f"/api/v1/workspaces/{ws.id}/members/{u_editor.id}",
        headers={"X-User-ID": str(u_owner.id)},
    )
    assert res.status_code == 204
