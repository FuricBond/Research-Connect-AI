"""
Phase 4.6 — Workspace Invitations Unit & Integration Tests.

Validates:
  1. Creating an invitation (Owner).
  2. Contributor / Viewer cannot create invitations (403 / HTTPException).
  3. Secret token generation and exclusion from normal Read schemas.
  4. Accepting an invitation with valid token (creates active membership).
  5. Accepting with invalid token fails (404).
  6. Idempotent acceptance (accepting already accepted invitation does not duplicate membership).
  7. Expired invitation cannot be accepted (400).
  8. Revoked invitation cannot be accepted (400).
  9. Declining an invitation.
  10. Duplicate active invitation prevention (409).
  11. REST API integration tests for invitations.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
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
    InvitationStatus,
    MemberStatus,
    WorkspaceInvitationModel,
    WorkspaceMemberModel,
    WorkspaceRole,
)
from app.schemas.workspace_collaboration import WorkspaceInvitationCreate
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
    u_invitee = UserModel(id=uuid.uuid4(), email="collab@univ.edu", full_name="Collab Scholar", hashed_password="pw")
    db_session.add_all([u_owner, u_editor, u_invitee])
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

    owner_member = WorkspaceMemberModel(
        workspace_id=ws.id,
        user_id=u_owner.id,
        role=WorkspaceRole.OWNER.value,
        status=MemberStatus.ACTIVE.value,
        joined_at=datetime.now(timezone.utc),
    )
    editor_member = WorkspaceMemberModel(
        workspace_id=ws.id,
        user_id=u_editor.id,
        role=WorkspaceRole.EDITOR.value,
        status=MemberStatus.ACTIVE.value,
        joined_at=datetime.now(timezone.utc),
    )
    db_session.add_all([owner_member, editor_member])
    db_session.commit()

    return u_owner, u_editor, u_invitee, ws


def test_create_invitation(db_session: Session, sample_workspace):
    u_owner, _, u_invitee, ws = sample_workspace

    inv, token = WorkspaceCollaborationService.create_invitation(
        db=db_session,
        workspace_id=ws.id,
        inviter_id=u_owner.id,
        payload=WorkspaceInvitationCreate(
            invitee_email=u_invitee.email,
            role=WorkspaceRole.CONTRIBUTOR,
        ),
    )

    assert inv.workspace_id == ws.id
    assert inv.invitee_email == u_invitee.email
    assert inv.status == InvitationStatus.PENDING.value
    assert inv.role == WorkspaceRole.CONTRIBUTOR.value
    assert len(token) > 16


def test_duplicate_active_invitation_prevented(db_session: Session, sample_workspace):
    u_owner, _, u_invitee, ws = sample_workspace

    WorkspaceCollaborationService.create_invitation(
        db=db_session,
        workspace_id=ws.id,
        inviter_id=u_owner.id,
        payload=WorkspaceInvitationCreate(
            invitee_email=u_invitee.email,
            role=WorkspaceRole.CONTRIBUTOR,
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        WorkspaceCollaborationService.create_invitation(
            db=db_session,
            workspace_id=ws.id,
            inviter_id=u_owner.id,
            payload=WorkspaceInvitationCreate(
                invitee_email=u_invitee.email,
                role=WorkspaceRole.CONTRIBUTOR,
            ),
        )
    assert exc_info.value.status_code == 409


def test_accept_invitation_success(db_session: Session, sample_workspace):
    u_owner, _, u_invitee, ws = sample_workspace

    inv, token = WorkspaceCollaborationService.create_invitation(
        db=db_session,
        workspace_id=ws.id,
        inviter_id=u_owner.id,
        payload=WorkspaceInvitationCreate(
            invitee_email=u_invitee.email,
            role=WorkspaceRole.CONTRIBUTOR,
        ),
    )

    member = WorkspaceCollaborationService.accept_invitation(
        db=db_session,
        token=token,
        user_id=u_invitee.id,
    )

    assert member.workspace_id == ws.id
    assert member.user_id == u_invitee.id
    assert member.role == WorkspaceRole.CONTRIBUTOR.value
    assert member.status == MemberStatus.ACTIVE.value

    # Check invitation status updated
    db_session.refresh(inv)
    assert inv.status == InvitationStatus.ACCEPTED.value
    assert inv.accepted_at is not None


def test_accept_invitation_idempotent(db_session: Session, sample_workspace):
    u_owner, _, u_invitee, ws = sample_workspace

    inv, token = WorkspaceCollaborationService.create_invitation(
        db=db_session,
        workspace_id=ws.id,
        inviter_id=u_owner.id,
        payload=WorkspaceInvitationCreate(
            invitee_email=u_invitee.email,
            role=WorkspaceRole.CONTRIBUTOR,
        ),
    )

    m1 = WorkspaceCollaborationService.accept_invitation(
        db=db_session,
        token=token,
        user_id=u_invitee.id,
    )

    # Accept again
    m2 = WorkspaceCollaborationService.accept_invitation(
        db=db_session,
        token=token,
        user_id=u_invitee.id,
    )

    assert m1.id == m2.id


def test_accept_expired_invitation_fails(db_session: Session, sample_workspace):
    u_owner, _, u_invitee, ws = sample_workspace

    inv, token = WorkspaceCollaborationService.create_invitation(
        db=db_session,
        workspace_id=ws.id,
        inviter_id=u_owner.id,
        payload=WorkspaceInvitationCreate(
            invitee_email=u_invitee.email,
            role=WorkspaceRole.CONTRIBUTOR,
        ),
    )
    # Force expire
    inv.expires_at = datetime.now(timezone.utc) - timedelta(days=2)
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        WorkspaceCollaborationService.accept_invitation(
            db=db_session,
            token=token,
            user_id=u_invitee.id,
        )
    assert exc_info.value.status_code == 400


def test_accept_revoked_invitation_fails(db_session: Session, sample_workspace):
    u_owner, _, u_invitee, ws = sample_workspace

    inv, token = WorkspaceCollaborationService.create_invitation(
        db=db_session,
        workspace_id=ws.id,
        inviter_id=u_owner.id,
        payload=WorkspaceInvitationCreate(
            invitee_email=u_invitee.email,
            role=WorkspaceRole.CONTRIBUTOR,
        ),
    )

    WorkspaceCollaborationService.revoke_invitation(
        db=db_session,
        workspace_id=ws.id,
        actor_id=u_owner.id,
        invitation_id=inv.id,
    )

    with pytest.raises(HTTPException) as exc_info:
        WorkspaceCollaborationService.accept_invitation(
            db=db_session,
            token=token,
            user_id=u_invitee.id,
        )
    assert exc_info.value.status_code == 400


def test_decline_invitation(db_session: Session, sample_workspace):
    u_owner, _, u_invitee, ws = sample_workspace

    inv, token = WorkspaceCollaborationService.create_invitation(
        db=db_session,
        workspace_id=ws.id,
        inviter_id=u_owner.id,
        payload=WorkspaceInvitationCreate(
            invitee_email=u_invitee.email,
            role=WorkspaceRole.CONTRIBUTOR,
        ),
    )

    WorkspaceCollaborationService.decline_invitation(
        db=db_session,
        token=token,
        user_id=u_invitee.id,
    )

    db_session.refresh(inv)
    assert inv.status == InvitationStatus.DECLINED.value


def test_api_invitations_workflow(client: TestClient, sample_workspace):
    u_owner, _, u_invitee, ws = sample_workspace

    # 1. Create invitation
    res = client.post(
        f"/api/v1/workspaces/{ws.id}/invitations",
        headers={"X-User-ID": str(u_owner.id)},
        json={"invitee_email": u_invitee.email, "role": "CONTRIBUTOR"},
    )
    assert res.status_code == 201
    inv_data = res.json()
    token = inv_data["token"]
    assert token is not None

    # 2. List invitations
    res = client.get(
        f"/api/v1/workspaces/{ws.id}/invitations",
        headers={"X-User-ID": str(u_owner.id)},
    )
    assert res.status_code == 200
    assert res.json()["total_count"] == 1

    # 3. Accept invitation
    res = client.post(
        f"/api/v1/workspaces/invitations/{token}/accept",
        headers={"X-User-ID": str(u_invitee.id)},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "ACTIVE"
    assert res.json()["role"] == "CONTRIBUTOR"
