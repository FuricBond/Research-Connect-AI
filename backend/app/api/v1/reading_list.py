"""
FastAPI Router for the Phase 5.14 personal reading list.

Any signed-in user, whatever their role, can save research works, track their reading status,
keep private notes and export the list as BibTeX. Every route answers 401 to anonymous callers,
403 for another user's item and 404 for an unknown one.

The static routes (`/lookup`, `/export.bib`) are declared before `/{item_id}`, so they are never
read as an item id. The prefix is deliberately outside /discovery, whose GET responses are cached
across users.
"""
from __future__ import annotations

from typing import Annotated
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import OptionalUserId, require_user_id
from app.db.session import get_db
from app.models.reading_list import ReadingStatus
from app.schemas.reading_list import (
    ReadingListItemCreate,
    ReadingListItemRead,
    ReadingListItemUpdate,
    ReadingListLookupResponse,
    ReadingListResponse,
)
from app.services.reading_list_service import ReadingListService

router = APIRouter(prefix="/reading-list", tags=["reading-list"])

# A GET URL carrying more ids than this risks the server's request-line limit.
EXPORT_SELECTION_LIMIT = 200


@router.get(
    "",
    response_model=ReadingListResponse,
    status_code=status.HTTP_200_OK,
    summary="List my reading list",
    description="The caller's saved works, most recently updated first, with counts per status.",
)
def list_reading_list(
    status_filter: Annotated[
        ReadingStatus | None, Query(alias="status", description="Only items in this status")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100, description="Page size")] = 50,
    offset: Annotated[int, Query(ge=0, description="Offset")] = 0,
    current_user_id: OptionalUserId = None,
    db: Session = Depends(get_db),
) -> ReadingListResponse:
    user_id = require_user_id(current_user_id)
    return ReadingListService.list_items(
        db, user_id, status=status_filter, limit=limit, offset=offset
    )


@router.get(
    "/lookup",
    response_model=ReadingListLookupResponse,
    status_code=status.HTTP_200_OK,
    summary="Which of these works have I saved?",
    description="Maps each given work id the caller has saved to its reading list item id.",
)
def lookup_reading_list(
    work_ids: Annotated[
        list[uuid.UUID] | None,
        Query(description=f"Up to {ReadingListService.LOOKUP_LIMIT} research work ids"),
    ] = None,
    current_user_id: OptionalUserId = None,
    db: Session = Depends(get_db),
) -> ReadingListLookupResponse:
    user_id = require_user_id(current_user_id)
    work_ids = work_ids or []
    if len(work_ids) > ReadingListService.LOOKUP_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"At most {ReadingListService.LOOKUP_LIMIT} work ids can be looked up at once.",
        )
    return ReadingListLookupResponse(saved=ReadingListService.lookup(db, user_id, work_ids))


@router.get(
    "/export.bib",
    status_code=status.HTTP_200_OK,
    summary="Export my reading list as BibTeX",
    description=(
        "BibTeX for the given items, or the whole list (optionally one status). Notes and "
        "statuses are never exported. An id belonging to another user rejects the export."
    ),
    response_class=Response,
)
def export_reading_list(
    item_ids: Annotated[
        list[uuid.UUID] | None,
        Query(description=f"Up to {EXPORT_SELECTION_LIMIT} reading list item ids"),
    ] = None,
    status_filter: Annotated[
        ReadingStatus | None, Query(alias="status", description="Only items in this status")
    ] = None,
    current_user_id: OptionalUserId = None,
    db: Session = Depends(get_db),
) -> Response:
    user_id = require_user_id(current_user_id)
    if item_ids is not None and len(item_ids) > EXPORT_SELECTION_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"At most {EXPORT_SELECTION_LIMIT} items can be exported by id at once.",
        )
    try:
        body = ReadingListService.export_bibtex(
            db, user_id, item_ids=item_ids, status=status_filter
        )
    except PermissionError as err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(err))
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
    return Response(
        content=body,
        media_type="application/x-bibtex; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="reading-list.bib"',
            "Cache-Control": "no-store",
        },
    )


@router.post(
    "",
    response_model=ReadingListItemRead,
    status_code=status.HTTP_201_CREATED,
    summary="Save a work to my reading list",
    description="201 when newly saved, 200 when the work was already on the list (unchanged).",
)
def add_to_reading_list(
    payload: ReadingListItemCreate,
    response: Response,
    current_user_id: OptionalUserId = None,
    db: Session = Depends(get_db),
) -> ReadingListItemRead:
    user_id = require_user_id(current_user_id)
    try:
        item, is_new = ReadingListService.add_work(db, user_id, payload)
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
    if not is_new:
        response.status_code = status.HTTP_200_OK
    return ReadingListService.build_item_read(item)


@router.get(
    "/{item_id}",
    response_model=ReadingListItemRead,
    status_code=status.HTTP_200_OK,
    summary="Get one reading list item",
)
def get_reading_list_item(
    item_id: uuid.UUID,
    current_user_id: OptionalUserId = None,
    db: Session = Depends(get_db),
) -> ReadingListItemRead:
    user_id = require_user_id(current_user_id)
    try:
        item = ReadingListService.get_owned_item(db, user_id, item_id)
    except PermissionError as err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(err))
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
    return ReadingListService.build_item_read(item)


@router.patch(
    "/{item_id}",
    response_model=ReadingListItemRead,
    status_code=status.HTTP_200_OK,
    summary="Update status or notes",
    description="Only the fields sent are changed; `notes: null` clears the notes.",
)
def update_reading_list_item(
    item_id: uuid.UUID,
    payload: ReadingListItemUpdate,
    current_user_id: OptionalUserId = None,
    db: Session = Depends(get_db),
) -> ReadingListItemRead:
    user_id = require_user_id(current_user_id)
    try:
        item = ReadingListService.update_item(db, user_id, item_id, payload)
    except PermissionError as err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(err))
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
    return ReadingListService.build_item_read(item)


@router.delete(
    "/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a work from my reading list",
)
def remove_from_reading_list(
    item_id: uuid.UUID,
    current_user_id: OptionalUserId = None,
    db: Session = Depends(get_db),
) -> Response:
    user_id = require_user_id(current_user_id)
    try:
        ReadingListService.remove_item(db, user_id, item_id)
    except PermissionError as err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(err))
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
