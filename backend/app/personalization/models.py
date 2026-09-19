"""
Domain Models and Schemas for Phase 5.2 — Explicit Preference Interpretation & Personalization Signals.

Provides typed, deterministic, explainable models for evaluating research opportunities
against explicit researcher preferences.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid

from pydantic import BaseModel, ConfigDict, Field


class PreferenceMatchType(str, Enum):
    """Classification of how an opportunity relates to researcher preferences."""

    PREFERRED_MATCH = "PREFERRED_MATCH"
    EXCLUDED_MATCH = "EXCLUDED_MATCH"
    NEUTRAL = "NEUTRAL"
    PARTIAL_MATCH = "PARTIAL_MATCH"
    CONFLICT = "CONFLICT"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class PreferenceDimension(str, Enum):
    """Evaluated preference dimensions matching Phase 5.1 categories."""

    KEYWORD = "KEYWORD"
    RESEARCH_DOMAIN = "RESEARCH_DOMAIN"
    COUNTRY = "COUNTRY"
    REGION = "REGION"
    INSTITUTION = "INSTITUTION"
    FUNDING = "FUNDING"
    ACADEMIC_LEVEL = "ACADEMIC_LEVEL"
    CAREER_STAGE = "CAREER_STAGE"
    OPPORTUNITY_TYPE = "OPPORTUNITY_TYPE"


class SignalPolarity(str, Enum):
    """Directional valence of a preference match signal."""

    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    NEUTRAL = "NEUTRAL"
    UNRESOLVED = "UNRESOLVED"


class PreferenceMatchSignal(BaseModel):
    """
    Structured, fine-grained match signal for a single preference dimension.
    Preserves raw evidence, deterministic explanations, and confidence.
    """

    model_config = ConfigDict(from_attributes=True)

    signal_id: str = Field(
        default_factory=lambda: f"pms-{uuid.uuid4().hex[:12]}",
        description="Unique signal identifier",
    )
    profile_id: uuid.UUID = Field(..., description="Canonical ResearchProfileModel ID")
    opportunity_id: uuid.UUID = Field(..., description="Canonical OpportunityModel ID")
    dimension: PreferenceDimension = Field(..., description="Evaluated preference dimension")
    preference_value: str = Field(..., description="Configured preference value")
    preference_type: str = Field(..., description="Preference type: PREFERRED or EXCLUDED")
    opportunity_value: str | None = Field(
        None,
        description="Matched or evaluated value from the opportunity",
    )
    match_type: PreferenceMatchType = Field(..., description="Evaluation outcome for this signal")
    polarity: SignalPolarity = Field(..., description="Directional polarity of the signal")
    evidence: str = Field(..., description="Human-readable and auditable evidence description")
    explanation: str = Field(..., description="Deterministic user-facing explanation")
    confidence: float = Field(
        1.0,
        ge=0.0,
        le=1.0,
        description="Confidence or certainty of the match",
    )
    is_explicit: bool = Field(
        True,
        description="Always True in Phase 5.2 (explicit preference foundation)",
    )
    metadata_payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured provenance metadata (e.g. canonical vs fallback flag)",
    )


class PreferencePersonalizationAssessment(BaseModel):
    """
    Comprehensive, explainable evaluation of an opportunity against all explicit researcher preferences.
    """

    model_config = ConfigDict(from_attributes=True)

    profile_id: uuid.UUID = Field(..., description="Canonical ResearchProfileModel ID")
    opportunity_id: uuid.UUID = Field(..., description="Canonical OpportunityModel ID")
    overall_match_state: PreferenceMatchType = Field(
        ...,
        description="Aggregate match state across all evaluated dimensions",
    )
    positive_matches_count: int = Field(0, description="Count of positive preferred matches")
    excluded_matches_count: int = Field(0, description="Count of explicit exclusion matches")
    conflict_count: int = Field(0, description="Count of preference conflicts detected")
    neutral_dimensions_count: int = Field(0, description="Count of neutral/unspecified dimensions")
    insufficient_evidence_count: int = Field(
        0,
        description="Count of dimensions where opportunity data was unavailable",
    )
    total_evaluated_preferences: int = Field(
        0,
        description="Total explicit preferences evaluated",
    )
    evidence_coverage: float = Field(
        1.0,
        ge=0.0,
        le=1.0,
        description="Ratio of evaluated dimensions with sufficient evidence [0.0, 1.0]",
    )
    deterministic_explanation: str = Field(
        ...,
        description="Authoritative, deterministic human-readable summary",
    )
    dimension_signals: list[PreferenceMatchSignal] = Field(
        default_factory=list,
        description="All individual per-dimension match signals",
    )
    positive_matches: list[PreferenceMatchSignal] = Field(
        default_factory=list,
        description="Signals representing positive preferred matches",
    )
    excluded_matches: list[PreferenceMatchSignal] = Field(
        default_factory=list,
        description="Signals representing explicit exclusion matches",
    )
    conflicts: list[PreferenceMatchSignal] = Field(
        default_factory=list,
        description="Signals representing conflicting preferences",
    )
    insufficient_evidence_dimensions: list[PreferenceDimension] = Field(
        default_factory=list,
        description="Dimensions where opportunity data was missing or incomplete",
    )
    neutral_dimensions: list[PreferenceDimension] = Field(
        default_factory=list,
        description="Dimensions where no preference exists or opportunity was neutral",
    )
    computed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Evaluation timestamp",
    )


class BatchOpportunityPreferenceMatchRequest(BaseModel):
    """Payload for batch preference match evaluation."""

    opportunity_ids: list[uuid.UUID] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="List of opportunity IDs to evaluate in batch",
    )


class BatchOpportunityPreferenceMatchResponse(BaseModel):
    """Response container for batch preference match evaluation."""

    model_config = ConfigDict(from_attributes=True)

    profile_id: uuid.UUID = Field(..., description="Canonical ResearchProfileModel ID")
    assessments: list[PreferencePersonalizationAssessment] = Field(
        default_factory=list,
        description="Evaluation assessments for each requested opportunity",
    )
    evaluated_count: int = Field(..., description="Number of opportunities evaluated")
