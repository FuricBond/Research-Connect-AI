"""
Pydantic Schemas for Phase 5.4 — Researcher Feedback & Interaction Signal Foundation.

Strict 1-to-1 parity with TypeScript definitions.
Provides type safety, input sanitization, and lossless serialization.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.researcher_interaction import (
    EXPLICIT_FEEDBACK_TYPES,
    NEGATIVE_EXPLICIT_TYPES,
    PASSIVE_OBSERVATION_TYPES,
    POSITIVE_EXPLICIT_TYPES,
    InteractionType,
)


class InteractionCreateRequest(BaseModel):
    """Payload for recording a researcher interaction with an opportunity."""

    interaction_type: InteractionType = Field(
        ...,
        description="Type of interaction (VIEWED, OPENED, SAVED, DISMISSED, HIDDEN, INTERESTED, NOT_INTERESTED, APPLIED, SHARED)",
    )
    source: str = Field(
        default="RECOMMENDATION",
        max_length=50,
        description="Context or channel where interaction occurred (e.g. RECOMMENDATION, DISCOVERY, SEARCH, DIRECT, WORKSPACE)",
    )
    client_event_id: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Optional client-generated event identifier or idempotency token",
    )
    metadata_payload: Optional[dict[str, Any]] = Field(
        default_factory=dict,
        description="Contextual metadata (e.g. rank position, session ID). Must not contain PII or credentials.",
    )

    @field_validator("metadata_payload")
    @classmethod
    def sanitize_metadata(cls, v: Optional[dict[str, Any]]) -> dict[str, Any]:
        if not v:
            return {}
        # Block forbidden sensitive keys
        forbidden_keys = {"password", "token", "secret", "authorization", "cookie", "ssn", "credit_card"}
        sanitized = {}
        for k, val in v.items():
            if k.lower() in forbidden_keys:
                continue
            # Restrict string length of values to prevent payload abuse
            if isinstance(val, str) and len(val) > 1000:
                sanitized[k] = val[:1000]
            else:
                sanitized[k] = val
        return sanitized


class InteractionResponse(BaseModel):
    """Response representation of an auditable researcher interaction event."""

    id: uuid.UUID
    profile_id: uuid.UUID
    opportunity_id: uuid.UUID
    interaction_type: InteractionType
    is_explicit_feedback: bool
    source: str
    client_event_id: Optional[str] = None
    metadata_payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OpportunityInteractionHistoryResponse(BaseModel):
    """Paginated list of interaction events for a specific opportunity in the context of a researcher."""

    opportunity_id: uuid.UUID
    profile_id: uuid.UUID
    interactions: list[InteractionResponse] = Field(default_factory=list)
    total_count: int
    limit: int
    offset: int


class ResearcherInteractionSummaryResponse(BaseModel):
    """
    Deterministic summary of a researcher's interaction signals across all opportunities.
    
    Strict Architectural Boundaries:
      - Contains transparent counts and bounded heuristic signals only.
      - Zero ML / Zero LLM: does NOT produce an opaque 'user preference score'.
      - Does NOT infer permanent preferences or alter explicit preference records.
    """

    profile_id: uuid.UUID
    total_interactions: int
    positive_explicit_count: int
    negative_explicit_count: int
    saved_count: int
    dismissed_count: int
    hidden_count: int
    interested_count: int
    not_interested_count: int
    viewed_count: int
    opened_count: int
    applied_count: int
    shared_count: int
    counts_by_type: dict[str, int] = Field(default_factory=dict)
    most_recent_interaction: Optional[InteractionResponse] = None
    recent_interactions: list[InteractionResponse] = Field(default_factory=list)
    interaction_strength_signal: Optional[float] = Field(
        default=None,
        description="Transparent bounded heuristic in [-1.0, 1.0] (positive - negative) / (total + 1). Not an opaque ML score.",
    )
