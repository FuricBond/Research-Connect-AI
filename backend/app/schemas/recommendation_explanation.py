"""
Pydantic schemas for Phase 3.8 — Personalization Explainability + Researcher UI.

Strict Architectural Boundaries:
  - Transparent, inspectable, and human-readable explanation layer over Phase 3.5 ranking.
  - Zero mathematical hallucinations: all claims are strictly grounded in active or historical signals.
  - Full score consistency: reported scores exactly match candidate and ranking engine scores.
  - Prominent safety dominance: high-risk opportunities prominently preserve risk warnings.
  - Point-in-time historical explanation immutability: frozen snapshots never re-rank with today's data.
"""
from __future__ import annotations

from enum import Enum
from typing import Any
import uuid

from pydantic import BaseModel, ConfigDict, Field


class ExplanationReasonCategory(str, Enum):
    """Semantic category classifying an individual explanation reason."""

    EXPLICIT_PREFERENCE = "EXPLICIT_PREFERENCE"
    EXPERTISE_MATCH = "EXPERTISE_MATCH"
    BEHAVIORAL_SIGNAL = "BEHAVIORAL_SIGNAL"
    PROFILE_MATCH = "PROFILE_MATCH"
    DOMAIN_RELEVANCE = "DOMAIN_RELEVANCE"
    DEADLINE_URGENCY = "DEADLINE_URGENCY"
    TRUST_SAFETY = "TRUST_SAFETY"
    NEGATIVE_SIGNAL = "NEGATIVE_SIGNAL"


class SignalImpact(str, Enum):
    """Direction of influence of a signal on the final recommendation."""

    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    NEUTRAL = "NEUTRAL"
    WARNING = "WARNING"


class ExplanationFactorSchema(BaseModel):
    """Detailed factored signal contributing to an opportunity's recommendation."""

    model_config = ConfigDict(from_attributes=True)

    category: ExplanationReasonCategory = Field(
        ...,
        description="Semantic category of the explanation factor",
    )
    title: str = Field(
        ...,
        description="Concise human-readable factor title (e.g. 'Opportunity Type Match')",
    )
    description: str = Field(
        ...,
        description="Full explanatory text (e.g. 'Matches your preferred type: Conference')",
    )
    impact: SignalImpact = Field(
        SignalImpact.POSITIVE,
        description="Direction of impact (POSITIVE, NEGATIVE, NEUTRAL, WARNING)",
    )
    weight_contribution: float = Field(
        0.0,
        description="Relative score or adjustment contribution of this factor",
    )


class RecommendationExplanationSchema(BaseModel):
    """
    Complete structured explanation container for an individual recommendation.

    Answers:
      - 'Why am I seeing this opportunity?'
      - 'Which preferences, expertise, interests, and behaviors influenced this ranking?'
    """

    model_config = ConfigDict(from_attributes=True)

    opportunity_id: uuid.UUID = Field(
        ...,
        description="Canonical opportunity identifier",
    )
    rank: int = Field(
        ...,
        ge=1,
        description="1-based recommendation rank position",
    )
    final_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Composite final recommendation score",
    )
    base_relevance_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Authoritative Phase 2 base relevance score",
    )
    personalization_contribution: float = Field(
        ...,
        ge=0.0,
        le=0.15,
        description="Bounded additive personalization contribution",
    )
    personalization_strength: str = Field(
        ...,
        description="Human-friendly personalization level: 'Highly personalized', 'Personalized', 'Some personalization', 'General recommendation'",
    )
    primary_reasons: list[str] = Field(
        default_factory=list,
        description="Top human-readable reasons in strict influence priority order",
    )
    supporting_reasons: list[str] = Field(
        default_factory=list,
        description="Secondary supporting reasons and contextual matches",
    )
    behavioral_reasons: list[str] = Field(
        default_factory=list,
        description="Learned interaction feedback reasons (saves, views, dismissals)",
    )
    preference_reasons: list[str] = Field(
        default_factory=list,
        description="Explicit researcher preference matches (types, modes, career stage)",
    )
    expertise_reasons: list[str] = Field(
        default_factory=list,
        description="Scholarly expertise and emerging research interests matches",
    )
    negative_signals: list[str] = Field(
        default_factory=list,
        description="Demotions, past dismissals, or risk warnings lowering score or requiring caution",
    )
    factors: list[ExplanationFactorSchema] = Field(
        default_factory=list,
        description="Structured explanation factor details",
    )
    risk_summary: str | None = Field(
        None,
        description="Phase 2.6 risk intelligence summary (verified publisher vs caution/predatory warning)",
    )
    deadline_summary: str | None = Field(
        None,
        description="Phase 2.7 deadline intelligence summary (days remaining, urgency level)",
    )
    confidence: float = Field(
        1.0,
        ge=0.0,
        le=1.0,
        description="Explanation confidence based on supporting signal volume and consistency",
    )
    trust_status: str = Field(
        "Verified",
        description="Trust status: 'Verified', 'Caution', or 'High Risk'",
    )
    is_historical: bool = Field(
        False,
        description="True if explanation was generated from an immutable historical snapshot",
    )
    ranking_version: str = Field(
        "phase3.8-v1",
        description="Ranking pipeline version that produced this recommendation",
    )


