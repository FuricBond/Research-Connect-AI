"""
Unit and Integration tests for HybridSearchService in app.services.hybrid_search_service.
"""
from __future__ import annotations

from unittest.mock import MagicMock
import uuid
import pytest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.opportunity import OpportunityModel
from app.models.research_knowledge import ResearchWorkModel
from app.repositories.lexical_repository import LexicalRepository, LexicalSearchResult
from app.repositories.vector_repository import VectorRepository, VectorSearchResult
from app.services.hybrid_search_service import (
    HybridSearchResult,
    HybridSearchService,
    calculate_candidate_limit,
)
from ml.embeddings.service import EmbeddingService


# ── A. UNIT TESTS ─────────────────────────────────────────────────────────────


class TestCandidateOversampling:
    """Tests for candidate oversampling limit calculation."""

    def test_default_multiplier(self):
        # 20 * 2.5 = 50
        assert calculate_candidate_limit(20, multiplier=2.5, min_candidates=20, max_limit=100) == 50

    def test_minimum_candidates_floor(self):
        # 5 * 2.5 = 12.5 -> 12, floored at min_candidates=20
        assert calculate_candidate_limit(5, multiplier=2.5, min_candidates=20, max_limit=100) == 20

    def test_maximum_candidates_ceiling(self):
        # 50 * 2.5 = 125, capped at max_limit=100
        assert calculate_candidate_limit(50, multiplier=2.5, min_candidates=20, max_limit=100) == 100


