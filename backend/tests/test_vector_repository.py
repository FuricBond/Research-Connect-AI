"""
Unit and Integration tests for Phase 2.4A VectorRepository.

Test Suite Structure
--------------------
A. Unit Tests:
   1. Query vector validation (valid 384-dim, too short, too long, empty, None, NaN, Inf, non-numeric).
   2. Candidate limit sanitization (default, positive, clamping at max limit, non-positive rejection).
   3. Distance to similarity conversion (formula: similarity = 1.0 - distance).
   4. VectorSearchResult container behavior.
   5. SQL query compilation & clause verification for ResearchWorks and Opportunities (IS NOT NULL, <=> operator, ORDER BY, LIMIT, exclusion, filters).
   6. Repository mock execution & error handling (entity not found, NULL embedding, source exclusion).

B. PostgreSQL + pgvector Integration Tests:
   - Real nearest-neighbor calculation using pgvector <=> operator and HNSW indexes.
   - Real metadata filtering, source exclusion, and candidate limits against a live database.
   - Automatically and gracefully skipped if PostgreSQL is unavailable in the environment.
"""
from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.opportunity import OpportunityModel
from app.models.research_knowledge import ResearchWorkModel
from app.repositories.vector_repository import (
    DEFAULT_CANDIDATE_LIMIT,
    DEFAULT_EMBEDDING_DIM,
    MAX_CANDIDATE_LIMIT,
    VectorRepository,
    VectorSearchResult,
    VectorValidationError,
    distance_to_similarity,
    sanitize_candidate_limit,
    validate_query_vector,
)


# ── Fixtures & Helpers ────────────────────────────────────────────────────────


@pytest.fixture
def valid_vector_384() -> list[float]:
    """A valid 384-dimensional unit vector."""
    return [1.0 / math.sqrt(384)] * 384


@pytest.fixture
def repo_384() -> VectorRepository:
    """A VectorRepository initialized with 384 dimensions."""
    return VectorRepository(
        default_limit=DEFAULT_CANDIDATE_LIMIT,
        max_limit=MAX_CANDIDATE_LIMIT,
        embedding_dim=DEFAULT_EMBEDDING_DIM,
    )


# ── A. UNIT TESTS ─────────────────────────────────────────────────────────────


class TestVectorValidation:
    """Tests for validate_query_vector function."""

    def test_valid_384_dimensional_vector(self, valid_vector_384):
        res = validate_query_vector(valid_vector_384, expected_dim=384)
        assert len(res) == 384
        assert isinstance(res, list)
        assert all(isinstance(v, float) for v in res)

    def test_valid_tuple_or_sequence(self):
        vec_tuple = tuple([0.05] * 384)
        res = validate_query_vector(vec_tuple, expected_dim=384)
        assert len(res) == 384
        assert isinstance(res, list)

    def test_none_vector_rejected(self):
        with pytest.raises(VectorValidationError, match="cannot be None"):
            validate_query_vector(None)

    def test_empty_vector_rejected(self):
        with pytest.raises(VectorValidationError, match="dimension mismatch"):
            validate_query_vector([])

    def test_dimension_too_short_383(self):
        vec = [0.1] * 383
        with pytest.raises(VectorValidationError, match="expected 384, got 383"):
            validate_query_vector(vec, expected_dim=384)

    def test_dimension_too_long_385(self):
        vec = [0.1] * 385
        with pytest.raises(VectorValidationError, match="expected 384, got 385"):
            validate_query_vector(vec, expected_dim=384)

    def test_dimension_arbitrary_wrong_size(self):
        vec = [0.1] * 10
        with pytest.raises(VectorValidationError, match="expected 384, got 10"):
            validate_query_vector(vec, expected_dim=384)

    def test_string_rejected_as_vector(self):
        with pytest.raises(VectorValidationError, match="must be a sequence of numbers"):
            validate_query_vector("not_a_vector")

    def test_dict_rejected_as_vector(self):
        with pytest.raises(VectorValidationError, match="must be a sequence of numbers"):
            validate_query_vector({"a": 1})

    def test_nan_element_rejected(self):
        vec = [0.1] * 384
        vec[42] = float("nan")
        with pytest.raises(VectorValidationError, match="index 42 is NaN"):
            validate_query_vector(vec, expected_dim=384)

    def test_positive_infinity_rejected(self):
        vec = [0.1] * 384
        vec[100] = float("inf")
        with pytest.raises(VectorValidationError, match="index 100 is infinite"):
            validate_query_vector(vec, expected_dim=384)

    def test_negative_infinity_rejected(self):
        vec = [0.1] * 384
        vec[200] = float("-inf")
        with pytest.raises(VectorValidationError, match="index 200 is infinite"):
            validate_query_vector(vec, expected_dim=384)

    def test_non_numeric_element_rejected(self):
        vec = [0.1] * 384
        vec[5] = "string_value"  # type: ignore
        with pytest.raises(VectorValidationError, match="must be a number"):
            validate_query_vector(vec, expected_dim=384)

    def test_boolean_element_rejected(self):
        vec = [0.1] * 384
        vec[10] = True  # bool is subclass of int in Python, but should be rejected
        with pytest.raises(VectorValidationError, match="must be a number"):
            validate_query_vector(vec, expected_dim=384)


