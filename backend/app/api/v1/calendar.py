from __future__ import annotations

from datetime import datetime
import logging
from typing import Annotated
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.calendar import CalendarEventType
from app.models.user import UserModel
from app.schemas.calendar import (
    CalendarCreate,
    CalendarEventCreate,
    CalendarEventListResponse,
    CalendarEventRead,
    CalendarEventUpdate,
    CalendarListResponse,
    CalendarRead,
    CalendarUpdate,
    OpportunityProjectResponse,
)
from app.services.research_calendar_service import ResearchCalendarService
from app.services.workspace_service import WorkspaceService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/calendar", tags=["calendar"])


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


# ============================================================================
# Calendar Endpoints
# ============================================================================

@router.post(
    "",
    response_model=CalendarRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create research calendar",
    description="Create a new research planning calendar for the authenticated researcher.",
)
def create_calendar(
    payload: CalendarCreate,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> CalendarRead:
    user_id = resolve_current_user(db, x_user_id)
    cal = ResearchCalendarService.create_calendar(db, user_id=user_id, payload=payload)
    return ResearchCalendarService.build_calendar_read(cal)


@router.get(
    "",
    response_model=CalendarListResponse,
    status_code=status.HTTP_200_OK,
    summary="List research calendars",
    description="Retrieve all research planning calendars owned by the authenticated researcher.",
)
def list_calendars(
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> CalendarListResponse:
    user_id = resolve_current_user(db, x_user_id)
    calendars = ResearchCalendarService.list_calendars(db, user_id=user_id)
    items = [ResearchCalendarService.build_calendar_read(cal, event_count=len(cal.events)) for cal in calendars]
    return CalendarListResponse(items=items, total=len(items))


@router.get(
    "/default",
    response_model=CalendarRead,
    status_code=status.HTTP_200_OK,
    summary="Get or initialize default calendar",
    description="Retrieve or lazily create the researcher's default research planning calendar.",
)
def get_default_calendar(
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> CalendarRead:
    user_id = resolve_current_user(db, x_user_id)
    cal = ResearchCalendarService.get_or_create_default_calendar(db, user_id=user_id)
    return ResearchCalendarService.build_calendar_read(cal, event_count=len(cal.events))


@router.get(
    "/{calendar_id}",
    response_model=CalendarRead,
    status_code=status.HTTP_200_OK,
    summary="Get research calendar by ID",
    description="Retrieve research calendar metadata validating researcher ownership.",
)
def get_calendar(
    calendar_id: uuid.UUID,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> CalendarRead:
    user_id = resolve_current_user(db, x_user_id)
    try:
        cal = ResearchCalendarService.get_calendar(db, calendar_id, user_id)
        return ResearchCalendarService.build_calendar_read(cal, event_count=len(cal.events))
    except PermissionError as err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(err))
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))


@router.patch(
    "/{calendar_id}",
    response_model=CalendarRead,
    status_code=status.HTTP_200_OK,
    summary="Update research calendar",
    description="Modify calendar name, description, timezone, or default status.",
)
def update_calendar(
    calendar_id: uuid.UUID,
    payload: CalendarUpdate,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> CalendarRead:
    user_id = resolve_current_user(db, x_user_id)
    try:
        cal = ResearchCalendarService.update_calendar(db, calendar_id, user_id, payload)
        return ResearchCalendarService.build_calendar_read(cal, event_count=len(cal.events))
    except PermissionError as err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(err))
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))


# ============================================================================
# Event Endpoints
# ============================================================================

@router.post(
    "/{calendar_id}/events",
    response_model=CalendarEventRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create custom planning event",
    description="Add a researcher-defined milestone or planning task to the calendar.",
)
def create_event(
    calendar_id: uuid.UUID,
    payload: CalendarEventCreate,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> CalendarEventRead:
    user_id = resolve_current_user(db, x_user_id)
    try:
        event = ResearchCalendarService.create_user_event(db, calendar_id, user_id, payload)
        return ResearchCalendarService.build_event_read(event)
    except PermissionError as err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(err))
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))


