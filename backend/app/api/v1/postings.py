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

Phase 5.11 — applications to research openings:

  POST /postings/{id}/applications              Apply to an open funded opening
  GET  /postings/{id}/applications              Review applications (author only)
  GET  /postings/applications/mine              The applicant's own applications
  GET  /postings/applications/mine/summary      Counts by status for the applicant
  GET  /postings/applications/{id}              Read one (applicant or author)
  POST /postings/applications/{id}/transition   Advance it, role-partitioned
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
from app.models.research_posting_application import (
    ApplicationStatus,
    ResearchPostingApplicationModel,
)
from app.schemas.research_posting_application import (
    ApplicationCreate,
    ApplicationDecision,
    ApplicationListResponse,
    ApplicationRead,
    ApplicationSummaryResponse,
)
from app.services.research_posting_application_service import (
    ApplicationNotAcceptedError,
    ApplicationNotFoundError,
    ApplicationPermissionError,
    DuplicateApplicationError,
    InvalidApplicationTransitionError,
    ResearchPostingApplicationService,
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


def _resolve_researcher_profile(db: Session, user: UserModel) -> ResearchProfileModel:
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
    profile = _resolve_researcher_profile(db, current_user)
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
    profile = _resolve_researcher_profile(db, current_user)
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
    profile = _resolve_researcher_profile(db, current_user)
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

    # Surface the reader's own application, if any, so the page can show its status instead of
    # offering an "Apply" button that would be refused as a duplicate.
    viewer_application_id = None
    viewer_application_status = None
    if current_user is not None:
        own = db.execute(
            select(
                ResearchPostingApplicationModel.id,
                ResearchPostingApplicationModel.status,
            ).where(
                ResearchPostingApplicationModel.posting_id == posting_id,
                ResearchPostingApplicationModel.applicant_user_id == current_user.id,
            )
        ).first()
        if own is not None:
            viewer_application_id, viewer_application_status = own

    return ResearchPostingService.build_posting_read(
        posting,
        requesting_user=current_user,
        viewer_application_id=viewer_application_id,
        viewer_application_status=viewer_application_status,
    )


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


# ============================================================================
# Phase 5.11 — Applications to research openings
# ============================================================================


@router.post(
    "/{posting_id}/applications",
    response_model=ApplicationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Apply to a research opening",
    description=(
        "Submits an application to an OPEN internship, assistantship or post-doc opening that "
        "handles applications on the platform. Re-applying after withdrawing reuses the same record."
    ),
)
def apply_to_posting(
    posting_id: uuid.UUID,
    payload: ApplicationCreate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> ApplicationRead:
    profile = _resolve_researcher_profile(db, current_user)
    try:
        application = ResearchPostingApplicationService.submit_application(
            db, posting_id, profile, current_user, payload
        )
    except ApplicationNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
    except ApplicationPermissionError as err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(err))
    except DuplicateApplicationError as err:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(err))
    except ApplicationNotAcceptedError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))
    return ResearchPostingApplicationService.build_application_read(
        application, current_user, "APPLICANT"
    )


@router.get(
    "/{posting_id}/applications",
    response_model=ApplicationListResponse,
    status_code=status.HTTP_200_OK,
    summary="Review applications to a posting",
    description="Lists a posting's applications. Restricted to the posting's author.",
)
def list_posting_applications(
    posting_id: uuid.UUID,
    current_user: CurrentUser,
    application_status: Annotated[
        ApplicationStatus | None, Query(alias="status", description="Filter by application status")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
) -> ApplicationListResponse:
    try:
        return ResearchPostingApplicationService.list_applications_for_posting(
            db, posting_id, current_user, status=application_status, limit=limit, offset=offset
        )
    except ApplicationNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
    except ApplicationPermissionError as err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(err))


@router.get(
    "/applications/mine",
    response_model=ApplicationListResponse,
    status_code=status.HTTP_200_OK,
    summary="List the authenticated researcher's applications",
)
def list_my_applications(
    current_user: CurrentUser,
    application_status: Annotated[
        ApplicationStatus | None, Query(alias="status", description="Filter by application status")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
) -> ApplicationListResponse:
    profile = _resolve_researcher_profile(db, current_user)
    return ResearchPostingApplicationService.list_my_applications(
        db, profile.id, current_user, status=application_status, limit=limit, offset=offset
    )


@router.get(
    "/applications/mine/summary",
    response_model=ApplicationSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Summarize the authenticated researcher's applications",
)
def get_my_application_summary(
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> ApplicationSummaryResponse:
    profile = _resolve_researcher_profile(db, current_user)
    return ResearchPostingApplicationService.summarize_my_applications(db, profile.id)


@router.get(
    "/applications/{application_id}",
    response_model=ApplicationRead,
    status_code=status.HTTP_200_OK,
    summary="Get an application",
    description=(
        "Readable by the applicant and by the posting's author. The author's private reviewer "
        "note is never returned to the applicant."
    ),
)
def get_application(
    application_id: uuid.UUID,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> ApplicationRead:
    try:
        application, actor_role = ResearchPostingApplicationService.get_application(
            db, application_id, current_user
        )
    except ApplicationNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
    return ResearchPostingApplicationService.build_application_read(
        application, current_user, actor_role
    )


@router.post(
    "/applications/{application_id}/transition",
    response_model=ApplicationRead,
    status_code=status.HTTP_200_OK,
    summary="Advance an application",
    description=(
        "Applies a lifecycle transition. Review decisions belong to the posting's author; "
        "withdrawal and the response to an offer belong to the applicant."
    ),
)
def transition_application(
    application_id: uuid.UUID,
    payload: ApplicationDecision,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> ApplicationRead:
    try:
        _, actor_role = ResearchPostingApplicationService.get_application(
            db, application_id, current_user
        )
        application = ResearchPostingApplicationService.transition_application(
            db,
            application_id,
            current_user,
            payload.target_status,
            decision_reason=payload.decision_reason,
            reviewer_note=payload.reviewer_note,
        )
    except ApplicationNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
    except ApplicationPermissionError as err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(err))
    except InvalidApplicationTransitionError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))
    return ResearchPostingApplicationService.build_application_read(
        application, current_user, actor_role
    )
