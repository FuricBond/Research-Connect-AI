"""
Decisions B and C against the running stack with PostgreSQL and real SMTP behind them: what a unit
test on SQLite cannot show. Administrators cannot recruit through any endpoint; an invitation needs
a confirmed address, proved by following a link that reached a mailbox; and two requests racing for
one invitation or one link cannot both win.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import secrets
import uuid

import httpx
import pytest
from sqlalchemy import create_engine, text

from conftest import API_URL, DATABASE_URL, Account, confirm_email, confirmation_token, mail_to, opportunity_by_title, register, remember_secret, request, scalar

POSTING = {
    "title": "Assistant for causal inference",
    "posting_type": "RESEARCH_ASSISTANTSHIP",
    "description": "Work on causal inference methods with the group for a semester.",
    "required_skills": ["python"],
    "opening_terms": {
        "compensation_type": "STIPEND",
        "compensation_amount": 1000,
        "compensation_currency": "USD",
        "compensation_period": "MONTH",
        "commitment_type": "PART_TIME",
        "hours_per_week": 10,
        "duration_months": 6,
        "accepts_applications": True,
    },
}


def _workspace(owner: Account) -> str:
    made = owner.post("/api/v1/workspace", json={"opportunity_id": opportunity_by_title("Conference on Applied Machine Learning")["id"]})
    assert made.status_code == 201, made.text
    return made.json()["id"]


def _invite(owner: Account, workspace: str, email: str) -> dict:
    made = owner.post(f"/api/v1/workspaces/{workspace}/invitations", json={"invitee_email": email, "role": "EDITOR"})
    assert made.status_code == 201, made.text
    return made.json()


# ── Decision B ───────────────────────────────────────────────────────────────


def test_an_administrator_is_refused_by_every_recruiting_endpoint_directly(demo):
    admin, faculty, student = demo["admin"], demo["faculty"], demo["student"]
    posting = faculty.post("/api/v1/postings", json={**POSTING, "title": f"Decision B {uuid.uuid4().hex[:6]}"}).json()
    posting_id = posting["id"]
    assert faculty.post(f"/api/v1/postings/{posting_id}/transition", json={"target_status": "OPEN"}).status_code == 200
    application = student.post(f"/api/v1/postings/{posting_id}/applications", json={"cover_note": "Hello"})
    assert application.status_code == 201, application.text
    application_id = application.json()["id"]

    for method, path, body in (
        ("POST", "/api/v1/postings", POSTING),
        ("GET", "/api/v1/postings/mine", None),
        ("GET", "/api/v1/postings/mine/summary", None),
        ("PATCH", f"/api/v1/postings/{posting_id}", {"summary": "Changed"}),
        ("POST", f"/api/v1/postings/{posting_id}/transition", {"target_status": "CLOSED"}),
        ("DELETE", f"/api/v1/postings/{posting_id}", None),
        ("GET", f"/api/v1/postings/{posting_id}/applications", None),
        ("GET", f"/api/v1/postings/applications/{application_id}", None),
        ("POST", f"/api/v1/postings/applications/{application_id}/transition", {"target_status": "UNDER_REVIEW"}),
    ):
        answer = request(method, path, admin.token, **({"json": body} if body is not None else {}))
        assert answer.status_code in (403, 404), f"{method} {path}: {answer.status_code}"

    # The same requests still work for the faculty member who wrote it, and the admin keeps admin.
    assert faculty.get(f"/api/v1/postings/{posting_id}/applications").status_code == 200
    assert faculty.post(f"/api/v1/postings/{posting_id}/transition", json={"target_status": "CLOSED"}).status_code == 200
    assert admin.get("/api/v1/admin/users").status_code == 200


def test_a_student_is_refused_too_and_keeps_the_applicants_side(demo):
    student = demo["student"]
    assert student.post("/api/v1/postings", json=POSTING).status_code == 403
    assert student.get("/api/v1/postings/mine").status_code == 403
    assert student.get("/api/v1/postings").status_code == 200
    assert student.get("/api/v1/postings/applications/mine").status_code == 200


# ── Decision C ───────────────────────────────────────────────────────────────


def test_the_migration_left_hashes_only(db):
    assert scalar(db, "SELECT count(*) FROM information_schema.columns WHERE table_name = 'email_verification_tokens' AND column_name = 'token'") == 0
    assert scalar(db, "SELECT count(*) FROM information_schema.columns WHERE table_name = 'workspace_invitations' AND column_name = 'token'") == 0
    assert scalar(db, "SELECT count(*) FROM users WHERE email LIKE 'demo.%' AND email_verified_address IS NULL") == 0


def test_registering_an_invited_address_claims_nothing_until_a_link_is_followed(db):
    owner = register(label="own-owner")
    workspace = _workspace(owner)
    address = f"own-invitee-{uuid.uuid4().hex[:8]}@researchconnect.test"
    made = _invite(owner, workspace, address)
    assert "token" not in made
    invitation = made["invitation"]
    assert invitation["invitee_user_id"] is None

    # The mailbox was told, without naming the workspace or carrying anything usable.
    told = [m for m in mail_to(address) if m["subject"] == "You have been invited to a research workspace"]
    for _ in range(50):
        if told:
            break
        told = [m for m in mail_to(address) if m["subject"] == "You have been invited to a research workspace"]
    assert told and "Conference on Applied Machine Learning" not in told[0]["text"] and "token" not in told[0]["text"]

    password = "Own-" + secrets.token_urlsafe(16)
    registered = request("POST", "/api/v1/auth/register", json={"email": address, "password": password, "full_name": "Own Invitee", "role": "STUDENT"})
    assert registered.status_code == 201, registered.text
    body = registered.json()
    invitee = Account(address, password, remember_secret(body["access_token"]), body["user"])
    assert body["user"]["email_verified"] is False

    mine = invitee.get("/api/v1/workspace-invitations/mine").json()
    assert mine["invitations"] == [] and mine["email_verified"] is False
    assert invitee.post(f"/api/v1/workspace-invitations/{invitation['id']}/accept").status_code == 403
    assert invitee.post(f"/api/v1/workspace-invitations/{invitation['id']}/decline").status_code == 403
    assert invitee.post(f"/api/v1/workspace-invitations/{uuid.uuid4()}/accept").status_code == 403
    assert "Conference on Applied Machine Learning" not in invitee.get("/api/v1/notifications").text

    confirm_email(invitee)
    assert invitee.get("/api/v1/auth/me").json()["email_verified"] is True
    assert [i["id"] for i in invitee.get("/api/v1/workspace-invitations/mine").json()["invitations"]] == [invitation["id"]]
    assert "Conference on Applied Machine Learning" in invitee.get("/api/v1/notifications").text
    assert invitee.post(f"/api/v1/workspace-invitations/{invitation['id']}/accept").json()["role"] == "EDITOR"
    assert scalar(db, "SELECT count(*) FROM workspace_members WHERE workspace_id = :w AND user_id = :u", w=workspace, u=invitee.id) == 1


def test_a_link_works_only_for_the_account_that_asked_and_only_once(db):
    asker, other = register(label="link-asker"), register(label="link-other")
    assert asker.post("/api/v1/auth/email-verification").status_code == 202
    token = confirmation_token(asker.email)

    stored = scalar(db, "SELECT token_hash FROM email_verification_tokens WHERE user_id = :u", u=asker.id)
    assert stored == hashlib.sha256(token.encode()).hexdigest()
    assert other.post("/api/v1/auth/email-verification/confirm", json={"token": token}).status_code == 400
    assert httpx.post(f"{API_URL}/api/v1/auth/email-verification/confirm", json={"token": token}, timeout=30).status_code == 401
    assert other.get("/api/v1/auth/me").json()["email_verified"] is False

    assert asker.post("/api/v1/auth/email-verification/confirm", json={"token": token}).json()["email_verified"] is True
    assert scalar(db, "SELECT consumed_at IS NOT NULL FROM email_verification_tokens WHERE user_id = :u", u=asker.id) is True


def test_racing_for_one_link_confirms_once(db):
    asker = register(label="link-race")
    assert asker.post("/api/v1/auth/email-verification").status_code == 202
    token = confirmation_token(asker.email)
    with ThreadPoolExecutor(max_workers=4) as pool:
        codes = sorted(pool.map(lambda _: asker.post("/api/v1/auth/email-verification/confirm", json={"token": token}).status_code, range(4)))
    # One claims it; the others either see it used (400) or the address already confirmed (200).
    assert 200 in codes and set(codes) <= {200, 400}
    assert scalar(db, "SELECT count(*) FROM email_verification_tokens WHERE user_id = :u AND consumed_at IS NOT NULL", u=asker.id) == 1
    assert asker.get("/api/v1/auth/me").json()["email_verified"] is True


def test_racing_answers_to_one_invitation_only_one_wins(db):
    owner, invitee = register(label="own-race-owner"), register(label="own-race")
    confirm_email(invitee)
    workspace = _workspace(owner)
    invitation = _invite(owner, workspace, invitee.email)["invitation"]
    with ThreadPoolExecutor(max_workers=6) as pool:
        codes = sorted(pool.map(
            lambda index: invitee.post(f"/api/v1/workspace-invitations/{invitation['id']}/{'accept' if index % 2 == 0 else 'decline'}").status_code,
            range(6),
        ))
    # One answer stands. A decline that wins answers 204, an accept 200; every other answer is 400.
    assert len([code for code in codes if code in (200, 204)]) == 1
    assert codes.count(400) == 5
    status = scalar(db, "SELECT status FROM workspace_invitations WHERE id = :id", id=invitation["id"])
    members = scalar(db, "SELECT count(*) FROM workspace_members WHERE workspace_id = :w AND user_id = :u", w=workspace, u=invitee.id)
    assert (status, members) in (("ACCEPTED", 1), ("DECLINED", 0))


def test_an_invitation_token_from_before_is_refused_without_a_confirmed_recipient_and_works_once(db):
    """The API hands out no token now; old ones may exist. Set one as the old API would have."""
    owner, invitee, stranger = register(label="tok-owner"), register(label="tok-invitee"), register(label="tok-stranger")
    confirm_email(stranger)
    workspace = _workspace(owner)
    invitation = _invite(owner, workspace, invitee.email)["invitation"]
    token = remember_secret(secrets.token_urlsafe(32))
    engine = create_engine(DATABASE_URL)
    with engine.begin() as connection:
        connection.execute(text("UPDATE workspace_invitations SET token_hash = :hash, invitee_user_id = :user WHERE id = :id"), {"hash": hashlib.sha256(token.encode()).hexdigest(), "user": invitee.id, "id": invitation["id"]})
    engine.dispose()

    assert invitee.post(f"/api/v1/workspaces/invitations/{token}/accept").status_code == 403
    assert stranger.post(f"/api/v1/workspaces/invitations/{token}/accept").status_code == 403
    assert owner.get(f"/api/v1/workspaces/{workspace}/invitations").json()["items"][0]["invitee_user_id"] is None

    confirm_email(invitee)
    assert invitee.post(f"/api/v1/workspaces/invitations/{token}/accept").status_code == 200
    assert invitee.post(f"/api/v1/workspaces/invitations/{token}/accept").status_code == 400


@pytest.mark.parametrize("path", ["/api/v1/workspace-invitations/mine"])
def test_a_visitor_gets_no_answer_about_invitations(path):
    assert httpx.get(f"{API_URL}{path}", timeout=30).status_code == 401
