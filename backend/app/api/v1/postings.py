"""
FastAPI Router for Phase 5.10 Faculty Research Postings.

  GET    /postings                      Discover OPEN postings (public)
  GET    /postings/mine                 The author's own postings, drafts included
  GET    /postings/mine/summary         Aggregated counts for the author
  POST   /postings                      Author a posting as DRAFT (FACULTY / ADMIN)
  GET    /postings/{id}                 Read one (drafts visible only to their author)
  PATCH  /postings/{id}                 Edit (author only)
  POST   /postings/{id}/transition      Lifecycle transition (author only)
  DELETE /postings/{id}                 Delete a DRAFT (author only)
"""
from __future__ import annotations

import logging
from typing import Annotated
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, OptionalUserId, get_optional_current_user
from app.db.session import get_db
from app.models.research_posting import PostingStatus, PostingType, PostingWorkMode
from app.models.research_profile import ResearchProfileModel
from app.models.user import UserModel
from app.schemas.research_posting import (
    PostingStatusTransition,
    PostingSummaryResponse,
    ResearchPostingCreate,
    ResearchPostingListResponse,
    ResearchPostingRead,
    ResearchPostingUpdate,
)
from app.services.research_posting_service import (
    InvalidPostingTransitionError,
    PostingNotFoundError,
    PostingPermissionError,
    ResearchPostingService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/postings", tags=["postings"])

OptionalUser = Annotated[UserModel | None, Depends(get_optional_current_user)]


def _resolve_author_profile(db: Session, user: UserModel) -> ResearchProfileModel:
    """A posting is authored by an academic identity, so the account needs a profile."""
    profile = db.execute(
        select(ResearchProfileModel).where(ResearchProfileModel.user_id == user.id)
    ).scalar_one_or_none()
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Create a researcher profile before authoring postings.",
        )
    return profile


@router.get(
    "",
    response_model=ResearchPostingListResponse,
    status_code=status.HTTP_200_OK,
    summary="Discover research postings",
    description="Lists publicly open faculty research postings with filtering and pagination.",
)
def list_postings(
    posting_type: Annotated[PostingType | None, Query(description="Filter by posting category")] = None,
    country: Annotated[str | None, Query(min_length=2, max_length=2, description="ISO 3166-1 alpha-2")] = None,
    work_mode: Annotated[PostingWorkMode | None, Query(description="Filter by work mode")] = None,
    topic_id: Annotated[uuid.UUID | None, Query(description="Filter by canonical topic")] = None,
    search: Annotated[str | None, Query(max_length=200, description="Match title, summary or description")] = None,
    accepting_only: Annotated[bool, Query(description="Only postings whose deadline has not passed")] = False,
    sort_by: Annotated[str, Query(description="created_at, updated_at, application_deadline, title, application_count")] = "created_at",
    sort_order: Annotated[str, Query(description="asc or desc")] = "desc",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    current_user: OptionalUser = None,
    db: Session = Depends(get_db),
) -> ResearchPostingListResponse:
    return ResearchPostingService.list_postings(
        db,
        requesting_user=current_user,
        posting_type=posting_type,
        country=country,
        work_mode=work_mode.value if work_mode else None,
        topic_id=topic_id,
        search=search,
        accepting_only=accepting_only,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/mine",
    response_model=ResearchPostingListResponse,
    status_code=status.HTTP_200_OK,
    summary="List the authenticated author's postings",
    description="Lists every posting authored by the caller, including DRAFT and ARCHIVED entries.",
)
def list_my_postings(
    current_user: CurrentUser,
    posting_status: Annotated[PostingStatus | None, Query(alias="status", description="Filter by lifecycle state")] = None,
    posting_type: Annotated[PostingType | None, Query(description="Filter by posting category")] = None,
    sort_by: Annotated[str, Query()] = "updated_at",
    sort_order: Annotated[str, Query()] = "desc",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
) -> ResearchPostingListResponse:
    profile = _resolve_author_profile(db, current_user)
    return ResearchPostingService.list_postings(
        db,
        requesting_user=current_user,
        author_profile_id=profile.id,
        posting_type=posting_type,
        status=posting_status,
        include_own_drafts=True,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/mine/summary",
    response_model=PostingSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Summarize the authenticated author's postings",
)
def get_my_posting_summary(
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> PostingSummaryResponse:
    profile = _resolve_author_profile(db, current_user)
    return ResearchPostingService.get_author_summary(db, profile.id)


@router.post(
    "",
    response_model=ResearchPostingRead,
    status_code=status.HTTP_201_CREATED,
    summary="Author a research posting",
    description=(
        "Creates a posting as a DRAFT. Requires a FACULTY or ADMIN account; publishing is a "
        "separate lifecycle transition."
    ),
)
def create_posting(
    payload: ResearchPostingCreate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> ResearchPostingRead:
    profile = _resolve_author_profile(db, current_user)
    try:
        posting = ResearchPostingService.create_posting(db, profile, current_user, payload)
    except PostingPermissionError as err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(err))
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))
    return ResearchPostingService.build_posting_read(posting, requesting_user=current_user)


@router.get(
    "/{posting_id}",
    response_model=ResearchPostingRead,
    status_code=status.HTTP_200_OK,
    summary="Get a research posting",
    description="Reads one posting. Postings that are not OPEN are visible only to their author.",
)
def get_posting(
    posting_id: uuid.UUID,
    current_user: OptionalUser = None,
    db: Session = Depends(get_db),
) -> ResearchPostingRead:
    try:
        posting = ResearchPostingService.get_posting(db, posting_id, requesting_user=current_user)
    except PostingNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
    return ResearchPostingService.build_posting_read(posting, requesting_user=current_user)


@router.patch(
    "/{posting_id}",
    response_model=ResearchPostingRead,
    status_code=status.HTTP_200_OK,
    summary="Update a research posting",
)
def update_posting(
    posting_id: uuid.UUID,
    payload: ResearchPostingUpdate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> ResearchPostingRead:
    try:
        posting = ResearchPostingService.update_posting(db, posting_id, current_user, payload)
    except PostingNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
    except PostingPermissionError as err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(err))
    except InvalidPostingTransitionError as err:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(err))
    return ResearchPostingService.build_posting_read(posting, requesting_user=current_user)


@router.post(
    "/{posting_id}/transition",
    response_model=ResearchPostingRead,
    status_code=status.HTTP_200_OK,
    summary="Transition a posting's lifecycle state",
    description="Applies a deterministic lifecycle transition, e.g. DRAFT to OPEN to FILLED.",
)
def transition_posting(
    posting_id: uuid.UUID,
    payload: PostingStatusTransition,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> ResearchPostingRead:
    try:
        posting = ResearchPostingService.transition_status(
            db, posting_id, current_user, payload.target_status, note=payload.note
        )
    except PostingNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
    except PostingPermissionError as err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(err))
    except InvalidPostingTransitionError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))
    return ResearchPostingService.build_posting_read(posting, requesting_user=current_user)


@router.delete(
    "/{posting_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a draft posting",
    description="Deletes a DRAFT posting. Published postings must be cancelled and archived instead.",
)
def delete_posting(
    posting_id: uuid.UUID,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> Response:
    try:
        ResearchPostingService.delete_posting(db, posting_id, current_user)
    except PostingNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
    except PostingPermissionError as err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(err))
    except InvalidPostingTransitionError as err:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(err))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
