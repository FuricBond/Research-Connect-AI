"""
Lexical / Full-Text Search Repository for Phase 2.4B.

Responsible for database-level full-text lexical search over:
  1. research_works (ResearchWorkModel)
  2. opportunities (OpportunityModel)

Uses PostgreSQL-native full-text search capabilities:
  - `to_tsvector('english', ...)` with section weighting (A, B, C)
  - `websearch_to_tsquery('english', :query)` for natural search parsing
  - `ts_rank_cd(...)` for Cover Density ranking

Searchable Documents & Weights
------------------------------
Research Works:
  - Weight A (1.0): `title` (primary relevance anchor)
  - Weight B (0.4): `abstract` (main content body)
  - Weight C (0.2): `work_type`, `language` (metadata classification)

Opportunities:
  - Weight A (1.0): `title` (conference/journal name)
  - Weight B (0.4): `summary`, `description` (call-for-papers details)
  - Weight C (0.2): `publisher`, `organizer`, `series_name`, `location`

Responsibilities
----------------
* Safely parse user queries using `websearch_to_tsquery`.
* Construct optimized full-text SQL queries with section weighting.
* Exclude source entities by ID (`exclude_work_id`, `exclude_opportunity_id`).
* Apply supported database-level metadata filters in exact parity with VectorRepository.
* Enforce safe candidate limits.
* Return ordered `LexicalSearchResult` objects containing 1-based ranks for RRF fusion.

Boundary
--------
This layer ONLY performs lexical candidate retrieval. It does NOT perform recommendation
ranking, topic weighting, personalization, or LLM reranking.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Sequence
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.opportunity import OpportunityModel
from app.models.research_knowledge import ResearchWorkModel
from app.repositories.vector_repository import (
    DEFAULT_CANDIDATE_LIMIT,
    MAX_CANDIDATE_LIMIT,
    sanitize_candidate_limit,
)

logger = logging.getLogger(__name__)

# Default search configuration language
DEFAULT_FTS_CONFIG: str = "english"


# ── Search Result Data Structure ──────────────────────────────────────────────


@dataclass(frozen=True)
class LexicalSearchResult:
    """
    Lightweight, immutable container for lexical retrieval candidates.

    Attributes
    ----------
    entity_id:
        Primary key UUID of the matched entity.
    lexical_score:
        Raw PostgreSQL ts_rank_cd relevance score.
    rank:
        1-based rank position in the lexical search result list (1 = highest score).
    entity_type:
        Type of entity: "research_work" or "opportunity".
    entity:
        Optional loaded ORM model instance if fetched during query execution.
    """

    entity_id: uuid.UUID
    lexical_score: float
    rank: int
    entity_type: str
    entity: Any | None = None


# ── Document Vector Builders ──────────────────────────────────────────────────


def build_research_work_tsvector(config: str = DEFAULT_FTS_CONFIG):
    """
    Construct a weighted tsvector expression for ResearchWorkModel.

    Weights:
      A: title
      B: abstract
      C: work_type, language
    """
    title_vec = func.setweight(
        func.to_tsvector(config, func.coalesce(ResearchWorkModel.title, "")), "A"
    )
    abstract_vec = func.setweight(
        func.to_tsvector(config, func.coalesce(ResearchWorkModel.abstract, "")), "B"
    )
    meta_vec = func.setweight(
        func.to_tsvector(
            config,
            func.coalesce(ResearchWorkModel.work_type, "")
            + " "
            + func.coalesce(ResearchWorkModel.language, ""),
        ),
        "C",
    )
    return title_vec.op("||")(abstract_vec).op("||")(meta_vec)


def build_opportunity_tsvector(config: str = DEFAULT_FTS_CONFIG):
    """
    Construct a weighted tsvector expression for OpportunityModel.

    Weights:
      A: title
      B: summary, description
      C: publisher, organizer, series_name, location
    """
    title_vec = func.setweight(
        func.to_tsvector(config, func.coalesce(OpportunityModel.title, "")), "A"
    )
    body_vec = func.setweight(
        func.to_tsvector(
            config,
            func.coalesce(OpportunityModel.summary, "")
            + " "
            + func.coalesce(OpportunityModel.description, ""),
        ),
        "B",
    )
    meta_vec = func.setweight(
        func.to_tsvector(
            config,
            func.coalesce(OpportunityModel.publisher, "")
            + " "
            + func.coalesce(OpportunityModel.organizer, "")
            + " "
            + func.coalesce(OpportunityModel.series_name, "")
            + " "
            + func.coalesce(OpportunityModel.location, ""),
        ),
        "C",
    )
    return title_vec.op("||")(body_vec).op("||")(meta_vec)


# ── Lexical Repository ────────────────────────────────────────────────────────


class LexicalRepository:
    """
    PostgreSQL full-text lexical search repository.

    Provides database-level lexical candidate searches for Research Works and
    Opportunities using Cover Density ranking (`ts_rank_cd`) over indexed GIN tsvectors.
    """

    def __init__(
        self,
        default_limit: int = DEFAULT_CANDIDATE_LIMIT,
        max_limit: int = MAX_CANDIDATE_LIMIT,
        fts_config: str = DEFAULT_FTS_CONFIG,
        use_stored_tsvector: bool = True,
    ) -> None:
        self.default_limit = default_limit
        self.max_limit = max_limit
        self.fts_config = fts_config
        self.use_stored_tsvector = use_stored_tsvector

    def _get_research_work_tsvector(self):
        """Return the tsvector expression: stored fts_vector column when enabled, or dynamic expression."""
        if self.use_stored_tsvector and hasattr(ResearchWorkModel, "fts_vector"):
            return ResearchWorkModel.fts_vector
        return build_research_work_tsvector(self.fts_config)

    def _get_opportunity_tsvector(self):
        """Return the tsvector expression: stored fts_vector column when enabled, or dynamic expression."""
        if self.use_stored_tsvector and hasattr(OpportunityModel, "fts_vector"):
            return OpportunityModel.fts_vector
        return build_opportunity_tsvector(self.fts_config)

    # ── Research Works Retrieval ──────────────────────────────────────────────

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
    ) -> list[LexicalSearchResult]:
        """
        Perform full-text lexical search over research_works.

        Parameters
        ----------
        session:
            Active SQLAlchemy Session.
        query:
            Natural language search query string.
        limit:
            Maximum number of candidates (default 20, capped at max_limit).
        exclude_work_id:
            Optional work UUID to exclude from results.
        publication_year:
            Filter by exact publication year.
        min_year:
            Filter publication_year >= min_year.
        max_year:
            Filter publication_year <= max_year.
        work_type:
            Filter by work type (article, preprint, ...).
        language:
            Filter by ISO language code.
        primary_source_id:
            Filter by publication venue (research_sources.id).
        is_oa:
            Filter by open-access status.
        min_citations:
            Filter cited_by_count >= min_citations.

        Returns
        -------
        list[LexicalSearchResult]
            Ranked candidate results ordered by lexical score descending.
        """
        if not query or not query.strip():
            return []

        safe_query = query.strip()
        safe_limit = sanitize_candidate_limit(limit, self.default_limit, self.max_limit)

        tsvector = self._get_research_work_tsvector()
        tsquery = func.websearch_to_tsquery(self.fts_config, safe_query)
        score_expr = func.ts_rank_cd(tsvector, tsquery)

        stmt = (
            select(ResearchWorkModel, score_expr.label("lexical_score"))
            .where(tsvector.op("@@")(tsquery))
        )

        # SQL-level filters
        if exclude_work_id is not None:
            stmt = stmt.where(ResearchWorkModel.id != exclude_work_id)

        if publication_year is not None:
            stmt = stmt.where(ResearchWorkModel.publication_year == publication_year)
        if min_year is not None:
            stmt = stmt.where(ResearchWorkModel.publication_year >= min_year)
        if max_year is not None:
            stmt = stmt.where(ResearchWorkModel.publication_year <= max_year)
        if work_type is not None:
            stmt = stmt.where(ResearchWorkModel.work_type == work_type.lower().strip())
        if language is not None:
            stmt = stmt.where(ResearchWorkModel.language == language.lower().strip())
        if primary_source_id is not None:
            stmt = stmt.where(ResearchWorkModel.primary_source_id == primary_source_id)
        if is_oa is not None:
            stmt = stmt.where(ResearchWorkModel.is_oa == is_oa)
        if min_citations is not None:
            stmt = stmt.where(ResearchWorkModel.cited_by_count >= min_citations)

        # Order by score descending
        stmt = stmt.order_by(score_expr.desc()).limit(safe_limit)

        rows = session.execute(stmt).all()

        results: list[LexicalSearchResult] = []
        for idx, (work, score) in enumerate(rows, start=1):
            results.append(
                LexicalSearchResult(
                    entity_id=work.id,
                    lexical_score=float(score),
                    rank=idx,
                    entity_type="research_work",
                    entity=work,
                )
            )

        return results

    # ── Opportunities Retrieval ───────────────────────────────────────────────

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
    ) -> list[LexicalSearchResult]:
        """
        Perform full-text lexical search over opportunities.

        Parameters
        ----------
        session:
            Active SQLAlchemy Session.
        query:
            Natural language search query string.
        limit:
            Maximum number of candidates (default 20, capped at max_limit).
        exclude_opportunity_id:
            Optional opportunity UUID to exclude from results.
        opportunity_type:
            Filter by opportunity type (CONFERENCE, JOURNAL, ...).
        status:
            Filter by status string or sequence of statuses.
        delivery_mode:
            Filter by delivery mode (ONLINE, OFFLINE, HYBRID).
        source_id:
            Filter by origin source ID in sources table.
        upcoming_only:
            If True, only return opportunities with submission_deadline >= now.
        submission_deadline_after:
            Filter submission_deadline >= specified datetime.

        Returns
        -------
        list[LexicalSearchResult]
            Ranked candidate results ordered by lexical score descending.
        """
        if not query or not query.strip():
            return []

        safe_query = query.strip()
        safe_limit = sanitize_candidate_limit(limit, self.default_limit, self.max_limit)

        tsvector = self._get_opportunity_tsvector()
        tsquery = func.websearch_to_tsquery(self.fts_config, safe_query)
        score_expr = func.ts_rank_cd(tsvector, tsquery)

        stmt = (
            select(OpportunityModel, score_expr.label("lexical_score"))
            .where(tsvector.op("@@")(tsquery))
        )

        # SQL-level filters
        if exclude_opportunity_id is not None:
            stmt = stmt.where(OpportunityModel.id != exclude_opportunity_id)

        if opportunity_type is not None:
            stmt = stmt.where(
                OpportunityModel.opportunity_type == opportunity_type.upper().strip()
            )

        if status is not None:
            if isinstance(status, str):
                stmt = stmt.where(OpportunityModel.status == status.upper().strip())
            else:
                stmt = stmt.where(
                    OpportunityModel.status.in_([s.upper().strip() for s in status])
                )

        if delivery_mode is not None:
            stmt = stmt.where(
                OpportunityModel.delivery_mode == delivery_mode.upper().strip()
            )

        if source_id is not None:
            stmt = stmt.where(OpportunityModel.source_id == source_id)

        if upcoming_only:
            now = datetime.now(tz=timezone.utc)
            stmt = stmt.where(OpportunityModel.submission_deadline >= now)
        elif submission_deadline_after is not None:
            stmt = stmt.where(
                OpportunityModel.submission_deadline >= submission_deadline_after
            )

        # Order by score descending
        stmt = stmt.order_by(score_expr.desc()).limit(safe_limit)

        rows = session.execute(stmt).all()

        results: list[LexicalSearchResult] = []
        for idx, (opp, score) in enumerate(rows, start=1):
            results.append(
                LexicalSearchResult(
                    entity_id=opp.id,
                    lexical_score=float(score),
                    rank=idx,
                    entity_type="opportunity",
                    entity=opp,
                )
            )

        return results


# Module-level default repository instance
lexical_repository = LexicalRepository()
