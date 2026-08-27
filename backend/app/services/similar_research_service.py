"""
Similar Research Retrieval Service for Phase 2.4C.

Answers the foundational research intelligence question:
"Given one research work, which other research works are most similar to it?"

Architectural Workflow
----------------------
1. Retrieve source ResearchWorkModel by UUID.
2. Validate source work existence, embedding presence, and 384-dim vector integrity.
3. Candidate Retrieval:
   - Semantic nearest neighbors via pgvector (VectorRepository).
   - Lexical matching via PostgreSQL full-text search (LexicalRepository).
4. Candidate Deduplication & Provenance Tracking.
5. Topic Overlap & Taxonomy Proximity Evaluation.
6. Multi-Signal Similarity Scoring:
   - Semantic Similarity (cosine similarity in [0.0, 1.0])
   - Lexical Similarity (normalized ts_rank_cd in [0.0, 1.0])
   - Topic Similarity (canonical topic overlap + DAG proximity in [0.0, 1.0])
7. Deterministic Composite Ranking with strict tie-breaking.
8. Exclude source entity (source work != candidate work).

Boundary
--------
Phase 2.4C is strictly a *retrieval capability*. It does NOT perform researcher profiling,
personalized recommendation scoring, deadline scoring, or LLM-based reranking.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
import os
import sys
from typing import Any, Sequence
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
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


# ── Domain Exceptions ─────────────────────────────────────────────────────────


class ResearchWorkNotFoundError(ValueError):
    """Raised when the requested source research work ID does not exist."""


class MissingEmbeddingError(VectorValidationError):
    """Raised when the source research work exists but has no embedding vector."""


# ── Similar Research Result Model ─────────────────────────────────────────────


@dataclass(frozen=True)
class SimilarResearchResult:
    """
    Structured similarity result for a retrieved candidate research work.

    Attributes
    ----------
    source_work_id:
        UUID of the source research work used as the query basis.
    candidate_work_id:
        UUID of the similar candidate research work.
    combined_similarity:
        Normalized composite similarity score in range [0.0, 1.0].
    semantic_similarity:
        Cosine similarity between source and candidate embeddings in [0.0, 1.0].
    lexical_similarity:
        Normalized PostgreSQL full-text search relevance score in [0.0, 1.0].
    topic_similarity:
        Canonical topic overlap and taxonomy proximity score in [0.0, 1.0].
    rank:
        1-based rank position in the final similar research results list.
    shared_topic_ids:
        List of canonical topic UUIDs shared between source and candidate.
    shared_topic_names:
        List of canonical topic display names shared between source and candidate.
    retrieval_sources:
        Retrieval channels that discovered this candidate (e.g. ["vector", "lexical"]).
    candidate_work:
        Optional attached ResearchWorkModel ORM instance.
    """

    source_work_id: uuid.UUID
    candidate_work_id: uuid.UUID
    combined_similarity: float
    semantic_similarity: float
    lexical_similarity: float
    topic_similarity: float
    rank: int
    shared_topic_ids: list[uuid.UUID] = field(default_factory=list)
    shared_topic_names: list[str] = field(default_factory=list)
    retrieval_sources: list[str] = field(default_factory=list)
    candidate_work: Any | None = None


# ── Normalization Utilities ───────────────────────────────────────────────────


def normalize_lexical_score(raw_score: float | None) -> float:
    """
    Normalize raw PostgreSQL ts_rank_cd cover density score into [0.0, 1.0).

    Uses a smooth, monotonic saturating transform: score / (score + 1.0).
    """
    if raw_score is None or raw_score <= 0.0:
        return 0.0
    return round(float(raw_score) / (float(raw_score) + 1.0), 6)


def calculate_topic_similarity(
    source_topics: Sequence[ResearchWorkTopicModel],
    candidate_topics: Sequence[ResearchWorkTopicModel],
    taxonomy_service: Any | None = None,
) -> tuple[float, list[uuid.UUID], list[str]]:
    """
    Calculate canonical topic overlap and taxonomy proximity between two works.

    Parameters
    ----------
    source_topics:
        Topic associations for the source research work.
    candidate_topics:
        Topic associations for the candidate research work.
    taxonomy_service:
        Optional TaxonomyService instance for hierarchical DAG ancestor traversal.

    Returns
    -------
    tuple[float, list[uuid.UUID], list[str]]
        (topic_similarity_in_[0, 1], shared_topic_ids, shared_topic_names)
    """
    if not source_topics or not candidate_topics:
        return 0.0, [], []

    source_map: dict[uuid.UUID, ResearchWorkTopicModel] = {
        assoc.topic_id: assoc for assoc in source_topics if assoc.topic_id is not None
    }
    candidate_map: dict[uuid.UUID, ResearchWorkTopicModel] = {
        assoc.topic_id: assoc for assoc in candidate_topics if assoc.topic_id is not None
    }

    shared_ids = sorted(
        list(set(source_map.keys()).intersection(set(candidate_map.keys()))),
        key=str,
    )
    shared_names: list[str] = []

    overlap_score = 0.0

    # 1. Exact canonical topic overlap
    for tid in shared_ids:
        s_assoc = source_map[tid]
        c_assoc = candidate_map[tid]

        # Extract name if loaded on topic model
        if getattr(s_assoc, "topic", None) is not None and getattr(s_assoc.topic, "name", None):
            shared_names.append(s_assoc.topic.name)
        elif getattr(c_assoc, "topic", None) is not None and getattr(c_assoc.topic, "name", None):
            shared_names.append(c_assoc.topic.name)

        s_conf = float(getattr(s_assoc, "confidence_score", 1.0))
        c_conf = float(getattr(c_assoc, "confidence_score", 1.0))
        base_match = min(s_conf, c_conf)

        # Primary topic match bonus
        is_s_primary = bool(getattr(s_assoc, "is_primary", False))
        is_c_primary = bool(getattr(c_assoc, "is_primary", False))
        if is_s_primary and is_c_primary:
            base_match += 0.20 * base_match

        overlap_score += base_match

    # 2. Hierarchical taxonomy proximity for unshared topics
    if taxonomy_service is not None:
        source_unshared = [
            assoc for tid, assoc in source_map.items() if tid not in shared_ids
        ]
        candidate_unshared = [
            assoc for tid, assoc in candidate_map.items() if tid not in shared_ids
        ]

        for s_assoc in source_unshared:
            s_slug = getattr(getattr(s_assoc, "topic", None), "slug", None)
            if not s_slug:
                continue
            s_ancestors = set(taxonomy_service.get_ancestors(s_slug))

            for c_assoc in candidate_unshared:
                c_slug = getattr(getattr(c_assoc, "topic", None), "slug", None)
                if not c_slug:
                    continue
                c_ancestors = set(taxonomy_service.get_ancestors(c_slug))

                # Shared ancestor overlap
                common_ancestors = s_ancestors.intersection(c_ancestors)
                if common_ancestors:
                    s_conf = float(getattr(s_assoc, "confidence_score", 1.0))
                    c_conf = float(getattr(c_assoc, "confidence_score", 1.0))
                    # Partial hierarchical credit (0.15 * min confidence)
                    overlap_score += 0.15 * min(s_conf, c_conf)

    # Calculate union weight for normalization
    source_weight_sum = sum(
        float(getattr(a, "confidence_score", 1.0)) for a in source_topics
    )
    cand_unshared_sum = sum(
        float(getattr(a, "confidence_score", 1.0))
        for tid, a in candidate_map.items()
        if tid not in shared_ids
    )
    total_union_weight = max(1.0, source_weight_sum + cand_unshared_sum)

    topic_sim = round(min(1.0, max(0.0, overlap_score / total_union_weight)), 6)
    return topic_sim, shared_ids, shared_names


# ── Similar Research Service ──────────────────────────────────────────────────


class SimilarResearchService:
    """
    Dedicated Similar Research Retrieval Service.

    Orchestrates semantic vector nearest-neighbor search, lexical full-text matching,
    and canonical topic overlap to retrieve and rank research works similar to a
    given source work.
    """

    def __init__(
        self,
        vec_repo: VectorRepository | None = None,
        lex_repo: LexicalRepository | None = None,
        taxonomy_service: Any | None = None,
        default_limit: int = getattr(
            settings, "similar_research_default_limit", DEFAULT_CANDIDATE_LIMIT
        ),
        max_limit: int = getattr(
            settings, "similar_research_max_limit", MAX_CANDIDATE_LIMIT
        ),
        candidate_multiplier: float = getattr(
            settings, "similar_research_candidate_multiplier", 2.5
        ),
        semantic_weight: float = getattr(
            settings, "similar_research_semantic_weight", 0.60
        ),
        lexical_weight: float = getattr(
            settings, "similar_research_lexical_weight", 0.20
        ),
        topic_weight: float = getattr(
            settings, "similar_research_topic_weight", 0.20
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
        self.embedding_dim = embedding_dim

    @property
    def taxonomy_service(self) -> Any:
        """Lazy-loaded TaxonomyService instance."""
        if self._taxonomy_service is None and TaxonomyService is not None:
            self._taxonomy_service = TaxonomyService()
        return self._taxonomy_service

    def get_similar_research(
        self,
        session: Session,
        work_id: uuid.UUID,
        *,
        limit: int | None = None,
        publication_year: int | None = None,
        min_year: int | None = None,
        max_year: int | None = None,
        work_type: str | None = None,
        language: str | None = None,
        primary_source_id: uuid.UUID | None = None,
        is_oa: bool | None = None,
        min_citations: int | None = None,
    ) -> list[SimilarResearchResult]:
        """
        Retrieve research works similar to the specified source work.

        Parameters
        ----------
        session:
            Active SQLAlchemy database session.
        work_id:
            UUID of the source ResearchWorkModel.
        limit:
            Number of similar research works to return (default 20, max 100).
        publication_year ... min_citations:
            Metadata filters propagated to vector and lexical retrieval channels.

        Returns
        -------
        list[SimilarResearchResult]
            Ranked list of similar research works ordered deterministically.

        Raises
        ------
        ResearchWorkNotFoundError:
            If work_id does not exist in the database.
        MissingEmbeddingError:
            If the source work exists but does not have an embedding.
        VectorValidationError:
            If the source work embedding vector fails validation.
        """
        # 1. Fetch source work
        source_work = session.get(ResearchWorkModel, work_id)
        if source_work is None:
            raise ResearchWorkNotFoundError(
                f"ResearchWork with ID {work_id} not found."
            )

        if source_work.embedding is None:
            raise MissingEmbeddingError(
                f"ResearchWork with ID {work_id} does not have an embedding."
            )

        # 2. Validate source work embedding
        valid_query_vector = validate_query_vector(
            source_work.embedding, self.embedding_dim
        )

        safe_limit = sanitize_candidate_limit(
            limit, self.default_limit, self.max_limit
        )
        candidate_limit = calculate_candidate_limit(
            safe_limit, self.candidate_multiplier, max_limit=self.max_limit
        )

        # 3. Retrieve Candidates from Vector Channel
        vector_results: list[VectorSearchResult] = []
        try:
            vector_results = self.vec_repo.search_research_works(
                session=session,
                query_embedding=valid_query_vector,
                limit=candidate_limit,
                exclude_work_id=work_id,
                publication_year=publication_year,
                min_year=min_year,
                max_year=max_year,
                work_type=work_type,
                language=language,
                primary_source_id=primary_source_id,
                is_oa=is_oa,
                min_citations=min_citations,
            )
        except Exception as exc:
            logger.warning("Vector retrieval for similar research failed: %s", exc)

        # 4. Retrieve Candidates from Lexical Channel (using source title as query)
        lexical_results: list[LexicalSearchResult] = []
        source_query_text = (source_work.title or "").strip()
        if source_query_text:
            try:
                lexical_results = self.lex_repo.search_research_works(
                    session=session,
                    query=source_query_text,
                    limit=candidate_limit,
                    exclude_work_id=work_id,
                    publication_year=publication_year,
                    min_year=min_year,
                    max_year=max_year,
                    work_type=work_type,
                    language=language,
                    primary_source_id=primary_source_id,
                    is_oa=is_oa,
                    min_citations=min_citations,
                )
            except Exception as exc:
                logger.warning("Lexical retrieval for similar research failed: %s", exc)

        # 5. Build Unified Candidate Map
        candidates_data: dict[uuid.UUID, dict[str, Any]] = {}

        for vr in vector_results:
            if vr.entity_id == work_id:
                continue  # Strict self-exclusion guarantee
            candidates_data[vr.entity_id] = {
                "entity_id": vr.entity_id,
                "semantic_similarity": max(0.0, min(1.0, float(vr.similarity))),
                "lexical_score": None,
                "sources": ["vector"],
                "entity": vr.entity,
            }

        for lr in lexical_results:
            if lr.entity_id == work_id:
                continue  # Strict self-exclusion guarantee
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

        # 6. Resolve Topics for Source and Candidate Works
        candidate_ids = list(candidates_data.keys())
        all_work_ids = [work_id] + candidate_ids

        # Fetch topic associations in a single query if not already present on entities
        topics_by_work: dict[uuid.UUID, list[ResearchWorkTopicModel]] = {
            wid: [] for wid in all_work_ids
        }

        # Check if topics are already loaded on entities (e.g. in test fixtures or eager loads)
        source_topics_loaded = getattr(source_work, "topic_associations", None)
        if source_topics_loaded is not None and len(source_topics_loaded) > 0:
            topics_by_work[work_id] = list(source_topics_loaded)

        for cid, cdata in candidates_data.items():
            centity = cdata.get("entity")
            if centity is not None:
                ctopics_loaded = getattr(centity, "topic_associations", None)
                if ctopics_loaded is not None and len(ctopics_loaded) > 0:
                    topics_by_work[cid] = list(ctopics_loaded)

        # Query database for any missing topic associations
        missing_topic_work_ids = [
            wid for wid, tlist in topics_by_work.items() if not tlist
        ]
        if missing_topic_work_ids:
            try:
                topic_stmt = (
                    select(ResearchWorkTopicModel)
                    .options(joinedload(ResearchWorkTopicModel.topic))
                    .where(ResearchWorkTopicModel.work_id.in_(missing_topic_work_ids))
                )
                topic_rows = session.execute(topic_stmt).scalars().all()
                for assoc in topic_rows:
                    if assoc.work_id in topics_by_work:
                        topics_by_work[assoc.work_id].append(assoc)
            except Exception as exc:
                logger.warning("Topic lookup query failed: %s", exc)

        source_work_topics = topics_by_work.get(work_id, [])

        # 7. Calculate Multi-Signal Similarities and Composite Scores
        total_weight = (
            self.semantic_weight + self.lexical_weight + self.topic_weight
        ) or 1.0
        w_sem = self.semantic_weight / total_weight
        w_lex = self.lexical_weight / total_weight
        w_top = self.topic_weight / total_weight

        candidate_results: list[SimilarResearchResult] = []

        for cid, cdata in candidates_data.items():
            sem_sim = cdata["semantic_similarity"]
            raw_lex = cdata["lexical_score"]
            lex_sim = normalize_lexical_score(raw_lex)

            cand_topics = topics_by_work.get(cid, [])
            top_sim, shared_tids, shared_tnames = calculate_topic_similarity(
                source_topics=source_work_topics,
                candidate_topics=cand_topics,
                taxonomy_service=self.taxonomy_service,
            )

            # Combined similarity formula
            combined_sim = round(
                w_sem * sem_sim + w_lex * lex_sim + w_top * top_sim, 6
            )

            candidate_results.append(
                SimilarResearchResult(
                    source_work_id=work_id,
                    candidate_work_id=cid,
                    combined_similarity=combined_sim,
                    semantic_similarity=sem_sim,
                    lexical_similarity=lex_sim,
                    topic_similarity=top_sim,
                    rank=0,  # assigned after deterministic sort
                    shared_topic_ids=shared_tids,
                    shared_topic_names=shared_tnames,
                    retrieval_sources=sorted(cdata["sources"]),
                    candidate_work=cdata["entity"],
                )
            )

        # 8. Deterministic Ranking & Tie-breaking
        # Primary: combined_similarity DESC
        # Secondary: semantic_similarity DESC
        # Tertiary: lexical_similarity DESC
        # Quaternary: topic_similarity DESC
        # Tie-breaker: candidate_work_id ASC (lexicographical UUID)
        candidate_results.sort(
            key=lambda r: (
                -r.combined_similarity,
                -r.semantic_similarity,
                -r.lexical_similarity,
                -r.topic_similarity,
                str(r.candidate_work_id),
            )
        )

        # 9. Apply Limit and Assign 1-Based Ranks
        limited_results = candidate_results[:safe_limit]

        final_ranked: list[SimilarResearchResult] = []
        for idx, res in enumerate(limited_results, start=1):
            final_ranked.append(
                SimilarResearchResult(
                    source_work_id=res.source_work_id,
                    candidate_work_id=res.candidate_work_id,
                    combined_similarity=res.combined_similarity,
                    semantic_similarity=res.semantic_similarity,
                    lexical_similarity=res.lexical_similarity,
                    topic_similarity=res.topic_similarity,
                    rank=idx,
                    shared_topic_ids=res.shared_topic_ids,
                    shared_topic_names=res.shared_topic_names,
                    retrieval_sources=res.retrieval_sources,
                    candidate_work=res.candidate_work,
                )
            )

        return final_ranked


# Module-level default service instance
similar_research_service = SimilarResearchService()
