"""
Hybrid & Recommendation Ranking Engine for Phase 2.5C.

Takes candidate results discovered by upstream retrieval and matching services
(e.g. VectorRepository, LexicalRepository, SimilarResearchService, ResearchOpportunityMatchingService)
and produces a consistently scored, deterministically ordered list of RankedCandidate results.

Architecture
------------
Input Candidates -> Academic Feature Extraction -> Weight Validation (>= 85% Relevance Dominance) ->
Composite Scoring -> Deterministic Tie-Breaking -> RankedCandidate list.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import logging
import math
from typing import Any, Sequence
import uuid

from app.core.config import settings
from app.ranking.features import AcademicFeatures, academic_feature_extractor
from app.ranking.signals import (
    RankingSignals,
    calculate_freshness,
    calculate_opportunity_quality,
    calculate_urgency,
    normalize_lexical_score,
    validate_signal,
)
from app.repositories.vector_repository import (
    DEFAULT_CANDIDATE_LIMIT,
    MAX_CANDIDATE_LIMIT,
    sanitize_candidate_limit,
)

logger = logging.getLogger(__name__)

# Minimum relevance mass invariant (85% dominance)
MIN_RELEVANCE_DOMINANCE_THRESHOLD: float = 0.85


# ── Ranking Mode Enumeration ──────────────────────────────────────────────────


class RankingMode(str, Enum):
    """Supported hybrid ranking modes with domain-tailored default weights."""

    RESEARCH_SIMILARITY = "research_similarity"
    RESEARCH_OPPORTUNITY = "research_opportunity"
    GENERAL = "general"


# ── Configurable Ranker Weights ───────────────────────────────────────────────


@dataclass(frozen=True)
class RankerWeights:
    """
    Configurable signal weights for hybrid and recommendation candidate scoring.

    Attributes
    ----------
    Relevance Signals (must satisfy sum >= 0.85 of total):
        semantic_weight:
            Weight for semantic embedding cosine similarity.
        lexical_weight:
            Weight for full-text search relevance.
        topic_weight:
            Weight for canonical topic overlap and taxonomy DAG proximity.

    Secondary Contextual Signals (must satisfy sum <= 0.15 of total):
        type_weight:
            Weight for publication / opportunity category compatibility.
        freshness_weight:
            Weight for publication date recency decay.
        urgency_weight:
            Weight for submission deadline proximity.
        quality_weight:
            Weight for opportunity quality signals (indexing, reliability, predatory penalty).

    Secondary Academic Signals (Phase 2.5B, must satisfy sum <= 0.15 of total):
        citation_weight:
            Weight for work citation impact (log-scaled).
        author_prominence_weight:
            Weight for lead/senior author citation prominence.
        author_position_weight:
            Weight for author contribution position / corresponding role.
        institution_weight:
            Weight for affiliated institution citation prestige.
        venue_weight:
            Weight for publication venue citation prestige and DOAJ status.
        open_access_weight:
            Weight for open-access accessibility tier.
    """

    # Relevance signals
    semantic_weight: float = 0.0
    lexical_weight: float = 0.0
    topic_weight: float = 0.0

    # Contextual secondary signals
    type_weight: float = 0.0
    freshness_weight: float = 0.0
    urgency_weight: float = 0.0
    quality_weight: float = 0.0

    # Phase 2.5 Academic secondary signals
    citation_weight: float = 0.0
    author_prominence_weight: float = 0.0
    author_position_weight: float = 0.0
    institution_weight: float = 0.0
    venue_weight: float = 0.0
    open_access_weight: float = 0.0

    @property
    def relevance_weights_sum(self) -> float:
        """Sum of core relevance weights (semantic, lexical, topic)."""
        return self.semantic_weight + self.lexical_weight + self.topic_weight

    @property
    def secondary_weights_sum(self) -> float:
        """Sum of secondary contextual and academic weights."""
        return (
            self.type_weight
            + self.freshness_weight
            + self.urgency_weight
            + self.quality_weight
            + self.citation_weight
            + self.author_prominence_weight
            + self.author_position_weight
            + self.institution_weight
            + self.venue_weight
            + self.open_access_weight
        )

    @property
    def total_weight(self) -> float:
        """Sum of all configured signal weights."""
        return self.relevance_weights_sum + self.secondary_weights_sum

    @property
    def relevance_fraction(self) -> float:
        """Proportion of weight allocated to core relevance signals."""
        tot = self.total_weight
        return self.relevance_weights_sum / tot if tot > 0.0 else 1.0

    @property
    def secondary_fraction(self) -> float:
        """Proportion of weight allocated to secondary signals."""
        tot = self.total_weight
        return self.secondary_weights_sum / tot if tot > 0.0 else 0.0

    def is_relevance_dominant(
        self, min_relevance: float = MIN_RELEVANCE_DOMINANCE_THRESHOLD
    ) -> bool:
        """Check whether relevance weight meets or exceeds the required threshold."""
        return self.relevance_fraction >= min_relevance - 1e-6

    def validate(
        self,
        enforce_relevance_dominance: bool = False,
        min_relevance: float = MIN_RELEVANCE_DOMINANCE_THRESHOLD,
    ) -> None:
        """
        Validate that all weights are non-negative, finite numbers.

        Parameters
        ----------
        enforce_relevance_dominance:
            If True, strictly asserts that relevance signals account for at least min_relevance (default 85%).
        min_relevance:
            Minimum relevance fraction required when enforcement is active.

        Raises
        ------
        ValueError:
            If any weight is non-numeric, negative, NaN, or infinite, or if dominance is violated.
        """
        fields = [
            ("semantic_weight", self.semantic_weight),
            ("lexical_weight", self.lexical_weight),
            ("topic_weight", self.topic_weight),
            ("type_weight", self.type_weight),
            ("freshness_weight", self.freshness_weight),
            ("urgency_weight", self.urgency_weight),
            ("quality_weight", self.quality_weight),
            ("citation_weight", self.citation_weight),
            ("author_prominence_weight", self.author_prominence_weight),
            ("author_position_weight", self.author_position_weight),
            ("institution_weight", self.institution_weight),
            ("venue_weight", self.venue_weight),
            ("open_access_weight", self.open_access_weight),
        ]
        for name, val in fields:
            if isinstance(val, bool) or not isinstance(val, (int, float)):
                raise ValueError(
                    f"Weight '{name}' must be numeric, got {type(val).__name__}."
                )
            f_val = float(val)
            if math.isnan(f_val):
                raise ValueError(f"Weight '{name}' cannot be NaN.")
            if math.isinf(f_val):
                raise ValueError(f"Weight '{name}' cannot be infinite.")
            if f_val < 0.0:
                raise ValueError(f"Weight '{name}' cannot be negative, got {f_val}.")

        if enforce_relevance_dominance and self.total_weight > 0.0:
            self.validate_relevance_dominance(min_relevance=min_relevance)

    def validate_relevance_dominance(
        self, min_relevance: float = MIN_RELEVANCE_DOMINANCE_THRESHOLD
    ) -> None:
        """
        Enforce that relevance weights comprise at least min_relevance (default 85%) of total weight mass.
        """
        self.validate(enforce_relevance_dominance=False)
        tot = self.total_weight
        if tot <= 0.0:
            return
        rel_frac = self.relevance_weights_sum / tot
        sec_frac = self.secondary_weights_sum / tot
        if rel_frac < min_relevance - 1e-6:
            raise ValueError(
                f"Relevance dominance invariant violated: relevance weight fraction ({rel_frac:.4f}) "
                f"must be >= {min_relevance:.2f}, secondary weight fraction ({sec_frac:.4f}) must be <= {1.0 - min_relevance:.2f}."
            )

    def normalized(self) -> RankerWeights:
        """
        Return a normalized RankerWeights instance where active weights sum to 1.0.

        If total weight sum is 0.0, returns an unchanged instance.
        """
        self.validate(enforce_relevance_dominance=False)
        total = self.total_weight
        if total <= 0.0:
            return self
        return RankerWeights(
            semantic_weight=round(self.semantic_weight / total, 6),
            lexical_weight=round(self.lexical_weight / total, 6),
            topic_weight=round(self.topic_weight / total, 6),
            type_weight=round(self.type_weight / total, 6),
            freshness_weight=round(self.freshness_weight / total, 6),
            urgency_weight=round(self.urgency_weight / total, 6),
            quality_weight=round(self.quality_weight / total, 6),
            citation_weight=round(self.citation_weight / total, 6),
            author_prominence_weight=round(self.author_prominence_weight / total, 6),
            author_position_weight=round(self.author_position_weight / total, 6),
            institution_weight=round(self.institution_weight / total, 6),
            venue_weight=round(self.venue_weight / total, 6),
            open_access_weight=round(self.open_access_weight / total, 6),
        )

    def with_relevance_dominance(
        self, min_relevance: float = MIN_RELEVANCE_DOMINANCE_THRESHOLD
    ) -> RankerWeights:
        """
        Project weights to guarantee that relevance signals account for at least min_relevance of total weight mass.
        """
        self.validate(enforce_relevance_dominance=False)
        rel_sum = self.relevance_weights_sum
        sec_sum = self.secondary_weights_sum
        tot = rel_sum + sec_sum
        if tot <= 0.0:
            return self

        if rel_sum / tot >= min_relevance - 1e-6:
            return self.normalized()

        target_sec_mass = 1.0 - min_relevance
        target_rel_mass = min_relevance

        rel_factor = target_rel_mass / rel_sum if rel_sum > 0 else 1.0
        sec_factor = target_sec_mass / sec_sum if sec_sum > 0 else 0.0

        return RankerWeights(
            semantic_weight=round(self.semantic_weight * rel_factor, 6),
            lexical_weight=round(self.lexical_weight * rel_factor, 6),
            topic_weight=round(self.topic_weight * rel_factor, 6),
            type_weight=round(self.type_weight * sec_factor, 6),
            freshness_weight=round(self.freshness_weight * sec_factor, 6),
            urgency_weight=round(self.urgency_weight * sec_factor, 6),
            quality_weight=round(self.quality_weight * sec_factor, 6),
            citation_weight=round(self.citation_weight * sec_factor, 6),
            author_prominence_weight=round(self.author_prominence_weight * sec_factor, 6),
            author_position_weight=round(self.author_position_weight * sec_factor, 6),
            institution_weight=round(self.institution_weight * sec_factor, 6),
            venue_weight=round(self.venue_weight * sec_factor, 6),
            open_access_weight=round(self.open_access_weight * sec_factor, 6),
        ).normalized()


# ── Ranked Candidate Result Model ─────────────────────────────────────────────


@dataclass(frozen=True)
class RankedCandidate:
    """
    Structured, fully explainable result container for a hybrid-ranked candidate entity.

    Attributes
    ----------
    entity_id:
        UUID of the ranked entity (research work or opportunity).
    entity_type:
        Type of entity ('research_work', 'opportunity', etc.).
    rank:
        1-based rank position in the final sorted results list.
    final_score:
        Normalized composite hybrid ranking score in range [0.0, 1.0].
    semantic_score:
        Semantic similarity component in range [0.0, 1.0].
    lexical_score:
        Lexical full-text relevance component in range [0.0, 1.0].
    topic_score:
        Canonical topic overlap component in range [0.0, 1.0].
    type_score:
        Publication/opportunity type compatibility component in range [0.0, 1.0].
    freshness_score:
        Recency freshness decay component in range [0.0, 1.0].
    urgency_score:
        Deadline urgency component in range [0.0, 1.0].
    quality_score:
        Opportunity quality component in range [0.0, 1.0].
    citation_score:
        Work citation impact component in range [0.0, 1.0].
    author_prominence_score:
        Author prominence component in range [0.0, 1.0].
    author_position_score:
        Author position leadership component in range [0.0, 1.0].
    institution_score:
        Institution prestige component in range [0.0, 1.0].
    venue_score:
        Venue prestige and quality component in range [0.0, 1.0].
    open_access_score:
        Open access accessibility component in range [0.0, 1.0].
    retrieval_sources:
        Retrieval channels that discovered this candidate (e.g. ['semantic', 'lexical']).
    shared_topic_ids:
        List of canonical topic UUIDs shared with the source entity.
    shared_topic_names:
        List of canonical topic display names shared with the source entity.
    candidate:
        Optional attached underlying ORM model or candidate envelope.
    reranker_adjustment:
        Optional score adjustment from cross-encoder neural reranker.
    raw_reranker_score:
        Raw logit / score produced by the cross-encoder.
    academic_features:
        Optional extracted AcademicFeatures container.
    """

    entity_id: uuid.UUID
    entity_type: str
    rank: int
    final_score: float
    semantic_score: float
    lexical_score: float
    topic_score: float
    type_score: float
    freshness_score: float
    urgency_score: float
    quality_score: float = 0.0

    # Phase 2.5 Academic Scores
    citation_score: float = 0.0
    author_prominence_score: float = 0.0
    author_position_score: float = 0.50
    institution_score: float = 0.0
    venue_score: float = 0.0
    open_access_score: float = 0.35

    retrieval_sources: list[str] = field(default_factory=list)
    shared_topic_ids: list[uuid.UUID] = field(default_factory=list)
    shared_topic_names: list[str] = field(default_factory=list)
    candidate: Any | None = None
    academic_features: AcademicFeatures | None = None
    reranker_adjustment: float | None = None
    raw_reranker_score: float | None = None
    # Phase 2.5E Diversity & Novelty Mechanics
    diversity_adjustment: float | None = None
    novelty_score: float | None = None
    redundancy_score: float | None = None
    redundancy_reasons: list[str] = field(default_factory=list)
    novelty_reasons: list[str] = field(default_factory=list)




# ── Hybrid Ranker Engine ──────────────────────────────────────────────────────


class HybridRanker:
    """
    Generic, production-grade Hybrid and Recommendation Ranking Engine.

    Normalizes candidate features across multiple retrieval channels, integrates
    Phase 2.5 canonical academic features, validates configuration weights (enforcing
    >= 85% relevance dominance), executes weighted composite scoring, and guarantees
    deterministic multi-key tie-breaking.
    """

    def __init__(
        self,
        default_limit: int = getattr(
            settings, "hybrid_ranking_default_limit", DEFAULT_CANDIDATE_LIMIT
        ),
        max_limit: int = getattr(
            settings, "hybrid_ranking_max_limit", MAX_CANDIDATE_LIMIT
        ),
        research_similarity_weights: RankerWeights | None = None,
        research_opportunity_weights: RankerWeights | None = None,
        general_weights: RankerWeights | None = None,
    ) -> None:
        self.default_limit = default_limit
        self.max_limit = max_limit

        # Research Similarity Mode Preset (Total = 1.0, Relevance = 0.90 >= 0.85, Freshness = 0.10)
        self.research_similarity_weights = research_similarity_weights or RankerWeights(
            semantic_weight=getattr(
                settings, "hybrid_ranking_research_similarity_semantic_weight", 0.50
            ),
            lexical_weight=getattr(
                settings, "hybrid_ranking_research_similarity_lexical_weight", 0.20
            ),
            topic_weight=getattr(
                settings, "hybrid_ranking_research_similarity_topic_weight", 0.20
            ),
            freshness_weight=getattr(
                settings, "hybrid_ranking_research_similarity_freshness_weight", 0.10
            ),
            type_weight=0.0,
            urgency_weight=0.0,
            quality_weight=0.0,
            citation_weight=0.0,
            author_prominence_weight=0.0,
            author_position_weight=0.0,
            institution_weight=0.0,
            venue_weight=0.0,
            open_access_weight=0.0,
        )

        # Research Opportunity Mode Preset (Total = 1.0, Relevance = 0.75, Secondary = 0.25)
        self.research_opportunity_weights = (
            research_opportunity_weights
            or RankerWeights(
                semantic_weight=getattr(
                    settings, "hybrid_ranking_opportunity_semantic_weight", 0.40
                ),
                lexical_weight=getattr(
                    settings, "hybrid_ranking_opportunity_lexical_weight", 0.15
                ),
                topic_weight=getattr(
                    settings, "hybrid_ranking_opportunity_topic_weight", 0.20
                ),
                type_weight=getattr(
                    settings, "hybrid_ranking_opportunity_type_weight", 0.10
                ),
                urgency_weight=getattr(
                    settings, "hybrid_ranking_opportunity_urgency_weight", 0.05
                ),
                quality_weight=getattr(
                    settings, "hybrid_ranking_opportunity_quality_weight", 0.10
                ),
                freshness_weight=0.0,
                citation_weight=0.0,
                author_prominence_weight=0.0,
                author_position_weight=0.0,
                institution_weight=0.0,
                venue_weight=0.0,
                open_access_weight=0.0,
            )
        )

        # General Research Search Preset (Total = 1.0, Relevance = 1.00 >= 0.85)
        self.general_weights = general_weights or RankerWeights(
            semantic_weight=0.50,
            lexical_weight=0.25,
            topic_weight=0.25,
            type_weight=0.0,
            freshness_weight=0.0,
            urgency_weight=0.0,
            quality_weight=0.0,
            citation_weight=0.0,
            author_prominence_weight=0.0,
            author_position_weight=0.0,
            institution_weight=0.0,
            venue_weight=0.0,
            open_access_weight=0.0,
        )

    def resolve_weights(
        self,
        mode: RankingMode | str,
        custom_weights: RankerWeights | None = None,
    ) -> RankerWeights:
        """Resolve, validate, and normalize the active weights for the given mode."""
        if custom_weights is not None:
            return custom_weights.normalized()

        str_mode = mode.value if isinstance(mode, RankingMode) else str(mode).lower()

        if str_mode == RankingMode.RESEARCH_SIMILARITY.value:
            return self.research_similarity_weights.normalized()
        elif str_mode == RankingMode.RESEARCH_OPPORTUNITY.value:
            return self.research_opportunity_weights.normalized()
        else:
            return self.general_weights.normalized()

    def extract_signals(
        self,
        candidate: Any,
        mode: str,
        reference_time: datetime | None = None,
        half_life_years: float | None = None,
        urgency_window_days: float | None = None,
        precomputed_academic_features: AcademicFeatures | None = None,
    ) -> tuple[
        uuid.UUID,
        str,
        RankingSignals,
        list[uuid.UUID],
        list[str],
        Any,
    ]:
        """
        Extract normalized ranking signals and academic features from any candidate container or model.
        """
        entity_id: uuid.UUID
        entity_type: str = "research_work"
        sem_sim: float = 0.0
        lex_sim: float = 0.0
        top_sim: float = 0.0
        typ_comp: float = 0.0
        freshness: float = 0.0
        urgency: float = 0.0
        opp_quality: float = 0.0
        retrieval_sources: list[str] = []
        shared_topic_ids: list[uuid.UUID] = []
        shared_topic_names: list[str] = []
        attached_entity: Any | None = None

        # Academic features defaults
        cit_impact: float = 0.0
        auth_prominence: float = 0.0
        auth_pos: float = 0.50
        inst_prestige: float = 0.0
        venue_prestige: float = 0.0
        oa_tier: float = 0.35

        # 1. Inspect Candidate Type
        cand_work_id = getattr(candidate, "candidate_work_id", None)
        opp_id = getattr(candidate, "opportunity_id", None)
        raw_entity_id = getattr(candidate, "entity_id", None)

        if cand_work_id is not None:
            # SimilarResearchResult
            entity_id = cand_work_id
            entity_type = "research_work"
            sem_sim = validate_signal(getattr(candidate, "semantic_similarity", 0.0), "semantic_similarity")
            lex_sim = validate_signal(getattr(candidate, "lexical_similarity", 0.0), "lexical_similarity")
            top_sim = validate_signal(getattr(candidate, "topic_similarity", 0.0), "topic_similarity")
            retrieval_sources = list(getattr(candidate, "retrieval_sources", []))
            shared_topic_ids = list(getattr(candidate, "shared_topic_ids", []))
            shared_topic_names = list(getattr(candidate, "shared_topic_names", []))
            attached_entity = getattr(candidate, "candidate_work", None)

            if attached_entity is not None:
                pub_year = getattr(attached_entity, "publication_year", None)
                pub_date = getattr(attached_entity, "publication_date", None)
                freshness = calculate_freshness(
                    publication_year=pub_year,
                    publication_date=pub_date,
                    half_life_years=half_life_years,
                )

        elif opp_id is not None:
            # ResearchOpportunityMatch
            entity_id = opp_id
            entity_type = "opportunity"
            sem_sim = validate_signal(getattr(candidate, "semantic_similarity", 0.0), "semantic_similarity")
            lex_sim = validate_signal(getattr(candidate, "lexical_similarity", 0.0), "lexical_similarity")
            top_sim = validate_signal(getattr(candidate, "topic_similarity", 0.0), "topic_similarity")
            typ_comp = validate_signal(getattr(candidate, "type_compatibility", 0.0), "type_compatibility")
            retrieval_sources = list(getattr(candidate, "retrieval_sources", []))
            shared_topic_ids = list(getattr(candidate, "shared_topic_ids", []))
            shared_topic_names = list(getattr(candidate, "shared_topic_names", []))
            attached_entity = getattr(candidate, "opportunity", None)

            if attached_entity is not None:
                deadline = getattr(attached_entity, "submission_deadline", None)
                urgency = calculate_urgency(
                    submission_deadline=deadline,
                    reference_time=reference_time,
                    window_days=urgency_window_days,
                )

            if hasattr(candidate, "quality_score") and getattr(candidate, "quality_score") is not None and getattr(candidate, "quality_score") > 0.0:
                opp_quality = validate_signal(getattr(candidate, "quality_score"), "quality_score")
            else:
                opp_quality = calculate_opportunity_quality(
                    attached_entity,
                    is_predatory_flag=getattr(candidate, "is_predatory_flag", getattr(candidate, "is_predatory", None)),
                    risk_score=getattr(candidate, "risk_score", None),
                    indexing=getattr(candidate, "indexing", None),
                    status=getattr(candidate, "status", None),
                )

        elif raw_entity_id is not None:
            # HybridSearchResult / VectorSearchResult / LexicalSearchResult / RankedCandidate / Generic
            entity_id = raw_entity_id
            entity_type = getattr(candidate, "entity_type", "research_work")
            attached_entity = getattr(candidate, "entity", getattr(candidate, "candidate", None))

            if hasattr(candidate, "semantic_score"):
                sem_sim = validate_signal(getattr(candidate, "semantic_score"), "semantic_score")
            elif hasattr(candidate, "vector_similarity"):
                sem_sim = validate_signal(getattr(candidate, "vector_similarity"), "vector_similarity")
            elif hasattr(candidate, "similarity"):
                sem_sim = validate_signal(getattr(candidate, "similarity"), "similarity")

            if hasattr(candidate, "lexical_score"):
                raw_lex = getattr(candidate, "lexical_score")
                if hasattr(candidate, "rank") and not hasattr(candidate, "final_score"):
                    lex_sim = normalize_lexical_score(raw_lex)
                else:
                    lex_sim = validate_signal(raw_lex, "lexical_score")

            if hasattr(candidate, "topic_score"):
                top_sim = validate_signal(getattr(candidate, "topic_score"), "topic_score")
            elif hasattr(candidate, "topic_similarity"):
                top_sim = validate_signal(getattr(candidate, "topic_similarity"), "topic_similarity")

            if hasattr(candidate, "type_score"):
                typ_comp = validate_signal(getattr(candidate, "type_score"), "type_score")
            elif hasattr(candidate, "type_compatibility"):
                typ_comp = validate_signal(getattr(candidate, "type_compatibility"), "type_compatibility")

            if hasattr(candidate, "freshness_score"):
                freshness = validate_signal(getattr(candidate, "freshness_score"), "freshness_score")
            elif hasattr(candidate, "freshness"):
                freshness = validate_signal(getattr(candidate, "freshness"), "freshness")
            elif attached_entity is not None and hasattr(attached_entity, "publication_year"):
                freshness = calculate_freshness(
                    publication_year=getattr(attached_entity, "publication_year", None),
                    publication_date=getattr(attached_entity, "publication_date", None),
                    half_life_years=half_life_years,
                )

            if hasattr(candidate, "urgency_score"):
                urgency = validate_signal(getattr(candidate, "urgency_score"), "urgency_score")
            elif hasattr(candidate, "urgency"):
                urgency = validate_signal(getattr(candidate, "urgency"), "urgency")
            elif attached_entity is not None and hasattr(attached_entity, "submission_deadline"):
                urgency = calculate_urgency(
                    submission_deadline=getattr(attached_entity, "submission_deadline", None),
                    reference_time=reference_time,
                    window_days=urgency_window_days,
                )

            if hasattr(candidate, "quality_score"):
                opp_quality = validate_signal(getattr(candidate, "quality_score"), "quality_score")
            elif hasattr(candidate, "opportunity_quality"):
                opp_quality = validate_signal(getattr(candidate, "opportunity_quality"), "opportunity_quality")
            elif entity_type == "opportunity" or (attached_entity is not None and (hasattr(attached_entity, "indexing") or hasattr(attached_entity, "is_predatory_flag"))):
                opp_quality = calculate_opportunity_quality(attached_entity)

            retrieval_sources = list(getattr(candidate, "retrieval_sources", []))
            shared_topic_ids = list(getattr(candidate, "shared_topic_ids", []))
            shared_topic_names = list(getattr(candidate, "shared_topic_names", []))

        elif isinstance(candidate, dict):
            # Dictionary candidate
            entity_id = uuid.UUID(str(candidate.get("entity_id", candidate.get("id"))))
            entity_type = str(candidate.get("entity_type", "research_work"))
            sem_sim = validate_signal(candidate.get("semantic_similarity", candidate.get("semantic_score", 0.0)), "semantic")
            lex_sim = validate_signal(candidate.get("lexical_similarity", candidate.get("lexical_score", 0.0)), "lexical")
            top_sim = validate_signal(candidate.get("topic_similarity", candidate.get("topic_score", 0.0)), "topic")
            typ_comp = validate_signal(candidate.get("type_compatibility", candidate.get("type_score", 0.0)), "type")
            freshness = validate_signal(candidate.get("freshness", candidate.get("freshness_score", 0.0)), "freshness")
            urgency = validate_signal(candidate.get("urgency", candidate.get("urgency_score", 0.0)), "urgency")
            if candidate.get("opportunity_quality") is not None or candidate.get("quality_score") is not None:
                opp_quality = validate_signal(candidate.get("opportunity_quality", candidate.get("quality_score")), "quality")
            elif entity_type == "opportunity" or "indexing" in candidate or "is_predatory_flag" in candidate:
                opp_quality = calculate_opportunity_quality(candidate)
            retrieval_sources = list(candidate.get("retrieval_sources", []))
            shared_topic_ids = list(candidate.get("shared_topic_ids", []))
            shared_topic_names = list(candidate.get("shared_topic_names", []))
            attached_entity = candidate.get("entity", candidate.get("candidate", candidate))
        else:
            raise ValueError(f"Unsupported candidate object type: {type(candidate).__name__}.")

        # 2. Extract Phase 2.5 Academic Features (Defensive Fallback)
        try:
            target_obj = attached_entity if attached_entity is not None else candidate
            if precomputed_academic_features is not None:
                cit_impact = precomputed_academic_features.citation_impact
                auth_prominence = precomputed_academic_features.author_prominence
                auth_pos = precomputed_academic_features.author_position
                inst_prestige = precomputed_academic_features.institution_prestige
                venue_prestige = precomputed_academic_features.venue_prestige
                oa_tier = precomputed_academic_features.open_access_tier
            elif hasattr(target_obj, "academic_features") and getattr(target_obj, "academic_features") is not None:
                af = getattr(target_obj, "academic_features")
                if isinstance(af, AcademicFeatures):
                    cit_impact = af.citation_impact
                    auth_prominence = af.author_prominence
                    auth_pos = af.author_position
                    inst_prestige = af.institution_prestige
                    venue_prestige = af.venue_prestige
                    oa_tier = af.open_access_tier
                elif isinstance(af, dict):
                    cit_impact = validate_signal(af.get("citation_impact", 0.0), "citation_impact")
                    auth_prominence = validate_signal(af.get("author_prominence", 0.0), "author_prominence")
                    auth_pos = validate_signal(af.get("author_position", 0.50), "author_position", default=0.50)
                    inst_prestige = validate_signal(af.get("institution_prestige", 0.0), "institution_prestige")
                    venue_prestige = validate_signal(af.get("venue_prestige", 0.0), "venue_prestige")
                    oa_tier = validate_signal(af.get("open_access_tier", 0.35), "open_access_tier", default=0.35)
            elif isinstance(target_obj, dict) and "academic_features" in target_obj:
                af_val = target_obj["academic_features"]
                if isinstance(af_val, AcademicFeatures):
                    cit_impact = af_val.citation_impact
                    auth_prominence = af_val.author_prominence
                    auth_pos = af_val.author_position
                    inst_prestige = af_val.institution_prestige
                    venue_prestige = af_val.venue_prestige
                    oa_tier = af_val.open_access_tier
                elif isinstance(af_val, dict):
                    cit_impact = validate_signal(af_val.get("citation_impact", 0.0), "citation_impact")
                    auth_prominence = validate_signal(af_val.get("author_prominence", 0.0), "author_prominence")
                    auth_pos = validate_signal(af_val.get("author_position", 0.50), "author_position", default=0.50)
                    inst_prestige = validate_signal(af_val.get("institution_prestige", 0.0), "institution_prestige")
                    venue_prestige = validate_signal(af_val.get("venue_prestige", 0.0), "venue_prestige")
                    oa_tier = validate_signal(af_val.get("open_access_tier", 0.35), "open_access_tier", default=0.35)
            elif isinstance(target_obj, dict) and any(
                k in target_obj
                for k in (
                    "citation_impact",
                    "author_prominence",
                    "author_position",
                    "institution_prestige",
                    "venue_prestige",
                    "open_access_tier",
                )
            ):
                if "citation_impact" in target_obj:
                    cit_impact = validate_signal(target_obj["citation_impact"], "citation_impact")
                if "author_prominence" in target_obj:
                    auth_prominence = validate_signal(target_obj["author_prominence"], "author_prominence")
                if "author_position" in target_obj:
                    auth_pos = validate_signal(target_obj["author_position"], "author_position", default=0.50)
                if "institution_prestige" in target_obj:
                    inst_prestige = validate_signal(target_obj["institution_prestige"], "institution_prestige")
                if "venue_prestige" in target_obj:
                    venue_prestige = validate_signal(target_obj["venue_prestige"], "venue_prestige")
                if "open_access_tier" in target_obj:
                    oa_tier = validate_signal(target_obj["open_access_tier"], "open_access_tier", default=0.35)
            else:
                extracted_af = academic_feature_extractor.extract_from_work(target_obj)
                cit_impact = extracted_af.citation_impact
                auth_prominence = extracted_af.author_prominence
                auth_pos = extracted_af.author_position
                inst_prestige = extracted_af.institution_prestige
                venue_prestige = extracted_af.venue_prestige
                oa_tier = extracted_af.open_access_tier
        except Exception as exc:
            logger.debug("Academic feature extraction fallback for candidate %s: %s", entity_id, exc)
            cit_impact = 0.0
            auth_prominence = 0.0
            auth_pos = 0.50
            inst_prestige = 0.0
            venue_prestige = 0.0
            oa_tier = 0.35

        # Check direct score overrides on candidate if present
        if hasattr(candidate, "citation_score") and getattr(candidate, "citation_score") is not None:
            cit_impact = validate_signal(getattr(candidate, "citation_score"), "citation_score")
        if hasattr(candidate, "author_prominence_score") and getattr(candidate, "author_prominence_score") is not None:
            auth_prominence = validate_signal(getattr(candidate, "author_prominence_score"), "author_prominence_score")
        if hasattr(candidate, "author_position_score") and getattr(candidate, "author_position_score") is not None:
            auth_pos = validate_signal(getattr(candidate, "author_position_score"), "author_position_score")
        if hasattr(candidate, "institution_score") and getattr(candidate, "institution_score") is not None:
            inst_prestige = validate_signal(getattr(candidate, "institution_score"), "institution_score")
        if hasattr(candidate, "venue_score") and getattr(candidate, "venue_score") is not None:
            venue_prestige = validate_signal(getattr(candidate, "venue_score"), "venue_score")
        if hasattr(candidate, "open_access_score") and getattr(candidate, "open_access_score") is not None:
            oa_tier = validate_signal(getattr(candidate, "open_access_score"), "open_access_score")

        signals = RankingSignals(
            semantic_similarity=sem_sim,
            lexical_similarity=lex_sim,
            topic_similarity=top_sim,
            type_compatibility=typ_comp,
            freshness=freshness,
            urgency=urgency,
            opportunity_quality=opp_quality,
            citation_impact=cit_impact,
            author_prominence=auth_prominence,
            author_position=auth_pos,
            institution_prestige=inst_prestige,
            venue_prestige=venue_prestige,
            open_access_tier=oa_tier,
            retrieval_sources=sorted(retrieval_sources),
        )

        return (
            entity_id,
            entity_type,
            signals,
            shared_topic_ids,
            shared_topic_names,
            attached_entity,
        )

    def rank(
        self,
        candidates: Sequence[Any],
        *,
        mode: RankingMode | str = RankingMode.GENERAL,
        weights: RankerWeights | None = None,
        limit: int | None = None,
        reference_time: datetime | None = None,
        half_life_years: float | None = None,
        urgency_window_days: float | None = None,
        session: Session | None = None,
    ) -> list[RankedCandidate]:
        """
        Rank a sequence of candidate results using normalized multi-signal weighting.

        Parameters
        ----------
        candidates:
            Sequence of candidate objects from retrieval or matching services.
        mode:
            Ranking mode ('research_similarity', 'research_opportunity', or 'general').
        weights:
            Optional custom weights. If omitted, uses configured defaults for mode.
        limit:
            Maximum number of ranked candidates to return (default 20, max 100).
        reference_time:
            Anchor timestamp for deadline urgency calculation.
        half_life_years:
            Half-life decay in years for publication freshness.
        urgency_window_days:
            Urgency window in days for opportunity submission deadlines.
        session:
            Optional active SQLAlchemy Session for batch eager relational loading.

        Returns
        -------
        list[RankedCandidate]
            Deterministically ordered ranked candidates.
        """
        if not candidates:
            return []

        safe_limit = sanitize_candidate_limit(
            limit, self.default_limit, self.max_limit
        )
        active_weights = self.resolve_weights(mode, weights)
        active_weights.validate(enforce_relevance_dominance=False)

        # Batch extract academic features upfront to eliminate N+1 database queries
        batch_academic_features = academic_feature_extractor.extract_batch(
            candidates, session=session
        )

        scored_candidates: list[RankedCandidate] = []

        for idx, cand in enumerate(candidates):
            precomputed_af = (
                batch_academic_features[idx]
                if idx < len(batch_academic_features)
                else None
            )
            (
                entity_id,
                entity_type,
                signals,
                shared_ids,
                shared_names,
                attached_entity,
            ) = self.extract_signals(
                candidate=cand,
                mode=str(mode),
                reference_time=reference_time,
                half_life_years=half_life_years,
                urgency_window_days=urgency_window_days,
                precomputed_academic_features=precomputed_af,
            )

            # Compute weighted composite final score across relevance, contextual, and academic features
            raw_final = (
                active_weights.semantic_weight * signals.semantic_similarity
                + active_weights.lexical_weight * signals.lexical_similarity
                + active_weights.topic_weight * signals.topic_similarity
                + active_weights.type_weight * signals.type_compatibility
                + active_weights.freshness_weight * signals.freshness
                + active_weights.urgency_weight * signals.urgency
                + active_weights.quality_weight * signals.opportunity_quality
                + active_weights.citation_weight * signals.citation_impact
                + active_weights.author_prominence_weight * signals.author_prominence
                + active_weights.author_position_weight * signals.author_position
                + active_weights.institution_weight * signals.institution_prestige
                + active_weights.venue_weight * signals.venue_prestige
                + active_weights.open_access_weight * signals.open_access_tier
            )

            final_score = round(min(1.0, max(0.0, raw_final)), 6)

            scored_candidates.append(
                RankedCandidate(
                    entity_id=entity_id,
                    entity_type=entity_type,
                    rank=0,  # assigned after deterministic sort
                    final_score=final_score,
                    semantic_score=signals.semantic_similarity,
                    lexical_score=signals.lexical_similarity,
                    topic_score=signals.topic_similarity,
                    type_score=signals.type_compatibility,
                    freshness_score=signals.freshness,
                    urgency_score=signals.urgency,
                    quality_score=signals.opportunity_quality,
                    citation_score=signals.citation_impact,
                    author_prominence_score=signals.author_prominence,
                    author_position_score=signals.author_position,
                    institution_score=signals.institution_prestige,
                    venue_score=signals.venue_prestige,
                    open_access_score=signals.open_access_tier,
                    retrieval_sources=signals.retrieval_sources,
                    shared_topic_ids=shared_ids,
                    shared_topic_names=shared_names,
                    candidate=attached_entity,
                    academic_features=precomputed_af,
                )
            )

        # Deterministic Ranking & Multi-Key Tie-breaking
        # 1. final_score DESC
        # 2. semantic_score DESC
        # 3. topic_score DESC
        # 4. lexical_score DESC
        # 5. citation_score DESC
        # 6. venue_score DESC
        # 7. quality_score DESC
        # 8. author_prominence_score DESC
        # 9. institution_score DESC
        # 10. type_score DESC
        # 11. freshness_score DESC
        # 12. urgency_score DESC
        # 13. open_access_score DESC
        # 14. author_position_score DESC
        # Tie-breaker: entity_id ASC (lexicographical string UUID)
        scored_candidates.sort(
            key=lambda c: (
                -c.final_score,
                -c.semantic_score,
                -c.topic_score,
                -c.lexical_score,
                -c.citation_score,
                -c.venue_score,
                -c.quality_score,
                -c.author_prominence_score,
                -c.institution_score,
                -c.type_score,
                -c.freshness_score,
                -c.urgency_score,
                -c.open_access_score,
                -c.author_position_score,
                str(c.entity_id),
            )
        )

        limited = scored_candidates[:safe_limit]

        final_ranked: list[RankedCandidate] = []
        for idx, item in enumerate(limited, start=1):
            final_ranked.append(
                RankedCandidate(
                    entity_id=item.entity_id,
                    entity_type=item.entity_type,
                    rank=idx,
                    final_score=item.final_score,
                    semantic_score=item.semantic_score,
                    lexical_score=item.lexical_score,
                    topic_score=item.topic_score,
                    type_score=item.type_score,
                    freshness_score=item.freshness_score,
                    urgency_score=item.urgency_score,
                    quality_score=item.quality_score,
                    citation_score=item.citation_score,
                    author_prominence_score=item.author_prominence_score,
                    author_position_score=item.author_position_score,
                    institution_score=item.institution_score,
                    venue_score=item.venue_score,
                    open_access_score=item.open_access_score,
                    retrieval_sources=item.retrieval_sources,
                    shared_topic_ids=item.shared_topic_ids,
                    shared_topic_names=item.shared_topic_names,
                    candidate=item.candidate,
                    academic_features=item.academic_features,
                )
            )

        return final_ranked


# Module-level default instance
hybrid_ranker = HybridRanker()