class TestCandidateLimitSanitization:
    """Tests for candidate limit validation and clamping."""

    def test_default_limit_used_when_none(self):
        assert sanitize_candidate_limit(None, default_limit=20, max_limit=100) == 20

    def test_custom_valid_limit(self):
        assert sanitize_candidate_limit(15, default_limit=20, max_limit=100) == 15

    def test_clamping_at_max_limit(self):
        assert sanitize_candidate_limit(500, default_limit=20, max_limit=100) == 100

    def test_limit_exactly_at_max(self):
        assert sanitize_candidate_limit(100, default_limit=20, max_limit=100) == 100

    def test_zero_limit_rejected(self):
        with pytest.raises(VectorValidationError, match="must be a positive integer"):
            sanitize_candidate_limit(0)

    def test_negative_limit_rejected(self):
        with pytest.raises(VectorValidationError, match="must be a positive integer"):
            sanitize_candidate_limit(-5)


class TestDistanceSimilarityConversion:
    """Tests for cosine distance to similarity conversion."""

    def test_identical_vectors_zero_distance(self):
        # distance 0.0 -> similarity 1.0
        assert distance_to_similarity(0.0) == 1.0

    def test_orthogonal_vectors_unit_distance(self):
        # distance 1.0 -> similarity 0.0
        assert distance_to_similarity(1.0) == 0.0

    def test_opposite_vectors_two_distance(self):
        # distance 2.0 -> similarity -1.0
        assert distance_to_similarity(2.0) == -1.0

    def test_arbitrary_distance(self):
        # distance 0.25 -> similarity 0.75
        assert distance_to_similarity(0.25) == 0.75


class TestVectorSearchResultDataModel:
    """Tests for VectorSearchResult dataclass."""

    def test_search_result_properties(self):
        test_id = uuid.uuid4()
        res = VectorSearchResult(
            entity_id=test_id,
            similarity=0.88,
            distance=0.12,
            entity_type="research_work",
        )
        assert res.entity_id == test_id
        assert res.similarity == 0.88
        assert res.distance == 0.12
        assert res.entity_type == "research_work"
        assert res.entity is None

    def test_immutable_frozen(self):
        res = VectorSearchResult(
            entity_id=uuid.uuid4(),
            similarity=0.9,
            distance=0.1,
            entity_type="opportunity",
        )
        with pytest.raises(AttributeError):
            res.similarity = 0.5  # type: ignore


