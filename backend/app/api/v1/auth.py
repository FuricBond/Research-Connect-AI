"""
Phase 6 — Authentication API.

  POST /auth/register  Create an account + researcher profile, returns an access token
  POST /auth/login     Exchange email + password for an access token (rate limited)
  GET  /auth/me        The authenticated caller's account
  POST /auth/logout    Revoke every token issued to the caller so far (Phase 6.7)
  POST /auth/change-password
                       Replace the caller's password, revoke their tokens and return a new one
                       (Phase 6.7, rate limited)
  POST /auth/email-verification
                       Email the caller a link that confirms their address (Decision C, rate limited)
  POST /auth/email-verification/confirm
                       Confirm the caller's address with that link's token (rate limited)
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser
from app.core.rate_limiter import email_verification_rate_limiter, get_client_ip, login_rate_limiter
from app.core.security import create_access_token
from app.db.session import get_db
from app.schemas.auth import (
    AuthenticatedUser,
    ChangePasswordRequest,
    EmailVerificationConfirm,
    EmailVerificationRequestResponse,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
)
from app.services.auth_service import (
    AuthService,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
)
from app.services.email_verification_service import (
    EmailDeliveryFailedError,
    EmailDeliveryUnavailableError,
    EmailVerificationService,
    InvalidEmailConfirmationError,
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


def _enforce_email_verification_rate_limit(user: CurrentUser) -> None:
    """Per account: each attempt can put a message in someone's mailbox."""
    status_info = email_verification_rate_limiter.check(f"account:{user.id}")
    if not status_info.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many confirmation attempts. Please wait a few minutes and try again.",
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

    token, expires_at = create_access_token(user.id, token_version=user.token_version)
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

    token, expires_at = create_access_token(user.id, token_version=user.token_version)
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


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Sign out everywhere",
    description=(
        "Phase 6.7: revokes every access token issued to the caller so far, including the one "
        "used for this request. Sign in again for a new token."
    ),
)
def logout(user: CurrentUser, db: Session = Depends(get_db)) -> Response:
    AuthService.revoke_tokens(db, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/email-verification",
    response_model=EmailVerificationRequestResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Email a link that confirms the caller's address",
    description=(
        "Decision C: sends a one-time link, valid for 24 hours, to the account's own address. A new "
        "request replaces the earlier link. Answers 503 when this server cannot mail the address."
    ),
    dependencies=[Depends(_enforce_email_verification_rate_limit)],
)
def request_email_verification(user: CurrentUser, db: Session = Depends(get_db)) -> EmailVerificationRequestResponse:
    try:
        sent = EmailVerificationService.request_confirmation(db, user)
    except EmailDeliveryUnavailableError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="This server cannot send email to your address, so it cannot be confirmed yet. Please contact an administrator.",
        )
    except EmailDeliveryFailedError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The confirmation email could not be sent just now. Try again in a few minutes.",
        )
    return EmailVerificationRequestResponse(status="SENT" if sent else "ALREADY_VERIFIED")


@router.post(
    "/email-verification/confirm",
    response_model=AuthenticatedUser,
    status_code=status.HTTP_200_OK,
    summary="Confirm the caller's address",
    description=(
        "Decision C: needs the link's token and the signed-in account that asked for it. Any other "
        "token (unknown, expired, used, another account's) gets the same answer."
    ),
    dependencies=[Depends(_enforce_email_verification_rate_limit)],
)
def confirm_email_verification(
    payload: EmailVerificationConfirm,
    user: CurrentUser,
    db: Session = Depends(get_db),
) -> AuthenticatedUser:
    try:
        confirmed = EmailVerificationService.confirm(db, user, payload.token)
    except InvalidEmailConfirmationError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This link does not confirm this account's address: it may have expired, been replaced or already been used, or belong to another account.",
        )
    return AuthService.build_authenticated_user(db, confirmed)


@router.post(
    "/change-password",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Change password",
    description=(
        "Phase 6.7: checks the current password, applies the registration password rules to the "
        "new one, revokes every earlier token and returns a fresh one. Rate limited like login."
    ),
    dependencies=[Depends(enforce_login_rate_limit)],
)
def change_password(
    payload: ChangePasswordRequest,
    user: CurrentUser,
    db: Session = Depends(get_db),
) -> TokenResponse:
    try:
        user = AuthService.change_password(db, user, payload.current_password, payload.new_password)
    except InvalidCredentialsError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))

    token, expires_at = create_access_token(user.id, token_version=user.token_version)
    return TokenResponse(
        access_token=token,
        expires_at=expires_at,
        user=AuthService.build_authenticated_user(db, user),
    )
