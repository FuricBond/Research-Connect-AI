from __future__ import annotations

from datetime import datetime
from typing import Any
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.calendar import CalendarEventStatus, CalendarEventType


# ============================================================================
# Research Calendar Schemas
# ============================================================================

class CalendarCreate(BaseModel):
    """Payload for creating a research planning calendar."""

    name: str = Field(
        default="Default Research Calendar",
        min_length=1,
        max_length=255,
        description="Name of the research calendar",
    )
    description: str | None = Field(
        default=None,
        description="Optional description or focus for this calendar",
    )
    timezone: str = Field(
        default="UTC",
        max_length=100,
        description="Preferred IANA display timezone (e.g. 'UTC', 'America/New_York')",
    )
    is_default: bool = Field(
        default=False,
        description="Whether this is the user's primary/default calendar",
    )


class CalendarUpdate(BaseModel):
    """Payload for updating research calendar settings."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    timezone: str | None = Field(default=None, max_length=100)
    is_default: bool | None = None


class CalendarRead(BaseModel):
    """Read schema for a research calendar."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    profile_id: uuid.UUID | None = None
    name: str
    description: str | None = None
    timezone: str
    is_default: bool
    created_at: datetime
    updated_at: datetime
    event_count: int = 0


class CalendarListResponse(BaseModel):
    """List response for calendars."""

    items: list[CalendarRead]
    total: int


# ============================================================================
# Research Calendar Event Schemas
# ============================================================================

class CalendarEventCreate(BaseModel):
    """Payload for creating a custom research planning event or milestone."""

    title: str = Field(
        min_length=1,
        max_length=255,
        description="Event display title (e.g., 'Finish experiment', 'Draft abstract')",
    )
    description: str | None = Field(
        default=None,
        description="Event details, checklist, or instructions",
    )
    event_type: CalendarEventType = Field(
        default=CalendarEventType.RESEARCH_MILESTONE,
        description="Event category: RESEARCH_MILESTONE, CUSTOM, etc.",
    )
    start_datetime: datetime | None = Field(
        default=None,
        description="Start timestamp with timezone (ISO 8601)",
    )
    end_datetime: datetime | None = Field(
        default=None,
        description="End timestamp with timezone (ISO 8601)",
    )
    date_str: str | None = Field(
        default=None,
        description="Date-only representation (e.g. '2026-08-20') if no exact time is defined",
    )
    all_day: bool = Field(
        default=False,
        description="Whether this is an all-day event",
    )
    timezone: str | None = Field(
        default=None,
        description="Original timezone string if known",
    )
    opportunity_id: uuid.UUID | None = Field(
        default=None,
        description="Optional linked opportunity ID",
    )
    submission_id: uuid.UUID | None = Field(
        default=None,
        description="Optional linked submission tracker ID",
    )
    status: CalendarEventStatus = Field(
        default=CalendarEventStatus.ACTIVE,
        description="Event lifecycle status",
    )
    provenance_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Custom user metadata or notes",
    )


class CalendarEventUpdate(BaseModel):
    """Payload for modifying a calendar event."""

    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    event_type: CalendarEventType | None = None
    start_datetime: datetime | None = None
    end_datetime: datetime | None = None
    date_str: str | None = None
    all_day: bool | None = None
    timezone: str | None = None
    status: CalendarEventStatus | None = None
    provenance_metadata: dict[str, Any] | None = None


class CalendarEventRead(BaseModel):
    """Read representation of a calendar event."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    calendar_id: uuid.UUID
    opportunity_id: uuid.UUID | None = None
    submission_id: uuid.UUID | None = None
    title: str
    description: str | None = None
    event_type: str
    start_datetime: datetime | None = None
    end_datetime: datetime | None = None
    date_str: str | None = None
    all_day: bool = False
    timezone: str | None = None
    is_canonical_projection: bool = False
    provenance_metadata: dict[str, Any] = Field(default_factory=dict)
    status: str
    created_at: datetime
    updated_at: datetime


class CalendarEventListResponse(BaseModel):
    """List response for calendar events."""

    items: list[CalendarEventRead]
    total: int


# ============================================================================
# Projection & Aggregate View Schemas
# ============================================================================

class OpportunityProjectRequest(BaseModel):
    """Request to project an opportunity's canonical milestones into a calendar."""

    opportunity_id: uuid.UUID
    submission_id: uuid.UUID | None = None


class OpportunityProjectResponse(BaseModel):
    """Result of projecting opportunity milestones into a calendar."""

    opportunity_id: uuid.UUID
    calendar_id: uuid.UUID
    projected_events: list[CalendarEventRead]
    created_count: int
    updated_count: int
    unchanged_count: int


class ResearcherCalendarViewResponse(BaseModel):
    """Aggregated researcher calendar view with statistics."""

    calendar: CalendarRead
    events: list[CalendarEventRead]
    total_events: int
    upcoming_deadlines_count: int
    conflict_count: int
    extension_count: int
