from __future__ import annotations

from dataclasses import dataclass
import math

from app.models.personalization_governance import (
    AdaptationState,
    GovernanceGateState,
    PersonalizationHealthState,
)


@dataclass(frozen=True)
class PersonalizationGovernanceConfig:
    """
    Configuration parameters, thresholds, and bounds for Phase 5.8 Personalization Governance & Drift Detection.

    All properties are immutable, deterministic, and versioned.
    """

    # Algorithm version
    algorithm_version: str = "5.8.1"

    # Evaluation windows
    default_historical_window_days: float = 60.0
    default_recent_window_days: float = 14.0
    min_recent_window_days: float = 3.0
    max_recent_window_days: float = 60.0
    max_historical_window_days: float = 365.0

    # Staleness threshold (180 days ~ 6 months without interaction)
    stale_evidence_days: float = 180.0

    # Minimum sample sizes
    min_interactions_for_evaluation: int = 3
    min_recent_interactions_for_drift: int = 2
    medium_evidence_interactions: int = 6
    high_evidence_interactions: int = 8

    # Drift thresholds
    drift_difference_threshold: float = 0.20
    reversing_drift_threshold: float = 0.15
    stable_difference_threshold: float = 0.05

    # Adaptation multipliers for governance gate states
    allow_multiplier: float = 1.0
    allow_bounded_multiplier: float = 0.50
    hold_multiplier: float = 0.25
    reduce_multiplier: float = 0.10
    suspend_multiplier: float = 0.0  # Strictly neutral 0.0

    # Hysteresis and recovery
    hysteresis_min_evidence: int = 3
    recovery_evidence_threshold: int = 5
    recovery_stability_ratio: float = 0.80

    # Invariant bounds
    max_contextual_modifier: float = 0.03
    min_contextual_modifier: float = -0.03
    max_calibration_modifier: float = 0.05
    min_calibration_modifier: float = -0.05
    max_total_adaptive_contribution: float = 0.10
    min_total_adaptive_contribution: float = -0.10


DEFAULT_GOVERNANCE_CONFIG = PersonalizationGovernanceConfig()
