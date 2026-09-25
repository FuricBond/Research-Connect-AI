"""
Phase 6 — Platform administration API (ADMIN role only).

  GET   /admin/users            List accounts (filter by role, search by email/name)
  PATCH /admin/users/{user_id}  Change role, activation, or verification status
"""
from __future__ import annotations

from typing import Annotated
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import AdminUser
from app.db.session import get_db
from app.schemas.auth import AdminUserListResponse, AdminUserRead, AdminUserUpdate, PlatformRole
from app.services.auth_service import AuthService, LastAdministratorError

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get(
    "/users",
    response_model=AdminUserListResponse,
    status_code=status.HTTP_200_OK,
    summary="List platform accounts",
)
def list_users(
    admin: AdminUser,
    role: Annotated[PlatformRole | None, Query(description="Filter by platform role")] = None,
    search: Annotated[str | None, Query(max_length=255, description="Match email or name")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
) -> AdminUserListResponse:
    return AuthService.list_users(db, role=role, search=search, limit=limit, offset=offset)


@router.patch(
    "/users/{user_id}",
    response_model=AdminUserRead,
    status_code=status.HTTP_200_OK,
    summary="Update an account's role or status",
)
def update_user(
    user_id: uuid.UUID,
    payload: AdminUserUpdate,
    admin: AdminUser,
    db: Session = Depends(get_db),
) -> AdminUserRead:
    try:
        user = AuthService.update_user(db, admin, user_id, payload)
    except LookupError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
    except LastAdministratorError as err:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(err))
    return AdminUserRead.model_validate(user)
