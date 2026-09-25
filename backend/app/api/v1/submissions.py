"""
FastAPI Router for Phase 4.2 Research Submission Management & Tracking.

Provides researcher-scoped submission endpoints:
  - Creating submissions for workspace items
  - Listing submissions with status/type/workspace filters & pagination
  - Summary metrics across submission lifecycle states
  - Retrieving and modifying submission draft metadata
  - Deterministic state machine status transitions
  - Deleting submissions (DRAFT or WITHDRAWN only)
  - Enforcing strict researcher isolation via the authenticated identity (Phase 6)
"""
from __future__ import annotations

import logging
from typing import Annotated
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import OptionalUserId, require_user_id
from app.db.session import get_db
from app.models.research_submission import SubmissionStatus, SubmissionType
from app.models.submission_document import DocumentStatus, DocumentType
from app.schemas.research_submission import (
    ResearchSubmissionCreate,
    ResearchSubmissionListResponse,
    ResearchSubmissionRead,
    ResearchSubmissionUpdate,
    SubmissionDocumentCreate,
    SubmissionDocumentListResponse,
    SubmissionDocumentRead,
    SubmissionDocumentUpdate,
    SubmissionDocumentVersionRead,
    SubmissionHistoryResponse,
    SubmissionReadinessResponse,
    SubmissionStatusTransition,
    SubmissionSummaryResponse,
)
from app.services.research_submission_document_service import (
    ResearchSubmissionDocumentService,
)
from app.services.research_submission_service import (
    InvalidSubmissionTransitionError,
    ResearchSubmissionService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/submissions", tags=["submissions"])


@router.post(
    "",
    response_model=ResearchSubmissionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create research submission",
    description="Create a structured research submission tracker for an opportunity in the researcher's workspace.",
)
def create_submission(
    payload: ResearchSubmissionCreate,
    current_user_id: OptionalUserId = None,
    db: Session = Depends(get_db),
) -> ResearchSubmissionRead:
    user_id = require_user_id(current_user_id)
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
    current_user_id: OptionalUserId = None,
    db: Session = Depends(get_db),
) -> ResearchSubmissionListResponse:
    user_id = require_user_id(current_user_id)
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
    current_user_id: OptionalUserId = None,
    db: Session = Depends(get_db),
) -> SubmissionSummaryResponse:
    user_id = require_user_id(current_user_id)
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
    current_user_id: OptionalUserId = None,
    db: Session = Depends(get_db),
) -> ResearchSubmissionRead:
    user_id = require_user_id(current_user_id)
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
    current_user_id: OptionalUserId = None,
    db: Session = Depends(get_db),
) -> ResearchSubmissionRead:
    user_id = require_user_id(current_user_id)
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
    current_user_id: OptionalUserId = None,
    db: Session = Depends(get_db),
) -> ResearchSubmissionRead:
    user_id = require_user_id(current_user_id)
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
    current_user_id: OptionalUserId = None,
    db: Session = Depends(get_db),
) -> Response:
    user_id = require_user_id(current_user_id)
    try:
        ResearchSubmissionService.delete_submission(db, user_id, submission_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except PermissionError as err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(err))
    except InvalidSubmissionTransitionError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))


# ── Phase 4.3: Submission Document & Artifact Endpoints ───────────────────────


@router.post(
    "/{submission_id}/documents",
    response_model=SubmissionDocumentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create submission document",
    description="Attach a document artifact (e.g. full paper, abstract, cover letter, dataset) to a research submission.",
)
def create_submission_document(
    submission_id: uuid.UUID,
    payload: SubmissionDocumentCreate,
    current_user_id: OptionalUserId = None,
    db: Session = Depends(get_db),
) -> SubmissionDocumentRead:
    user_id = require_user_id(current_user_id)
    try:
        return ResearchSubmissionDocumentService.create_document(
            db=db,
            user_id=user_id,
            submission_id=submission_id,
            payload=payload,
        )
    except PermissionError as err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(err))
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))


@router.get(
    "/{submission_id}/documents",
    response_model=SubmissionDocumentListResponse,
    status_code=status.HTTP_200_OK,
    summary="List submission documents",
    description="List all document artifacts for a research submission with status and category filtering.",
)
def list_submission_documents(
    submission_id: uuid.UUID,
    status_filter: Annotated[DocumentStatus | None, Query(alias="status", description="Filter by document status")] = None,
    document_type: Annotated[DocumentType | None, Query(description="Filter by document category")] = None,
    is_required: Annotated[bool | None, Query(description="Filter by required flag")] = None,
    include_archived: Annotated[bool, Query(description="Include archived documents")] = True,
    current_user_id: OptionalUserId = None,
    db: Session = Depends(get_db),
) -> SubmissionDocumentListResponse:
    user_id = require_user_id(current_user_id)
    try:
        return ResearchSubmissionDocumentService.list_documents(
            db=db,
            user_id=user_id,
            submission_id=submission_id,
            status=status_filter,
            document_type=document_type,
            is_required=is_required,
            include_archived=include_archived,
        )
    except PermissionError as err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(err))
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))


