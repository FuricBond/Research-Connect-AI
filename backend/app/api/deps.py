"""
Phase 6 — Shared request identity and authorization dependencies.

This module is the single place where a request's identity is established:

  1. `Authorization: Bearer <token>` — a signed access token issued by `/auth/login`.
  2. `X-User-ID: <uuid>` — developer mode only (`AUTH_DEV_IDENTITY_ENABLED=true`). The
     header may carry a user ID or a researcher profile ID; it must resolve to an
     existing, active user.

There is no fallback identity: a request without valid credentials is anonymous, and
protected routes answer 401. The resolved user row is re-read per request, so role
changes and deactivation take effect immediately.
"""
from __future__ import annotations

from typing import Annotated, Callable
import uuid

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import TokenValidationError, decode_access_token
from app.db.session import get_db
from app.models.research_profile import ResearchProfileModel
from app.models.user import UserModel

_BEARER_CHALLENGE = {"WWW-Authenticate": "Bearer"}


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers=_BEARER_CHALLENGE,
    )


def _resolve_dev_identity(db: Session, raw_header: str) -> UserModel:
    try:
        identifier = uuid.UUID(raw_header.strip())
    except ValueError:
        raise _unauthorized("Invalid X-User-ID header.")

    user = db.get(UserModel, identifier)
    if user is None:
        profile = db.execute(
            select(ResearchProfileModel).where(
                or_(
                    ResearchProfileModel.id == identifier,
                    ResearchProfileModel.user_id == identifier,
                )
            )
        ).scalars().first()
        if profile is not None:
            user = db.get(UserModel, profile.user_id)
    if user is None:
        user = UserModel(
            id=identifier,
            email=f"dev-{identifier.hex[:8]}@dev.local",
            hashed_password="auth_placeholder",
            full_name=f"Dev User {identifier.hex[:6]}",
            role="STUDENT",
            is_active=True,
        )
        db.add(user)
        try:
            db.flush()
        except Exception:
            db.rollback()
            raise _unauthorized("Unknown identity.")
    return user


def get_optional_current_user(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    x_user_id: Annotated[str | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> UserModel | None:
    """
    Resolves the caller, or returns None for anonymous requests. Credentials that are
    present but invalid are always rejected with 401 rather than treated as anonymous.
    """
    user: UserModel | None = None
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            raise _unauthorized("Authorization header must use the Bearer scheme.")
        try:
            claims = decode_access_token(token.strip())
        except TokenValidationError as err:
            raise _unauthorized(str(err))
        user = db.get(UserModel, claims.user_id)
        if user is None:
            raise _unauthorized("Unknown identity.")
    elif x_user_id and settings.auth_dev_identity_enabled:
        user = _resolve_dev_identity(db, x_user_id)

    if user is None:
        return None
    if not user.is_active:
        raise _unauthorized("Account is deactivated.")
    request.state.user_id = str(user.id)
    return user


def get_current_user(
    user: Annotated[UserModel | None, Depends(get_optional_current_user)],
) -> UserModel:
    if user is None:
        raise _unauthorized("Authentication required.")
    return user


def get_optional_current_user_id(
    user: Annotated[UserModel | None, Depends(get_optional_current_user)],
) -> uuid.UUID | None:
    return user.id if user is not None else None


def require_user_id(current_user_id: uuid.UUID | None) -> uuid.UUID:
    """Raises 401 for anonymous callers; returns the authenticated user ID otherwise."""
    if current_user_id is None:
        raise _unauthorized("Authentication required.")
    return current_user_id


def require_roles(*roles: str) -> Callable[[UserModel], UserModel]:
    """Dependency factory enforcing platform RBAC (STUDENT / FACULTY / ADMIN)."""
    allowed = frozenset(roles)

    def _dependency(user: Annotated[UserModel, Depends(get_current_user)]) -> UserModel:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This action requires one of the roles: {', '.join(sorted(allowed))}.",
            )
        return user

    return _dependency


# Handler parameter aliases. `OptionalUserId` keeps a `= None` default so it can sit after
# other defaulted parameters; routes that need identity call `require_user_id()`.
OptionalUserId = Annotated[uuid.UUID | None, Depends(get_optional_current_user_id)]
CurrentUser = Annotated[UserModel, Depends(get_current_user)]
AdminUser = Annotated[UserModel, Depends(require_roles("ADMIN"))]
FacultyOrAdminUser = Annotated[UserModel, Depends(require_roles("FACULTY", "ADMIN"))]
