"""
Phase 6.7 (Fix 5/9) — access tokens can be revoked (finding F-2).

Before this, signing out only cleared the browser: a token stayed valid for its whole lifetime
(up to 480 minutes). Every token now carries the account's token_version ("ver"), and the
version moves on when the account signs out, changes its password or is deactivated.

  Logout            POST /auth/logout revokes every token issued so far (204); others' tokens
                    keep working; signing in again works.
  Legacy tokens     A token without "ver" counts as version 0, so sessions from before the
                    change keep working until the account's first sign-out.
  Change password   Checks the current password (400 if wrong), applies the registration rules
                    to the new one (422), revokes old tokens and returns a fresh one. Rate
                    limited like login.
  Deactivation      Still refused at once, and reactivation does not bring old tokens back.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid

from fastapi.testclient import TestClient
import jwt
import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.security import create_access_token, decode_access_token, get_signing_key, hash_password
from app.db.session import get_db
from app.db.types import TSVector, Vector
from app.main import app
from app.models import Base
from app.models.user import UserModel

compiles(JSONB, "sqlite")(lambda type_, compiler, **kw: "JSON")
compiles(Vector, "sqlite")(lambda type_, compiler, **kw: "TEXT")
compiles(TSVector, "sqlite")(lambda type_, compiler, **kw: "TEXT")

# Generated per run; never a literal password in the suite.
PASSWORD = "Pw-" + uuid.uuid4().hex[:16]


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


def _account(db: Session, email: str, role: str = "STUDENT") -> UserModel:
    user = UserModel(
        id=uuid.uuid4(),
        email=email,
        hashed_password=hash_password(PASSWORD),
        full_name="Test Account",
        role=role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    return user


def _login(client: TestClient, email: str, password: str = PASSWORD) -> str:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _me(client: TestClient, token: str) -> int:
    return client.get("/api/v1/auth/me", headers=_bearer(token)).status_code


def _legacy_token(user_id: uuid.UUID, **extra) -> str:
    """A token shaped like those issued before Phase 6.7: no "ver" claim."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    payload = {
        "sub": str(user_id),
        "iss": settings.auth_issuer,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=30)).timestamp()),
        "type": "access",
        **extra,
    }
    return jwt.encode(payload, get_signing_key(), algorithm=settings.auth_algorithm)


# ── Tokens ──────────────────────────────────────────────────────────────────


def test_tokens_carry_the_version_they_were_issued_under():
    user_id = uuid.uuid4()
    token, _ = create_access_token(user_id, token_version=3)
    assert jwt.decode(token, options={"verify_signature": False})["ver"] == 3
    assert decode_access_token(token).token_version == 3
    assert decode_access_token(create_access_token(user_id)[0]).token_version == 0
    assert decode_access_token(_legacy_token(user_id)).token_version == 0


@pytest.mark.parametrize("bad_version", ["1", -1, True, 1.5, None])
def test_a_malformed_version_claim_is_refused(client: TestClient, db_session: Session, bad_version):
    user = _account(db_session, "malformed@lab.test")
    assert _me(client, _legacy_token(user.id, ver=bad_version)) == 401


# ── Logout ──────────────────────────────────────────────────────────────────


def test_logout_revokes_the_token_and_signing_in_again_works(client: TestClient, db_session: Session):
    user = _account(db_session, "priya@lab.test")
    token = _login(client, "priya@lab.test")
    assert _me(client, token) == 200

    resp = client.post("/api/v1/auth/logout", headers=_bearer(token))
    assert resp.status_code == 204
    assert resp.content == b""

    old = client.get("/api/v1/auth/me", headers=_bearer(token))
    assert old.status_code == 401
    assert old.json()["detail"] == "Access token has been revoked."
    # The revoked token cannot sign out (or do anything) again.
    assert client.post("/api/v1/auth/logout", headers=_bearer(token)).status_code == 401

    db_session.refresh(user)
    assert user.token_version == 1
    fresh = _login(client, "priya@lab.test")
    assert _me(client, fresh) == 200


def test_logout_requires_sign_in(client: TestClient):
    assert client.post("/api/v1/auth/logout").status_code == 401


def test_logout_revokes_every_session_of_that_account_only(client: TestClient, db_session: Session):
    _account(db_session, "priya@lab.test")
    _account(db_session, "omar@lab.test")
    laptop = _login(client, "priya@lab.test")
    phone = _login(client, "priya@lab.test")
    other = _login(client, "omar@lab.test")

    assert client.post("/api/v1/auth/logout", headers=_bearer(laptop)).status_code == 204

    assert _me(client, laptop) == 401
    assert _me(client, phone) == 401
    assert _me(client, other) == 200