class TestHybridSearchServiceMocked:
    """Tests for HybridSearchService with mocked lexical and vector repositories."""

    @pytest.fixture
    def mock_lex_repo(self) -> MagicMock:
        return MagicMock(spec=LexicalRepository)

    @pytest.fixture
    def mock_vec_repo(self) -> MagicMock:
        return MagicMock(spec=VectorRepository)

    @pytest.fixture
    def mock_emb_service(self) -> MagicMock:
        svc = MagicMock(spec=EmbeddingService)
        svc.encode_one.return_value = [0.05] * 384
        return svc

    @pytest.fixture
    def hybrid_service(
        self, mock_lex_repo, mock_vec_repo, mock_emb_service
    ) -> HybridSearchService:
        return HybridSearchService(
            lex_repo=mock_lex_repo,
            vec_repo=mock_vec_repo,
            embedding_service=mock_emb_service,
            default_limit=20,
            max_limit=100,
            candidate_multiplier=2.5,
            rrf_k=60,
        )

    def test_empty_query_returns_empty_list(self, hybrid_service):
        mock_session = MagicMock(spec=Session)
        assert hybrid_service.search_research_works(mock_session, "") == []
        assert hybrid_service.search_opportunities(mock_session, "   ") == []

    def test_dual_path_fusion_and_deduplication(
        self, hybrid_service, mock_lex_repo, mock_vec_repo
    ):
        mock_session = MagicMock(spec=Session)

        id_a = uuid.uuid4()
        id_b = uuid.uuid4()
        id_c = uuid.uuid4()

        work_a = ResearchWorkModel(id=id_a, title="Work A")
        work_b = ResearchWorkModel(id=id_b, title="Work B")
        work_c = ResearchWorkModel(id=id_c, title="Work C")

        # Lexical finds A (rank 1), B (rank 2)
        mock_lex_repo.search_research_works.return_value = [
            LexicalSearchResult(entity_id=id_a, lexical_score=0.8, rank=1, entity_type="research_work", entity=work_a),
            LexicalSearchResult(entity_id=id_b, lexical_score=0.5, rank=2, entity_type="research_work", entity=work_b),
        ]

        # Vector finds B (rank 1), C (rank 2)
        mock_vec_repo.search_research_works.return_value = [
            VectorSearchResult(entity_id=id_b, similarity=0.95, distance=0.05, entity_type="research_work", entity=work_b),
            VectorSearchResult(entity_id=id_c, similarity=0.85, distance=0.15, entity_type="research_work", entity=work_c),
        ]

        results = hybrid_service.search_research_works(mock_session, "quantum computing", limit=10)

        # 3 unique candidates: B, A, C
        assert len(results) == 3

        # Winner must be B (found by both channels: rank 2 in lex, rank 1 in vec)
        # Score = 1/62 + 1/61 ≈ 0.01612903 + 0.01639344 = 0.03252247
        assert results[0].entity_id == id_b
        assert results[0].lexical_rank == 2
        assert results[0].vector_rank == 1
        assert results[0].lexical_score == 0.5
        assert results[0].vector_similarity == 0.95
        assert results[0].retrieval_sources == ["lexical", "vector"]
        assert results[0].entity == work_b

        # Second must be A (found by lexical only: rank 1)
        # Score = 1/61 ≈ 0.01639344
        assert results[1].entity_id == id_a
        assert results[1].lexical_rank == 1
        assert results[1].vector_rank is None
        assert results[1].retrieval_sources == ["lexical"]

        # Third must be C (found by vector only: rank 2)
        # Score = 1/62 ≈ 0.01612903
        assert results[2].entity_id == id_c
        assert results[2].vector_rank == 2
        assert results[2].lexical_rank is None
        assert results[2].retrieval_sources == ["vector"]

    def test_filter_propagation_to_both_repos(
        self, hybrid_service, mock_lex_repo, mock_vec_repo
    ):
        mock_session = MagicMock(spec=Session)
        mock_lex_repo.search_opportunities.return_value = []
        mock_vec_repo.search_opportunities.return_value = []

        exclude_id = uuid.uuid4()
        source_id = uuid.uuid4()

        hybrid_service.search_opportunities(
            mock_session,
            "machine learning conference",
            limit=10,
            exclude_opportunity_id=exclude_id,
            opportunity_type="CONFERENCE",
            status="ACTIVE",
            delivery_mode="ONLINE",
            source_id=source_id,
            upcoming_only=True,
        )

        # Verify candidate limit oversampling: 10 * 2.5 = 25
        mock_lex_repo.search_opportunities.assert_called_once_with(
            mock_session,
            "machine learning conference",
            limit=25,
            exclude_opportunity_id=exclude_id,
            opportunity_type="CONFERENCE",
            status="ACTIVE",
            delivery_mode="ONLINE",
            source_id=source_id,
            upcoming_only=True,
            submission_deadline_after=None,
        )

        mock_vec_repo.search_opportunities.assert_called_once_with(
            mock_session,
            [0.05] * 384,
            limit=25,
            exclude_opportunity_id=exclude_id,
            opportunity_type="CONFERENCE",
            status="ACTIVE",
            delivery_mode="ONLINE",
            source_id=source_id,
            upcoming_only=True,
            submission_deadline_after=None,
        )

    def test_lexical_failure_gracefully_returns_vector_candidates(
        self, hybrid_service, mock_lex_repo, mock_vec_repo
    ):
        mock_session = MagicMock(spec=Session)
        mock_lex_repo.search_research_works.side_effect = Exception("DB fulltext syntax error")

        opp_id = uuid.uuid4()
        mock_vec_repo.search_research_works.return_value = [
            VectorSearchResult(entity_id=opp_id, similarity=0.9, distance=0.1, entity_type="research_work")
        ]

        results = hybrid_service.search_research_works(mock_session, "deep learning", limit=5)
        assert len(results) == 1
        assert results[0].entity_id == opp_id
        assert results[0].retrieval_sources == ["vector"]

    def test_embedding_failure_gracefully_returns_lexical_candidates(
        self, hybrid_service, mock_lex_repo, mock_emb_service
    ):
        mock_session = MagicMock(spec=Session)
        mock_emb_service.encode_one.side_effect = Exception("Model inference failure")

        work_id = uuid.uuid4()
        mock_lex_repo.search_research_works.return_value = [
            LexicalSearchResult(entity_id=work_id, lexical_score=0.7, rank=1, entity_type="research_work")
        ]

        results = hybrid_service.search_research_works(mock_session, "neural networks", limit=5)
        assert len(results) == 1
        assert results[0].entity_id == work_id
        assert results[0].retrieval_sources == ["lexical"]


# ── B. POSTGRESQL INTEGRATION TESTS ───────────────────────────────────────────


def _is_postgres_available() -> bool:
    try:
        engine = create_engine(settings.database_url, pool_pre_ping=True)
        with engine.connect() as conn:
            res = conn.execute(select(1)).scalar_one_or_none()
            return res == 1
    except Exception:
        return False


postgres_integration = pytest.mark.skipif(
    not _is_postgres_available(),
    reason="PostgreSQL is not reachable in current environment.",
)


@postgres_integration
class TestPostgreSQLHybridIntegration:
    def test_live_hybrid_search_research_works(self):
        from app.db.session import SessionLocal

        service = HybridSearchService()
        with SessionLocal() as session:
            results = service.search_research_works(session, "machine learning", limit=5)
            assert isinstance(results, list)
            for r in results:
                assert isinstance(r.entity_id, uuid.UUID)
                assert isinstance(r.hybrid_score, float)
                assert r.entity_type == "research_work"

    def test_live_hybrid_search_opportunities(self):
        from app.db.session import SessionLocal

        service = HybridSearchService()
        with SessionLocal() as session:
            results = service.search_opportunities(session, "computer vision", limit=5)
            assert isinstance(results, list)
            for r in results:
                assert isinstance(r.entity_id, uuid.UUID)
                assert isinstance(r.hybrid_score, float)
                assert r.entity_type == "opportunity"
