"""Phase 5.14 — Personal reading list schemas."""
from __future__ import annotations

from datetime import datetime
import uuid

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.reading_list import ReadingStatus

NOTES_MAX_LENGTH = 10_000


def _clean_notes(value: str | None) -> str | None:
    """Whitespace-only notes are no notes; anything else is kept exactly as written."""
    if value is None or not value.strip():
        return None
    return value


class ReadingListItemCreate(BaseModel):
    """Save a research work to the caller's reading list."""

    work_id: uuid.UUID
    status: ReadingStatus = ReadingStatus.TO_READ
    notes: str | None = Field(default=None, max_length=NOTES_MAX_LENGTH)

    @field_validator("notes")
    @classmethod
    def clean_notes(cls, v: str | None) -> str | None:
        return _clean_notes(v)


class ReadingListItemUpdate(BaseModel):
    """
    Partial update. Only the fields the caller sent are applied, so sending `notes: null`
    clears the notes while leaving the status alone.
    """

    status: ReadingStatus | None = None
    notes: str | None = Field(default=None, max_length=NOTES_MAX_LENGTH)

    @field_validator("notes")
    @classmethod
    def clean_notes(cls, v: str | None) -> str | None:
        return _clean_notes(v)

    @model_validator(mode="after")
    def status_cannot_be_cleared(self) -> "ReadingListItemUpdate":
        if "status" in self.model_fields_set and self.status is None:
            raise ValueError("status cannot be null")
        return self


class ReadingListWorkSummary(BaseModel):
    """The bibliographic details shown for a saved work."""

    id: uuid.UUID
    title: str
    doi: str | None = None
    publication_year: int | None = None
    work_type: str | None = None
    venue_name: str | None = None
    authors: list[str] = Field(default_factory=list)
    landing_page_url: str | None = None


class ReadingListItemRead(BaseModel):
    """One saved work with the owner's status and private notes."""

    id: uuid.UUID
    work_id: uuid.UUID
    status: ReadingStatus
    notes: str | None = None
    status_updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    work: ReadingListWorkSummary


class ReadingListResponse(BaseModel):
    """A page of the caller's reading list."""

    items: list[ReadingListItemRead] = Field(default_factory=list)
    total_count: int = 0
    limit: int
    offset: int
    counts_by_status: dict[str, int] = Field(
        default_factory=dict,
        description="Items per status across the whole list, regardless of the status filter",
    )


class ReadingListLookupResponse(BaseModel):
    """Which of the asked-about works the caller has saved."""

    saved: dict[uuid.UUID, uuid.UUID] = Field(
        default_factory=dict,
        description="work_id -> reading list item id, for saved works only",
    )
