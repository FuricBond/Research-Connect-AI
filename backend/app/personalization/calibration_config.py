from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Mapping

from app.models.personalization_calibration import (
    AttributionConfidence,
    FeedbackOutcomeType,
)
from app.models.researcher_interaction import InteractionType


@dataclass(frozen=True)
class PersonalizationCalibrationConfig:
    """
    Configuration parameters and thresholds for Phase 5.6 Personalization Calibration.

    All properties are immutable and deterministic.
    """

    # Algorithm version
    algorithm_version: str = "5.6.1"

    # Temporal attribution windows
    attribution_window_days: float = 14.0
    direct_window_hours: float = 24.0
    likely_window_days: float = 7.0

    # Attribution confidence multipliers
    confidence_multipliers: Mapping[AttributionConfidence, float] = field(
        default_factory=lambda: {
            AttributionConfidence.DIRECT: 1.0,
            AttributionConfidence.LIKELY: 0.75,
            AttributionConfidence.WEAK: 0.40,
            AttributionConfidence.UNATTRIBUTED: 0.0,
        }
    )

    # Base outcome weights by interaction type
    interaction_weights: Mapping[str, float] = field(
        default_factory=lambda: {
            # Strong positive
            InteractionType.APPLIED.value: 1.0,
            InteractionType.INTERESTED.value: 0.8,
            # Moderate positive
            InteractionType.SAVED.value: 0.6,
            InteractionType.SHARED.value: 0.3,
            # Weak positive
            InteractionType.OPENED.value: 0.10,
            InteractionType.VIEWED.value: 0.05,
            # Negative
            InteractionType.NOT_INTERESTED.value: -0.70,
            InteractionType.DISMISSED.value: -0.50,
            InteractionType.HIDDEN.value: -0.90,
        }
    )

    # Interaction type to outcome type mapping
    outcome_classification: Mapping[str, FeedbackOutcomeType] = field(
        default_factory=lambda: {
            InteractionType.APPLIED.value: FeedbackOutcomeType.STRONG_POSITIVE,
            InteractionType.INTERESTED.value: FeedbackOutcomeType.STRONG_POSITIVE,
            InteractionType.SAVED.value: FeedbackOutcomeType.MODERATE_POSITIVE,
            InteractionType.SHARED.value: FeedbackOutcomeType.MODERATE_POSITIVE,
            InteractionType.OPENED.value: FeedbackOutcomeType.WEAK_POSITIVE,
            InteractionType.VIEWED.value: FeedbackOutcomeType.WEAK_POSITIVE,
            InteractionType.NOT_INTERESTED.value: FeedbackOutcomeType.NEGATIVE,
            InteractionType.DISMISSED.value: FeedbackOutcomeType.NEGATIVE,
            InteractionType.HIDDEN.value: FeedbackOutcomeType.NEGATIVE,
        }
    )

    # Exponential temporal decay
    half_life_days: float = 30.0
    min_decay_weight_floor: float = 0.05
    max_horizon_days: float = 90.0

    # Calibration modifier bounds
    max_positive_modifier: float = 0.05
    max_negative_modifier: float = -0.05

    # Evidence volume thresholds
    insufficient_min_count: int = 3
    early_min_count: int = 3
    calibrating_min_count: int = 6
    stable_min_count: int = 12

    # Minimum confidence thresholds
    insufficient_min_confidence: float = 0.20
    stable_min_confidence: float = 0.50

    # Conflicted evidence threshold
    conflict_ratio_threshold: float = 0.40

    # Volume scaling curvature
    volume_scale_kappa: float = 8.0
    consistency_epsilon: float = 1e-4

    # Anti-feedback-loop safeguards
    max_outcomes_per_opportunity_per_signal: int = 1

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

    def get_attribution_confidence(
        self,
        recommendation_time: float,
        interaction_time: float,
        is_direct_session_link: bool = False,
    ) -> tuple[AttributionConfidence, float]:
        """
        Determine attribution tier and confidence multiplier based on timing and direct link.

        Parameters
        ----------
        recommendation_time : float
            Timestamp of recommendation exposure in seconds.
        interaction_time : float
            Timestamp of subsequent interaction in seconds.
        is_direct_session_link : bool
            Whether interaction carries explicit recommendation session or snapshot link.
        """
        diff_seconds = interaction_time - recommendation_time

        # Interaction occurred before recommendation: cannot be attributed
        if diff_seconds < 0:
            return AttributionConfidence.UNATTRIBUTED, 0.0

        diff_days = diff_seconds / 86400.0

        # Outside attribution window: cannot be attributed
        if diff_days > self.attribution_window_days:
            return AttributionConfidence.UNATTRIBUTED, 0.0

        if is_direct_session_link or diff_seconds <= self.direct_window_hours * 3600.0:
            conf = AttributionConfidence.DIRECT
        elif diff_days <= self.likely_window_days:
            conf = AttributionConfidence.LIKELY
        else:
            conf = AttributionConfidence.WEAK

        multiplier = self.confidence_multipliers.get(conf, 0.0)
        return conf, multiplier


DEFAULT_CALIBRATION_CONFIG = PersonalizationCalibrationConfig()