@router.get(
    "/{submission_id}/documents/{document_id}",
    response_model=SubmissionDocumentRead,
    status_code=status.HTTP_200_OK,
    summary="Get submission document",
    description="Retrieve a single submission document artifact and its active version metadata.",
)
def get_submission_document(
    submission_id: uuid.UUID,
    document_id: uuid.UUID,
    current_user_id: OptionalUserId = None,
    db: Session = Depends(get_db),
) -> SubmissionDocumentRead:
    user_id = require_user_id(current_user_id)
    try:
        doc = ResearchSubmissionDocumentService.get_document(
            db=db,
            user_id=user_id,
            submission_id=submission_id,
            document_id=document_id,
        )
        if doc is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document with ID '{document_id}' not found for submission '{submission_id}'.",
            )
        return doc
    except PermissionError as err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(err))
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))


@router.patch(
    "/{submission_id}/documents/{document_id}",
    response_model=SubmissionDocumentRead,
    status_code=status.HTTP_200_OK,
    summary="Update submission document",
    description="Partially update a submission document, update its status, or create a new immutable version snapshot.",
)
def update_submission_document(
    submission_id: uuid.UUID,
    document_id: uuid.UUID,
    payload: SubmissionDocumentUpdate,
    current_user_id: OptionalUserId = None,
    db: Session = Depends(get_db),
) -> SubmissionDocumentRead:
    user_id = require_user_id(current_user_id)
    try:
        return ResearchSubmissionDocumentService.update_document(
            db=db,
            user_id=user_id,
            submission_id=submission_id,
            document_id=document_id,
            payload=payload,
        )
    except PermissionError as err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(err))
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))


@router.delete(
    "/{submission_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete submission document",
    description="Permanently delete a submission document and all its historical version records.",
)
def delete_submission_document(
    submission_id: uuid.UUID,
    document_id: uuid.UUID,
    current_user_id: OptionalUserId = None,
    db: Session = Depends(get_db),
) -> Response:
    user_id = require_user_id(current_user_id)
    try:
        ResearchSubmissionDocumentService.delete_document(
            db=db,
            user_id=user_id,
            submission_id=submission_id,
            document_id=document_id,
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except PermissionError as err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(err))
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))


@router.get(
    "/{submission_id}/documents/{document_id}/versions",
    response_model=list[SubmissionDocumentVersionRead],
    status_code=status.HTTP_200_OK,
    summary="List document version history",
    description="Retrieve all immutable historical versions and metadata snapshots for a document.",
)
def list_document_versions(
    submission_id: uuid.UUID,
    document_id: uuid.UUID,
    current_user_id: OptionalUserId = None,
    db: Session = Depends(get_db),
) -> list[SubmissionDocumentVersionRead]:
    user_id = require_user_id(current_user_id)
    try:
        return ResearchSubmissionDocumentService.list_document_versions(
            db=db,
            user_id=user_id,
            submission_id=submission_id,
            document_id=document_id,
        )
    except PermissionError as err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(err))
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))


# ── Phase 4.3: Submission Readiness Assessment Endpoint ───────────────────────


@router.get(
    "/{submission_id}/readiness",
    response_model=SubmissionReadinessResponse,
    status_code=status.HTTP_200_OK,
    summary="Evaluate submission readiness",
    description="Run deterministic readiness assessment on a submission, checking required documents, metadata completeness, and canonical deadline context.",
)
def evaluate_submission_readiness(
    submission_id: uuid.UUID,
    current_user_id: OptionalUserId = None,
    db: Session = Depends(get_db),
) -> SubmissionReadinessResponse:
    user_id = require_user_id(current_user_id)
    try:
        return ResearchSubmissionDocumentService.evaluate_readiness(
            db=db,
            user_id=user_id,
            submission_id=submission_id,
        )
    except PermissionError as err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(err))
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))


# ── Phase 4.3: Submission Audit History Timeline Endpoint ─────────────────────


@router.get(
    "/{submission_id}/history",
    response_model=SubmissionHistoryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get submission audit history",
    description="Retrieve chronological audit history events for submission status transitions, document changes, and version creations.",
)
def get_submission_history(
    submission_id: uuid.UUID,
    limit: Annotated[int, Query(ge=1, le=100, description="Max events to return")] = 50,
    offset: Annotated[int, Query(ge=0, description="Pagination offset")] = 0,
    current_user_id: OptionalUserId = None,
    db: Session = Depends(get_db),
) -> SubmissionHistoryResponse:
    user_id = require_user_id(current_user_id)
    try:
        return ResearchSubmissionDocumentService.get_submission_history(
            db=db,
            user_id=user_id,
            submission_id=submission_id,
            limit=limit,
            offset=offset,
        )
    except PermissionError as err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(err))
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))

