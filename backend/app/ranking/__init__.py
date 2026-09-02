"""
Hybrid Recommendation Ranking Package (Phase 2.5D).

Exports:
  - HybridRanker: Generic multi-signal deterministic recommendation ranker.
  - RankedCandidate: Explainable ranking result model.
  - RankingMode: Preconfigured ranking modes (GENERAL, RESEARCH_SIMILARITY, RESEARCH_OPPORTUNITY).
  - RankerWeights: Validated, normalized signal weights.
  - RankingSignals: Normalized candidate feature container.
  - AcademicFeatures: Canonical academic feature container.
  - AcademicFeatureExtractor: Deterministic feature extraction service with batch loading.
  - AcademicCoverageDiagnostics: Lightweight coverage diagnostic utility.
  - VenueResolver: Publication venue normalizer and canonicalizer.
  - normalize_issn, normalize_venue_name, get_canonical_venue_key.
  - calculate_freshness: Publication age decay calculation.
  - calculate_urgency: Submission deadline urgency calculation.
  - normalize_lexical_score: Full-text search score normalization.
  - validate_signal: Finite number validation and clamping.
  - hybrid_ranker: Singleton default ranker instance.
"""
from app.ranking.diagnostics import AcademicCoverageDiagnostics
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
from app.ranking.venue_intelligence import (
    VenueResolver,
    get_canonical_venue_key,
    normalize_issn,
    normalize_venue_name,
    venue_resolver,
)

__all__ = [
    "AcademicCoverageDiagnostics",
    "AcademicFeatureExtractor",
    "AcademicFeatures",
    "HybridRanker",
    "RankedCandidate",
    "RankerWeights",
    "RankingMode",
    "RankingSignals",
    "VenueResolver",
    "academic_feature_extractor",
    "calculate_author_position_score",
    "calculate_author_prominence",
    "calculate_citation_impact",
    "calculate_freshness",
    "calculate_institution_prestige",
    "calculate_open_access_tier",
    "calculate_urgency",
    "calculate_venue_prestige",
    "get_canonical_venue_key",
    "hybrid_ranker",
    "normalize_issn",
    "normalize_lexical_score",
    "normalize_venue_name",
    "validate_signal",
    "venue_resolver",
]
