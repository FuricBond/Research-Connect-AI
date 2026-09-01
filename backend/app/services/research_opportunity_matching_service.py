"""
Research ↔ Opportunity Matching Service for Phase 2.4D.

Responsible for matching scholarly research works to relevant academic opportunities
(Conferences, Journals, Workshops, CFPs, Special Issues).

Architectural Workflow
----------------------
1. Retrieve source ResearchWorkModel by UUID.
2. Validate source work existence and check embedding presence.
   - If embedding is present, validate 384-dim vector.
   - If embedding is missing and require_embedding=True, raise MissingEmbeddingError.
   - If require_embedding=False, gracefully degrade to lexical/topic channels.
3. Candidate Retrieval:
   - Semantic nearest neighbors via pgvector (VectorRepository.search_opportunities).
   - Lexical matching via PostgreSQL full-text search (LexicalRepository.search_opportunities).
4. Candidate Unification & Provenance Tracking (["semantic"], ["lexical"], ["semantic", "lexical"]).
5. Topic Compatibility Evaluation:
   - Exact canonical topic overlap weighted by assignment confidences.
   - Primary topic match bonus.
   - Hierarchical DAG ancestor proximity via TaxonomyService.
6. Opportunity-Type Compatibility Evaluation:
   - Deterministic compatibility matrix between work_type and opportunity_type.
7. Multi-Signal Composite Match Scoring:
   - Semantic Similarity (cosine similarity in [0.0, 1.0])
   - Lexical Similarity (normalized ts_rank_cd in [0.0, 1.0])
   - Topic Compatibility (canonical topic overlap + DAG proximity in [0.0, 1.0])
   - Type Compatibility (deterministic matrix score in [0.0, 1.0])
8. Deterministic Ranking & Stable Tie-Breaking:
   - Primary: match_score DESC
   - Secondary: semantic_similarity DESC
   - Tertiary: topic_similarity DESC
   - Quaternary: lexical_similarity DESC
   - Quinary: type_compatibility DESC
   - Tie-breaker: opportunity UUID ASC

Boundary
--------
Phase 2.4D is strictly a *matching capability*. It does NOT perform researcher profiling,
personalized user recommendations, natural-language explanation generation, or FastAPI endpoint exposure.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
import os
import sys
from typing import Any, Sequence
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.models.opportunity import OpportunityModel, OpportunityTopicModel
from app.models.research_knowledge import (
    ResearchWorkModel,
    ResearchWorkTopicModel,
)
from app.repositories.lexical_repository import (
    LexicalRepository,
    LexicalSearchResult,
    lexical_repository,
)
from app.repositories.vector_repository import (
    DEFAULT_CANDIDATE_LIMIT,
    MAX_CANDIDATE_LIMIT,
    VectorRepository,
    VectorSearchResult,
    VectorValidationError,
    sanitize_candidate_limit,
    validate_query_vector,
    vector_repository,
)
from app.services.hybrid_search_service import calculate_candidate_limit
from app.services.similar_research_service import (
    MissingEmbeddingError,
    ResearchWorkNotFoundError,
    normalize_lexical_score,
)

# Ensure repository root is available for ml imports
_root_path = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
if _root_path not in sys.path:
    sys.path.insert(0, _root_path)

try:
    from ml.topic_analysis.taxonomy import TaxonomyService
except ImportError:
    TaxonomyService = None  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)


# ── Structured Match Result Model ─────────────────────────────────────────────


@dataclass(frozen=True)
class ResearchOpportunityMatch:
    """
    Structured matching result between a research work and an academic opportunity.

    Attributes
    ----------
    research_work_id:
        UUID of the source research work.
    opportunity_id:
        UUID of the candidate opportunity.
    match_score:
        Composite multi-signal match score in range [0.0, 1.0].
    semantic_similarity:
        Cosine similarity between research and opportunity embeddings in [0.0, 1.0].
    lexical_similarity:
        Normalized PostgreSQL full-text search relevance score in [0.0, 1.0].
    topic_similarity:
        Canonical topic overlap and taxonomy DAG proximity in [0.0, 1.0].
    type_compatibility:
        Deterministic research work type to opportunity type compatibility in [0.0, 1.0].
    rank:
        1-based rank position in the final ranked opportunities list.
    shared_topic_ids:
        List of canonical topic UUIDs shared between research work and opportunity.
    shared_topic_names:
        List of canonical topic display names shared between research work and opportunity.
    retrieval_sources:
        Retrieval channels that discovered this opportunity (e.g. ["semantic", "lexical"]).
    opportunity:
        Optional attached OpportunityModel ORM instance.
    """

    research_work_id: uuid.UUID
    opportunity_id: uuid.UUID
    match_score: float
    semantic_similarity: float
    lexical_similarity: float
    topic_similarity: float
    type_compatibility: float
    rank: int = 0
    quality_score: float = 0.0
    shared_topic_ids: list[uuid.UUID] = field(default_factory=list)
    shared_topic_names: list[str] = field(default_factory=list)
    retrieval_sources: list[str] = field(default_factory=list)
    opportunity: Any | None = None


# ── Opportunity Type Compatibility Matrix ─────────────────────────────────────


TYPE_COMPATIBILITY_MATRIX: dict[str, dict[str, float]] = {
    "article": {
        "JOURNAL": 1.00,
        "SPECIAL_ISSUE": 0.95,
        "CALL_FOR_PAPERS": 0.85,
        "CONFERENCE": 0.70,
        "WORKSHOP": 0.60,
    },
    "journal-article": {
        "JOURNAL": 1.00,
        "SPECIAL_ISSUE": 0.95,
        "CALL_FOR_PAPERS": 0.85,
        "CONFERENCE": 0.70,
        "WORKSHOP": 0.60,
    },
    "review": {
        "JOURNAL": 1.00,
        "SPECIAL_ISSUE": 0.95,
        "CALL_FOR_PAPERS": 0.85,
        "CONFERENCE": 0.65,
        "WORKSHOP": 0.55,
    },
    "proceedings-article": {
        "CONFERENCE": 1.00,
        "WORKSHOP": 0.90,
        "CALL_FOR_PAPERS": 0.85,
        "SPECIAL_ISSUE": 0.70,
        "JOURNAL": 0.65,
    },
    "conference-paper": {
        "CONFERENCE": 1.00,
        "WORKSHOP": 0.90,
        "CALL_FOR_PAPERS": 0.85,
        "SPECIAL_ISSUE": 0.70,
        "JOURNAL": 0.65,
    },
    "workshop-paper": {
        "WORKSHOP": 1.00,
        "CONFERENCE": 0.85,
        "CALL_FOR_PAPERS": 0.75,
        "SPECIAL_ISSUE": 0.65,
        "JOURNAL": 0.50,
    },
    "preprint": {
        "CONFERENCE": 0.90,
        "JOURNAL": 0.90,
        "WORKSHOP": 0.85,
        "SPECIAL_ISSUE": 0.85,
        "CALL_FOR_PAPERS": 0.90,
    },
    "book-chapter": {
        "CALL_FOR_PAPERS": 0.80,
        "SPECIAL_ISSUE": 0.80,
        "JOURNAL": 0.60,
        "CONFERENCE": 0.50,
        "WORKSHOP": 0.50,
    },
    "dissertation": {
        "JOURNAL": 0.80,
        "CONFERENCE": 0.75,
        "WORKSHOP": 0.70,
        "SPECIAL_ISSUE": 0.75,
        "CALL_FOR_PAPERS": 0.75,
    },
}

DEFAULT_TYPE_COMPATIBILITY: float = 0.70


def calculate_type_compatibility(
    work_type: str | None,
    opportunity_type: str | None,
) -> float:
    """
    Calculate deterministic compatibility between research work type and opportunity type.

    Parameters
    ----------
    work_type:
        Type of research work (e.g. 'article', 'preprint', 'conference-paper').
    opportunity_type:
        Type of opportunity (e.g. 'CONFERENCE', 'JOURNAL', 'WORKSHOP').

    Returns
    -------
    float
        Compatibility score in range [0.0, 1.0].
    """
    if not work_type or not opportunity_type:
        return DEFAULT_TYPE_COMPATIBILITY

    w_type = work_type.lower().strip()
    o_type = opportunity_type.upper().strip()

    mapping = TYPE_COMPATIBILITY_MATRIX.get(w_type)
    if mapping and o_type in mapping:
        return mapping[o_type]

    return DEFAULT_TYPE_COMPATIBILITY


# ── Topic Compatibility Function ──────────────────────────────────────────────


def calculate_topic_compatibility(
    work_topics: Sequence[ResearchWorkTopicModel],
    opportunity_topics: Sequence[OpportunityTopicModel],
    taxonomy_service: Any | None = None,
) -> tuple[float, list[uuid.UUID], list[str]]:
    """
    Calculate canonical topic overlap and taxonomy DAG proximity between a research work
    and an academic opportunity.

    Parameters
    ----------
    work_topics:
        Topic associations for the research work.
    opportunity_topics:
        Topic associations for the academic opportunity.
    taxonomy_service:
        Optional TaxonomyService instance for hierarchical DAG ancestor traversal.

    Returns
    -------
    tuple[float, list[uuid.UUID], list[str]]
        (topic_compatibility_in_[0, 1], shared_topic_ids, shared_topic_names)
    """
    if not work_topics or not opportunity_topics:
        return 0.0, [], []

    work_map: dict[uuid.UUID, ResearchWorkTopicModel] = {
        assoc.topic_id: assoc for assoc in work_topics if assoc.topic_id is not None
    }
    opp_map: dict[uuid.UUID, OpportunityTopicModel] = {
        assoc.topic_id: assoc for assoc in opportunity_topics if assoc.topic_id is not None
    }

    shared_ids = sorted(
        list(set(work_map.keys()).intersection(set(opp_map.keys()))),
        key=str,
    )
    shared_names: list[str] = []

    overlap_score = 0.0

    # 1. Exact canonical topic overlap
    for tid in shared_ids:
        w_assoc = work_map[tid]
        o_assoc = opp_map[tid]

        if getattr(w_assoc, "topic", None) is not None and getattr(w_assoc.topic, "name", None):
            shared_names.append(w_assoc.topic.name)
        elif getattr(o_assoc, "topic", None) is not None and getattr(o_assoc.topic, "name", None):
            shared_names.append(o_assoc.topic.name)

        w_conf = float(getattr(w_assoc, "confidence_score", 1.0))
        o_conf = float(getattr(o_assoc, "confidence_score", 1.0))
        base_match = min(w_conf, o_conf)

        # Primary topic match bonus
        is_w_primary = bool(getattr(w_assoc, "is_primary", False))
        is_o_primary = bool(getattr(o_assoc, "is_primary", False))
        if is_w_primary and is_o_primary:
            base_match += 0.20 * base_match

        overlap_score += base_match

    # 2. Hierarchical taxonomy proximity for unshared topics
    if taxonomy_service is not None:
        work_unshared = [
            assoc for tid, assoc in work_map.items() if tid not in shared_ids
        ]
        opp_unshared = [
            assoc for tid, assoc in opp_map.items() if tid not in shared_ids
        ]

        for w_assoc in work_unshared:
            w_slug = getattr(getattr(w_assoc, "topic", None), "slug", None)
            if not w_slug:
                continue
            w_ancestors = set(taxonomy_service.get_ancestors(w_slug))

            for o_assoc in opp_unshared:
                o_slug = getattr(getattr(o_assoc, "topic", None), "slug", None)
                if not o_slug:
                    continue
                o_ancestors = set(taxonomy_service.get_ancestors(o_slug))

                common_ancestors = w_ancestors.intersection(o_ancestors)
                if common_ancestors:
                    w_conf = float(getattr(w_assoc, "confidence_score", 1.0))
                    o_conf = float(getattr(o_assoc, "confidence_score", 1.0))
                    overlap_score += 0.15 * min(w_conf, o_conf)

    # Calculate union weight for normalization
    work_weight_sum = sum(
        float(getattr(a, "confidence_score", 1.0)) for a in work_topics
    )
    opp_unshared_sum = sum(
        float(getattr(a, "confidence_score", 1.0))
        for tid, a in opp_map.items()
        if tid not in shared_ids
    )
    total_union_weight = max(1.0, work_weight_sum + opp_unshared_sum)

    topic_comp = round(min(1.0, max(0.0, overlap_score / total_union_weight)), 6)
    return topic_comp, shared_ids, shared_names


# ── Research ↔ Opportunity Matching Service ───────────────────────────────────


class ResearchOpportunityMatchingService:
    """
    Orchestrates candidate retrieval and multi-signal matching between a
    Research Work and academic Opportunities.
    """

    def __init__(
        self,
        vec_repo: VectorRepository | None = None,
        lex_repo: LexicalRepository | None = None,
        taxonomy_service: Any | None = None,
        default_limit: int = getattr(
            settings, "research_opportunity_default_limit", DEFAULT_CANDIDATE_LIMIT
        ),
        max_limit: int = getattr(
            settings, "research_opportunity_max_limit", MAX_CANDIDATE_LIMIT
        ),
        candidate_multiplier: float = getattr(
            settings, "research_opportunity_candidate_multiplier", 2.5
        ),
        semantic_weight: float = getattr(
            settings, "research_opportunity_semantic_weight", 0.50
        ),
        lexical_weight: float = getattr(
            settings, "research_opportunity_lexical_weight", 0.20
        ),
        topic_weight: float = getattr(
            settings, "research_opportunity_topic_weight", 0.20
        ),
        type_weight: float = getattr(
            settings, "research_opportunity_type_weight", 0.10
        ),
        embedding_dim: int = getattr(settings, "embedding_dim", 384),
    ) -> None:
        self.vec_repo = vec_repo or vector_repository
        self.lex_repo = lex_repo or lexical_repository
        self._taxonomy_service = taxonomy_service
        self.default_limit = default_limit
        self.max_limit = max_limit
        self.candidate_multiplier = candidate_multiplier
        self.semantic_weight = semantic_weight
        self.lexical_weight = lexical_weight
        self.topic_weight = topic_weight
        self.type_weight = type_weight
        self.embedding_dim = embedding_dim

    @property
    def taxonomy_service(self) -> Any:
        """Lazy-loaded TaxonomyService instance."""
        if self._taxonomy_service is None and TaxonomyService is not None:
            self._taxonomy_service = TaxonomyService()
        return self._taxonomy_service

    def match_opportunities(
        self,
        session: Session,
        work_id: uuid.UUID,
        *,
        limit: int | None = None,
        opportunity_type: str | None = None,
        status: str | Sequence[str] | None = None,
        delivery_mode: str | None = None,
        source_id: uuid.UUID | None = None,
        upcoming_only: bool = False,
        submission_deadline_after: datetime | None = None,
        require_embedding: bool = False,
    ) -> list[ResearchOpportunityMatch]:
        """
        Match a research work to relevant academic opportunities.

        Parameters
        ----------
        session:
            Active SQLAlchemy database session.
        work_id:
            UUID of the source ResearchWorkModel.
        limit:
            Number of matched opportunities to return (default 20, max 100).
        opportunity_type:
            Filter by opportunity type (CONFERENCE, JOURNAL, WORKSHOP, ...).
        status:
            Filter by status (e.g. 'ACTIVE').
        delivery_mode:
            Filter by delivery mode ('ONLINE', 'OFFLINE', 'HYBRID').
        source_id:
            Filter by origin source ID.
        upcoming_only:
            If True, only return opportunities with submission_deadline >= now.
        submission_deadline_after:
            Filter submission_deadline >= specified datetime.
        require_embedding:
            If True and source work has no embedding, raises MissingEmbeddingError.
            If False, degrades gracefully to lexical and topic channels.

        Returns
        -------
        list[ResearchOpportunityMatch]
            Deterministically ranked opportunity matches with composite scores and provenance.

        Raises
        ------
        ResearchWorkNotFoundError:
            If work_id does not exist in the database.
        MissingEmbeddingError:
            If require_embedding=True and source work has no embedding vector.
        VectorValidationError:
            If source work embedding fails validation.
        """
        # 1. Fetch source work
        source_work = session.get(ResearchWorkModel, work_id)
        if source_work is None:
            raise ResearchWorkNotFoundError(
                f"ResearchWork with ID {work_id} not found."
            )

        # 2. Embedding handling & validation
        valid_query_vector: list[float] | None = None
        if source_work.embedding is not None:
            valid_query_vector = validate_query_vector(
                source_work.embedding, self.embedding_dim
            )
        elif require_embedding:
            raise MissingEmbeddingError(
                f"ResearchWork with ID {work_id} does not have an embedding."
            )

        safe_limit = sanitize_candidate_limit(
            limit, self.default_limit, self.max_limit
        )
        candidate_limit = calculate_candidate_limit(
            safe_limit, self.candidate_multiplier, max_limit=self.max_limit
        )

        # 3. Retrieve Candidates from Semantic Channel
        vector_results: list[VectorSearchResult] = []
        if valid_query_vector is not None:
            try:
                vector_results = self.vec_repo.search_opportunities(
                    session=session,
                    query_embedding=valid_query_vector,
                    limit=candidate_limit,
                    opportunity_type=opportunity_type,
                    status=status,
                    delivery_mode=delivery_mode,
                    source_id=source_id,
                    upcoming_only=upcoming_only,
                    submission_deadline_after=submission_deadline_after,
                )
            except Exception as exc:
                logger.warning("Vector retrieval for opportunity matching failed: %s", exc)

        # 4. Retrieve Candidates from Lexical Channel
        lexical_results: list[LexicalSearchResult] = []
        source_query_text = (source_work.title or "").strip()
        if source_query_text:
            try:
                lexical_results = self.lex_repo.search_opportunities(
                    session=session,
                    query=source_query_text,
                    limit=candidate_limit,
                    opportunity_type=opportunity_type,
                    status=status,
                    delivery_mode=delivery_mode,
                    source_id=source_id,
                    upcoming_only=upcoming_only,
                    submission_deadline_after=submission_deadline_after,
                )
            except Exception as exc:
                logger.warning("Lexical retrieval for opportunity matching failed: %s", exc)

        # 5. Build Unified Candidate Map
        candidates_data: dict[uuid.UUID, dict[str, Any]] = {}

        for vr in vector_results:
            candidates_data[vr.entity_id] = {
                "entity_id": vr.entity_id,
                "semantic_similarity": max(0.0, min(1.0, float(vr.similarity))),
                "lexical_score": None,
                "sources": ["semantic"],
                "entity": vr.entity,
            }

        for lr in lexical_results:
            if lr.entity_id in candidates_data:
                candidates_data[lr.entity_id]["lexical_score"] = float(lr.lexical_score)
                candidates_data[lr.entity_id]["sources"].append("lexical")
                if candidates_data[lr.entity_id]["entity"] is None and lr.entity is not None:
                    candidates_data[lr.entity_id]["entity"] = lr.entity
            else:
                candidates_data[lr.entity_id] = {
                    "entity_id": lr.entity_id,
                    "semantic_similarity": 0.0,
                    "lexical_score": float(lr.lexical_score),
                    "sources": ["lexical"],
                    "entity": lr.entity,
                }

        if not candidates_data:
            return []

        # 6. Resolve Topics for Research Work and Candidate Opportunities
        candidate_opp_ids = list(candidates_data.keys())

        # Research work topics
        work_topics: list[ResearchWorkTopicModel] = []
        source_topics_loaded = getattr(source_work, "topic_associations", None)
        if source_topics_loaded is not None and len(source_topics_loaded) > 0:
            work_topics = list(source_topics_loaded)
        else:
            try:
                work_topic_stmt = (
                    select(ResearchWorkTopicModel)
                    .options(joinedload(ResearchWorkTopicModel.topic))
                    .where(ResearchWorkTopicModel.work_id == work_id)
                )
                work_topics = session.execute(work_topic_stmt).scalars().all()
            except Exception as exc:
                logger.warning("Research work topic query failed: %s", exc)

        # Candidate opportunity topics
        opp_topics_by_id: dict[uuid.UUID, list[OpportunityTopicModel]] = {
            oid: [] for oid in candidate_opp_ids
        }

        for oid, odata in candidates_data.items():
            oentity = odata.get("entity")
            if oentity is not None:
                otopics_loaded = getattr(oentity, "topic_associations", None)
                if otopics_loaded is not None and len(otopics_loaded) > 0:
                    opp_topics_by_id[oid] = list(otopics_loaded)

        missing_opp_topic_ids = [
            oid for oid, tlist in opp_topics_by_id.items() if not tlist
        ]
        if missing_opp_topic_ids:
            try:
                opp_topic_stmt = (
                    select(OpportunityTopicModel)
                    .options(joinedload(OpportunityTopicModel.topic))
                    .where(OpportunityTopicModel.opportunity_id.in_(missing_opp_topic_ids))
                )
                opp_topic_rows = session.execute(opp_topic_stmt).scalars().all()
                for assoc in opp_topic_rows:
                    if assoc.opportunity_id in opp_topics_by_id:
                        opp_topics_by_id[assoc.opportunity_id].append(assoc)
            except Exception as exc:
                logger.warning("Opportunity topic lookup query failed: %s", exc)

        # 7. Multi-Signal Scoring
        total_weight = (
            self.semantic_weight
            + self.lexical_weight
            + self.topic_weight
            + self.type_weight
        ) or 1.0

        w_sem = self.semantic_weight / total_weight
        w_lex = self.lexical_weight / total_weight
        w_top = self.topic_weight / total_weight
        w_typ = self.type_weight / total_weight

        matches: list[ResearchOpportunityMatch] = []

        for oid, odata in candidates_data.items():
            sem_sim = odata["semantic_similarity"]
            raw_lex = odata["lexical_score"]
            lex_sim = normalize_lexical_score(raw_lex)

            cand_opp_topics = opp_topics_by_id.get(oid, [])
            top_sim, shared_tids, shared_tnames = calculate_topic_compatibility(
                work_topics=work_topics,
                opportunity_topics=cand_opp_topics,
                taxonomy_service=self.taxonomy_service,
            )

            # If shared topics found, add "topic" to retrieval sources
            sources = list(odata["sources"])
            if top_sim > 0.0 and "topic" not in sources:
                sources.append("topic")

            opp_entity = odata.get("entity")
            opp_type = getattr(opp_entity, "opportunity_type", None) if opp_entity else None
            type_comp = calculate_type_compatibility(source_work.work_type, opp_type)

            # Composite match score
            comp_score = round(
                w_sem * sem_sim
                + w_lex * lex_sim
                + w_top * top_sim
                + w_typ * type_comp,
                6,
            )

            matches.append(
                ResearchOpportunityMatch(
                    research_work_id=work_id,
                    opportunity_id=oid,
                    match_score=comp_score,
                    semantic_similarity=sem_sim,
                    lexical_similarity=lex_sim,
                    topic_similarity=top_sim,
                    type_compatibility=type_comp,
                    rank=0,  # assigned after deterministic sort
                    shared_topic_ids=shared_tids,
                    shared_topic_names=shared_tnames,
                    retrieval_sources=sorted(sources),
                    opportunity=opp_entity,
                )
            )

        # 8. Deterministic Ranking & Tie-breaking
        # Primary: match_score DESC
        # Secondary: semantic_similarity DESC
        # Tertiary: topic_similarity DESC
        # Quaternary: lexical_similarity DESC
        # Quinary: type_compatibility DESC
        # Tie-breaker: opportunity_id ASC (lexicographical UUID)
        matches.sort(
            key=lambda m: (
                -m.match_score,
                -m.semantic_similarity,
                -m.topic_similarity,
                -m.lexical_similarity,
                -m.type_compatibility,
                str(m.opportunity_id),
            )
        )

        # 9. Apply Limit and Assign 1-Based Ranks
        limited_matches = matches[:safe_limit]

        final_ranked: list[ResearchOpportunityMatch] = []
        for idx, match in enumerate(limited_matches, start=1):
            final_ranked.append(
                ResearchOpportunityMatch(
                    research_work_id=match.research_work_id,
                    opportunity_id=match.opportunity_id,
                    match_score=match.match_score,
                    semantic_similarity=match.semantic_similarity,
                    lexical_similarity=match.lexical_similarity,
                    topic_similarity=match.topic_similarity,
                    type_compatibility=match.type_compatibility,
                    rank=idx,
                    shared_topic_ids=match.shared_topic_ids,
                    shared_topic_names=match.shared_topic_names,
                    retrieval_sources=match.retrieval_sources,
                    opportunity=match.opportunity,
                )
            )

        return final_ranked


# Module-level default service instance
research_opportunity_matching_service = ResearchOpportunityMatchingService()
