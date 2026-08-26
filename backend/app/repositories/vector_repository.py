"""
Vector Retrieval Repository for Phase 2.4A.

Responsible for database-level semantic nearest-neighbor retrieval over:
  1. research_works (ResearchWorkModel)
  2. opportunities (OpportunityModel)

Consumes the 384-dimensional L2-normalized embeddings generated in Phase 2.3B
via PostgreSQL + pgvector (using the HNSW cosine-distance index).

Responsibilities
----------------
* Validate incoming query vectors (dimension, NaN, Inf, numeric types).
* Construct optimized SQL queries using the pgvector `<=>` cosine distance operator.
* Exclude NULL embeddings.
* Exclude source entities by ID.
* Apply supported database-level metadata filters.
* Enforce safe candidate limits (default=20, max=100).
* Expose cosine similarity (1.0 - distance) rather than raw distance.

Boundary
--------
This layer ONLY performs candidate retrieval. It does NOT perform recommendation
ranking, hybrid search scoring, topic weighting, or LLM reranking.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Sequence
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.opportunity import OpportunityModel
from app.models.research_knowledge import ResearchWorkModel

logger = logging.getLogger(__name__)

# ── Constants & Limits ────────────────────────────────────────────────────────

DEFAULT_CANDIDATE_LIMIT: int = 20
MAX_CANDIDATE_LIMIT: int = 100
DEFAULT_EMBEDDING_DIM: int = getattr(settings, "embedding_dim", 384)


# ── Exceptions ────────────────────────────────────────────────────────────────


class VectorValidationError(ValueError):
    """Raised when an input query embedding vector fails validation."""


# ── Search Result Data Structure ──────────────────────────────────────────────


@dataclass(frozen=True)
class VectorSearchResult:
    """
    Lightweight, immutable container for vector retrieval candidates.

    Attributes
    ----------
    entity_id:
        Primary key UUID of the matched entity.
    similarity:
        Cosine similarity score in range [-1.0, 1.0], typically [0.0, 1.0] for
        L2-normalized embeddings, where 1.0 indicates identity.
    distance:
        Raw pgvector cosine distance (1.0 - similarity).
    entity_type:
        Type of entity: "research_work" or "opportunity".
    entity:
        Optional loaded ORM model instance if fetched during query execution.
    """

    entity_id: uuid.UUID
    similarity: float
    distance: float
    entity_type: str
    entity: Any | None = None


# ── Validation Functions ──────────────────────────────────────────────────────


def validate_query_vector(
    vector: Sequence[float] | Any,
    expected_dim: int = DEFAULT_EMBEDDING_DIM,
) -> list[float]:
    """
    Validate and return a normalized float list for a query embedding.

    Parameters
    ----------
    vector:
        The input query embedding vector (sequence of numbers).
    expected_dim:
        Expected vector dimensionality (defaults to 384 from configuration).

    Returns
    -------
    list[float]
        A clean Python list of floats.

    Raises
    ------
    VectorValidationError:
        If vector is None, not a sequence, wrong dimension, or contains NaN/Inf/non-numeric.
    """
    if vector is None:
        raise VectorValidationError("Query vector cannot be None.")

    if isinstance(vector, (str, bytes, bytearray, dict)):
        raise VectorValidationError(
            f"Query vector must be a sequence of numbers, got {type(vector).__name__}."
        )

    try:
        dim = len(vector)
    except TypeError as exc:
        raise VectorValidationError(
            f"Query vector must be a sized sequence, got {type(vector).__name__}."
        ) from exc

    if dim != expected_dim:
        raise VectorValidationError(
            f"Query vector dimension mismatch: expected {expected_dim}, got {dim}."
        )

    validated: list[float] = []
    for idx, val in enumerate(vector):
        if not isinstance(val, (int, float)) or isinstance(val, bool):
            raise VectorValidationError(
                f"Query vector element at index {idx} must be a number, got {type(val).__name__}."
            )
        f_val = float(val)
        if math.isnan(f_val):
            raise VectorValidationError(
                f"Query vector element at index {idx} is NaN."
            )
        if math.isinf(f_val):
            raise VectorValidationError(
                f"Query vector element at index {idx} is infinite."
            )
        validated.append(f_val)

    return validated


def sanitize_candidate_limit(
    limit: int | None,
    default_limit: int = DEFAULT_CANDIDATE_LIMIT,
    max_limit: int = MAX_CANDIDATE_LIMIT,
) -> int:
    """
    Validate and clamp the candidate limit within safe boundaries.

    Parameters
    ----------
    limit:
        Requested limit or None for default.
    default_limit:
        Default limit if None is provided.
    max_limit:
        Maximum allowed candidate limit.

    Returns
    -------
    int
        Clamped limit in range [1, max_limit].
    """
    if limit is None:
        return default_limit
    if limit <= 0:
        raise VectorValidationError(
            f"Candidate limit must be a positive integer, got {limit}."
        )
    return min(limit, max_limit)


def distance_to_similarity(distance: float) -> float:
    """Convert pgvector cosine distance to cosine similarity (1.0 - distance)."""
    return round(1.0 - float(distance), 6)


# ── Vector Repository ─────────────────────────────────────────────────────────


class VectorRepository:
    """
    PostgreSQL + pgvector vector retrieval repository.

    Provides database-level nearest-neighbor candidate searches for
    Research Works and Opportunities.
    """

    def __init__(
        self,
        default_limit: int = DEFAULT_CANDIDATE_LIMIT,
        max_limit: int = MAX_CANDIDATE_LIMIT,
        embedding_dim: int = DEFAULT_EMBEDDING_DIM,
    ) -> None:
        self.default_limit = default_limit
        self.max_limit = max_limit
        self.embedding_dim = embedding_dim

    # ── Research Works Retrieval ──────────────────────────────────────────────

    def search_research_works(
        self,
        session: Session,
        query_embedding: Sequence[float],
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
    ) -> list[VectorSearchResult]:
        """
        Perform semantic nearest-neighbor search over research_works.

        Parameters
        ----------
        session:
            Active SQLAlchemy Session.
        query_embedding:
            384-dimensional query vector.
        limit:
            Maximum number of candidates (default 20, capped at max_limit).
        exclude_work_id:
            Optional work UUID to exclude from results (source entity exclusion).
        publication_year:
            Filter by exact publication year.
        min_year:
            Filter publication_year >= min_year.
        max_year:
            Filter publication_year <= max_year.
        work_type:
            Filter by work type (article, preprint, book-chapter, ...).
        language:
            Filter by ISO language code (e.g. 'en', 'de').
        primary_source_id:
            Filter by publication venue (research_sources.id).
        is_oa:
            Filter by open-access status.
        min_citations:
            Filter cited_by_count >= min_citations.

        Returns
        -------
        list[VectorSearchResult]
            Candidate results ordered by cosine similarity descending.
        """
        valid_vector = validate_query_vector(query_embedding, self.embedding_dim)
        safe_limit = sanitize_candidate_limit(limit, self.default_limit, self.max_limit)

        # Distance expression via pgvector cosine distance operator <=>
        distance_expr = ResearchWorkModel.embedding.cosine_distance(valid_vector)

        stmt = (
            select(ResearchWorkModel, distance_expr.label("distance"))
            .where(ResearchWorkModel.embedding.is_not(None))
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

        # Order by nearest neighbor (distance ascending <=> similarity descending)
        stmt = stmt.order_by(distance_expr.asc()).limit(safe_limit)

        rows = session.execute(stmt).all()

        results: list[VectorSearchResult] = []
        for work, distance in rows:
            dist_val = float(distance)
            sim_val = distance_to_similarity(dist_val)
            results.append(
                VectorSearchResult(
                    entity_id=work.id,
                    similarity=sim_val,
                    distance=dist_val,
                    entity_type="research_work",
                    entity=work,
                )
            )

        return results

    def find_similar_research_works(
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
    ) -> list[VectorSearchResult]:
        """
        Find research works similar to an existing research work.

        Automatically retrieves the source work's embedding, excludes the source
        work from the candidate set, and executes vector retrieval.
        """
        work = session.get(ResearchWorkModel, work_id)
        if work is None:
            raise ValueError(f"ResearchWork with ID {work_id} not found.")

        if work.embedding is None:
            raise VectorValidationError(
                f"ResearchWork with ID {work_id} does not have an embedding."
            )

        return self.search_research_works(
            session=session,
            query_embedding=work.embedding,
            limit=limit,
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

    # ── Opportunities Retrieval ───────────────────────────────────────────────

    def search_opportunities(
        self,
        session: Session,
        query_embedding: Sequence[float],
        *,
        limit: int | None = None,
        exclude_opportunity_id: uuid.UUID | None = None,
        opportunity_type: str | None = None,
        status: str | Sequence[str] | None = None,
        delivery_mode: str | None = None,
        source_id: uuid.UUID | None = None,
        upcoming_only: bool = False,
        submission_deadline_after: datetime | None = None,
    ) -> list[VectorSearchResult]:
        """
        Perform semantic nearest-neighbor search over opportunities.

        Parameters
        ----------
        session:
            Active SQLAlchemy Session.
        query_embedding:
            384-dimensional query vector.
        limit:
            Maximum number of candidates (default 20, capped at max_limit).
        exclude_opportunity_id:
            Optional opportunity UUID to exclude from results.
        opportunity_type:
            Filter by opportunity type (CONFERENCE, JOURNAL, WORKSHOP, ...).
        status:
            Filter by status string or sequence of statuses (ACTIVE, EXPIRED, ...).
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
        list[VectorSearchResult]
            Candidate results ordered by cosine similarity descending.
        """
        valid_vector = validate_query_vector(query_embedding, self.embedding_dim)
        safe_limit = sanitize_candidate_limit(limit, self.default_limit, self.max_limit)

        distance_expr = OpportunityModel.embedding.cosine_distance(valid_vector)

        stmt = (
            select(OpportunityModel, distance_expr.label("distance"))
            .where(OpportunityModel.embedding.is_not(None))
        )

        # SQL-level filters
        if exclude_opportunity_id is not None:
            stmt = stmt.where(OpportunityModel.id != exclude_opportunity_id)

        if opportunity_type is not None:
            stmt = stmt.where(
                OpportunityModel.opportunity_type == opportunity_type.upper().strip()
            )

        if status is not None:
            if isinstance(status, (list, tuple, set)):
                stmt = stmt.where(
                    OpportunityModel.status.in_([s.upper().strip() for s in status])
                )
            else:
                stmt = stmt.where(OpportunityModel.status == status.upper().strip())

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

        # Order by nearest neighbor
        stmt = stmt.order_by(distance_expr.asc()).limit(safe_limit)

        rows = session.execute(stmt).all()

        results: list[VectorSearchResult] = []
        for opp, distance in rows:
            dist_val = float(distance)
            sim_val = distance_to_similarity(dist_val)
            results.append(
                VectorSearchResult(
                    entity_id=opp.id,
                    similarity=sim_val,
                    distance=dist_val,
                    entity_type="opportunity",
                    entity=opp,
                )
            )

        return results

    def find_similar_opportunities(
        self,
        session: Session,
        opportunity_id: uuid.UUID,
        *,
        limit: int | None = None,
        opportunity_type: str | None = None,
        status: str | Sequence[str] | None = None,
        delivery_mode: str | None = None,
        source_id: uuid.UUID | None = None,
        upcoming_only: bool = False,
        submission_deadline_after: datetime | None = None,
    ) -> list[VectorSearchResult]:
        """
        Find opportunities similar to an existing opportunity.

        Automatically retrieves the source opportunity's embedding, excludes the
        source opportunity from candidates, and executes vector retrieval.
        """
        opp = session.get(OpportunityModel, opportunity_id)
        if opp is None:
            raise ValueError(f"Opportunity with ID {opportunity_id} not found.")

        if opp.embedding is None:
            raise VectorValidationError(
                f"Opportunity with ID {opportunity_id} does not have an embedding."
            )

        return self.search_opportunities(
            session=session,
            query_embedding=opp.embedding,
            limit=limit,
            exclude_opportunity_id=opportunity_id,
            opportunity_type=opportunity_type,
            status=status,
            delivery_mode=delivery_mode,
            source_id=source_id,
            upcoming_only=upcoming_only,
            submission_deadline_after=submission_deadline_after,
        )


# Module-level default repository instance for convenience
vector_repository = VectorRepository()
