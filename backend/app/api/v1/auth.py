"""
Phase 6 — Authentication API.

  POST /auth/register  Create an account + researcher profile, returns an access token
  POST /auth/login     Exchange email + password for an access token (rate limited)
  GET  /auth/me        The authenticated caller's account
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser
from app.core.rate_limiter import get_client_ip, login_rate_limiter
from app.core.security import create_access_token
from app.db.session import get_db
from app.schemas.auth import AuthenticatedUser, LoginRequest, RegisterRequest, TokenResponse
from app.services.auth_service import (
    AuthService,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


def enforce_login_rate_limit(request: Request) -> None:
    status_info = login_rate_limiter.check(f"auth:{get_client_ip(request)}")
    if not status_info.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many authentication attempts. Please wait and try again.",
            headers={"Retry-After": str(status_info.reset_after_seconds)},
        )


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new account",
    description="Creates a STUDENT or FACULTY account with a researcher profile and returns an access token.",
    dependencies=[Depends(enforce_login_rate_limit)],
)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    try:
        user = AuthService.register(db, payload)
    except EmailAlreadyRegisteredError as err:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(err))
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))

    token, expires_at = create_access_token(user.id)
    return TokenResponse(
        access_token=token,
        expires_at=expires_at,
        user=AuthService.build_authenticated_user(db, user),
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Log in",
    description="Verifies email and password and returns a signed bearer access token.",
    dependencies=[Depends(enforce_login_rate_limit)],
)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    try:
        user = AuthService.authenticate(db, payload.email, payload.password)
    except InvalidCredentialsError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(err),
            headers={"WWW-Authenticate": "Bearer"},
        )

    token, expires_at = create_access_token(user.id)
    logger.info("Login succeeded", extra={"login_user_id": str(user.id)})
    return TokenResponse(
        access_token=token,
        expires_at=expires_at,
        user=AuthService.build_authenticated_user(db, user),
    )


@router.get(
    "/me",
    response_model=AuthenticatedUser,
    status_code=status.HTTP_200_OK,
    summary="Get the authenticated account",
)
def get_me(user: CurrentUser, db: Session = Depends(get_db)) -> AuthenticatedUser:
    return AuthService.build_authenticated_user(db, user)
