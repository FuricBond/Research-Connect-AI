"""Phase 5.15 — Posting fit schemas."""
from __future__ import annotations

from datetime import datetime
import uuid

from pydantic import BaseModel, Field

MAX_BATCH_POSTINGS = 100


class PostingFitReason(BaseModel):
    """One part of the fit, with what matched. Ordered by contribution, then code."""

    code: str = Field(description="TOPIC, SKILLS, OPENING, EXCLUDED or DEADLINE_PASSED")
    label: str
    weight: float = Field(description="Share of the score this part carries; 0 for notices")
    matched: list[str] = Field(default_factory=list)


class PostingFitRead(BaseModel):
    """How well one posting fits the signed-in student."""

    posting_id: uuid.UUID
    score: int | None = Field(
        default=None,
        ge=0,
        le=100,
        description="0-100, or null when the student has recorded no interests to compare",
    )
    band: str | None = Field(default=None, description="Strong, Good, Partial or Low")
    reasons: list[PostingFitReason] = Field(default_factory=list)
    gaps: list[str] = Field(
        default_factory=list,
        description="Up to five required skills the student has not recorded",
    )
    computed_at: datetime


class PostingFitBatchRequest(BaseModel):
    posting_ids: list[uuid.UUID] = Field(max_length=MAX_BATCH_POSTINGS)


class PostingFitBatchResponse(BaseModel):
    """Fits for the visible postings among those asked for, in request order."""

    fits: list[PostingFitRead] = Field(default_factory=list)
