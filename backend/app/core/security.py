"""
Phase 6 — Authentication primitives: password hashing and signed access tokens.

Passwords are hashed with bcrypt. Access tokens are HS256 JWTs carrying the user ID
as `sub`. Authorization decisions never trust claims beyond `sub`: the user row (role,
is_active) is re-read on every request so role changes and deactivation apply at once.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import functools
import logging
import secrets
import uuid

import bcrypt
import jwt

from app.core.config import settings

logger = logging.getLogger(__name__)

# bcrypt only reads the first 72 bytes of input; bcrypt>=5 raises instead of truncating.
BCRYPT_MAX_PASSWORD_BYTES = 72
MIN_SECRET_KEY_LENGTH = 32

@functools.lru_cache(maxsize=4)
def _dummy_password_hash(rounds: int) -> bytes:
    """
    Hash compared against when an account does not exist or has no usable password, so
    login latency does not reveal which emails are registered. Same cost as real hashes.
    """
    return bcrypt.hashpw(b"researchconnect-timing-guard", bcrypt.gensalt(rounds=rounds))


class TokenValidationError(Exception):
    """Raised when an access token is malformed, expired, or has an invalid signature."""


@dataclass(frozen=True)
class AccessTokenClaims:
    user_id: uuid.UUID
    issued_at: datetime
    expires_at: datetime


_ephemeral_secret: str | None = None


def get_signing_key() -> str:
    """
    Returns the JWT signing secret.

    In production a configured secret is mandatory. Elsewhere an ephemeral random key is
    generated once per process so development works without configuration.
    """
    global _ephemeral_secret
    if settings.auth_secret_key:
        return settings.auth_secret_key
    if settings.app_env == "production":
        raise RuntimeError("AUTH_SECRET_KEY must be set when APP_ENV=production.")
    if _ephemeral_secret is None:
        _ephemeral_secret = secrets.token_urlsafe(64)
        logger.warning(
            "AUTH_SECRET_KEY is not set; using an ephemeral signing key. "
            "Issued tokens become invalid when the server restarts."
        )
    return _ephemeral_secret


def validate_security_settings() -> None:
    """Fail fast on insecure configuration. Called once at application startup."""
    if settings.app_env != "production":
        return
    if len(settings.auth_secret_key) < MIN_SECRET_KEY_LENGTH:
        raise RuntimeError(
            f"AUTH_SECRET_KEY must be at least {MIN_SECRET_KEY_LENGTH} characters when APP_ENV=production."
        )
    if settings.auth_dev_identity_enabled:
        raise RuntimeError("AUTH_DEV_IDENTITY_ENABLED must be false when APP_ENV=production.")


def hash_password(password: str) -> str:
    encoded = password.encode("utf-8")
    if len(encoded) > BCRYPT_MAX_PASSWORD_BYTES:
        raise ValueError(f"Password must be at most {BCRYPT_MAX_PASSWORD_BYTES} bytes.")
    return bcrypt.hashpw(encoded, bcrypt.gensalt(rounds=settings.auth_bcrypt_rounds)).decode("ascii")


def verify_password(password: str, hashed_password: str | None) -> bool:
    """
    Constant-work password check. Accounts created before Phase 6 carry a non-bcrypt
    placeholder hash and can never authenticate with a password.
    """
    encoded = password.encode("utf-8")
    if len(encoded) > BCRYPT_MAX_PASSWORD_BYTES:
        return False
    candidate = (hashed_password or "").encode("ascii", errors="ignore")
    try:
        return bcrypt.checkpw(encoded, candidate)
    except ValueError:
        # Invalid or legacy placeholder hash: burn equivalent work, then reject.
        burn_password_check(password)
        return False


def burn_password_check(password: str) -> None:
    """Performs a throwaway bcrypt comparison (used when the account does not exist)."""
    bcrypt.checkpw(
        password.encode("utf-8")[:BCRYPT_MAX_PASSWORD_BYTES],
        _dummy_password_hash(settings.auth_bcrypt_rounds),
    )


def create_access_token(user_id: uuid.UUID, now: datetime | None = None) -> tuple[str, datetime]:
    """Issues a signed access token. Returns (token, expires_at)."""
    issued_at = (now or datetime.now(timezone.utc)).replace(microsecond=0)
    expires_at = issued_at + timedelta(minutes=settings.auth_access_token_expire_minutes)
    payload = {
        "sub": str(user_id),
        "iss": settings.auth_issuer,
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
        "type": "access",
    }
    token = jwt.encode(payload, get_signing_key(), algorithm=settings.auth_algorithm)
    return token, expires_at


def decode_access_token(token: str) -> AccessTokenClaims:
    try:
        payload = jwt.decode(
            token,
            get_signing_key(),
            algorithms=[settings.auth_algorithm],
            issuer=settings.auth_issuer,
            options={"require": ["sub", "exp", "iat", "iss"]},
        )
    except jwt.ExpiredSignatureError as err:
        raise TokenValidationError("Access token has expired.") from err
    except jwt.InvalidTokenError as err:
        raise TokenValidationError("Access token is invalid.") from err

    if payload.get("type") != "access":
        raise TokenValidationError("Access token is invalid.")
    try:
        user_id = uuid.UUID(str(payload["sub"]))
    except ValueError as err:
        raise TokenValidationError("Access token is invalid.") from err

    return AccessTokenClaims(
        user_id=user_id,
        issued_at=datetime.fromtimestamp(payload["iat"], tz=timezone.utc),
        expires_at=datetime.fromtimestamp(payload["exp"], tz=timezone.utc),
    )
