"""
Phase 2.4E — Hybrid Ranking Engine Package.

Exports:
  - HybridRanker: Generic multi-signal ranker.
  - RankedCandidate: Explainable ranking result model.
  - RankingMode: Preconfigured ranking modes.
  - RankerWeights: Validated, normalized signal weights.
  - RankingSignals: Normalized candidate feature container.
  - calculate_freshness: Publication age decay calculation.
  - calculate_urgency: Submission deadline urgency calculation.
  - normalize_lexical_score: Full-text search score normalization.
  - validate_signal: Finite number validation and clamping.
  - hybrid_ranker: Singleton default ranker instance.
"""
from app.ranking.features import (
    AcademicFeatureExtractor,
    AcademicFeatures,
    academic_feature_extractor,
    calculate_author_position_score,
    calculate_author_prominence,
    calculate_citation_impact,
    calculate_institution_prestige,
    calculate_open_access_tier,
    calculate_venue_prestige,
)
from app.ranking.hybrid_ranker import (
    HybridRanker,
    RankedCandidate,
    RankerWeights,
    RankingMode,
    hybrid_ranker,
)
from app.ranking.signals import (
    RankingSignals,
    calculate_freshness,
    calculate_urgency,
    normalize_lexical_score,
    validate_signal,
)

__all__ = [
    "AcademicFeatureExtractor",
    "AcademicFeatures",
    "HybridRanker",
    "RankedCandidate",
    "RankerWeights",
    "RankingMode",
    "RankingSignals",
    "academic_feature_extractor",
    "calculate_author_position_score",
    "calculate_author_prominence",
    "calculate_citation_impact",
    "calculate_freshness",
    "calculate_institution_prestige",
    "calculate_open_access_tier",
    "calculate_urgency",
    "calculate_venue_prestige",
    "hybrid_ranker",
    "normalize_lexical_score",
    "validate_signal",
]
