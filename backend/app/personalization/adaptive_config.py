"""
Centralized Configuration for Phase 5.5 — Adaptive Preference Signal Aggregation & Personalization Bridge.

Defines:
  - Interaction event base weights
  - Temporal exponential decay parameters
  - Volume scaling and confidence parameters
  - Minimum evidence thresholds
  - Dimension importance weights for adaptive personalization
  - Safety contribution limits and explicit preference protection floors
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Mapping

from app.models.adaptive_signal import AdaptiveSignalDimension
from app.models.researcher_interaction import InteractionType


@dataclass(frozen=True)
class AdaptiveSignalConfig:
    """
    Configuration parameters for adaptive preference signal aggregation.
    """

    # Base interaction weights: positive signals increase affinity, negative signals decrease it
    interaction_weights: Mapping[str, float] = field(
        default_factory=lambda: {
            InteractionType.VIEWED.value: 0.05,        # Weak positive observation
            InteractionType.OPENED.value: 0.10,        # Weak positive observation
            InteractionType.SAVED.value: 0.50,         # Strong positive intentional action
            InteractionType.INTERESTED.value: 0.60,    # Strong positive explicit feedback
            InteractionType.APPLIED.value: 1.00,       # Highest commitment positive action
            InteractionType.SHARED.value: 0.40,        # Moderate collaborative endorsement
            InteractionType.NOT_INTERESTED.value: -0.60, # Strong negative explicit feedback
            InteractionType.DISMISSED.value: -0.40,    # Negative feedback (skipped)
            InteractionType.HIDDEN.value: -0.70,       # Strong negative action (hidden)
        }
    )

    # Temporal exponential decay parameters
    half_life_days: float = 30.0
    decay_lambda: float = math.log(2.0) / 30.0  # ~0.023105
    max_horizon_days: float = 180.0

    # Volume scaling kappa: 1.0 - exp(-N / kappa)
    volume_scale_kappa: float = 5.0

    # Smoothing parameters
    strength_smoothing_epsilon: float = 1.0
    consistency_epsilon: float = 0.10

    # Minimum evidence thresholds
    insufficient_min_count: int = 3
    insufficient_min_confidence: float = 0.25
    emerging_min_count: int = 3
    emerging_min_confidence: float = 0.25
    established_min_count: int = 6
    established_min_confidence: float = 0.50
    strong_min_count: int = 12
    strong_min_confidence: float = 0.75

    # Maximum additive contribution of adaptive signals to personalization
    # Strictly bounded so Phase 4 relevance dominance (>= 0.85) is never compromised
    max_adaptive_contribution: float = 0.10

    # Explicit preference dominance floor: if an explicit preferred preference exists,
    # opposing adaptive signals cannot reduce its score below this floor
    explicit_preference_dominance_floor: float = 0.50

    # Dimension weights for additive personalization scoring (sum to 1.00)
    dimension_weights: Mapping[AdaptiveSignalDimension, float] = field(
        default_factory=lambda: {
            AdaptiveSignalDimension.OPPORTUNITY_TYPE: 0.35,
            AdaptiveSignalDimension.RESEARCH_TOPIC: 0.35,
            AdaptiveSignalDimension.DELIVERY_MODE: 0.10,
            AdaptiveSignalDimension.LOCATION: 0.10,
            AdaptiveSignalDimension.PUBLISHER: 0.10,
        }
    )

    # Version identifier
    algorithm_version: str = "5.5.1"

    def get_interaction_weight(self, interaction_type: str | InteractionType) -> float:
        """Return base weight for an interaction type."""
        key = interaction_type.value if isinstance(interaction_type, InteractionType) else str(interaction_type)
        return self.interaction_weights.get(key, 0.0)

    def calculate_decay(self, age_days: float) -> float:
        """Calculate deterministic exponential decay for age in days."""
        clamped_age = max(0.0, min(age_days, self.max_horizon_days))
        return math.exp(-self.decay_lambda * clamped_age)


DEFAULT_ADAPTIVE_CONFIG = AdaptiveSignalConfig()
