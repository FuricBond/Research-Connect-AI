"""
FastAPI Router for Phase 4.2 Research Submission Management & Tracking.

Provides researcher-scoped submission endpoints:
  - Creating submissions for workspace items
  - Listing submissions with status/type/workspace filters & pagination
  - Summary metrics across submission lifecycle states
  - Retrieving and modifying submission draft metadata
  - Deterministic state machine status transitions
  - Deleting submissions (DRAFT or WITHDRAWN only)
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
from app.models.research_submission import SubmissionStatus, SubmissionType
from app.models.user import UserModel
from app.schemas.research_submission import (
    ResearchSubmissionCreate,
    ResearchSubmissionListResponse,
    ResearchSubmissionRead,
    ResearchSubmissionUpdate,
    SubmissionStatusTransition,
    SubmissionSummaryResponse,
)
from app.services.research_submission_service import (
    InvalidSubmissionTransitionError,
    ResearchSubmissionService,
)
from app.services.workspace_service import WorkspaceService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/submissions", tags=["submissions"])


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
    response_model=ResearchSubmissionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create research submission",
    description="Create a structured research submission tracker for an opportunity in the researcher's workspace.",
)
def create_submission(
    payload: ResearchSubmissionCreate,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> ResearchSubmissionRead:
    user_id = resolve_current_user(db, x_user_id)
    try:
        submission = ResearchSubmissionService.create_submission(db, user_id, payload)
        return ResearchSubmissionService.build_submission_read(submission)
    except PermissionError as err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(err))
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))


@router.get(
    "",
    response_model=ResearchSubmissionListResponse,
    status_code=status.HTTP_200_OK,
    summary="List research submissions",
    description="List researcher-scoped submissions with filtering by status, submission type, workspace item, and search.",
)
def list_submissions(
    status_filter: Annotated[SubmissionStatus | None, Query(alias="status", description="Filter by submission status")] = None,
    submission_type: Annotated[SubmissionType | None, Query(description="Filter by submission type")] = None,
    workspace_item_id: Annotated[uuid.UUID | None, Query(description="Filter by linked workspace item")] = None,
    search: Annotated[str | None, Query(description="Search in title, venue, tracking ID, or notes")] = None,
    sort_by: Annotated[str, Query(description="Sort field: updated_at, created_at, submitted_at, decision_at, status")] = "updated_at",
    sort_order: Annotated[str, Query(description="Sort order: asc, desc")] = "desc",
    limit: Annotated[int, Query(ge=1, le=100, description="Page size limit")] = 50,
    offset: Annotated[int, Query(ge=0, description="Offset")] = 0,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> ResearchSubmissionListResponse:
    user_id = resolve_current_user(db, x_user_id)
    return ResearchSubmissionService.list_submissions(
        db=db,
        user_id=user_id,
        status=status_filter,
        submission_type=submission_type,
        workspace_item_id=workspace_item_id,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/summary",
    response_model=SubmissionSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get submission summary statistics",
    description="Get statistical counts of research submissions grouped by status and submission type.",
)
def get_submission_summary(
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> SubmissionSummaryResponse:
    user_id = resolve_current_user(db, x_user_id)
    return ResearchSubmissionService.get_summary(db, user_id)


@router.get(
    "/{submission_id}",
    response_model=ResearchSubmissionRead,
    status_code=status.HTTP_200_OK,
    summary="Get single research submission",
    description="Retrieve a single research submission by ID with allowed transitions and deadline context.",
)
def get_submission(
    submission_id: uuid.UUID,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> ResearchSubmissionRead:
    user_id = resolve_current_user(db, x_user_id)
    try:
        submission = ResearchSubmissionService.get_submission(db, user_id, submission_id)
        if submission is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Submission with ID '{submission_id}' not found.",
            )
        return ResearchSubmissionService.build_submission_read(submission)
    except PermissionError as err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(err))


@router.patch(
    "/{submission_id}",
    response_model=ResearchSubmissionRead,
    status_code=status.HTTP_200_OK,
    summary="Update research submission metadata",
    description="Update metadata (title, abstract, tracking ID, portal URL, venue, notes) for a research submission.",
)
def update_submission(
    submission_id: uuid.UUID,
    payload: ResearchSubmissionUpdate,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> ResearchSubmissionRead:
    user_id = resolve_current_user(db, x_user_id)
    try:
        updated = ResearchSubmissionService.update_submission(db, user_id, submission_id, payload)
        return ResearchSubmissionService.build_submission_read(updated)
    except PermissionError as err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(err))
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))


@router.post(
    "/{submission_id}/transition",
    response_model=ResearchSubmissionRead,
    status_code=status.HTTP_200_OK,
    summary="Transition research submission status",
    description="Transition a research submission across valid workflow stages using the deterministic state machine.",
)
def transition_submission_status(
    submission_id: uuid.UUID,
    payload: SubmissionStatusTransition,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> ResearchSubmissionRead:
    user_id = resolve_current_user(db, x_user_id)
    try:
        item = ResearchSubmissionService.transition_status(
            db=db,
            user_id=user_id,
            submission_id=submission_id,
            target_status=payload.target_status,
            notes=payload.notes,
        )
        return ResearchSubmissionService.build_submission_read(item)
    except PermissionError as err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(err))
    except InvalidSubmissionTransitionError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))


@router.delete(
    "/{submission_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete research submission",
    description="Permanently delete a submission (allowed only in DRAFT or WITHDRAWN state).",
)
def delete_submission(
    submission_id: uuid.UUID,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> Response:
    user_id = resolve_current_user(db, x_user_id)
    try:
        ResearchSubmissionService.delete_submission(db, user_id, submission_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except PermissionError as err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(err))
    except InvalidSubmissionTransitionError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
