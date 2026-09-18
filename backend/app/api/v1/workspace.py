"""
FastAPI Router for Phase 4.1 Opportunity Workspace.

Provides researcher-scoped workspace endpoints:
  - Adding opportunities to workspace (SAVED)
  - Listing workspace opportunities with filtering & pagination
  - Summary metrics across statuses and priorities
  - Retrieving and modifying workspace item metadata
  - Deterministic state machine status transitions
  - Archiving and unarchiving
  - Deleting/removing from workspace
  - Enforcing strict researcher isolation via X-User-ID header
"""
from __future__ import annotations

import logging
from typing import Annotated
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.saved_opportunity import SavedOpportunityModel
from app.models.user import UserModel
from app.schemas.workspace import (
    WorkspaceItemCreate,
    WorkspaceItemRead,
    WorkspaceItemUpdate,
    WorkspaceListResponse,
    WorkspacePriority,
    WorkspaceStatus,
    WorkspaceStatusTransition,
    WorkspaceSummaryResponse,
)
from app.services.workspace_service import InvalidTransitionError, WorkspaceService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workspace", tags=["workspace"])


def resolve_current_user(
    db: Session,
    x_user_id: uuid.UUID | None,
) -> uuid.UUID:
    """
    Resolves the authenticated user ID from the X-User-ID header or falls back to
    the single active user in developer mode.
    """
    if x_user_id is not None:
        return WorkspaceService.resolve_user_id(db, x_user_id)

    # Fallback in demo/local development if no X-User-ID is explicitly provided
    fallback_user = db.execute(
        select(UserModel).order_by(UserModel.created_at.asc())
    ).scalars().first()
    if fallback_user is not None:
        return fallback_user.id

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required: Please provide an 'X-User-ID' header.",
    )


@router.post(
    "",
    response_model=WorkspaceItemRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add opportunity to workspace",
    description="Add an academic opportunity to the researcher workspace with initial workflow state (default: SAVED).",
)
def add_to_workspace(
    payload: WorkspaceItemCreate,
    response: Response,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> WorkspaceItemRead:
    user_id = resolve_current_user(db, x_user_id)
    try:
        item, is_new = WorkspaceService.add_opportunity(db, user_id, payload)
        if not is_new:
            response.status_code = status.HTTP_200_OK
        return WorkspaceService.build_workspace_item_read(item)
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))


@router.get(
    "",
    response_model=WorkspaceListResponse,
    status_code=status.HTTP_200_OK,
    summary="List workspace opportunities",
    description="List researcher-scoped workspace opportunities with filtering by status, priority, tags, and search.",
)
def list_workspace(
    status_filter: Annotated[WorkspaceStatus | None, Query(alias="status", description="Filter by workflow state")] = None,
    priority: Annotated[WorkspacePriority | None, Query(description="Filter by priority rating")] = None,
    tag: Annotated[str | None, Query(description="Filter by exact tag")] = None,
    search: Annotated[str | None, Query(description="Search in opportunity title or notes")] = None,
    include_archived: Annotated[bool, Query(description="Whether to include ARCHIVED items")] = False,
    sort_by: Annotated[str, Query(description="Sort field: updated_at, created_at, deadline, priority, status")] = "updated_at",
    sort_order: Annotated[str, Query(description="Sort order: asc, desc")] = "desc",
    limit: Annotated[int, Query(ge=1, le=100, description="Page size limit")] = 50,
    offset: Annotated[int, Query(ge=0, description="Offset")] = 0,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> WorkspaceListResponse:
    user_id = resolve_current_user(db, x_user_id)
    return WorkspaceService.list_workspace_items(
        db=db,
        user_id=user_id,
        status=status_filter,
        priority=priority,
        tag=tag,
        search=search,
        include_archived=include_archived,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/summary",
    response_model=WorkspaceSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get workspace summary",
    description="Get statistical counts of items grouped by status and priority for the authenticated researcher.",
)
def get_workspace_summary(
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> WorkspaceSummaryResponse:
    user_id = resolve_current_user(db, x_user_id)
    return WorkspaceService.get_summary(db, user_id)


@router.get(
    "/{item_id}",
    response_model=WorkspaceItemRead,
    status_code=status.HTTP_200_OK,
    summary="Get single workspace item",
    description="Retrieve a single workspace item with canonical opportunity details and allowed workflow transitions.",
)
def get_workspace_item(
    item_id: uuid.UUID,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> WorkspaceItemRead:
    user_id = resolve_current_user(db, x_user_id)
    try:
        item = WorkspaceService.get_workspace_item(db, user_id, item_id)
        if item is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Workspace item with ID '{item_id}' not found.",
            )
        return WorkspaceService.build_workspace_item_read(item)
    except PermissionError as err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(err))


@router.patch(
    "/{item_id}",
    response_model=WorkspaceItemRead,
    status_code=status.HTTP_200_OK,
    summary="Update workspace item metadata",
    description="Partially update metadata (priority, notes, tags) for a workspace item.",
)
def update_workspace_item(
    item_id: uuid.UUID,
    payload: WorkspaceItemUpdate,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> WorkspaceItemRead:
    user_id = resolve_current_user(db, x_user_id)
    try:
        updated = WorkspaceService.update_workspace_item(db, user_id, item_id, payload)
        return WorkspaceService.build_workspace_item_read(updated)
    except PermissionError as err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(err))
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))


