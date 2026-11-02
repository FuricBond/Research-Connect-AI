"""
Audit FUNC-01 and SEC-05 — an invitee answers an invitation from their own account.

The notifications page lists what the signed-in account was invited to; accepting or declining
needs no token. Every refusal says why, the invitation belongs to one account only, and the
database holds only a hash of the token, which never appears in a list or a log.

Accounts here have confirmed their addresses: what happens without that is Decision C,
test_invitation_email_ownership.py. The API no longer hands out tokens, so a test that needs one
asks the service, as if it had been handed out before that.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import logging
import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from app.core.middleware import RedactInvitationTokens, redact_invitation_token
from app.db.session import get_db
from app.db.types import TSVector, Vector
from app.main import app
from app.models.base import Base
from app.models.notification import NotificationModel
from app.models.opportunity import OpportunityModel
from app.models.research_profile import ResearchProfileModel
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
from app.services.reminder_scheduler_service import MockEmailProvider, get_email_provider, set_email_provider
from app.services.workspace_collaboration_service import WorkspaceCollaborationService

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
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_session: Session) -> TestClient:
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _account(db: Session, email: str, name: str) -> UserModel:
    user = UserModel(
        id=uuid.uuid4(),
        email=email,
        full_name=name,
        hashed_password="pw",
        is_active=True,
        email_verified_address=email.lower(),
    )
    db.add(user)
    db.flush()
    db.add(ResearchProfileModel(id=uuid.uuid4(), user_id=user.id, academic_status="POSTGRADUATE"))
    db.commit()
    return user


@pytest.fixture
def people(db_session: Session):
    owner = _account(db_session, "owner@univ.edu", "Olu Owner")
    invitee = _account(db_session, "invitee@univ.edu", "Ines Invitee")
    other = _account(db_session, "other@univ.edu", "Otto Other")
    call = OpportunityModel(id=uuid.uuid4(), title="Causal ML Workshop", opportunity_type="CONFERENCE", status="ACTIVE")
    db_session.add(call)
    db_session.flush()
    workspace = SavedOpportunityModel(
        id=uuid.uuid4(), user_id=owner.id, opportunity_id=call.id, status=WorkspaceStatus.PLANNING.value
    )
    db_session.add(workspace)
    db_session.flush()
    db_session.add(
        WorkspaceMemberModel(
            workspace_id=workspace.id,
            user_id=owner.id,
            role=WorkspaceRole.OWNER.value,
            status=MemberStatus.ACTIVE.value,
            joined_at=datetime.now(timezone.utc),
        )
    )
    db_session.commit()
    return owner, invitee, other, workspace


def _h(user: UserModel) -> dict[str, str]:
    return {"X-User-ID": str(user.id)}


def _invite(client: TestClient, owner: UserModel, workspace, email: str = "invitee@univ.edu", role: str = "EDITOR") -> dict:
    res = client.post(f"/api/v1/workspaces/{workspace.id}/invitations", headers=_h(owner), json={"invitee_email": email, "role": role})
    assert res.status_code == 201, res.text
    return res.json()


def _with_token(db: Session, owner: UserModel, workspace, email: str = "invitee@univ.edu") -> tuple[WorkspaceInvitationModel, str]:
    return WorkspaceCollaborationService.create_invitation(
        db, workspace.id, owner.id, WorkspaceInvitationCreate(invitee_email=email, role=WorkspaceRole.EDITOR)
    )


def test_the_invitee_sees_accepts_and_joins_with_the_invited_role(client: TestClient, db_session: Session, people):
    owner, invitee, _, workspace = people
    invitation = _invite(client, owner, workspace)["invitation"]

    mine = client.get("/api/v1/workspace-invitations/mine", headers=_h(invitee))
    assert mine.status_code == 200
    listed = mine.json()["invitations"]
    assert [i["id"] for i in listed] == [invitation["id"]]
    assert listed[0]["workspace_title"] == "Causal ML Workshop"
    assert listed[0]["inviter_name"] == "Olu Owner"
    assert listed[0]["role"] == "EDITOR"
    assert "token" not in listed[0] and "token_hash" not in listed[0]

    accepted = client.post(f"/api/v1/workspace-invitations/{invitation['id']}/accept", headers=_h(invitee))
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["role"] == "EDITOR"

    members = client.get(f"/api/v1/workspaces/{workspace.id}/members", headers=_h(owner)).json()["items"]
    assert {m["user_id"]: m["role"] for m in members}[str(invitee.id)] == "EDITOR"

    after = client.get("/api/v1/workspace-invitations/mine", headers=_h(invitee)).json()
    assert after["invitations"] == []
    assert [(s["workspace_id"], s["workspace_title"], s["owner_name"], s["role"]) for s in after["shared_workspaces"]] == [
        (str(workspace.id), "Causal ML Workshop", "Olu Owner", "EDITOR")
    ]
    assert client.get(f"/api/v1/workspace/{workspace.id}", headers=_h(invitee)).status_code == 200


def test_the_notification_says_what_can_be_done_and_carries_no_token(client: TestClient, db_session: Session, people):
    owner, invitee, _, workspace = people
    _row, token = _with_token(db_session, owner, workspace)
    profile = db_session.execute(select(ResearchProfileModel).where(ResearchProfileModel.user_id == invitee.id)).scalar_one()
    note = db_session.execute(select(NotificationModel).where(NotificationModel.profile_id == profile.id)).scalar_one()
    assert note.notification_type == "WORKSPACE_INVITATION"
    assert "Accept or decline" in note.body
    assert "Olu Owner" in note.body and "Causal ML Workshop" in note.body
    assert token not in note.body and token not in str(note.metadata_json)


def test_nobody_can_answer_someone_elses_invitation(client: TestClient, db_session: Session, people):
    owner, invitee, other, workspace = people
    row, token = _with_token(db_session, owner, workspace)
    invitation_id = str(row.id)

    assert client.get("/api/v1/workspace-invitations/mine", headers=_h(other)).json()["invitations"] == []
    # The owner who sent it, and a stranger, hear what an id that does not exist hears.
    for actor in (owner, other):
        for action in ("accept", "decline"):
            res = client.post(f"/api/v1/workspace-invitations/{invitation_id}/{action}", headers=_h(actor))
            assert res.status_code == 404, res.text
    unknown = client.post(f"/api/v1/workspace-invitations/{uuid.uuid4()}/accept", headers=_h(other))
    assert unknown.status_code == 404
    # Holding the token is not enough either.
    for action in ("accept", "decline"):
        res = client.post(f"/api/v1/workspaces/invitations/{token}/{action}", headers=_h(other))
        assert res.status_code == 403, res.text
        assert "invitee@univ.edu" not in res.text

    row = db_session.get(WorkspaceInvitationModel, uuid.UUID(invitation_id))
    assert row.status == InvitationStatus.PENDING.value
    assert client.post(f"/api/v1/workspace-invitations/{invitation_id}/accept", headers=_h(invitee)).status_code == 200


def test_signed_out_is_refused(client: TestClient, people):
    owner, _, _, workspace = people
    invitation_id = _invite(client, owner, workspace)["invitation"]["id"]
    assert client.get("/api/v1/workspace-invitations/mine").status_code == 401
    assert client.post(f"/api/v1/workspace-invitations/{invitation_id}/accept").status_code == 401
    assert client.post(f"/api/v1/workspace-invitations/{invitation_id}/decline").status_code == 401


def test_declining_ends_the_invitation_and_grants_nothing(client: TestClient, db_session: Session, people):
    owner, invitee, _, workspace = people
    invitation_id = _invite(client, owner, workspace)["invitation"]["id"]

    declined = client.post(f"/api/v1/workspace-invitations/{invitation_id}/decline", headers=_h(invitee))
    assert declined.status_code == 204
    assert client.get(f"/api/v1/workspace/{workspace.id}", headers=_h(invitee)).status_code == 403
    assert client.get("/api/v1/workspace-invitations/mine", headers=_h(invitee)).json()["invitations"] == []

    again = client.post(f"/api/v1/workspace-invitations/{invitation_id}/accept", headers=_h(invitee))
    assert again.status_code == 400
    assert "already been declined" in again.json()["detail"]


def test_an_expired_invitation_cannot_be_answered_and_is_not_listed(client: TestClient, db_session: Session, people):
    owner, invitee, _, workspace = people
    invitation_id = _invite(client, owner, workspace)["invitation"]["id"]
    row = db_session.get(WorkspaceInvitationModel, uuid.UUID(invitation_id))
    row.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    db_session.commit()

    assert client.get("/api/v1/workspace-invitations/mine", headers=_h(invitee)).json()["invitations"] == []
    res = client.post(f"/api/v1/workspace-invitations/{invitation_id}/accept", headers=_h(invitee))
    assert res.status_code == 400
    assert "expired" in res.json()["detail"]
    db_session.refresh(row)
    assert row.status == InvitationStatus.EXPIRED.value
    assert client.post(f"/api/v1/workspace-invitations/{invitation_id}/decline", headers=_h(invitee)).status_code == 400


@pytest.mark.parametrize("first, second, word", [
    ("accept", "accept", "already been accepted"),
    ("accept", "decline", "already been accepted"),
    ("decline", "decline", "already been declined"),
])
def test_an_invitation_is_answered_once(client: TestClient, people, first, second, word):
    owner, invitee, _, workspace = people
    invitation_id = _invite(client, owner, workspace)["invitation"]["id"]
    assert client.post(f"/api/v1/workspace-invitations/{invitation_id}/{first}", headers=_h(invitee)).status_code < 300
    res = client.post(f"/api/v1/workspace-invitations/{invitation_id}/{second}", headers=_h(invitee))
    assert res.status_code == 400
    assert word in res.json()["detail"]


def test_a_removed_member_cannot_come_back_on_an_old_invitation(client: TestClient, db_session: Session, people):
    owner, invitee, _, workspace = people
    row, token = _with_token(db_session, owner, workspace)
    invitation_id = str(row.id)
    assert client.post(f"/api/v1/workspace-invitations/{invitation_id}/accept", headers=_h(invitee)).status_code == 200
    assert client.delete(f"/api/v1/workspaces/{workspace.id}/members/{invitee.id}", headers=_h(owner)).status_code == 204

    assert client.post(f"/api/v1/workspace-invitations/{invitation_id}/accept", headers=_h(invitee)).status_code == 400
    assert client.post(f"/api/v1/workspaces/invitations/{token}/accept", headers=_h(invitee)).status_code == 400
    assert client.get(f"/api/v1/workspace/{workspace.id}", headers=_h(invitee)).status_code == 403


def test_a_revoked_invitation_cannot_be_answered_or_revoked_again(client: TestClient, db_session: Session, people):
    owner, invitee, _, workspace = people
    row, token = _with_token(db_session, owner, workspace)
    invitation_id = str(row.id)
    revoke = f"/api/v1/workspaces/{workspace.id}/invitations/{invitation_id}"
    assert client.delete(revoke, headers=_h(owner)).status_code == 204

    assert client.get("/api/v1/workspace-invitations/mine", headers=_h(invitee)).json()["invitations"] == []
    for url in (f"/api/v1/workspace-invitations/{invitation_id}/accept", f"/api/v1/workspaces/invitations/{token}/accept"):
        res = client.post(url, headers=_h(invitee))
        assert res.status_code == 400
        assert "revoked" in res.json()["detail"]
    assert client.delete(revoke, headers=_h(owner)).status_code == 400


def test_an_accepted_invitation_cannot_be_revoked_into_a_false_state(client: TestClient, db_session: Session, people):
    owner, invitee, _, workspace = people
    invitation_id = _invite(client, owner, workspace)["invitation"]["id"]
    assert client.post(f"/api/v1/workspace-invitations/{invitation_id}/accept", headers=_h(invitee)).status_code == 200
    assert client.delete(f"/api/v1/workspaces/{workspace.id}/invitations/{invitation_id}", headers=_h(owner)).status_code == 400
    assert db_session.get(WorkspaceInvitationModel, uuid.UUID(invitation_id)).status == InvitationStatus.ACCEPTED.value


def test_accepting_never_changes_the_role_of_someone_already_active(client: TestClient, db_session: Session, people):
    owner, invitee, _, workspace = people
    invitation_id = _invite(client, owner, workspace, role="VIEWER")["invitation"]["id"]
    assert client.post(f"/api/v1/workspaces/{workspace.id}/members", headers=_h(owner), json={"user_id": str(invitee.id), "role": "EDITOR"}).status_code == 201

    assert client.post(f"/api/v1/workspace-invitations/{invitation_id}/accept", headers=_h(invitee)).json()["role"] == "EDITOR"


def test_a_viewer_who_accepted_stays_a_viewer(client: TestClient, people):
    owner, invitee, _, workspace = people
    invitation_id = _invite(client, owner, workspace, role="VIEWER")["invitation"]["id"]
    assert client.post(f"/api/v1/workspace-invitations/{invitation_id}/accept", headers=_h(invitee)).status_code == 200
    created = client.post(f"/api/v1/workspaces/{workspace.id}/tasks", headers=_h(invitee), json={"title": "x"})
    assert created.status_code == 403
    assert client.post(f"/api/v1/workspaces/{workspace.id}/invitations", headers=_h(invitee), json={"invitee_email": "z@univ.edu", "role": "VIEWER"}).status_code == 403


def test_someone_invited_before_signing_up_finds_it_once_they_confirm_the_address(client: TestClient, db_session: Session, people):
    class Mailbox(MockEmailProvider):
        delivers_mail = True

    before, mailbox = get_email_provider(), Mailbox()
    set_email_provider(mailbox)
    owner, _, _, workspace = people
    invitation_id = _invite(client, owner, workspace, email="Newcomer@Univ.edu")["invitation"]["id"]

    registered = client.post(
        "/api/v1/auth/register",
        json={"email": "newcomer@univ.edu", "password": "A-long-enough-passw0rd", "full_name": "Nia Newcomer", "role": "STUDENT"},
    )
    assert registered.status_code == 201, registered.text
    token = registered.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/v1/workspace-invitations/mine", headers=headers).json()["invitations"] == []

    assert client.post("/api/v1/auth/email-verification", headers=headers).status_code == 202
    link = next(m["body_text"] for m in mailbox.sent_emails if m["subject"] == "Confirm your email address")
    set_email_provider(before)
    confirm = link.split("#token=")[1].split()[0]
    assert client.post("/api/v1/auth/email-verification/confirm", headers=headers, json={"token": confirm}).status_code == 200

    mine = client.get("/api/v1/workspace-invitations/mine", headers=headers).json()["invitations"]
    assert [i["id"] for i in mine] == [invitation_id]
    profile = db_session.execute(
        select(ResearchProfileModel).join(UserModel).where(UserModel.email == "newcomer@univ.edu")
    ).scalar_one()
    assert db_session.execute(select(NotificationModel).where(NotificationModel.profile_id == profile.id)).scalar_one().notification_type == "WORKSPACE_INVITATION"
    assert client.post(f"/api/v1/workspace-invitations/{invitation_id}/accept", headers=headers).status_code == 200


# ── SEC-05 ───────────────────────────────────────────────────────────────────


def test_only_a_hash_of_the_token_is_stored(client: TestClient, db_session: Session, people):
    owner, invitee, _, workspace = people
    row, token = _with_token(db_session, owner, workspace)
    assert row.token_hash == hashlib.sha256(token.encode()).hexdigest()
    assert token not in row.token_hash
    assert not hasattr(row, "token")

    # The stored value is not itself usable as a token.
    assert client.post(f"/api/v1/workspaces/invitations/{row.token_hash}/accept", headers=_h(invitee)).status_code == 404
    assert client.post(f"/api/v1/workspaces/invitations/{token}/accept", headers=_h(invitee)).status_code == 200


def test_no_list_carries_a_token(client: TestClient, db_session: Session, people):
    owner, invitee, _, workspace = people
    _row, token = _with_token(db_session, owner, workspace)
    for res in (
        client.get(f"/api/v1/workspaces/{workspace.id}/invitations", headers=_h(owner)),
        client.get("/api/v1/workspace-invitations/mine", headers=_h(invitee)),
    ):
        assert res.status_code == 200
        assert token not in res.text and "token" not in res.text


def test_a_token_in_a_path_never_reaches_a_log_line(client: TestClient, db_session: Session, people, caplog):
    owner, invitee, _, workspace = people
    _row, token = _with_token(db_session, owner, workspace)
    with caplog.at_level(logging.INFO, logger="app.access"):
        client.post(f"/api/v1/workspaces/invitations/{token}/accept", headers=_h(invitee))
    assert "/invitations/[redacted]/accept" in caplog.text
    assert token not in caplog.text

    assert redact_invitation_token(f"/api/workspace/invitations/{token}/decline") == "/api/workspace/invitations/[redacted]/decline"
    record = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s - "%s %s" %d', ("1.2.3.4", "POST", f"/api/v1/workspaces/invitations/{token}/accept", 200), None)
    assert RedactInvitationTokens().filter(record) is True
    assert token not in record.getMessage()
