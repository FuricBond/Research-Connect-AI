"""
Hybrid Search Service for Phase 2.4B.

Orchestrates dual-path candidate retrieval:
  1. Lexical search via PostgreSQL full-text search (LexicalRepository)
  2. Semantic vector search via pgvector (VectorRepository)
  3. Rank-based fusion via Reciprocal Rank Fusion (RRF)

Key Responsibilities
--------------------
* Compute candidate oversampling limits to ensure high candidate recall before fusion.
* Generate a 384-dimensional query embedding via EmbeddingService (query-only embedding).
* Apply identical metadata filters and source entity exclusions to both retrieval channels.
* Merge lexical and vector candidate sets into a unified, deduplicated list of HybridSearchResult.
* Expose full candidate provenance (`retrieval_sources`, `lexical_rank`, `vector_rank`, etc.).

Boundary
--------
This layer ONLY performs candidate retrieval and fusion. It does NOT perform recommendation
ranking, topic-weighted personalization, deadline scoring, or LLM reranking.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Sequence
import uuid

from sqlalchemy.orm import Session

from app.core.config import settings
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
    sanitize_candidate_limit,
    vector_repository,
)
from app.search.query_intelligence import (
    QueryIntelligenceResult,
    QueryIntelligenceService,
    query_intelligence_service,
)
from app.search.rrf import (
    DEFAULT_RRF_K,
    FusedCandidate,
    fuse_ranked_candidates,
)
import os
import sys

# Ensure repository root is on sys.path for ml package imports
_root_path = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
if _root_path not in sys.path:
    sys.path.insert(0, _root_path)

try:
    from ml.embeddings.service import EmbeddingService
except ImportError:
    EmbeddingService = None  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)


# ── Unified Hybrid Search Result Model ────────────────────────────────────────


@dataclass(frozen=True)
class HybridSearchResult:
    """
    Unified candidate result container from hybrid search fusion.

    Attributes
    ----------
    entity_id:
        Primary key UUID of the matched candidate.
    entity_type:
        Type of entity ("research_work" or "opportunity").
    hybrid_score:
        Fused RRF score (higher indicates stronger combined ranking).
    lexical_rank:
        1-based rank position in lexical results, or None if not found lexically.
    vector_rank:
        1-based rank position in vector results, or None if not found semantically.
    lexical_score:
        Raw PostgreSQL full-text search score (ts_rank_cd), or None.
    vector_similarity:
        Cosine similarity score from pgvector (1.0 - distance), or None.
    retrieval_sources:
        List of retrieval channels that discovered this candidate (e.g. ["lexical", "vector"]).
    entity:
        Optional attached ORM model instance.
    """

    entity_id: uuid.UUID
    entity_type: str
    hybrid_score: float
    lexical_rank: int | None = None
    vector_rank: int | None = None
    lexical_score: float | None = None
    vector_similarity: float | None = None
    retrieval_sources: list[str] = field(default_factory=list)
    entity: Any | None = None


# ── Candidate Oversampling Strategy ───────────────────────────────────────────


def calculate_candidate_limit(
    final_limit: int,
    multiplier: float = 2.5,
    min_candidates: int = DEFAULT_CANDIDATE_LIMIT,
    max_limit: int = MAX_CANDIDATE_LIMIT,
) -> int:
    """
    Calculate the number of candidates to retrieve from each individual channel.

    Oversampling ensures that candidates appearing high in one channel but
    moderately in another are not missed prior to RRF fusion.

    Parameters
    ----------
    final_limit:
        The target number of fused results requested by the caller.
    multiplier:
        Oversampling factor (default: 2.5x).
    min_candidates:
        Floor for candidate retrieval (default: 20).
    max_limit:
        Ceiling for candidate retrieval (default: 100).
    """
    raw = int(final_limit * multiplier)
    return min(max_limit, max(min_candidates, raw))


# ── Hybrid Search Service ─────────────────────────────────────────────────────


class HybridSearchService:
    """
    Hybrid search orchestrator combining lexical full-text search and semantic
    pgvector retrieval via Reciprocal Rank Fusion.
    """

    def __init__(
        self,
        lex_repo: LexicalRepository | None = None,
        vec_repo: VectorRepository | None = None,
        embedding_service: EmbeddingService | None = None,
        query_intelligence: QueryIntelligenceService | None = None,
        default_limit: int = getattr(settings, "hybrid_search_default_limit", DEFAULT_CANDIDATE_LIMIT),
        max_limit: int = getattr(settings, "hybrid_search_max_limit", MAX_CANDIDATE_LIMIT),
        candidate_multiplier: float = getattr(settings, "hybrid_search_candidate_multiplier", 2.5),
        rrf_k: int = getattr(settings, "hybrid_search_rrf_k", DEFAULT_RRF_K),
    ) -> None:
        self.lex_repo = lex_repo or lexical_repository
        self.vec_repo = vec_repo or vector_repository
        self._embedding_service = embedding_service
        self.query_intelligence = query_intelligence or query_intelligence_service
        self.default_limit = default_limit
        self.max_limit = max_limit
        self.candidate_multiplier = candidate_multiplier
        self.rrf_k = rrf_k

    @property
    def embedding_service(self) -> EmbeddingService:
        """Lazy-loaded EmbeddingService instance."""
        if self._embedding_service is None:
            self._embedding_service = EmbeddingService()
        return self._embedding_service

    # ── Research Works Hybrid Search ──────────────────────────────────────────

    def search_research_works(
        self,
        session: Session,
        query: str,
        *,
        limit: int | None = None,
        exclude_work_id: uuid.UUID | None = None,
        publication_year: int | None = None,
        min_year: int | None = None,
        max_year: int | None = None,
        work_type: str | None = None,
        language: str | None = None,
        primary_source_id: uuid.UUID | None = None,
        is_oa: bool | None = None,
        min_citations: int | None = None,
    ) -> list[HybridSearchResult]:
        """
        Execute hybrid search (lexical + vector + RRF) over research_works.

        Applies deterministic query intelligence:
        - Lexical search receives the expanded query (acronyms expanded to phrases).
        - Vector search receives the normalized query (clean natural semantics).

        Parameters
        ----------
        session:
            Active SQLAlchemy database session.
        query:
            Natural language search query.
        limit:
            Final number of fused candidate results (default: 20, max: 100).
        exclude_work_id:
            Source work UUID to exclude from results.
        publication_year ... min_citations:
            Metadata filters propagated identically to both retrieval channels.

        Returns
        -------
        list[HybridSearchResult]
            Fused and deduplicated candidate results.
        """
        if not query or not query.strip():
            return []

        qi_res = self.query_intelligence.process(query)
        if not qi_res.normalized_query:
            return []

        semantic_query = qi_res.normalized_query
        lexical_query = qi_res.expanded_query

        safe_limit = sanitize_candidate_limit(limit, self.default_limit, self.max_limit)
        candidate_limit = calculate_candidate_limit(
            safe_limit, self.candidate_multiplier, max_limit=self.max_limit
        )

        # 1. Lexical Retrieval (uses expanded query for higher term hit rate)
        lexical_results: list[LexicalSearchResult] = []
        try:
            lexical_results = self.lex_repo.search_research_works(
                session,
                lexical_query,
                limit=candidate_limit,
                exclude_work_id=exclude_work_id,
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
            logger.warning("Lexical search for research works failed: %s", exc)

        # 2. Semantic Vector Retrieval (uses normalized query for clean embeddings)
        vector_results: list[VectorSearchResult] = []
        try:
            query_embedding = self.embedding_service.encode_one(semantic_query)
            vector_results = self.vec_repo.search_research_works(
                session,
                query_embedding,
                limit=candidate_limit,
                exclude_work_id=exclude_work_id,
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
            logger.warning("Vector search for research works failed: %s", exc)

        # 3. RRF Fusion
        fused_candidates = fuse_ranked_candidates(
            {"lexical": lexical_results, "vector": vector_results},
            k=self.rrf_k,
            limit=safe_limit,
        )

        return self._to_hybrid_results(fused_candidates)

    # ── Opportunities Hybrid Search ───────────────────────────────────────────

    def search_opportunities(
        self,
        session: Session,
        query: str,
        *,
        limit: int | None = None,
        exclude_opportunity_id: uuid.UUID | None = None,
        opportunity_type: str | None = None,
        status: str | Sequence[str] | None = None,
        delivery_mode: str | None = None,
        source_id: uuid.UUID | None = None,
        upcoming_only: bool = False,
        submission_deadline_after: datetime | None = None,
    ) -> list[HybridSearchResult]:
        """
        Execute hybrid search (lexical + vector + RRF) over opportunities.

        Applies deterministic query intelligence:
        - Lexical search receives the expanded query (acronyms expanded to phrases).
        - Vector search receives the normalized query (clean natural semantics).

        Parameters
        ----------
        session:
            Active SQLAlchemy database session.
        query:
            Natural language search query.
        limit:
            Final number of fused candidate results (default: 20, max: 100).
        exclude_opportunity_id:
            Source opportunity UUID to exclude from results.
        opportunity_type ... submission_deadline_after:
            Metadata filters propagated identically to both retrieval channels.

        Returns
        -------
        list[HybridSearchResult]
            Fused and deduplicated candidate results.
        """
        if not query or not query.strip():
            return []

        qi_res = self.query_intelligence.process(query)
        if not qi_res.normalized_query:
            return []

        semantic_query = qi_res.normalized_query
        lexical_query = qi_res.expanded_query

        safe_limit = sanitize_candidate_limit(limit, self.default_limit, self.max_limit)
        candidate_limit = calculate_candidate_limit(
            safe_limit, self.candidate_multiplier, max_limit=self.max_limit
        )

        # 1. Lexical Retrieval (uses expanded query)
        lexical_results: list[LexicalSearchResult] = []
        try:
            lexical_results = self.lex_repo.search_opportunities(
                session,
                lexical_query,
                limit=candidate_limit,
                exclude_opportunity_id=exclude_opportunity_id,
                opportunity_type=opportunity_type,
                status=status,
                delivery_mode=delivery_mode,
                source_id=source_id,
                upcoming_only=upcoming_only,
                submission_deadline_after=submission_deadline_after,
            )
        except Exception as exc:
            logger.warning("Lexical search for opportunities failed: %s", exc)

        # 2. Semantic Vector Retrieval (uses normalized query)
        vector_results: list[VectorSearchResult] = []
        try:
            query_embedding = self.embedding_service.encode_one(semantic_query)
            vector_results = self.vec_repo.search_opportunities(
                session,
                query_embedding,
                limit=candidate_limit,
                exclude_opportunity_id=exclude_opportunity_id,
                opportunity_type=opportunity_type,
                status=status,
                delivery_mode=delivery_mode,
                source_id=source_id,
                upcoming_only=upcoming_only,
                submission_deadline_after=submission_deadline_after,
            )
        except Exception as exc:
            logger.warning("Vector search for opportunities failed: %s", exc)

        # 3. RRF Fusion
        fused_candidates = fuse_ranked_candidates(
            {"lexical": lexical_results, "vector": vector_results},
            k=self.rrf_k,
            limit=safe_limit,
        )

        return self._to_hybrid_results(fused_candidates)

    # ── Result Transformation Helper ──────────────────────────────────────────

    def _to_hybrid_results(
        self, fused_candidates: Sequence[FusedCandidate]
    ) -> list[HybridSearchResult]:
        """Convert internal FusedCandidate objects to clean HybridSearchResult models."""
        results: list[HybridSearchResult] = []
        for fc in fused_candidates:
            results.append(
                HybridSearchResult(
                    entity_id=fc.entity_id,
                    entity_type=fc.entity_type,
                    hybrid_score=fc.rrf_score,
                    lexical_rank=fc.ranks.get("lexical"),
                    vector_rank=fc.ranks.get("vector"),
                    lexical_score=fc.scores.get("lexical"),
                    vector_similarity=fc.scores.get("vector"),
                    retrieval_sources=fc.retrieval_sources,
                    entity=fc.entity,
                )
            )
        return results


# Module-level default service instance
hybrid_search_service = HybridSearchService()