def test_a_token_without_a_version_works_until_the_first_logout(client: TestClient, db_session: Session):
    user = _account(db_session, "legacy@lab.test")
    legacy = _legacy_token(user.id)
    assert _me(client, legacy) == 200

    assert client.post("/api/v1/auth/logout", headers=_bearer(legacy)).status_code == 204
    assert _me(client, legacy) == 401


# ── Change password ─────────────────────────────────────────────────────────


def test_change_password_revokes_old_tokens_and_returns_a_working_one(client: TestClient, db_session: Session):
    _account(db_session, "priya@lab.test")
    old_token = _login(client, "priya@lab.test")
    other_session = _login(client, "priya@lab.test")
    new_password = "New-" + uuid.uuid4().hex[:12]

    resp = client.post(
        "/api/v1/auth/change-password",
        headers=_bearer(old_token),
        json={"current_password": PASSWORD, "new_password": new_password},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["token_type"] == "bearer" and body["user"]["email"] == "priya@lab.test"

    assert _me(client, old_token) == 401
    assert _me(client, other_session) == 401
    assert _me(client, body["access_token"]) == 200

    assert client.post(
        "/api/v1/auth/login", json={"email": "priya@lab.test", "password": PASSWORD}
    ).status_code == 401
    assert _me(client, _login(client, "priya@lab.test", new_password)) == 200


def test_change_password_with_a_wrong_current_password_is_400_and_changes_nothing(
    client: TestClient, db_session: Session
):
    _account(db_session, "priya@lab.test")
    token = _login(client, "priya@lab.test")

    resp = client.post(
        "/api/v1/auth/change-password",
        headers=_bearer(token),
        json={"current_password": "not-the-password", "new_password": "Another-long-pass"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Current password is incorrect."
    assert _me(client, token) == 200
    assert _login(client, "priya@lab.test")


@pytest.mark.parametrize(
    "new_password",
    ["short", " leading-space-pass", "trailing-space-pass ", "x" * 73],
)
def test_change_password_applies_the_registration_rules(client: TestClient, db_session: Session, new_password):
    _account(db_session, "priya@lab.test")
    token = _login(client, "priya@lab.test")

    resp = client.post(
        "/api/v1/auth/change-password",
        headers=_bearer(token),
        json={"current_password": PASSWORD, "new_password": new_password},
    )
    assert resp.status_code == 422
    assert _me(client, token) == 200


def test_change_password_requires_sign_in(client: TestClient):
    resp = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "Another-long-pass"},
    )
    assert resp.status_code == 401


def test_change_password_is_rate_limited_like_login(client: TestClient, db_session: Session):
    _account(db_session, "priya@lab.test")
    token = _login(client, "priya@lab.test")
    payload = {"current_password": "wrong-guess", "new_password": "Another-long-pass"}

    statuses = [
        client.post("/api/v1/auth/change-password", headers=_bearer(token), json=payload).status_code
        for _ in range(settings.auth_login_rate_limit_per_minute)
    ]
    # The sign-in above used one attempt from the same budget.
    assert statuses[-1] == 429
    assert set(statuses[:-1]) == {400}
    assert "Retry-After" in client.post(
        "/api/v1/auth/change-password", headers=_bearer(token), json=payload
    ).headers


# ── Deactivation ────────────────────────────────────────────────────────────


def test_deactivation_still_revokes_at_once_and_reactivation_does_not_revive_tokens(
    client: TestClient, db_session: Session
):
    _account(db_session, "admin@lab.test", role="ADMIN")
    target = _account(db_session, "priya@lab.test")
    admin_token = _login(client, "admin@lab.test")
    target_token = _login(client, "priya@lab.test")
    assert _me(client, target_token) == 200

    off = client.patch(
        f"/api/v1/admin/users/{target.id}", headers=_bearer(admin_token), json={"is_active": False}
    )
    assert off.status_code == 200
    assert _me(client, target_token) == 401

    on = client.patch(
        f"/api/v1/admin/users/{target.id}", headers=_bearer(admin_token), json={"is_active": True}
    )
    assert on.status_code == 200
    assert _me(client, target_token) == 401
    assert _me(client, _login(client, "priya@lab.test")) == 200
    # The administrator's own session is untouched.
    assert _me(client, admin_token) == 200