@router.get(
    "/{calendar_id}/events",
    response_model=CalendarEventListResponse,
    status_code=status.HTTP_200_OK,
    summary="List calendar events",
    description="Retrieve events for a calendar with optional date range, type, or opportunity filters.",
)
def list_events(
    calendar_id: uuid.UUID,
    start_date: datetime | None = Query(default=None, description="Filter events on or after this timestamp"),
    end_date: datetime | None = Query(default=None, description="Filter events on or before this timestamp"),
    event_type: CalendarEventType | None = Query(default=None, description="Filter by event category"),
    opportunity_id: uuid.UUID | None = Query(default=None, description="Filter by linked opportunity"),
    submission_id: uuid.UUID | None = Query(default=None, description="Filter by linked submission tracker"),
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> CalendarEventListResponse:
    user_id = resolve_current_user(db, x_user_id)
    try:
        events = ResearchCalendarService.list_events(
            db=db,
            calendar_id=calendar_id,
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
            event_type=event_type,
            opportunity_id=opportunity_id,
            submission_id=submission_id,
        )
        items = [ResearchCalendarService.build_event_read(ev) for ev in events]
        return CalendarEventListResponse(items=items, total=len(items))
    except PermissionError as err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(err))
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))


@router.get(
    "/{calendar_id}/events/{event_id}",
    response_model=CalendarEventRead,
    status_code=status.HTTP_200_OK,
    summary="Get calendar event by ID",
    description="Retrieve details and provenance for a single calendar event.",
)
def get_event(
    calendar_id: uuid.UUID,
    event_id: uuid.UUID,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> CalendarEventRead:
    user_id = resolve_current_user(db, x_user_id)
    try:
        ev = ResearchCalendarService.get_event(db, calendar_id, event_id, user_id)
        return ResearchCalendarService.build_event_read(ev)
    except PermissionError as err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(err))
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))


@router.patch(
    "/{calendar_id}/events/{event_id}",
    response_model=CalendarEventRead,
    status_code=status.HTTP_200_OK,
    summary="Update calendar event",
    description="Modify custom event details, status, or date/time properties.",
)
def update_event(
    calendar_id: uuid.UUID,
    event_id: uuid.UUID,
    payload: CalendarEventUpdate,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> CalendarEventRead:
    user_id = resolve_current_user(db, x_user_id)
    try:
        ev = ResearchCalendarService.update_event(db, calendar_id, event_id, user_id, payload)
        return ResearchCalendarService.build_event_read(ev)
    except PermissionError as err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(err))
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))


@router.delete(
    "/{calendar_id}/events/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete calendar event",
    description="Remove an event from the research planning calendar.",
)
def delete_event(
    calendar_id: uuid.UUID,
    event_id: uuid.UUID,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> Response:
    user_id = resolve_current_user(db, x_user_id)
    try:
        ResearchCalendarService.delete_event(db, calendar_id, event_id, user_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except PermissionError as err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(err))
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))


# ============================================================================
# Opportunity Projection & iCal Export
# ============================================================================

@router.post(
    "/{calendar_id}/opportunities/{opportunity_id}/project",
    response_model=OpportunityProjectResponse,
    status_code=status.HTTP_200_OK,
    summary="Project opportunity milestones to calendar",
    description="Deterministically project Phase 2.7 canonical deadline milestones into calendar events with complete provenance.",
)
def project_opportunity(
    calendar_id: uuid.UUID,
    opportunity_id: uuid.UUID,
    submission_id: uuid.UUID | None = Query(default=None, description="Optional associated submission ID"),
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> OpportunityProjectResponse:
    user_id = resolve_current_user(db, x_user_id)
    try:
        return ResearchCalendarService.project_opportunity_to_calendar(
            db=db,
            calendar_id=calendar_id,
            user_id=user_id,
            opportunity_id=opportunity_id,
            submission_id=submission_id,
        )
    except PermissionError as err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(err))
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))


@router.get(
    "/{calendar_id}/export.ics",
    status_code=status.HTTP_200_OK,
    summary="Export calendar to iCalendar (.ics)",
    description="Export research calendar events as a standard RFC 5545 iCalendar (.ics) file.",
)
def export_calendar_ics(
    calendar_id: uuid.UUID,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> Response:
    user_id = resolve_current_user(db, x_user_id)
    try:
        ical_content = ResearchCalendarService.generate_ical_feed(db, calendar_id, user_id)
        return Response(
            content=ical_content,
            media_type="text/calendar; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="calendar_{calendar_id}.ics"',
                "Cache-Control": "no-cache, no-store, must-revalidate",
            },
        )
    except PermissionError as err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(err))
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
