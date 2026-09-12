from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
import uuid

from pydantic import BaseModel, ConfigDict, Field


class FeedbackType(str, Enum):
    """Supported feedback interaction event types (Phase 3.6)."""

    VIEW = "VIEW"
    SAVE = "SAVE"
    DISMISS = "DISMISS"
    INTERESTED = "INTERESTED"
    NOT_INTERESTED = "NOT_INTERESTED"
    APPLY = "APPLY"


class FeedbackSource(str, Enum):
    """Originating channel where the interaction occurred."""

    RECOMMENDATION = "RECOMMENDATION"
    DISCOVERY = "DISCOVERY"
    DIRECT = "DIRECT"
    SEARCH = "SEARCH"


# ── Request Schemas ───────────────────────────────────────────────────────────


class FeedbackCreateRequest(BaseModel):
    """Payload to record an interaction feedback event."""

    opportunity_id: uuid.UUID = Field(
        ...,
        description="Target Opportunity ID for the feedback event",
    )
    feedback_type: FeedbackType = Field(
        ...,
        description="Type of feedback: VIEW, SAVE, DISMISS, INTERESTED, NOT_INTERESTED, APPLY",
    )
    source: FeedbackSource = Field(
        default=FeedbackSource.RECOMMENDATION,
        description="Originating channel",
    )
    notes: str | None = Field(
        default=None,
        max_length=1000,
        description="Optional researcher note or categorization tag",
    )
    rank_position: int | None = Field(
        default=None,
        ge=1,
        le=500,
        description="Rank position where candidate was presented",
    )
    recommendation_session_id: str | None = Field(
        default=None,
        max_length=100,
        description="Session attribution token",
    )
    metadata_snapshot: dict[str, Any] | None = Field(
        default=None,
        description="Optional snapshot of opportunity/ranking attributes at interaction time",
    )


class FeedbackUpdateRequest(BaseModel):
    """Payload to update an existing feedback item (notes or metadata)."""

    notes: str | None = Field(
        default=None,
        max_length=1000,
        description="Updated researcher note",
    )
    metadata_snapshot: dict[str, Any] | None = Field(
        default=None,
        description="Updated snapshot metadata",
    )


# ── Response Schemas ──────────────────────────────────────────────────────────


class FeedbackItemResponse(BaseModel):
    """Full detail of a recorded researcher recommendation feedback event."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    researcher_id: uuid.UUID
    opportunity_id: uuid.UUID
    feedback_type: str
    source: str
    notes: str | None = None
    rank_position: int | None = None
    recommendation_session_id: str | None = None
    metadata_snapshot: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime | None = None
    # Joined opportunity display attributes
    opportunity_title: str | None = None
    opportunity_type: str | None = None
    delivery_mode: str | None = None
    location: str | None = None


class FeedbackListResponse(BaseModel):
    """Paginated list of recorded feedback items."""

    model_config = ConfigDict(from_attributes=True)

    items: list[FeedbackItemResponse] = Field(default_factory=list)
    total: int = Field(..., ge=0)
    limit: int = Field(..., ge=1)
    offset: int = Field(..., ge=0)


class BehavioralSignalSchema(BaseModel):
    """
    Deterministically learned behavioral signal derived from feedback history.

    Represents learned preference for a specific attribute (topic, opportunity_type,
    delivery_mode, etc.) backed by temporal decay, diminishing returns, and confidence.
    """

    model_config = ConfigDict(from_attributes=True)

    category: str = Field(..., description="Attribute taxonomy category (TOPIC, OPPORTUNITY_TYPE, etc.)")
    preference_key: str = Field(..., description="Attribute key")
    preference_value: str = Field(..., description="Normalized canonical value")
    display_label: str = Field(..., description="Human-readable display label")
    raw_score: float = Field(..., description="Cumulative signed decayed weight")
    normalized_score: float = Field(..., ge=-1.0, le=1.0, description="Normalized score in [-1.0, 1.0]")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in [0.0, 1.0]")
    sample_size: int = Field(..., ge=0, description="Number of supporting interaction events")
    direction: str = Field(..., description="'POSITIVE' or 'NEGATIVE'")
    recency_score: float = Field(..., ge=0.0, le=1.0, description="Mean temporal recency factor")
    last_interacted_at: datetime | None = None


class FeedbackSummaryResponse(BaseModel):
    """Aggregated summary of researcher interaction feedback and behavioral learning."""

    model_config = ConfigDict(from_attributes=True)

    total_feedback_count: int = Field(0, ge=0)
    counts_by_type: dict[str, int] = Field(default_factory=dict)
    top_positive_topics: list[str] = Field(default_factory=list)
    top_negative_topics: list[str] = Field(default_factory=list)
    overall_confidence: float = Field(0.0, ge=0.0, le=1.0)
    suppressed_count: int = Field(0, ge=0)
    is_cold_start: bool = True
