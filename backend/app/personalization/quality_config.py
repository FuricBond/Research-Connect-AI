from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Mapping

from app.models.personalization_quality import (
    ContextualFallbackLevel,
    QualityEvaluationState,
)


@dataclass(frozen=True)
class PersonalizationQualityConfig:
    """
    Configuration parameters, thresholds, and bounds for Phase 5.7 Personalization Quality Evaluation.

    All properties are immutable, deterministic, and versioned.
    """

    # Algorithm version
    algorithm_version: str = "5.7.1"

    # Evaluation windows
    default_evaluation_period_days: float = 30.0
    max_evaluation_period_days: float = 365.0
    min_evaluation_period_days: float = 1.0

    # Evidence volume thresholds
    insufficient_min_count: int = 3
    early_min_count: int = 3
    stable_min_count: int = 10

    # Minimum confidence thresholds
    insufficient_min_confidence: float = 0.20
    context_min_confidence: float = 0.30
    stable_min_confidence: float = 0.50

    # Contextual adaptation bounds
    max_contextual_modifier: float = 0.03
    min_contextual_modifier: float = -0.03

    # Clamping bounds for combined calibration and adaptive signals
    max_calibration_modifier: float = 0.05
    min_calibration_modifier: float = -0.05
    max_total_adaptive_contribution: float = 0.10
    min_total_adaptive_contribution: float = -0.10

    # Exponential temporal decay
    half_life_days: float = 30.0
    min_decay_weight_floor: float = 0.05
    max_horizon_days: float = 90.0

    # Hysteresis and stability
    hysteresis_buffer: float = 0.01
    min_state_transition_evidence: int = 2

    # Anti-feedback-loop safeguards
    max_outcomes_per_opportunity_per_context: int = 1

    # Lift thresholds for state classification
    positive_lift_threshold: float = 0.03
    negative_lift_threshold: float = -0.03

    def calculate_decay(self, age_days: float) -> float:
        """
        Calculate deterministic exponential temporal decay factor.
        Formula: 2^(-age_days / half_life_days), clamped above floor.
        """
        if age_days <= 0.0:
            return 1.0
        if age_days > self.max_horizon_days:
            return 0.0
        decay = math.pow(2.0, -age_days / self.half_life_days)
        return max(self.min_decay_weight_floor, min(1.0, decay))

    def determine_evaluation_state(
        self,
        sample_size: int,
        confidence: float,
        lift: float,
        positive_rate: float,
        negative_rate: float,
    ) -> QualityEvaluationState:
        """
        Determine deterministic quality evaluation state based on volume, confidence, and lift.
        """
        if sample_size < self.insufficient_min_count or confidence < self.insufficient_min_confidence:
            return QualityEvaluationState.INSUFFICIENT_DATA

        if sample_size < self.stable_min_count or confidence < self.stable_min_confidence:
            # Under moderate sample size: EARLY_SIGNAL or EVALUATING
            if lift >= self.positive_lift_threshold:
                return QualityEvaluationState.EARLY_SIGNAL
            if lift <= self.negative_lift_threshold:
                return QualityEvaluationState.EARLY_SIGNAL
            return QualityEvaluationState.EVALUATING

        # Stable sample size & confidence
        if lift >= self.positive_lift_threshold and positive_rate > negative_rate:
            return QualityEvaluationState.POSITIVE
        if lift <= self.negative_lift_threshold and negative_rate > positive_rate:
            return QualityEvaluationState.NEGATIVE
        if abs(lift) < self.positive_lift_threshold and (positive_rate > 0 and negative_rate > 0):
            return QualityEvaluationState.MIXED
        return QualityEvaluationState.STABLE


DEFAULT_QUALITY_CONFIG = PersonalizationQualityConfig()
