from __future__ import annotations

from datetime import datetime
from typing import Any
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.personalization_calibration import (
    AttributionConfidence,
    CalibrationState,
    FeedbackOutcomeType,
)


class RecommendationFeedbackAttributionSchema(BaseModel):
    """Granular attribution event linking recommendation exposure to feedback interaction."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    profile_id: uuid.UUID
    opportunity_id: uuid.UUID
    interaction_id: uuid.UUID | None = None
    dimension: str
    signal_value: str
    personalization_contribution: float = 0.0
    interaction_type: str
    outcome_type: FeedbackOutcomeType
    attribution_confidence: AttributionConfidence
    attribution_weight: float = 1.0
    decay_adjusted_weight: float = 0.0
    recommendation_timestamp: datetime
    interaction_timestamp: datetime
    algorithm_version: str = "5.6.1"
    created_at: datetime


class PersonalizationCalibrationSchema(BaseModel):
    """Domain representation of an aggregated personalization calibration record."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    profile_id: uuid.UUID
    signal_id: uuid.UUID | None = None
    dimension: str
    signal_value: str
    recommendations_influenced_count: int = 0
    positive_outcome_count: int = 0
    negative_outcome_count: int = 0
    neutral_outcome_count: int = 0
    accumulated_positive_weight: float = 0.0
    accumulated_negative_weight: float = 0.0
    net_calibration_modifier: float = 0.0
    calibration_confidence: float = 0.0
    calibration_state: CalibrationState = CalibrationState.INSUFFICIENT_DATA
    algorithm_version: str = "5.6.1"
    deterministic_explanation: str
    latest_feedback_timestamp: datetime | None = None
    created_at: datetime
    updated_at: datetime


class PersonalizationCalibrationResponse(BaseModel):
    """Paginated or summary response containing all calibrations for a researcher."""

    profile_id: uuid.UUID
    items: list[PersonalizationCalibrationSchema] = Field(default_factory=list)
    total_count: int = 0
    state_counts: dict[str, int] = Field(default_factory=dict)
    average_confidence: float = 0.0
    calibrated_signals_count: int = 0


class PersonalizationCalibrationDetailResponse(BaseModel):
    """Detailed view of a single signal calibration with granular attribution events."""

    calibration: PersonalizationCalibrationSchema
    attributions: list[RecommendationFeedbackAttributionSchema] = Field(default_factory=list)
    total_attributions: int = 0


class CalibrationRecomputeRequest(BaseModel):
    """Optional configuration parameters for on-demand calibration recomputation."""

    attribution_window_days: float | None = Field(
        default=None,
        ge=1.0,
        le=90.0,
        description="Override attribution window horizon in days (default 14.0)",
    )
