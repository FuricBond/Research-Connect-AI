"""
Domain models for Phase 5.5 — Adaptive Preference Signal Aggregation & Personalization Bridge.

Re-exports schemas from app.schemas.adaptive_signal.
"""
from __future__ import annotations

from app.models.adaptive_signal import (
    AdaptiveEvidenceState,
    AdaptiveSignalDimension,
)
from app.schemas.adaptive_signal import (
    AdaptivePersonalizationContribution,
    AdaptivePreferenceSignal,
    AdaptiveSignalExplanationResponse,
    AdaptiveSignalRecomputeRequest,
    AdaptiveSignalsResponse,
)

__all__ = [
    "AdaptiveSignalDimension",
    "AdaptiveEvidenceState",
    "AdaptivePreferenceSignal",
    "AdaptivePersonalizationContribution",
    "AdaptiveSignalsResponse",
    "AdaptiveSignalExplanationResponse",
    "AdaptiveSignalRecomputeRequest",
]
