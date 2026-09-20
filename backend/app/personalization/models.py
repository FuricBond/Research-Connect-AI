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

from app.personalization.adaptive_models import AdaptivePersonalizationContribution


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


# =============================================================================
# Phase 5.3 — Personalization-Aware Opportunity Scoring & Explainability Models
# =============================================================================


class PersonalizationContribution(BaseModel):
    """
    Structured contribution of a single preference dimension to the personalization score.
    """

    model_config = ConfigDict(from_attributes=True)

    dimension: PreferenceDimension = Field(..., description="Evaluated preference dimension")
    match_type: PreferenceMatchType = Field(..., description="Dimension match outcome")
    polarity: SignalPolarity = Field(..., description="Signal polarity")
    weight: float = Field(..., ge=0.0, le=1.0, description="Dimension base weight in [0.0, 1.0]")
    raw_contribution: float = Field(..., description="Signed raw contribution")
    normalized_contribution: float = Field(..., description="Contribution normalized by active weights")
    preference_value: str = Field(..., description="Explicit preference value")
    opportunity_value: str | None = Field(None, description="Evaluated opportunity value")
    evidence: str = Field(..., description="Factual evidence")
    explanation: str = Field(..., description="Deterministic explanation")


class PersonalizationDimensionScore(BaseModel):
    """
    Aggregate score and status for a single preference dimension.
    """

    model_config = ConfigDict(from_attributes=True)

    dimension: PreferenceDimension = Field(..., description="Evaluated preference dimension")
    score: float = Field(..., ge=0.0, le=1.0, description="Dimension score in [0.0, 1.0]")
    weight: float = Field(..., ge=0.0, le=1.0, description="Dimension weight")
    weighted_score: float = Field(..., description="Dimension score multiplied by weight")
    status: PreferenceMatchType = Field(..., description="Dimension match status")
    explanation: str = Field(..., description="Human-readable explanation")


class PersonalizationScoreBreakdown(BaseModel):
    """
    Comprehensive breakdown of personalization scoring across dimensions and polarities.
    """

    model_config = ConfigDict(from_attributes=True)

    dimension_scores: dict[PreferenceDimension, PersonalizationDimensionScore] = Field(
        default_factory=dict,
        description="Per-dimension scores and statuses",
    )
    positive_contributions: list[PersonalizationContribution] = Field(
        default_factory=list,
        description="Dimensions with positive preferred matches",
    )
    negative_contributions: list[PersonalizationContribution] = Field(
        default_factory=list,
        description="Dimensions with explicit exclusion penalties",
    )
    neutral_contributions: list[PersonalizationContribution] = Field(
        default_factory=list,
        description="Dimensions with neutral / unspecified preferences",
    )
    unresolved_contributions: list[PersonalizationContribution] = Field(
        default_factory=list,
        description="Dimensions with conflicts or insufficient evidence",
    )
    total_positive_weight: float = Field(0.0, ge=0.0, description="Sum of positive weights")
    total_negative_weight: float = Field(0.0, ge=0.0, description="Sum of negative weights")
    active_dimensions_count: int = Field(0, description="Number of active preference dimensions evaluated")


class PersonalizationExplanation(BaseModel):
    """
    Multi-faceted, deterministic explanation of personalization scoring.
    """

    model_config = ConfigDict(from_attributes=True)

    summary: str = Field(..., description="Executive summary of personalization score")
    positive_reasons: list[str] = Field(default_factory=list, description="Reasons for positive score contributions")
    negative_reasons: list[str] = Field(default_factory=list, description="Reasons for negative score penalties")
    unresolved_reasons: list[str] = Field(default_factory=list, description="Reasons for unresolved/conflict signals")
    insufficient_evidence_reasons: list[str] = Field(
        default_factory=list,
        description="Dimensions where opportunity evidence was missing",
    )
    neutral_reasons: list[str] = Field(default_factory=list, description="Dimensions without explicit preferences")


class PersonalizationScore(BaseModel):
    """
    Calculated personalization score with bounding and confidence metrics.
    """

    model_config = ConfigDict(from_attributes=True)

    bounded_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Authoritative bounded personalization score in [0.0, 1.0]",
    )
    normalized_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Score normalized relative to active preferences in [0.0, 1.0]",
    )
    absolute_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Score relative to all 9 dimensions in [0.0, 1.0]",
    )
    raw_score: float = Field(
        ...,
        description="Signed net contribution (positive minus negative)",
    )
    positive_contribution: float = Field(..., ge=0.0, description="Sum of positive contributions")
    negative_penalty: float = Field(..., ge=0.0, description="Sum of negative penalties")
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Evidence completeness confidence in [0.0, 1.0]",
    )
    match_state: PreferenceMatchType = Field(..., description="Overall match state from Phase 5.2")


class PersonalizationAssessment(BaseModel):
    """
    Complete Phase 5.3 Personalization Assessment combining score, breakdown, explanations,
    and underlying Phase 5.2 preference match signals.
    """

    model_config = ConfigDict(from_attributes=True)

    profile_id: uuid.UUID = Field(..., description="Canonical ResearchProfileModel ID")
    opportunity_id: uuid.UUID = Field(..., description="Canonical OpportunityModel ID")
    personalization_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Top-level bounded score in [0.0, 1.0]",
    )
    score: PersonalizationScore = Field(..., description="Detailed score metrics")
    breakdown: PersonalizationScoreBreakdown = Field(..., description="Structured dimension breakdown")
    explanation: PersonalizationExplanation = Field(..., description="Deterministic natural-language explanations")
    preference_assessment: PreferencePersonalizationAssessment = Field(
        ...,
        description="Underlying Phase 5.2 preference evaluation",
    )
    adaptive_score: float = Field(
        0.0,
        description="Additive bounded contribution from Phase 5.5 adaptive preference signals [-0.10, +0.10]",
    )
    adaptive_contributions: list[AdaptivePersonalizationContribution] = Field(
        default_factory=list,
        description="Dimension-level adaptive preference contributions",
    )
    calibration_score: float = Field(
        0.0,
        description="Net additive calibration modifier from Phase 5.6 [-0.05, +0.05]",
    )
    evaluated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp of evaluation",
    )


class BatchPersonalizationRequest(BaseModel):
    """Payload for batch personalization scoring."""

    opportunity_ids: list[uuid.UUID] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="List of opportunity IDs to score in batch",
    )


class BatchPersonalizationResponse(BaseModel):
    """Response container for batch personalization scoring."""

    model_config = ConfigDict(from_attributes=True)

    profile_id: uuid.UUID = Field(..., description="Canonical ResearchProfileModel ID")
    assessments: list[PersonalizationAssessment] = Field(
        default_factory=list,
        description="Personalization assessments for each requested opportunity",
    )
    evaluated_count: int = Field(..., description="Number of opportunities evaluated")