class LearnedSignalItemSchema(BaseModel):
    """Summary of an individual learned preference dimension."""

    model_config = ConfigDict(from_attributes=True)

    dimension: str = Field(..., description="Category (TOPIC, OPPORTUNITY_TYPE, DELIVERY_MODE, etc.)")
    value: str = Field(..., description="Preference value (e.g. 'Machine Learning', 'Conference')")
    strength: str = Field(..., description="'Strong', 'Moderate', 'Weak', or 'Negative'")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in learned signal")
    direction: str = Field(..., description="'POSITIVE' or 'NEGATIVE'")
    sample_count: int = Field(0, description="Number of supporting feedback events")


class PersonalizationSummaryResponse(BaseModel):
    """
    Researcher-level personalization overview.

    Provides a comprehensive snapshot of active profile signals, learned preferences,
    and system confidence to power the 'Your Research Personalization' dashboard.
    """

    model_config = ConfigDict(from_attributes=True)

    researcher_id: uuid.UUID = Field(
        ...,
        description="Canonical researcher profile identifier",
    )
    active_interests_count: int = Field(
        ...,
        description="Total active scholarly research interests and expertise topics",
    )
    strong_expertise_count: int = Field(
        ...,
        description="Count of verified primary/secondary expertise topics",
    )
    explicit_preferences_count: int = Field(
        ...,
        description="Count of explicitly configured researcher preferences",
    )
    behavioral_signals_count: int = Field(
        ...,
        description="Count of active learned behavioral preference signals",
    )
    personalization_confidence: str = Field(
        ...,
        description="Overall personalization confidence: 'High', 'Moderate', 'Low', 'Cold Start'",
    )
    confidence_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Numerical personalization confidence score",
    )
    is_cold_start: bool = Field(
        ...,
        description="True if researcher has insufficient profile/preference data",
    )
    has_feedback: bool = Field(
        ...,
        description="True if researcher has submitted recommendation feedback",
    )
    total_feedback_count: int = Field(
        ...,
        description="Total feedback interactions recorded",
    )
    learned_topics: list[LearnedSignalItemSchema] = Field(
        default_factory=list,
        description="Top learned topic preferences from activity",
    )
    learned_opportunity_types: list[LearnedSignalItemSchema] = Field(
        default_factory=list,
        description="Learned opportunity type affinities (conferences, journals, grants)",
    )
    learned_delivery_modes: list[LearnedSignalItemSchema] = Field(
        default_factory=list,
        description="Learned delivery mode affinities (online, hybrid, in-person)",
    )
    top_positive_signals: list[str] = Field(
        default_factory=list,
        description="Top positive drivers across explicit and learned preferences",
    )
    top_negative_signals: list[str] = Field(
        default_factory=list,
        description="Suppression and negative signal drivers",
    )
