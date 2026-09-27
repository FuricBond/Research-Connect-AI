"""
Step 5 — the authentication lifecycle over real HTTP against APP_ENV=production.

Registration -> JWT -> authenticated request -> the browser discards the token (logout)
-> protected request refused. Production authentication is `Authorization: Bearer <JWT>`;
the developer `X-User-ID` header must not authenticate anyone here.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import json

from conftest import (
    login,
    new_password,
    observe,
    register,
    request,
    rows,
    unique_email,
)


def _b64(data: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(data, separators=(",", ":")).encode()).rstrip(b"=").decode()


def test_registration_issues_a_bearer_token_and_stores_only_a_bcrypt_hash(db):
    email = unique_email("reg")
    password = new_password()
    response = request("POST", "/api/v1/auth/register", json={
        "email": email.upper(), "password": password, "full_name": "Reg Istered",
        "institution_name": "Fairview Institute of Technology",
    })
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["token_type"].lower() == "bearer" and body["access_token"].count(".") == 2
    assert datetime.fromisoformat(body["expires_at"].replace("Z", "+00:00")) > datetime.now(timezone.utc)
    user = body["user"]
    assert user["email"] == email, "emails are normalized to lower case"
    assert user["role"] == "STUDENT" and user["is_active"] and user["profile_id"]
    assert not {"password", "hashed_password"} & set(user)
    stored = rows(db, "SELECT hashed_password FROM users WHERE email = :e", e=email)[0]["hashed_password"]
    assert stored.startswith("$2") and password not in stored


def test_duplicate_email_is_rejected_case_insensitively():
    account = register()
    again = request("POST", "/api/v1/auth/register", json={
        "email": account.email.upper(), "password": new_password(), "full_name": "Second",
    })
    assert again.status_code == 409, again.text


def test_registration_policy_is_enforced():
    short = request("POST", "/api/v1/auth/register", json={"email": unique_email("weak"), "password": "short1", "full_name": "W"})
    assert short.status_code == 422
    admin = request("POST", "/api/v1/auth/register", json={
        "email": unique_email("admin"), "password": new_password(), "full_name": "Self Promoted", "role": "ADMIN",
    })
    assert admin.status_code == 422, "ADMIN is granted only by an administrator"


def test_login_accepts_the_right_password_and_refuses_others_without_disclosing_accounts():
    account = register()
    good = login(account.email, account.password)
    assert good.status_code == 200 and good.json()["user"]["id"] == account.id
    wrong = login(account.email, account.password + "x")
    unknown = login(unique_email("nobody"), account.password)
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["detail"] == unknown.json()["detail"], "same answer for a wrong password and an unknown email"


def test_the_bearer_token_authenticates_and_nothing_else_does():
    account, other = register(), register()
    me = account.get("/api/v1/auth/me")
    assert me.status_code == 200 and me.json()["id"] == account.id
    assert request("GET", "/api/v1/auth/me").status_code == 401, "no credentials"
    assert request("GET", "/api/v1/auth/me", headers={"Authorization": "Bearer not-a-jwt"}).status_code == 401
    # A token whose payload was edited to name another user fails signature verification.
    header, payload, signature = account.token.split(".")
    claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    claims["sub"] = other.id
    forged = f"{header}.{_b64(claims)}.{signature}"
    assert request("GET", "/api/v1/auth/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401
    # The developer identity header is refused in production, alone or next to a real token.
    assert request("GET", "/api/v1/auth/me", headers={"X-User-ID": account.id}).status_code == 401
    mixed = request("GET", "/api/v1/auth/me", token=account.token, headers={"X-User-ID": other.id})
    assert mixed.status_code == 200 and mixed.json()["id"] == account.id


def test_protected_routes_refuse_anonymous_callers():
    account = register()
    for path in ("/api/v1/workspace", "/api/v1/notifications", "/api/v1/postings/applications/mine",
                 f"/api/v1/researchers/{account.profile_id}/preferences"):
        assert request("GET", path).status_code == 401, path


def test_logout_is_client_side_and_a_session_without_its_token_is_anonymous():
    """
    The API has no logout endpoint: signing out discards the token in the browser (Phase 6.2),
    after which requests are anonymous. Whether the discarded token still works until it
    expires is recorded as an observation for the Phase 6.7 security audit, not asserted.
    """
    account = register()
    assert request("POST", "/api/v1/auth/logout", token=account.token).status_code in (404, 405)
    assert request("GET", "/api/v1/workspace").status_code == 401  # the browser after sign-out
    observe("discarded_token_still_valid_until_expiry", account.get("/api/v1/auth/me").status_code == 200)


def test_a_deactivated_account_is_refused_immediately_and_restored_on_reactivation(demo):
    account = register()
    assert account.get("/api/v1/auth/me").status_code == 200
    admin = demo["admin"]
    off = admin.patch(f"/api/v1/admin/users/{account.id}", json={"is_active": False})
    assert off.status_code == 200 and off.json()["is_active"] is False
    assert account.get("/api/v1/auth/me").status_code == 401, "the live token stops working at once"
    assert login(account.email, account.password).status_code == 401
    on = admin.patch(f"/api/v1/admin/users/{account.id}", json={"is_active": True})
    assert on.status_code == 200
    assert account.get("/api/v1/auth/me").status_code == 200
