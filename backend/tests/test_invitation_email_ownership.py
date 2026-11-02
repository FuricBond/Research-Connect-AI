"""
Decision C — an invitation is claimed only by someone who proved they receive mail at its address.

Registering with an invited address, or holding an invitation's id or token, is not enough. These
tests use a provider that delivers, read the link out of the message as its recipient would, and
try each way around it. Races on the real database are in e2e/api/test_11_final_remediation.py.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import re
import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from app.db.session import get_db
from app.db.types import TSVector, Vector
from app.main import app
from app.models.base import Base
from app.models.email_verification import EmailVerificationTokenModel
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
from app.services.email_verification_service import has_verified_email, normalize_email
from app.services.reminder_scheduler_service import (
    DeliveryResult,
    MockEmailProvider,
    get_email_provider,
    set_email_provider,
)
from app.services.workspace_collaboration_service import WorkspaceCollaborationService

compiles(JSONB, "sqlite")(lambda type_, compiler, **kw: "JSON")
compiles(Vector, "sqlite")(lambda type_, compiler, **kw: "TEXT")
compiles(TSVector, "sqlite")(lambda type_, compiler, **kw: "TEXT")


class Mailbox(MockEmailProvider):
    """A provider that counts as delivering, and keeps what it sent for the test to read."""

    delivers_mail = True

    def token_for(self, address: str) -> str:
        bodies = [m["body_text"] for m in self.sent_emails if m["to"] == address and m["subject"] == "Confirm your email address"]
        assert bodies, f"no confirmation email for {address}"
        return re.search(r"/verify-email#token=(\S+)", bodies[-1]).group(1)


@pytest.fixture
def mailbox():
    before = get_email_provider()
    provider = Mailbox()
    set_email_provider(provider)
    yield provider
    set_email_provider(before)


@pytest.fixture
def db_session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
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


def _account(db: Session, email: str, name: str = "A Person", *, confirmed: bool = False) -> UserModel:
    user = UserModel(id=uuid.uuid4(), email=email, full_name=name, hashed_password="pw", is_active=True)
    if confirmed:
        user.email_verified_address = normalize_email(email)
        user.email_verified_at = datetime.now(timezone.utc)
    db.add(user)
    db.flush()
    db.add(ResearchProfileModel(id=uuid.uuid4(), user_id=user.id, academic_status="POSTGRADUATE"))
    db.commit()
    return user


def _h(user: UserModel) -> dict[str, str]:
    return {"X-User-ID": str(user.id)}


@pytest.fixture
def workspace(db_session: Session):
    owner = _account(db_session, "owner@univ.edu", "Olu Owner", confirmed=True)
    call = OpportunityModel(id=uuid.uuid4(), title="Causal ML Workshop", opportunity_type="CONFERENCE", status="ACTIVE")
    db_session.add(call)
    db_session.flush()
    saved = SavedOpportunityModel(id=uuid.uuid4(), user_id=owner.id, opportunity_id=call.id, status=WorkspaceStatus.PLANNING.value)
    db_session.add(saved)
    db_session.flush()
    db_session.add(
        WorkspaceMemberModel(
            workspace_id=saved.id,
            user_id=owner.id,
            role=WorkspaceRole.OWNER.value,
            status=MemberStatus.ACTIVE.value,
            joined_at=datetime.now(timezone.utc),
        )
    )
    db_session.commit()
    return owner, saved


def _invite(client: TestClient, owner: UserModel, saved, email: str) -> dict:
    res = client.post(f"/api/v1/workspaces/{saved.id}/invitations", headers=_h(owner), json={"invitee_email": email, "role": "EDITOR"})
    assert res.status_code == 201, res.text
    return res.json()["invitation"]


def _accept(client: TestClient, user: UserModel, invitation_id: str):
    return client.post(f"/api/v1/workspace-invitations/{invitation_id}/accept", headers=_h(user))


def _confirm(client: TestClient, mailbox: Mailbox, user: UserModel) -> None:
    assert client.post("/api/v1/auth/email-verification", headers=_h(user)).status_code == 202
    token = mailbox.token_for(user.email)
    assert client.post("/api/v1/auth/email-verification/confirm", headers=_h(user), json={"token": token}).json()["email_verified"] is True


def _member_ids(db: Session, saved) -> set[uuid.UUID]:
    db.expire_all()
    return set(
        db.execute(
            select(WorkspaceMemberModel.user_id).where(
                WorkspaceMemberModel.workspace_id == saved.id,
                WorkspaceMemberModel.status == MemberStatus.ACTIVE.value,
            )
        ).scalars()
    )


# ── The four questions an acceptance asks ─────────────────────────────────────


def test_the_right_recipient_with_a_confirmed_address_joins(client, db_session, workspace, mailbox):
    owner, saved = workspace
    invitee = _account(db_session, "invitee@univ.edu")
    invitation = _invite(client, owner, saved, "invitee@univ.edu")
    _confirm(client, mailbox, invitee)

    listed = client.get("/api/v1/workspace-invitations/mine", headers=_h(invitee)).json()
    assert listed["email_verified"] is True
    assert [i["id"] for i in listed["invitations"]] == [invitation["id"]]
    assert _accept(client, invitee, invitation["id"]).json()["role"] == "EDITOR"
    assert invitee.id in _member_ids(db_session, saved)


def test_the_right_recipient_without_a_confirmed_address_is_held(client, db_session, workspace):
    owner, saved = workspace
    invitee = _account(db_session, "invitee@univ.edu")
    invitation = _invite(client, owner, saved, "invitee@univ.edu")

    refused = _accept(client, invitee, invitation["id"])
    assert refused.status_code == 403
    assert refused.json()["detail"] == "Confirm your email address before answering workspace invitations."
    assert client.post(f"/api/v1/workspace-invitations/{invitation['id']}/decline", headers=_h(invitee)).status_code == 403
    assert invitee.id not in _member_ids(db_session, saved)
    db_session.expire_all()
    assert db_session.get(WorkspaceInvitationModel, uuid.UUID(invitation["id"])).status == InvitationStatus.PENDING.value


def test_someone_with_another_confirmed_address_is_refused(client, db_session, workspace):
    owner, saved = workspace
    other = _account(db_session, "other@univ.edu", confirmed=True)
    invitation = _invite(client, owner, saved, "invitee@univ.edu")
    assert _accept(client, other, invitation["id"]).status_code == 404
    assert client.get("/api/v1/workspace-invitations/mine", headers=_h(other)).json()["invitations"] == []


def test_registering_the_invited_address_without_confirming_claims_nothing(client, db_session, workspace):
    owner, saved = workspace
    invitation = _invite(client, owner, saved, "victim@univ.edu")

    registered = client.post(
        "/api/v1/auth/register",
        json={"email": "victim@univ.edu", "password": "Sq1!-correct-horse", "full_name": "Not The Owner", "role": "STUDENT"},
    )
    assert registered.status_code == 201, registered.text
    body = registered.json()
    assert body["user"]["email_verified"] is False
    squatter = {"Authorization": f"Bearer {body['access_token']}"}

    mine = client.get("/api/v1/workspace-invitations/mine", headers=squatter).json()
    assert mine["invitations"] == [] and mine["email_verified"] is False
    assert client.post(f"/api/v1/workspace-invitations/{invitation['id']}/accept", headers=squatter).status_code == 403
    assert client.post(f"/api/v1/workspace-invitations/{invitation['id']}/decline", headers=squatter).status_code == 403
    notifications = client.get("/api/v1/notifications", headers=squatter).json()
    assert "Causal ML Workshop" not in str(notifications) and "Olu Owner" not in str(notifications)
    db_session.expire_all()
    row = db_session.get(WorkspaceInvitationModel, uuid.UUID(invitation["id"]))
    assert row.invitee_user_id is None and row.status == InvitationStatus.PENDING.value


def test_confirming_then_accepting_works_and_the_invitee_is_told_only_then(client, db_session, workspace, mailbox):
    owner, saved = workspace
    invitee = _account(db_session, "invitee@univ.edu")
    invitation = _invite(client, owner, saved, "invitee@univ.edu")
    notices = lambda: db_session.execute(select(NotificationModel).where(NotificationModel.title == "Invitation to a research workspace")).scalars().all()
    assert notices() == []

    _confirm(client, mailbox, invitee)
    assert len(notices()) == 1
    assert "Causal ML Workshop" in notices()[0].body
    assert _accept(client, invitee, invitation["id"]).status_code == 200


# ── Lifecycle ─────────────────────────────────────────────────────────────────


def test_an_expired_invitation_cannot_be_accepted(client, db_session, workspace):
    owner, saved = workspace
    invitee = _account(db_session, "invitee@univ.edu", confirmed=True)
    invitation = _invite(client, owner, saved, "invitee@univ.edu")
    row = db_session.get(WorkspaceInvitationModel, uuid.UUID(invitation["id"]))
    row.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    db_session.commit()
    refused = _accept(client, invitee, invitation["id"])
    assert refused.status_code == 400 and "expired" in refused.json()["detail"]


def test_a_revoked_invitation_cannot_be_accepted(client, db_session, workspace):
    owner, saved = workspace
    invitee = _account(db_session, "invitee@univ.edu", confirmed=True)
    invitation = _invite(client, owner, saved, "invitee@univ.edu")
    assert client.delete(f"/api/v1/workspaces/{saved.id}/invitations/{invitation['id']}", headers=_h(owner)).status_code == 204
    refused = _accept(client, invitee, invitation["id"])
    assert refused.status_code == 400 and "revoked" in refused.json()["detail"]


def _with_token(db: Session, owner: UserModel, saved, email: str) -> tuple[WorkspaceInvitationModel, str]:
    """As if the token had been handed out before the API stopped returning it."""
    return WorkspaceCollaborationService.create_invitation(db, saved.id, owner.id, WorkspaceInvitationCreate(invitee_email=email, role=WorkspaceRole.EDITOR))


def test_a_token_works_once_for_a_confirmed_recipient(client, db_session, workspace):
    owner, saved = workspace
    invitee = _account(db_session, "invitee@univ.edu", confirmed=True)
    _row, token = _with_token(db_session, owner, saved, "invitee@univ.edu")
    assert client.post(f"/api/v1/workspaces/invitations/{token}/accept", headers=_h(invitee)).status_code == 200
    again = client.post(f"/api/v1/workspaces/invitations/{token}/accept", headers=_h(invitee))
    assert again.status_code == 400 and "already" in again.json()["detail"]


def test_a_token_alone_gets_an_unconfirmed_or_wrong_account_nowhere(client, db_session, workspace):
    owner, saved = workspace
    unconfirmed = _account(db_session, "invitee@univ.edu")
    wrong = _account(db_session, "wrong@univ.edu", confirmed=True)
    _row, token = _with_token(db_session, owner, saved, "invitee@univ.edu")

    assert client.post(f"/api/v1/workspaces/invitations/{token}/accept", headers=_h(unconfirmed)).status_code == 403
    assert client.post(f"/api/v1/workspaces/invitations/{token}/decline", headers=_h(unconfirmed)).status_code == 403
    assert client.post(f"/api/v1/workspaces/invitations/{token}/accept", headers=_h(wrong)).status_code == 403
    assert client.post(f"/api/v1/workspaces/invitations/{token}/accept").status_code == 401
    assert _member_ids(db_session, saved) == {owner.id}


def test_an_unconfirmed_account_cannot_tell_a_real_invitation_from_a_made_up_one(client, db_session, workspace):
    owner, saved = workspace
    unconfirmed = _account(db_session, "invitee@univ.edu")
    invitation = _invite(client, owner, saved, "invitee@univ.edu")
    _row, token = _with_token(db_session, owner, saved, "second@univ.edu")

    real_id = _accept(client, unconfirmed, invitation["id"])
    fake_id = _accept(client, unconfirmed, str(uuid.uuid4()))
    assert (real_id.status_code, real_id.json()) == (fake_id.status_code, fake_id.json())
    real_token = client.post(f"/api/v1/workspaces/invitations/{token}/accept", headers=_h(unconfirmed))
    fake_token = client.post("/api/v1/workspaces/invitations/not-a-token/accept", headers=_h(unconfirmed))
    assert (real_token.status_code, real_token.json()) == (fake_token.status_code, fake_token.json())


def test_a_pending_invitation_from_before_this_rule_waits_like_any_other(client, db_session, workspace, mailbox):
    """An older row is bound to an account that proved nothing. The binding gives it nothing."""
    owner, saved = workspace
    invitee = _account(db_session, "invitee@univ.edu")
    row, _token = _with_token(db_session, owner, saved, "invitee@univ.edu")
    row.invitee_user_id = invitee.id
    db_session.commit()

    assert _accept(client, invitee, str(row.id)).status_code == 403
    assert client.get("/api/v1/workspace-invitations/mine", headers=_h(invitee)).json()["invitations"] == []
    # Nor does the inviter learn from the old binding that the address has an account.
    assert client.get(f"/api/v1/workspaces/{saved.id}/invitations", headers=_h(owner)).json()["items"][0]["invitee_user_id"] is None

    _confirm(client, mailbox, invitee)
    assert _accept(client, invitee, str(row.id)).status_code == 200


def test_an_address_invited_in_capitals_matches_after_normalizing(client, db_session, workspace, mailbox):
    owner, saved = workspace
    invitee = _account(db_session, "Invitee@Univ.edu")
    invitation = _invite(client, owner, saved, "  INVITEE@univ.EDU ")
    _confirm(client, mailbox, invitee)
    assert _accept(client, invitee, invitation["id"]).status_code == 200


# ── Tokens never leave ────────────────────────────────────────────────────────


def test_no_raw_invitation_token_is_stored_or_returned(client, db_session, workspace):
    owner, saved = workspace
    made = client.post(f"/api/v1/workspaces/{saved.id}/invitations", headers=_h(owner), json={"invitee_email": "a@univ.edu", "role": "VIEWER"})
    assert made.status_code == 201
    assert "token" not in made.text
    listed = client.get(f"/api/v1/workspaces/{saved.id}/invitations", headers=_h(owner))
    assert "token" not in listed.text

    row, token = _with_token(db_session, owner, saved, "b@univ.edu")
    assert row.token_hash == hashlib.sha256(token.encode()).hexdigest()
    assert token not in str({c.name: getattr(row, c.name) for c in WorkspaceInvitationModel.__table__.columns})


def test_only_a_hash_of_a_confirmation_token_is_stored(client, db_session, mailbox):
    user = _account(db_session, "a@univ.edu")
    res = client.post("/api/v1/auth/email-verification", headers=_h(user))
    assert res.json() == {"status": "SENT"}
    token = mailbox.token_for(user.email)
    assert token not in res.text
    row = db_session.execute(select(EmailVerificationTokenModel)).scalar_one()
    assert row.token_hash == hashlib.sha256(token.encode()).hexdigest()
    assert token not in str({c.name: getattr(row, c.name) for c in EmailVerificationTokenModel.__table__.columns})


# ── The confirmation itself ───────────────────────────────────────────────────


def test_a_confirmation_link_works_only_for_the_account_that_asked(client, db_session, mailbox):
    """Someone registers another person's address; that person clicks the link while signed in as themselves."""
    squatter = _account(db_session, "victim@univ.edu")
    victim_elsewhere = _account(db_session, "victim.other@univ.edu")
    assert client.post("/api/v1/auth/email-verification", headers=_h(squatter)).status_code == 202
    token = mailbox.token_for("victim@univ.edu")

    refused = client.post("/api/v1/auth/email-verification/confirm", headers=_h(victim_elsewhere), json={"token": token})
    assert refused.status_code == 400
    assert client.post("/api/v1/auth/email-verification/confirm", json={"token": token}).status_code == 401
    db_session.expire_all()
    assert not has_verified_email(squatter) and not has_verified_email(victim_elsewhere)


