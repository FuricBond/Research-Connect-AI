"""
Phase 6 — Authentication primitives: password hashing and signed access tokens.

Passwords are hashed with bcrypt. Access tokens are HS256 JWTs carrying the user ID
as `sub`. Authorization decisions never trust claims beyond `sub`: the user row (role,
is_active) is re-read on every request so role changes and deactivation apply at once.
Phase 6.7 adds `ver`, the account's token_version at issue; a token whose version no longer
matches the row (after sign-out, a password change or deactivation) is refused.
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
from sqlalchemy.engine import make_url

from app.core.config import DEVELOPMENT_DATABASE_URL, settings

logger = logging.getLogger(__name__)

# bcrypt only reads the first 72 bytes of input; bcrypt>=5 raises instead of truncating.
BCRYPT_MAX_PASSWORD_BYTES = 72
MIN_SECRET_KEY_LENGTH = 32
# A generated secret (secrets.token_urlsafe, openssl rand -hex) easily clears this; a
# placeholder such as "changeme" repeated to length does not.
MIN_SECRET_KEY_DISTINCT_CHARACTERS = 10
MIN_PRODUCTION_BCRYPT_ROUNDS = 10

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
    # Phase 6.7: the account's token_version when the token was issued ("ver"; 0 if absent).
    token_version: int = 0


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


def _uses_development_database_credentials(database_url: str) -> bool:
    try:
        configured = make_url(database_url)
    except Exception:
        return False  # an unparsable URL fails when the engine connects
    development_password = make_url(DEVELOPMENT_DATABASE_URL).password
    return configured.password is not None and configured.password == development_password


def validate_security_settings() -> None:
    """
    Fail fast on insecure configuration. Called once at application startup.

    Outside production nothing is enforced here (range and format checks live on the
    Settings fields and apply everywhere). In production every problem is reported at
    once, so an operator can fix the configuration in one pass.
    """
    if settings.app_env != "production":
        return

    problems: list[str] = []
    secret = settings.auth_secret_key
    if len(secret) < MIN_SECRET_KEY_LENGTH:
        problems.append(f"AUTH_SECRET_KEY must be at least {MIN_SECRET_KEY_LENGTH} characters")
    elif len(set(secret)) < MIN_SECRET_KEY_DISTINCT_CHARACTERS:
        problems.append(
            "AUTH_SECRET_KEY is too repetitive to be a generated secret "
            '(generate one with: python -c "import secrets; print(secrets.token_urlsafe(64))")'
        )
    if settings.auth_dev_identity_enabled:
        problems.append("AUTH_DEV_IDENTITY_ENABLED must be false")
    if settings.auth_bcrypt_rounds < MIN_PRODUCTION_BCRYPT_ROUNDS:
        problems.append(f"AUTH_BCRYPT_ROUNDS must be at least {MIN_PRODUCTION_BCRYPT_ROUNDS}")
    if _uses_development_database_credentials(settings.database_url):
        problems.append(
            "DATABASE_URL must be set explicitly; the built-in development credentials are not "
            "accepted"
        )
    if (
        settings.email_provider == "smtp"
        and settings.smtp_security == "none"
        and settings.smtp_username.strip()
    ):
        # Phase 5.16: the SMTP login would cross the network unencrypted.
        problems.append("SMTP_SECURITY must be starttls or ssl when SMTP_USERNAME is set")
    if problems:
        raise RuntimeError("Refusing to start with APP_ENV=production: " + "; ".join(problems) + ".")

    if settings.log_level == "DEBUG":
        logger.warning(
            "LOG_LEVEL=DEBUG with APP_ENV=production: debug logs can include request data and "
            "full database error details"
        )


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


def create_access_token(
    user_id: uuid.UUID,
    now: datetime | None = None,
    token_version: int = 0,
) -> tuple[str, datetime]:
    """
    Issues a signed access token. Returns (token, expires_at). `token_version` is the
    account's current users.token_version; the token stops working once that moves on.
    """
    issued_at = (now or datetime.now(timezone.utc)).replace(microsecond=0)
    expires_at = issued_at + timedelta(minutes=settings.auth_access_token_expire_minutes)
    payload = {
        "sub": str(user_id),
        "iss": settings.auth_issuer,
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
        "type": "access",
        "ver": token_version,
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

    # Tokens issued before Phase 6.7 have no "ver" and count as version 0.
    token_version = payload.get("ver", 0)
    if isinstance(token_version, bool) or not isinstance(token_version, int) or token_version < 0:
        raise TokenValidationError("Access token is invalid.")

    return AccessTokenClaims(
        user_id=user_id,
        issued_at=datetime.fromtimestamp(payload["iat"], tz=timezone.utc),
        expires_at=datetime.fromtimestamp(payload["exp"], tz=timezone.utc),
        token_version=token_version,
    )