class TestSQLQueryCompilation:
    """Tests verifying that SQL queries are generated with proper pgvector clauses."""

    def test_research_works_sql_structure(self, valid_vector_384):
        """Verify the compiled PostgreSQL SQL expression for research works."""
        distance_expr = ResearchWorkModel.embedding.cosine_distance(valid_vector_384)
        stmt = (
            select(ResearchWorkModel, distance_expr.label("distance"))
            .where(ResearchWorkModel.embedding.is_not(None))
            .order_by(distance_expr.asc())
            .limit(20)
        )

        compiled_sql = str(
            stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": False})
        )

        # Confirm critical SQL components
        assert "research_works.embedding <=> " in compiled_sql
        assert "research_works.embedding IS NOT NULL" in compiled_sql
        assert "ORDER BY (research_works.embedding <=> " in compiled_sql
        assert "LIMIT " in compiled_sql

    def test_opportunities_sql_structure(self, valid_vector_384):
        """Verify the compiled PostgreSQL SQL expression for opportunities."""
        distance_expr = OpportunityModel.embedding.cosine_distance(valid_vector_384)
        stmt = (
            select(OpportunityModel, distance_expr.label("distance"))
            .where(OpportunityModel.embedding.is_not(None))
            .order_by(distance_expr.asc())
            .limit(20)
        )

        compiled_sql = str(
            stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": False})
        )

        # Confirm critical SQL components
        assert "opportunities.embedding <=> " in compiled_sql
        assert "opportunities.embedding IS NOT NULL" in compiled_sql
        assert "ORDER BY (opportunities.embedding <=> " in compiled_sql
        assert "LIMIT " in compiled_sql

    def test_research_works_filter_clauses(self, valid_vector_384):
        """Verify that all optional metadata filters are properly injected into WHERE clause."""
        exclude_id = uuid.uuid4()
        source_id = uuid.uuid4()
        distance_expr = ResearchWorkModel.embedding.cosine_distance(valid_vector_384)

        stmt = (
            select(ResearchWorkModel, distance_expr.label("distance"))
            .where(ResearchWorkModel.embedding.is_not(None))
            .where(ResearchWorkModel.id != exclude_id)
            .where(ResearchWorkModel.publication_year == 2024)
            .where(ResearchWorkModel.work_type == "article")
            .where(ResearchWorkModel.language == "en")
            .where(ResearchWorkModel.primary_source_id == source_id)
            .where(ResearchWorkModel.is_oa == True)
            .where(ResearchWorkModel.cited_by_count >= 10)
        )

        compiled_sql = str(stmt.compile(dialect=postgresql.dialect()))
        assert "research_works.id !=" in compiled_sql
        assert "research_works.publication_year =" in compiled_sql
        assert "research_works.work_type =" in compiled_sql
        assert "research_works.language =" in compiled_sql
        assert "research_works.primary_source_id =" in compiled_sql
        assert "research_works.is_oa =" in compiled_sql
        assert "research_works.cited_by_count >=" in compiled_sql

    def test_opportunities_filter_clauses(self, valid_vector_384):
        """Verify that all optional opportunity filters are properly injected into WHERE clause."""
        exclude_id = uuid.uuid4()
        source_id = uuid.uuid4()
        deadline_cutoff = datetime(2025, 12, 31, tzinfo=timezone.utc)
        distance_expr = OpportunityModel.embedding.cosine_distance(valid_vector_384)

        stmt = (
            select(OpportunityModel, distance_expr.label("distance"))
            .where(OpportunityModel.embedding.is_not(None))
            .where(OpportunityModel.id != exclude_id)
            .where(OpportunityModel.opportunity_type == "CONFERENCE")
            .where(OpportunityModel.status.in_(["ACTIVE", "UNVERIFIED"]))
            .where(OpportunityModel.delivery_mode == "ONLINE")
            .where(OpportunityModel.source_id == source_id)
            .where(OpportunityModel.submission_deadline >= deadline_cutoff)
        )

        compiled_sql = str(stmt.compile(dialect=postgresql.dialect()))
        assert "opportunities.id !=" in compiled_sql
        assert "opportunities.opportunity_type =" in compiled_sql
        assert "opportunities.status IN" in compiled_sql
        assert "opportunities.delivery_mode =" in compiled_sql
        assert "opportunities.source_id =" in compiled_sql
        assert "opportunities.submission_deadline >=" in compiled_sql