def test_every_bad_confirmation_gets_the_same_answer(client, db_session, mailbox):
    user = _account(db_session, "a@univ.edu")
    other = _account(db_session, "b@univ.edu")
    client.post("/api/v1/auth/email-verification", headers=_h(other))
    others_token = mailbox.token_for("b@univ.edu")
    client.post("/api/v1/auth/email-verification", headers=_h(user))
    expired_token = mailbox.token_for("a@univ.edu")
    row = db_session.execute(select(EmailVerificationTokenModel).where(EmailVerificationTokenModel.user_id == user.id)).scalar_one()
    row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.commit()

    unknown = client.post("/api/v1/auth/email-verification/confirm", headers=_h(user), json={"token": "made-up"})
    expired = client.post("/api/v1/auth/email-verification/confirm", headers=_h(user), json={"token": expired_token})
    foreign = client.post("/api/v1/auth/email-verification/confirm", headers=_h(user), json={"token": others_token})
    assert unknown.status_code == expired.status_code == foreign.status_code == 400
    assert unknown.json() == expired.json() == foreign.json()


def test_a_new_link_replaces_the_old_one_and_a_link_works_once(client, db_session, mailbox):
    user = _account(db_session, "a@univ.edu")
    client.post("/api/v1/auth/email-verification", headers=_h(user))
    first = mailbox.token_for(user.email)
    client.post("/api/v1/auth/email-verification", headers=_h(user))
    second = mailbox.token_for(user.email)
    assert first != second
    assert client.post("/api/v1/auth/email-verification/confirm", headers=_h(user), json={"token": first}).status_code == 400
    assert client.post("/api/v1/auth/email-verification/confirm", headers=_h(user), json={"token": second}).json()["email_verified"] is True
    assert db_session.execute(select(EmailVerificationTokenModel.consumed_at)).scalar_one() is not None
    assert client.post("/api/v1/auth/email-verification", headers=_h(user)).json() == {"status": "ALREADY_VERIFIED"}


