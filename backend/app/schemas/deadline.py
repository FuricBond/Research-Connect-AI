"""
Pydantic API Schemas for Deadline Intelligence (Phase 2.7F).

Provides typed, loss-aware schemas for:
  - Deadline evidence, normalization, and temporal assessments
  - Multi-source observations and authority tiers
  - Sequential revision history and extension detection
  - Canonical deadline views and multi-source conflict states
  - Full opportunity deadline intelligence container with deterministic explainability

CRITICAL INVARIANTS:
1. Loss-aware serialization: distinguishes MISSING, INVALID, AMBIGUOUS,
   EXPIRED, UPCOMING, DUE_TODAY, SOURCE_CONFLICT, SUPERSEDED, and EQUIVALENT_SOURCES.
   Never silently collapses conflict or retracted states to null without explanation.
2. Presentation parity: all scoring, status, urgency, and conflict decisions
   originate in the backend domain layer (Phases 2.7B–2.7E). Zero client-side math.
3. Pure, deterministic schemas without external network or LLM dependencies.
"""
from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DeadlineEvidenceSchema(BaseModel):
    """Raw, structured, and provenance-tracked deadline evidence extracted from a source."""

    model_config = ConfigDict(from_attributes=True)

    deadline_type: str
    raw_value: str | None = None
    raw_text: str | None = None
    source: str = "unknown"
    source_url: str | None = None
    source_field: str = ""
    extraction_method: str = "DIRECT_FIELD"
    confidence: float = 1.0
    provenance: str = "UNKNOWN"
    is_present: bool = True
    precision: str = "DATE_ONLY"
    timezone_indicator: str = "UNSPECIFIED"
    parsed_year: int | None = None
    parsed_month: int | None = None
    parsed_day: int | None = None
    parsed_time_str: str | None = None
    is_ambiguous: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class NormalizedDeadlineSchema(BaseModel):
    """Standardized, deterministic temporal representation of an academic deadline."""

    model_config = ConfigDict(from_attributes=True)

    deadline_type: str
    local_date: date | None = None
    local_time: time | None = None
    timezone_name: str | None = None
    timezone_offset: str | None = None
    normalized_utc: datetime | None = None
    precision: str = "DATE_ONLY"
    timezone_source: str = "UNKNOWN"
    normalization_confidence: float = 1.0
    normalization_status: str = "NORMALIZED"
    is_end_of_day_inferred: bool = False
    source_evidence: DeadlineEvidenceSchema | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeadlineAssessmentSchema(BaseModel):
    """Structured temporal assessment for a single academic milestone."""

    model_config = ConfigDict(from_attributes=True)

    deadline_type: str
    reference_time: datetime
    normalized_deadline: NormalizedDeadlineSchema | None = None
    status: str = "MISSING"  # UPCOMING, DUE_TODAY, EXPIRED, MISSING, INVALID, AMBIGUOUS
    urgency_tier: str = "UNKNOWN"  # CRITICAL, URGENT, APPROACHING, DISTANT, DUE_TODAY, EXPIRED, UNKNOWN
    urgency_score: float = 0.0
    seconds_remaining: float | None = None
    minutes_remaining: float | None = None
    hours_remaining: float | None = None
    days_remaining: float | None = None
    confidence: float = 0.0
    explanation: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeadlineObservationSchema(BaseModel):
    """Atomic observation of an academic milestone from a specific source at a specific time."""

    model_config = ConfigDict(from_attributes=True)

    opportunity_id: str | None = None
    deadline_type: str
    raw_value: str | None = None
    normalized_deadline: NormalizedDeadlineSchema | None = None
    source: str = "unknown"
    source_url: str | None = None
    observation_time: datetime | None = None
    provenance: str = "UNKNOWN"
    extraction_method: str = "DIRECT_FIELD"
    authority_tier: int = 0
    normalization_confidence: float = 1.0
    source_confidence: float = 1.0
    is_current: bool = True
    is_retracted: bool = False
    retraction_evidence: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeadlineRevisionSchema(BaseModel):
    """Temporal delta and classification between successive deadline observations."""

    model_config = ConfigDict(from_attributes=True)

    deadline_type: str
    classification: str  # INITIAL, UNCHANGED, EXTENDED, MOVED_EARLIER, REPLACED, RETRACTED, CONFLICTING, EQUIVALENT
    days_diff: float | None = None
    hours_diff: float | None = None
    explanation: str = ""
    previous_observation: DeadlineObservationSchema | None = None
    current_observation: DeadlineObservationSchema
    metadata: dict[str, Any] = Field(default_factory=dict)


class CanonicalDeadlineViewSchema(BaseModel):
    """Synthesized authoritative view for a single milestone, resolving multi-source conflicts."""

    model_config = ConfigDict(from_attributes=True)

    deadline_type: str
    canonical_deadline: NormalizedDeadlineSchema | None = None
    canonical_assessment: DeadlineAssessmentSchema | None = None
    selected_source: str | None = None
    selected_observation: DeadlineObservationSchema | None = None
    all_observations: list[DeadlineObservationSchema] = Field(default_factory=list)
    revision_history: list[DeadlineRevisionSchema] = Field(default_factory=list)
    latest_revision: DeadlineRevisionSchema | None = None
    conflict_state: str = "NO_CONFLICT"  # NO_CONFLICT, EQUIVALENT_SOURCES, SOURCE_CONFLICT, SUPERSEDED, INSUFFICIENT_EVIDENCE
    confidence: float = 0.0
    explanation: str = ""
    unresolved_alternatives: list[DeadlineObservationSchema] = Field(default_factory=list)

    # Phase 2.7F Deterministic Explainability fields
    deterministic_explanation: str = ""
    source_selection_reason: str | None = None
    conflict_reason: str | None = None
    extension_reason: str | None = None
    unresolved_reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class OpportunityDeadlineSchema(BaseModel):
    """Complete composite deadline intelligence container for an academic opportunity."""

    model_config = ConfigDict(from_attributes=True)

    opportunity_id: str | None = None
    reference_time: datetime
    primary_milestone: str = "SUBMISSION"
    primary_view: CanonicalDeadlineViewSchema | None = None
    milestone_views: dict[str, CanonicalDeadlineViewSchema] = Field(default_factory=dict)
    summary: str = ""
    has_extension: bool = False
    has_conflict: bool = False
    primary_reason: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
