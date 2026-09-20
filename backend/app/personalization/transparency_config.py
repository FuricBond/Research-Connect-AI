from dataclasses import dataclass


@dataclass(frozen=True)
class PersonalizationTransparencyConfig:
    """
    Configuration parameters and thresholds for Phase 5.9 Personalization Transparency.
    """

    algorithm_version: str = "5.9.1"

    # Thresholds for net personalization impact classification:
    #   |delta| < 0.02 -> NO_PERSONALIZATION
    #   0.02 <= |delta| < 0.06 -> LOW_PERSONALIZATION
    #   0.06 <= |delta| < 0.12 -> MODERATE_PERSONALIZATION
    #   |delta| >= 0.12 -> STRONG_PERSONALIZATION
    impact_low_threshold: float = 0.02
    impact_moderate_threshold: float = 0.06
    impact_strong_threshold: float = 0.12


DEFAULT_TRANSPARENCY_CONFIG = PersonalizationTransparencyConfig()