def test_changing_the_account_email_ends_the_confirmation(client, db_session, workspace, mailbox):
    """No path changes an address today. If one ever does, the proof does not travel with it."""
    owner, saved = workspace
    user = _account(db_session, "first@univ.edu")
    invitation = _invite(client, owner, saved, "first@univ.edu")
    second = _invite(client, owner, saved, "second@univ.edu")
    _confirm(client, mailbox, user)

    user.email = "second@univ.edu"
    db_session.commit()
    assert client.get("/api/v1/auth/me", headers=_h(user)).json()["email_verified"] is False
    assert _accept(client, user, second["id"]).status_code == 403
    assert _accept(client, user, invitation["id"]).status_code == 403


def test_no_endpoint_lets_an_account_change_its_email(client, db_session):
    user = _account(db_session, "a@univ.edu", confirmed=True)
    admin = _account(db_session, "admin@univ.edu")
    admin.role = "ADMIN"
    db_session.commit()
    assert client.patch(f"/api/v1/admin/users/{user.id}", headers=_h(admin), json={"email": "b@univ.edu"}).status_code in (200, 422)
    db_session.expire_all()
    assert db_session.get(UserModel, user.id).email == "a@univ.edu"


def test_two_accounts_can_never_hold_one_confirmed_address(db_session):
    _account(db_session, "a@univ.edu", confirmed=True)
    duplicate = UserModel(id=uuid.uuid4(), email="A@univ.edu", full_name="B", hashed_password="pw", email_verified_address="a@univ.edu")
    db_session.add(duplicate)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_without_a_mail_server_nothing_can_be_confirmed(client, db_session):
    """The default, in-memory provider cannot prove anything: this fails closed, and says so."""
    assert get_email_provider().delivers_mail is False
    user = _account(db_session, "a@univ.edu")
    refused = client.post("/api/v1/auth/email-verification", headers=_h(user))
    assert refused.status_code == 503 and "cannot send email" in refused.json()["detail"]
    assert db_session.execute(select(EmailVerificationTokenModel)).scalars().all() == []