@router.post(
    "/{item_id}/transition",
    response_model=WorkspaceItemRead,
    status_code=status.HTTP_200_OK,
    summary="Transition workspace status",
    description="Transition a workspace opportunity across valid workflow stages using the deterministic state machine.",
)
def transition_workspace_status(
    item_id: uuid.UUID,
    payload: WorkspaceStatusTransition,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> WorkspaceItemRead:
    user_id = resolve_current_user(db, x_user_id)
    try:
        item = WorkspaceService.transition_status(
            db=db,
            user_id=user_id,
            item_id=item_id,
            target_status=payload.target_status,
            notes=payload.notes,
        )
        return WorkspaceService.build_workspace_item_read(item)
    except PermissionError as err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(err))
    except InvalidTransitionError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))


@router.post(
    "/{item_id}/archive",
    response_model=WorkspaceItemRead,
    status_code=status.HTTP_200_OK,
    summary="Archive workspace item",
    description="Move an active workspace opportunity to ARCHIVED status.",
)
def archive_workspace_item(
    item_id: uuid.UUID,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> WorkspaceItemRead:
    user_id = resolve_current_user(db, x_user_id)
    try:
        item = WorkspaceService.archive_item(db, user_id, item_id)
        return WorkspaceService.build_workspace_item_read(item)
    except PermissionError as err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(err))
    except InvalidTransitionError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))


@router.post(
    "/{item_id}/unarchive",
    response_model=WorkspaceItemRead,
    status_code=status.HTTP_200_OK,
    summary="Unarchive workspace item",
    description="Restore an archived workspace opportunity back to an active state (default: SAVED).",
)
def unarchive_workspace_item(
    item_id: uuid.UUID,
    target_status: Annotated[WorkspaceStatus, Query(description="Target active state")] = WorkspaceStatus.SAVED,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> WorkspaceItemRead:
    user_id = resolve_current_user(db, x_user_id)
    try:
        item = WorkspaceService.unarchive_item(db, user_id, item_id, target_status)
        return WorkspaceService.build_workspace_item_read(item)
    except PermissionError as err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(err))
    except InvalidTransitionError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))


@router.delete(
    "/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove opportunity from workspace",
    description="Permanently remove an opportunity from the researcher workspace.",
)
def remove_from_workspace(
    item_id: uuid.UUID,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> Response:
    user_id = resolve_current_user(db, x_user_id)
    try:
        WorkspaceService.remove_item(db, user_id, item_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except PermissionError as err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(err))
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
