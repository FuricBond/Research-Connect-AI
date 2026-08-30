"""
Hybrid Ranking Engine for Phase 2.4E.

Takes candidate results discovered by upstream retrieval and matching services
(e.g. VectorRepository, LexicalRepository, SimilarResearchService, ResearchOpportunityMatchingService)
and produces a consistently scored, deterministically ordered list of RankedCandidate results.

Architecture
------------
Input Candidates -> Signal Extraction -> Weight Normalization -> Composite Scoring -> Deterministic Tie-Breaking -> RankedCandidate list.
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
from app.ranking.signals import (
    RankingSignals,
    calculate_freshness,
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
    Configurable signal weights for hybrid candidate scoring.

    Attributes
    ----------
    semantic_weight:
        Weight for semantic embedding cosine similarity.
    lexical_weight:
        Weight for full-text search relevance.
    topic_weight:
        Weight for canonical topic overlap and taxonomy DAG proximity.
    type_weight:
        Weight for publication / opportunity category compatibility.
    freshness_weight:
        Weight for publication date recency decay.
    urgency_weight:
        Weight for submission deadline proximity.
    """

    semantic_weight: float = 0.0
    lexical_weight: float = 0.0
    topic_weight: float = 0.0
    type_weight: float = 0.0
    freshness_weight: float = 0.0
    urgency_weight: float = 0.0

    def validate(self) -> None:
        """
        Validate that all weights are non-negative, finite numbers.

        Raises
        ------
        ValueError:
            If any weight is non-numeric, negative, NaN, or infinite.
        """
        fields = [
            ("semantic_weight", self.semantic_weight),
            ("lexical_weight", self.lexical_weight),
            ("topic_weight", self.topic_weight),
            ("type_weight", self.type_weight),
            ("freshness_weight", self.freshness_weight),
            ("urgency_weight", self.urgency_weight),
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

    def normalized(self) -> RankerWeights:
        """
        Return a normalized RankerWeights instance where active weights sum to 1.0.

        If total weight sum is 0.0, returns an unchanged instance.
        """
        self.validate()
        total = (
            self.semantic_weight
            + self.lexical_weight
            + self.topic_weight
            + self.type_weight
            + self.freshness_weight
            + self.urgency_weight
        )
        if total <= 0.0:
            return self
        return RankerWeights(
            semantic_weight=round(self.semantic_weight / total, 6),
            lexical_weight=round(self.lexical_weight / total, 6),
            topic_weight=round(self.topic_weight / total, 6),
            type_weight=round(self.type_weight / total, 6),
            freshness_weight=round(self.freshness_weight / total, 6),
            urgency_weight=round(self.urgency_weight / total, 6),
        )


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
    retrieval_sources:
        Retrieval channels that discovered this candidate (e.g. ['semantic', 'lexical']).
    shared_topic_ids:
        List of canonical topic UUIDs shared with the source entity.
    shared_topic_names:
        List of canonical topic display names shared with the source entity.
    candidate:
        Optional attached underlying ORM model or candidate envelope.
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
    retrieval_sources: list[str] = field(default_factory=list)
    shared_topic_ids: list[uuid.UUID] = field(default_factory=list)
    shared_topic_names: list[str] = field(default_factory=list)
    candidate: Any | None = None


# ── Hybrid Ranker Engine ──────────────────────────────────────────────────────


class HybridRanker:
    """
    Generic, production-grade Hybrid Ranking Engine.

    Normalizes candidate features across multiple retrieval channels, validates
    configuration weights, executes weighted composite scoring, and guarantees
    deterministic tie-breaking.
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
        )

        self.research_opportunity_weights = (
            research_opportunity_weights
            or RankerWeights(
                semantic_weight=getattr(
                    settings, "hybrid_ranking_opportunity_semantic_weight", 0.45
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
                    settings, "hybrid_ranking_opportunity_urgency_weight", 0.10
                ),
                freshness_weight=0.0,
            )
        )

        self.general_weights = general_weights or RankerWeights(
            semantic_weight=0.50,
            lexical_weight=0.25,
            topic_weight=0.25,
            type_weight=0.0,
            freshness_weight=0.0,
            urgency_weight=0.0,
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
    ) -> tuple[
        uuid.UUID,
        str,
        RankingSignals,
        list[uuid.UUID],
        list[str],
        Any,
    ]:
        """
        Extract normalized ranking signals from any candidate container or model.

        Supports:
          - SimilarResearchResult (Phase 2.4C)
          - ResearchOpportunityMatch (Phase 2.4D)
          - HybridSearchResult (Phase 2.4B)
          - VectorSearchResult (Phase 2.4A)
          - LexicalSearchResult (Phase 2.4B)
          - RankedCandidate (Re-ranking)
          - Generic objects / dicts with entity identifiers
        """
        entity_id: uuid.UUID
        entity_type: str = "research_work"
        sem_sim: float = 0.0
        lex_sim: float = 0.0
        top_sim: float = 0.0
        typ_comp: float = 0.0
        freshness: float = 0.0
        urgency: float = 0.0
        retrieval_sources: list[str] = []
        shared_topic_ids: list[uuid.UUID] = []
        shared_topic_names: list[str] = []
        attached_entity: Any | None = None

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

            # Compute freshness if candidate entity has publication date/year
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

            # Compute urgency if opportunity has submission deadline
            if attached_entity is not None:
                deadline = getattr(attached_entity, "submission_deadline", None)
                urgency = calculate_urgency(
                    submission_deadline=deadline,
                    reference_time=reference_time,
                    window_days=urgency_window_days,
                )

        elif raw_entity_id is not None:
            # HybridSearchResult / VectorSearchResult / LexicalSearchResult / RankedCandidate / Generic
            entity_id = raw_entity_id
            entity_type = getattr(candidate, "entity_type", "research_work")
            attached_entity = getattr(candidate, "entity", getattr(candidate, "candidate", None))

            # Scores extraction
            if hasattr(candidate, "semantic_score"):
                sem_sim = validate_signal(getattr(candidate, "semantic_score"), "semantic_score")
            elif hasattr(candidate, "vector_similarity"):
                sem_sim = validate_signal(getattr(candidate, "vector_similarity"), "vector_similarity")
            elif hasattr(candidate, "similarity"):
                sem_sim = validate_signal(getattr(candidate, "similarity"), "similarity")

            if hasattr(candidate, "lexical_score"):
                raw_lex = getattr(candidate, "lexical_score")
                if hasattr(candidate, "rank") and not hasattr(candidate, "final_score"):
                    # Raw lexical search result with ts_rank_cd
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
            retrieval_sources = list(candidate.get("retrieval_sources", []))
            shared_topic_ids = list(candidate.get("shared_topic_ids", []))
            shared_topic_names = list(candidate.get("shared_topic_names", []))
            attached_entity = candidate.get("entity", candidate.get("candidate"))
        else:
            raise ValueError(f"Unsupported candidate object type: {type(candidate).__name__}.")

        signals = RankingSignals(
            semantic_similarity=sem_sim,
            lexical_similarity=lex_sim,
            topic_similarity=top_sim,
            type_compatibility=typ_comp,
            freshness=freshness,
            urgency=urgency,
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
        active_weights.validate()

        scored_candidates: list[RankedCandidate] = []

        for cand in candidates:
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
            )

            # Compute weighted composite final score
            raw_final = (
                active_weights.semantic_weight * signals.semantic_similarity
                + active_weights.lexical_weight * signals.lexical_similarity
                + active_weights.topic_weight * signals.topic_similarity
                + active_weights.type_weight * signals.type_compatibility
                + active_weights.freshness_weight * signals.freshness
                + active_weights.urgency_weight * signals.urgency
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
                    retrieval_sources=signals.retrieval_sources,
                    shared_topic_ids=shared_ids,
                    shared_topic_names=shared_names,
                    candidate=attached_entity,
                )
            )

        # Deterministic Ranking & Tie-breaking
        # Primary: final_score DESC
        # Secondary: semantic_score DESC
        # Tertiary: topic_score DESC
        # Quaternary: lexical_score DESC
        # Quinary: type_score DESC
        # Senary: freshness_score DESC
        # Septenary: urgency_score DESC
        # Tie-breaker: entity_id ASC (lexicographical UUID)
        scored_candidates.sort(
            key=lambda c: (
                -c.final_score,
                -c.semantic_score,
                -c.topic_score,
                -c.lexical_score,
                -c.type_score,
                -c.freshness_score,
                -c.urgency_score,
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
                    retrieval_sources=item.retrieval_sources,
                    shared_topic_ids=item.shared_topic_ids,
                    shared_topic_names=item.shared_topic_names,
                    candidate=item.candidate,
                )
            )

        return final_ranked


# Module-level default instance
hybrid_ranker = HybridRanker()
