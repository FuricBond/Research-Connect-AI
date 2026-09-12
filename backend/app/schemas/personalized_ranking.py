"""
Pydantic schemas for Phase 3.5 — Personalization Ranking Layer.

Strict Architectural Boundaries:
  - Preserves Phase 2 base ranker and Phase 2.6 risk & Phase 2.7 deadline intelligence.
  - Personalization adjustment is strictly bounded: MAX_PERSONALIZATION_CONTRIBUTION <= 0.15.
  - Exposes structured explainable breakdown for later Phase 3.8 explainability work.
  - Enables direct R0 (base) vs R1 (personalized) ablation comparisons.
"""
from __future__ import annotations

from typing import Any
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.personalized_candidate import (
    CandidateProvenanceSchema,
    PersonalizedCandidateOpportunitySchema,
)
from app.schemas.recommendation_explanation import RecommendationExplanationSchema


class PersonalizationScoreBreakdownSchema(BaseModel):
    """
    Detailed, explainable breakdown of the individual components
    comprising the bounded personalization adjustment.
    """

    model_config = ConfigDict(from_attributes=True)

    explicit_preference_score: float = Field(
        0.0,
        ge=0.0,
        le=1.0,
        description="Match score from explicit researcher preferences (weight: 0.40)",
    )
    inferred_preference_score: float = Field(
        0.0,
        ge=0.0,
        le=1.0,
        description="Match score from verified inferred preferences (weight: 0.15)",
    )
    expertise_match_score: float = Field(
        0.0,
        ge=0.0,
        le=1.0,
        description="Match score from Phase 3.2 scholarly expertise & emerging interests (weight: 0.25)",
    )
    profile_match_score: float = Field(
        0.0,
        ge=0.0,
        le=1.0,
        description="Match score from profile keywords and target opportunity types (weight: 0.10)",
    )
    provenance_score: float = Field(
        0.0,
        ge=0.0,
        le=1.0,
        description="Candidate source breadth from Phase 3.4 multi-channel discovery (weight: 0.10)",
    )
    behavioral_score: float = Field(
        0.0,
        ge=0.0,
        le=1.0,
        description="Match score from Phase 3.6 learned behavioral feedback signals",
    )
    behavioral_confidence: float = Field(
        0.0,
        ge=0.0,
        le=1.0,
        description="Confidence of supporting behavioral feedback signals",
    )
    behavioral_adjustment: float = Field(
        0.0,
        description="Signed contribution of learned behavioral feedback to personalization",
    )
    raw_personalization_score: float = Field(
        0.0,
        ge=0.0,
        le=1.0,
        description="Normalized composite personalization score in [0.0, 1.0] before damping/capping",
    )
    relevance_damping: float = Field(
        1.0,
        ge=0.0,
        le=1.0,
        description="Base-relevance damping factor preventing manufacture of relevance for weak candidates",
    )


class MatchedPersonalizationSignalsSchema(BaseModel):
    """
    Human-readable summaries of specific signals matched between candidate and researcher.
    """

    model_config = ConfigDict(from_attributes=True)

    matched_preferences: list[str] = Field(
        default_factory=list,
        description="Specific preference dimensions matched (e.g. 'Conference', 'Hybrid')",
    )
    matched_expertise: list[str] = Field(
        default_factory=list,
        description="Scholarly expertise topics matched (e.g. 'Machine Learning (Primary)')",
    )
    matched_topics: list[str] = Field(
        default_factory=list,
        description="All matched canonical topic names",
    )
    matched_types: list[str] = Field(
        default_factory=list,
        description="Matched opportunity types or delivery modes",
    )


class PersonalizedRankedCandidateSchema(BaseModel):
    """
    An individual personalized recommendation result, containing both
    Phase 2 base relevance and Phase 3.5 bounded personalization adjustments.
    """

    model_config = ConfigDict(from_attributes=True)

    opportunity_id: uuid.UUID = Field(..., description="Canonical opportunity identifier")
    rank: int = Field(..., ge=1, description="1-based final personalized rank position (R1)")
    base_rank: int = Field(..., ge=1, description="1-based Phase 2 base rank position (R0 baseline)")
    rank_delta: int = Field(
        ...,
        description="Rank movement (base_rank - rank: >0 promoted, <0 demoted, 0 unchanged)",
    )
    final_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Composite final recommendation score: min(1.0, base_relevance_score + adjustment)",
    )
    base_relevance_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Authoritative Phase 2 base relevance score (HybridRanker composite)",
    )
    personalization_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Raw composite personalization score in [0.0, 1.0]",
    )
    personalization_adjustment: float = Field(
        ...,
        ge=0.0,
        le=0.15,
        description="Bounded additive personalization contribution (strictly capped at 0.15)",
    )
    score_breakdown: PersonalizationScoreBreakdownSchema = Field(
        ...,
        description="Component-level score attribution",
    )
    matched_signals: MatchedPersonalizationSignalsSchema = Field(
        ...,
        description="Human-readable matched signal summaries",
    )
    provenance: CandidateProvenanceSchema = Field(
        ...,
        description="Phase 3.4 candidate pool entry provenance",
    )
    opportunity: PersonalizedCandidateOpportunitySchema = Field(
        ...,
        description="Opportunity metadata with Phase 2.6 risk & Phase 2.7 deadline intelligence",
    )
    explanation: RecommendationExplanationSchema | None = Field(
        None,
        description="Phase 3.8 structured human-readable and machine-inspectable explanation",
    )


class AblationSummarySchema(BaseModel):
    """
    Deterministic diagnostic comparison between Phase 2 baseline (R0)
    and Phase 3.5 personalized ranking (R1).
    """

    model_config = ConfigDict(from_attributes=True)

    total_candidates: int = Field(..., description="Total candidate count evaluated")
    reordered_candidates_count: int = Field(..., description="Number of candidates whose rank changed")
    max_rank_promotion: int = Field(0, description="Highest rank increase (+N)")
    max_rank_demotion: int = Field(0, description="Highest rank decrease (-N)")
    average_personalization_adjustment: float = Field(
        0.0,
        description="Mean personalization adjustment applied across candidates",
    )
    invariants_verified: bool = Field(
        True,
        description="True if all relevance dominance and monotonicity invariants were preserved",
    )


class PersonalizedRankingResponse(BaseModel):
    """
    Authoritative response envelope for Phase 3.5 Personalization Ranking Layer.
    """

    model_config = ConfigDict(from_attributes=True)

    researcher_id: uuid.UUID = Field(..., description="Target researcher profile identifier")
    total_candidates: int = Field(..., description="Total available candidates before pagination")
    ranked_count: int = Field(..., description="Number of recommendations returned in this response")
    is_cold_start: bool = Field(..., description="True if fallback retrieval / cold start applied")
    personalization_enabled: bool = Field(
        True,
        description="True if Phase 3.5 personalization adjustment was applied (False = pure R0 base rank)",
    )
    max_personalization_contribution: float = Field(
        0.15,
        description="Bounded maximum personalization adjustment ceiling",
    )
    recommendations: list[PersonalizedRankedCandidateSchema] = Field(
        default_factory=list,
        description="Deterministically ranked personalized recommendations",
    )
    ablation_summary: AblationSummarySchema | None = Field(
        None,
        description="Diagnostic comparison against Phase 2 baseline ranking",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Execution metadata and performance diagnostics",
    )
