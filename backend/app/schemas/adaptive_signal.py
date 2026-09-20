"""
Pydantic Schemas for Phase 5.5 — Adaptive Preference Signal Aggregation & Personalization Bridge.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.adaptive_signal import (
    AdaptiveEvidenceState,
    AdaptiveSignalDimension,
)


class AdaptivePreferenceSignal(BaseModel):
    """Aggregated adaptive preference signal for a specific researcher and attribute."""

    id: uuid.UUID
    profile_id: uuid.UUID
    dimension: AdaptiveSignalDimension
    signal_value: str
    positive_evidence_count: int
    negative_evidence_count: int
    total_evidence_count: int
    decay_adjusted_positive_weight: float
    decay_adjusted_negative_weight: float
    weighted_signal_strength: float = Field(
        ...,
        description="Bounded net signal strength in [-1.0, 1.0]",
    )
    confidence: float = Field(
        ...,
        description="Confidence metric in [0.0, 1.0]",
    )
    evidence_state: AdaptiveEvidenceState
    evidence_window_days: float
    latest_evidence_timestamp: Optional[datetime] = None
    algorithm_version: str
    deterministic_explanation: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AdaptivePersonalizationContribution(BaseModel):
    """Dimension-level contribution of an adaptive signal to opportunity scoring."""

    dimension: AdaptiveSignalDimension
    signal_value: str
    signal_strength: float
    confidence: float
    evidence_state: AdaptiveEvidenceState
    weight: float
    raw_contribution: float
    bounded_contribution: float
    calibration_modifier: float = 0.0
    explanation: str

    model_config = ConfigDict(from_attributes=True)


class AdaptiveSignalsResponse(BaseModel):
    """Response container for researcher adaptive signals."""

    profile_id: uuid.UUID
    items: list[AdaptivePreferenceSignal]
    total_count: int

    model_config = ConfigDict(from_attributes=True)


class AdaptiveSignalExplanationResponse(BaseModel):
    """Deterministic, structured summary explanation of all adaptive signals for a researcher."""

    profile_id: uuid.UUID
    established_signals_count: int
    emerging_signals_count: int
    insufficient_signals_count: int
    conflict_signals_count: int
    summary_explanation: str
    dimension_explanations: dict[str, list[str]] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)


class AdaptiveSignalRecomputeRequest(BaseModel):
    """Payload for triggering an explicit adaptive signal recomputation."""

    reference_time: Optional[datetime] = Field(
        default=None,
        description="Explicit reference timestamp for deterministic temporal decay. Defaults to current UTC time.",
    )
    force_recompute: bool = Field(
        default=False,
        description="Whether to force recalculation even if recent signals exist.",
    )