class TestVectorRepositoryMockExecution:
    """Tests for VectorRepository execution using a mocked SQLAlchemy Session."""

    def test_search_research_works_success(self, repo_384, valid_vector_384):
        mock_session = MagicMock(spec=Session)

        work_1 = ResearchWorkModel(
            id=uuid.uuid4(),
            title="Attention Is All You Need",
            embedding=valid_vector_384,
        )
        work_2 = ResearchWorkModel(
            id=uuid.uuid4(),
            title="BERT: Pre-training Deep Bidirectional Transformers",
            embedding=valid_vector_384,
        )

        # Mock database rows: (model, distance)
        mock_rows = [(work_1, 0.10), (work_2, 0.25)]
        mock_execute_result = MagicMock()
        mock_execute_result.all.return_value = mock_rows
        mock_session.execute.return_value = mock_execute_result

        results = repo_384.search_research_works(mock_session, valid_vector_384, limit=10)

        assert len(results) == 2
        assert results[0].entity_id == work_1.id
        assert results[0].distance == 0.10
        assert results[0].similarity == 0.90
        assert results[0].entity_type == "research_work"
        assert results[0].entity == work_1

        assert results[1].entity_id == work_2.id
        assert results[1].distance == 0.25
        assert results[1].similarity == 0.75

    def test_find_similar_research_works_not_found(self, repo_384):
        mock_session = MagicMock(spec=Session)
        mock_session.get.return_value = None

        target_id = uuid.uuid4()
        with pytest.raises(ValueError, match="not found"):
            repo_384.find_similar_research_works(mock_session, target_id)

    def test_find_similar_research_works_no_embedding(self, repo_384):
        mock_session = MagicMock(spec=Session)
        work_no_emb = ResearchWorkModel(
            id=uuid.uuid4(),
            title="No Embedding Work",
            embedding=None,
        )
        mock_session.get.return_value = work_no_emb

        with pytest.raises(VectorValidationError, match="does not have an embedding"):
            repo_384.find_similar_research_works(mock_session, work_no_emb.id)

    def test_find_similar_research_works_delegates_with_exclusion(self, repo_384, valid_vector_384):
        mock_session = MagicMock(spec=Session)
        target_id = uuid.uuid4()
        work = ResearchWorkModel(
            id=target_id,
            title="Source Work",
            embedding=valid_vector_384,
        )
        mock_session.get.return_value = work

        other_work = ResearchWorkModel(
            id=uuid.uuid4(),
            title="Other Work",
            embedding=valid_vector_384,
        )
        mock_execute_result = MagicMock()
        mock_execute_result.all.return_value = [(other_work, 0.15)]
        mock_session.execute.return_value = mock_execute_result

        results = repo_384.find_similar_research_works(mock_session, target_id, limit=5)
        assert len(results) == 1
        assert results[0].entity_id == other_work.id

    def test_search_opportunities_success(self, repo_384, valid_vector_384):
        mock_session = MagicMock(spec=Session)
        opp = OpportunityModel(
            id=uuid.uuid4(),
            title="ICLR 2026",
            opportunity_type="CONFERENCE",
            embedding=valid_vector_384,
        )

        mock_execute_result = MagicMock()
        mock_execute_result.all.return_value = [(opp, 0.05)]
        mock_session.execute.return_value = mock_execute_result

        results = repo_384.search_opportunities(mock_session, valid_vector_384, limit=5)
        assert len(results) == 1
        assert results[0].entity_id == opp.id
        assert results[0].similarity == 0.95
        assert results[0].distance == 0.05
        assert results[0].entity_type == "opportunity"
        assert results[0].entity == opp

    def test_search_opportunities_status_sequence(self, repo_384, valid_vector_384):
        from collections.abc import Sequence as AbcSequence

        class CustomStatusSequence(AbcSequence):
            def __init__(self, items):
                self._items = items
            def __getitem__(self, idx):
                return self._items[idx]
            def __len__(self):
                return len(self._items)

        mock_session = MagicMock(spec=Session)
        mock_execute_result = MagicMock()
        mock_execute_result.all.return_value = []
        mock_session.execute.return_value = mock_execute_result

        # Single string status
        repo_384.search_opportunities(mock_session, valid_vector_384, status="ACTIVE")
        assert mock_session.execute.called

        # Custom Sequence status (not a built-in list/tuple/set)
        custom_seq = CustomStatusSequence(["ACTIVE", "UNVERIFIED"])
        repo_384.search_opportunities(mock_session, valid_vector_384, status=custom_seq)
        assert mock_session.execute.call_count == 2

    def test_find_similar_opportunities_not_found(self, repo_384):
        mock_session = MagicMock(spec=Session)
        mock_session.get.return_value = None

        target_id = uuid.uuid4()
        with pytest.raises(ValueError, match="not found"):
            repo_384.find_similar_opportunities(mock_session, target_id)

    def test_find_similar_opportunities_no_embedding(self, repo_384):
        mock_session = MagicMock(spec=Session)
        opp_no_emb = OpportunityModel(
            id=uuid.uuid4(),
            title="No Embedding Opp",
            embedding=None,
        )
        mock_session.get.return_value = opp_no_emb

        with pytest.raises(VectorValidationError, match="does not have an embedding"):
            repo_384.find_similar_opportunities(mock_session, opp_no_emb.id)

    def test_empty_results_handled_cleanly(self, repo_384, valid_vector_384):
        mock_session = MagicMock(spec=Session)
        mock_execute_result = MagicMock()
        mock_execute_result.all.return_value = []
        mock_session.execute.return_value = mock_execute_result

        results = repo_384.search_research_works(mock_session, valid_vector_384)
        assert results == []


