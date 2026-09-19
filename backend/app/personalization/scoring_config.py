"""
Centralized Configuration for Phase 5.3 — Personalization-Aware Opportunity Scoring.

Defines dimension importance weights, match multipliers, and safety bounds.
All scoring parameters are centralized here rather than scattered across logic.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from app.personalization.models import PreferenceDimension, PreferenceMatchType


@dataclass(frozen=True)
class PersonalizationScoringConfig:
    """
    Immutable configuration defining explicit weights and multipliers for personalization scoring.

    Design Rationale for Weights (Sum = 1.00):
      - KEYWORD (0.20): Direct lexical/topical alignment with researcher's specific terms.
      - RESEARCH_DOMAIN (0.20): High-level discipline and field alignment from canonical taxonomy.
      - OPPORTUNITY_TYPE (0.15): Fundamental format alignment (e.g. Conference vs. Grant vs. Fellowship).
      - COUNTRY (0.10): Primary geographic preference and mobility constraint.
      - REGION (0.05): Broader geographic preference (e.g. Europe, North America).
      - INSTITUTION (0.10): Hosting or organizing institution preference.
      - FUNDING (0.10): Financial requirement, stipend, or grant threshold alignment.
      - ACADEMIC_LEVEL (0.05): Target academic seniority (PhD, Postdoc, Faculty).
      - CAREER_STAGE (0.05): Career phase alignment (Early Career, Senior).
    """

    # Base dimension weights (must sum to 1.00)
    dimension_weights: Mapping[PreferenceDimension, float] = field(
        default_factory=lambda: {
            PreferenceDimension.KEYWORD: 0.20,
            PreferenceDimension.RESEARCH_DOMAIN: 0.20,
            PreferenceDimension.OPPORTUNITY_TYPE: 0.15,
            PreferenceDimension.COUNTRY: 0.10,
            PreferenceDimension.REGION: 0.05,
            PreferenceDimension.INSTITUTION: 0.10,
            PreferenceDimension.FUNDING: 0.10,
            PreferenceDimension.ACADEMIC_LEVEL: 0.05,
            PreferenceDimension.CAREER_STAGE: 0.05,
        }
    )

    # Match state multipliers applied to dimension weights
    # Preferred match contributes full positive weight * confidence
    preferred_multiplier: float = 1.0
    # Partial match contributes half positive weight * confidence
    partial_multiplier: float = 0.5
    # Explicit exclusion applies full negative penalty (subtracted from score)
    exclusion_multiplier: float = 1.0
    # Conflict contributes 0.0 to avoid fabricating resolution
    conflict_multiplier: float = 0.0
    # Missing opportunity evidence strictly contributes 0.0 (never negative)
    insufficient_evidence_multiplier: float = 0.0
    # Neutral / unspecified preference contributes 0.0
    neutral_multiplier: float = 0.0

    def __post_init__(self) -> None:
        total_w = sum(self.dimension_weights.values())
        if abs(total_w - 1.0) > 1e-6:
            raise ValueError(f"Total dimension weights must sum to 1.00, got {total_w:.4f}")

    def get_dimension_weight(self, dimension: PreferenceDimension) -> float:
        """Return the configured base weight for a dimension."""
        return self.dimension_weights.get(dimension, 0.0)

    def get_match_multiplier(self, match_type: PreferenceMatchType) -> float:
        """Return the multiplier for a given match type."""
        if match_type == PreferenceMatchType.PREFERRED_MATCH:
            return self.preferred_multiplier
        if match_type == PreferenceMatchType.PARTIAL_MATCH:
            return self.partial_multiplier
        if match_type == PreferenceMatchType.EXCLUDED_MATCH:
            return -self.exclusion_multiplier
        if match_type == PreferenceMatchType.CONFLICT:
            return self.conflict_multiplier
        if match_type == PreferenceMatchType.INSUFFICIENT_EVIDENCE:
            return self.insufficient_evidence_multiplier
        if match_type == PreferenceMatchType.NEUTRAL:
            return self.neutral_multiplier
        return 0.0


# Default global scoring configuration instance
DEFAULT_SCORING_CONFIG = PersonalizationScoringConfig()
