from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.personalization_quality import (
    ContextualFallbackLevel,
    QualityEvaluationState,
)


class PersonalizationQualityEvaluationSchema(BaseModel):
    """Domain representation of an aggregated personalization quality evaluation record."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    profile_id: uuid.UUID
    evaluation_period_days: float = 30.0
    recommendations_evaluated_count: int = 0
    attributed_interactions_count: int = 0
    positive_outcomes_count: int = 0
    negative_outcomes_count: int = 0
    neutral_outcomes_count: int = 0
    observed_engagement_rate: float = 0.0
    observed_positive_rate: float = 0.0
    observed_negative_rate: float = 0.0
    baseline_engagement_rate: float = 0.0
    baseline_positive_rate: float = 0.0
    observed_personalization_lift: float = 0.0
    confidence: float = 0.0
    evaluation_state: QualityEvaluationState = QualityEvaluationState.INSUFFICIENT_DATA
    diversity_score: float = 0.0
    novelty_rate: float = 0.0
    contextual_breakdown: dict[str, Any] = Field(default_factory=dict)
    deterministic_explanation: str
    algorithm_version: str = "5.7.1"
    created_at: datetime
    updated_at: datetime


class PersonalizationContextualAdaptationSchema(BaseModel):
    """Domain representation of a contextual adaptation record for a signal in a specific context."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    profile_id: uuid.UUID
    dimension: str
    signal_value: str
    context_dimension: str
    context_value: str
    sample_size: int = 0
    positive_count: int = 0
    negative_count: int = 0
    observed_lift: float = 0.0
    confidence: float = 0.0
    fallback_level: ContextualFallbackLevel = ContextualFallbackLevel.RESEARCHER_EXACT_CONTEXT
    contextual_modifier: float = 0.0
    hysteresis_state: str = "STABLE"
    evaluation_state: QualityEvaluationState = QualityEvaluationState.INSUFFICIENT_DATA
    deterministic_explanation: str
    algorithm_version: str = "5.7.1"
    created_at: datetime
    updated_at: datetime


class ContextualSummaryItem(BaseModel):
    """Summary of personalization performance in a specific context."""

    context_dimension: str
    context_value: str
    sample_size: int = 0
    positive_rate: float = 0.0
    observed_lift: float = 0.0
    evaluation_state: QualityEvaluationState
    explanation: str


class SignalQualitySummaryItem(BaseModel):
    """Summary of personalization quality for a specific signal."""

    dimension: str
    signal_value: str
    sample_size: int = 0
    positive_count: int = 0
    negative_count: int = 0
    observed_lift: float = 0.0
    confidence: float = 0.0
    evaluation_state: QualityEvaluationState
    contexts_count: int = 0
    explanation: str


class PersonalizationQualityResponse(BaseModel):
    """Top-level response for researcher personalization quality."""

    profile_id: uuid.UUID
    evaluation: PersonalizationQualityEvaluationSchema
    context_summaries: list[ContextualSummaryItem] = Field(default_factory=list)
    deterministic_explanation: str


class ContextualAdaptationsResponse(BaseModel):
    """Response containing all contextual adaptations for a researcher."""

    profile_id: uuid.UUID
    items: list[PersonalizationContextualAdaptationSchema] = Field(default_factory=list)
    total_count: int = 0


class SignalQualityResponse(BaseModel):
    """Response containing signal-level quality breakdowns."""

    profile_id: uuid.UUID
    items: list[SignalQualitySummaryItem] = Field(default_factory=list)
    total_count: int = 0


class QualityRecomputeRequest(BaseModel):
    """Payload for triggering on-demand quality evaluation recomputation."""

    reference_time: Optional[datetime] = Field(
        default=None,
        description="Explicit reference timestamp for deterministic temporal evaluation. Defaults to current UTC time.",
    )
    evaluation_period_days: Optional[float] = Field(
        default=None,
        ge=1.0,
        le=365.0,
        description="Evaluation window in days (default: 30.0).",
    )
    force_recompute: bool = Field(
        default=False,
        description="Whether to force recalculation.",
    )