def test_an_address_the_provider_may_not_mail_is_refused(client, db_session, mailbox, monkeypatch):
    monkeypatch.setattr(mailbox, "accepts_recipient", lambda address: False)
    user = _account(db_session, "a@univ.edu")
    assert client.post("/api/v1/auth/email-verification", headers=_h(user)).status_code == 503
    assert mailbox.sent_emails == []


def test_a_failed_send_leaves_no_usable_link(client, db_session, mailbox, monkeypatch):
    monkeypatch.setattr(mailbox, "send_email", lambda **kw: DeliveryResult(success=False, error_message="down", retryable=True))
    user = _account(db_session, "a@univ.edu")
    refused = client.post("/api/v1/auth/email-verification", headers=_h(user))
    assert refused.status_code == 503 and "Try again" in refused.json()["detail"]
    assert db_session.execute(select(EmailVerificationTokenModel)).scalars().all() == []


def test_asking_for_links_is_rate_limited_per_account(client, db_session, mailbox):
    user = _account(db_session, "a@univ.edu")
    codes = [client.post("/api/v1/auth/email-verification", headers=_h(user)).status_code for _ in range(6)]
    assert codes == [202] * 5 + [429]
    other = _account(db_session, "b@univ.edu")
    assert client.post("/api/v1/auth/email-verification", headers=_h(other)).status_code == 202