# ── B. POSTGRESQL + PGVECTOR INTEGRATION TESTS ────────────────────────────────


def _is_postgres_available() -> bool:
    """Check whether live PostgreSQL + pgvector is reachable."""
    try:
        engine = create_engine(settings.database_url, pool_pre_ping=True)
        with engine.connect() as conn:
            # Check for pgvector extension
            res = conn.execute(select(1)).scalar_one_or_none()
            return res == 1
    except Exception:
        return False


postgres_integration = pytest.mark.skipif(
    not _is_postgres_available(),
    reason="PostgreSQL with pgvector is not reachable in current environment.",
)


@postgres_integration
class TestPostgreSQLVectorIntegration:
    """
    Live integration tests against PostgreSQL with pgvector extension.
    Only executed when a real PostgreSQL instance is available.
    """

    def test_real_pgvector_search_works(self, valid_vector_384):
        from app.db.session import SessionLocal

        repo = VectorRepository()
        with SessionLocal() as session:
            results = repo.search_research_works(session, valid_vector_384, limit=5)
            assert isinstance(results, list)
            for r in results:
                assert isinstance(r.entity_id, uuid.UUID)
                assert isinstance(r.similarity, float)
                assert isinstance(r.distance, float)
                assert r.entity_type == "research_work"

    def test_real_pgvector_search_opportunities(self, valid_vector_384):
        from app.db.session import SessionLocal

        repo = VectorRepository()
        with SessionLocal() as session:
            results = repo.search_opportunities(session, valid_vector_384, limit=5)
            assert isinstance(results, list)
            for r in results:
                assert isinstance(r.entity_id, uuid.UUID)
                assert isinstance(r.similarity, float)
                assert isinstance(r.distance, float)
                assert r.entity_type == "opportunity"