# ── What an inviter or a visitor can learn ────────────────────────────────────


def test_an_inviter_cannot_tell_whether_an_address_has_an_account(client, db_session, workspace, mailbox):
    owner, saved = workspace
    _account(db_session, "known@univ.edu")
    known = _invite(client, owner, saved, "known@univ.edu")
    unknown = _invite(client, owner, saved, "nobody@univ.edu")
    assert set(known) == set(unknown)
    assert known["invitee_user_id"] is None and unknown["invitee_user_id"] is None
    assert known["status"] == unknown["status"] == "PENDING"
    # Both mailboxes hear the same thing; neither message names the workspace.
    invites = [m for m in mailbox.sent_emails if m["subject"] == "You have been invited to a research workspace"]
    assert sorted(m["to"] for m in invites) == ["known@univ.edu", "nobody@univ.edu"]
    assert invites[0]["body_text"] == invites[1]["body_text"]
    assert "Causal ML Workshop" not in invites[0]["body_text"] and "token" not in invites[0]["body_text"]


def test_a_confirmed_invitee_is_notified_rather_than_emailed_again(client, db_session, workspace, mailbox):
    owner, saved = workspace
    _account(db_session, "known@univ.edu", confirmed=True)
    _invite(client, owner, saved, "known@univ.edu")
    assert [m for m in mailbox.sent_emails if m["subject"] == "You have been invited to a research workspace"] == []
    assert db_session.execute(select(NotificationModel).where(NotificationModel.title == "Invitation to a research workspace")).scalars().one() is not None


def test_a_visitor_learns_nothing_without_an_account(client, db_session, workspace):
    owner, saved = workspace
    invitation = _invite(client, owner, saved, "invitee@univ.edu")
    for path in (
        f"/api/v1/workspace-invitations/{invitation['id']}/accept",
        f"/api/v1/workspace-invitations/{uuid.uuid4()}/accept",
        "/api/v1/workspaces/invitations/made-up/accept",
        "/api/v1/auth/email-verification",
    ):
        assert client.post(path).status_code == 401, path
    assert client.get("/api/v1/workspace-invitations/mine").status_code == 401


def test_too_many_invitation_emails_stop_but_the_invitations_do_not(client, db_session, workspace, mailbox):
    owner, saved = workspace
    for index in range(22):
        _invite(client, owner, saved, f"person{index}@univ.edu")
    assert len([m for m in mailbox.sent_emails if m["subject"] == "You have been invited to a research workspace"]) == 20
    assert client.get(f"/api/v1/workspaces/{saved.id}/invitations", headers=_h(owner)).json()["total_count"] == 22
