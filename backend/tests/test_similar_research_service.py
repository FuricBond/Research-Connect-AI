"""
Unit and Integration tests for SimilarResearchService in app.services.similar_research_service.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
import uuid
import pytest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.research_knowledge import (
    ResearchWorkModel,
    ResearchWorkTopicModel,
)
from app.models.topic import TopicModel
from app.repositories.lexical_repository import LexicalRepository, LexicalSearchResult
from app.repositories.vector_repository import (
    VectorRepository,
    VectorSearchResult,
    VectorValidationError,
)
from app.services.similar_research_service import (
    MissingEmbeddingError,
    ResearchWorkNotFoundError,
    SimilarResearchResult,
    SimilarResearchService,
    calculate_topic_similarity,
    normalize_lexical_score,
)
from ml.topic_analysis.taxonomy import TaxonomyNode, TaxonomyService


# ── A. UNIT TESTS: HELPER FUNCTIONS ──────────────────────────────────────────


class TestNormalizationAndTopicHelper:
    """Tests for score normalization and topic similarity helper functions."""

    def test_normalize_lexical_score_none_or_zero(self):
        assert normalize_lexical_score(None) == 0.0
        assert normalize_lexical_score(0.0) == 0.0
        assert normalize_lexical_score(-0.5) == 0.0

    def test_normalize_lexical_score_monotonic(self):
        s1 = normalize_lexical_score(0.5)
        s2 = normalize_lexical_score(1.0)
        s3 = normalize_lexical_score(3.0)
        assert 0.0 < s1 < s2 < s3 < 1.0
        assert s1 == round(0.5 / 1.5, 6)
        assert s2 == 0.5
        assert s3 == 0.75

    def test_calculate_topic_similarity_empty(self):
        topic_sim, shared_ids, shared_names = calculate_topic_similarity([], [])
        assert topic_sim == 0.0
        assert shared_ids == []
        assert shared_names == []

    def test_calculate_topic_similarity_exact_overlap(self):
        t1_id = uuid.uuid4()
        t2_id = uuid.uuid4()

        top1 = TopicModel(id=t1_id, name="Machine Learning", slug="machine-learning")
        top2 = TopicModel(id=t2_id, name="Deep Learning", slug="deep-learning")

        source_topics = [
            ResearchWorkTopicModel(
                topic_id=t1_id,
                confidence_score=0.90,
                is_primary=True,
                topic=top1,
            ),
            ResearchWorkTopicModel(
                topic_id=t2_id,
                confidence_score=0.80,
                is_primary=False,
                topic=top2,
            ),
        ]

        cand_topics = [
            ResearchWorkTopicModel(
                topic_id=t1_id,
                confidence_score=0.90,
                is_primary=True,
                topic=top1,
            ),
        ]

        topic_sim, shared_ids, shared_names = calculate_topic_similarity(
            source_topics, cand_topics
        )
        assert t1_id in shared_ids
        assert "Machine Learning" in shared_names
        assert topic_sim > 0.50

    def test_calculate_topic_similarity_hierarchical_ancestor(self):
        t_ml_id = uuid.uuid4()
        t_nlp_id = uuid.uuid4()

        top_ml = TopicModel(id=t_ml_id, name="Machine Learning", slug="machine-learning")
        top_nlp = TopicModel(id=t_nlp_id, name="Natural Language Processing", slug="natural-language-processing")

        source_topics = [
            ResearchWorkTopicModel(
                topic_id=t_ml_id,
                confidence_score=0.80,
                is_primary=True,
                topic=top_ml,
            )
        ]
        cand_topics = [
            ResearchWorkTopicModel(
                topic_id=t_nlp_id,
                confidence_score=0.80,
                is_primary=True,
                topic=top_nlp,
            )
        ]

        tax_service = TaxonomyService()
        topic_sim, shared_ids, shared_names = calculate_topic_similarity(
            source_topics, cand_topics, taxonomy_service=tax_service
        )
        # They both share parent 'artificial-intelligence' and root 'computer-science'
        assert shared_ids == []
        assert topic_sim > 0.0


# ── B. UNIT TESTS: SIMILAR RESEARCH SERVICE ───────────────────────────────────


class TestSimilarResearchServiceMocked:
    """Unit tests for SimilarResearchService with mocked dependencies."""

    @pytest.fixture
    def mock_vec_repo(self) -> MagicMock:
        return MagicMock(spec=VectorRepository)

    @pytest.fixture
    def mock_lex_repo(self) -> MagicMock:
        return MagicMock(spec=LexicalRepository)

    @pytest.fixture
    def similar_service(
        self, mock_vec_repo, mock_lex_repo
    ) -> SimilarResearchService:
        return SimilarResearchService(
            vec_repo=mock_vec_repo,
            lex_repo=mock_lex_repo,
            default_limit=20,
            max_limit=100,
            candidate_multiplier=2.5,
            semantic_weight=0.60,
            lexical_weight=0.20,
            topic_weight=0.20,
            embedding_dim=384,
        )

    def test_source_work_not_found_raises_error(self, similar_service):
        mock_session = MagicMock(spec=Session)
        mock_session.get.return_value = None

        work_id = uuid.uuid4()
        with pytest.raises(ResearchWorkNotFoundError, match="not found"):
            similar_service.get_similar_research(mock_session, work_id)

    def test_source_work_missing_embedding_raises_error(self, similar_service):
        mock_session = MagicMock(spec=Session)
        work_id = uuid.uuid4()
        source_work = ResearchWorkModel(id=work_id, title="No Embedding Work", embedding=None)
        mock_session.get.return_value = source_work

        with pytest.raises(MissingEmbeddingError, match="does not have an embedding"):
            similar_service.get_similar_research(mock_session, work_id)

    def test_source_work_invalid_embedding_dim_raises_error(self, similar_service):
        mock_session = MagicMock(spec=Session)
        work_id = uuid.uuid4()
        source_work = ResearchWorkModel(id=work_id, title="Bad Dim Work", embedding=[0.1] * 128)
        mock_session.get.return_value = source_work

        with pytest.raises(VectorValidationError, match="dimension mismatch"):
            similar_service.get_similar_research(mock_session, work_id)

    def test_strict_self_exclusion(
        self, similar_service, mock_vec_repo, mock_lex_repo
    ):
        mock_session = MagicMock(spec=Session)
        source_id = uuid.uuid4()
        cand_id = uuid.uuid4()

        source_work = ResearchWorkModel(
            id=source_id,
            title="Source Work",
            embedding=[0.05] * 384,
        )
        cand_work = ResearchWorkModel(
            id=cand_id,
            title="Candidate Work",
            embedding=[0.05] * 384,
        )

        mock_session.get.return_value = source_work

        # Mock vector repo returning both source_id (erroneously) and cand_id
        mock_vec_repo.search_research_works.return_value = [
            VectorSearchResult(entity_id=source_id, similarity=1.0, distance=0.0, entity_type="research_work", entity=source_work),
            VectorSearchResult(entity_id=cand_id, similarity=0.88, distance=0.12, entity_type="research_work", entity=cand_work),
        ]
        mock_lex_repo.search_research_works.return_value = []

        results = similar_service.get_similar_research(mock_session, source_id)

        # Source work must never be in returned results
        assert len(results) == 1
        assert results[0].candidate_work_id == cand_id
        assert all(r.candidate_work_id != source_id for r in results)

    def test_multi_channel_fusion_and_scoring(
        self, similar_service, mock_vec_repo, mock_lex_repo
    ):
        mock_session = MagicMock(spec=Session)
        source_id = uuid.uuid4()
        id_a = uuid.uuid4()
        id_b = uuid.uuid4()
        id_c = uuid.uuid4()

        source_work = ResearchWorkModel(
            id=source_id,
            title="Deep Learning Foundations",
            embedding=[0.05] * 384,
        )
        work_a = ResearchWorkModel(id=id_a, title="Deep Learning Systems")
        work_b = ResearchWorkModel(id=id_b, title="Neural Networks Basics")
        work_c = ResearchWorkModel(id=id_c, title="Quantum Computing")

        mock_session.get.return_value = source_work

        # Vector channel retrieves A (0.90) and B (0.70)
        mock_vec_repo.search_research_works.return_value = [
            VectorSearchResult(entity_id=id_a, similarity=0.90, distance=0.10, entity_type="research_work", entity=work_a),
            VectorSearchResult(entity_id=id_b, similarity=0.70, distance=0.30, entity_type="research_work", entity=work_b),
        ]

        # Lexical channel retrieves A (score=1.0) and C (score=0.5)
        mock_lex_repo.search_research_works.return_value = [
            LexicalSearchResult(entity_id=id_a, lexical_score=1.0, rank=1, entity_type="research_work", entity=work_a),
            LexicalSearchResult(entity_id=id_c, lexical_score=0.5, rank=2, entity_type="research_work", entity=work_c),
        ]

        results = similar_service.get_similar_research(mock_session, source_id, limit=10)

        assert len(results) == 3
        # Work A is found in both channels and has high semantic + lexical
        assert results[0].candidate_work_id == id_a
        assert results[0].rank == 1
        assert "vector" in results[0].retrieval_sources
        assert "lexical" in results[0].retrieval_sources
        assert results[0].semantic_similarity == 0.90
        assert results[0].lexical_similarity == 0.50  # 1.0 / (1.0 + 1.0)

    def test_filter_propagation(
        self, similar_service, mock_vec_repo, mock_lex_repo
    ):
        mock_session = MagicMock(spec=Session)
        source_id = uuid.uuid4()
        source_work = ResearchWorkModel(
            id=source_id,
            title="Filtered Query Work",
            embedding=[0.05] * 384,
        )
        mock_session.get.return_value = source_work
        mock_vec_repo.search_research_works.return_value = []
        mock_lex_repo.search_research_works.return_value = []

        venue_id = uuid.uuid4()
        similar_service.get_similar_research(
            mock_session,
            source_id,
            limit=15,
            publication_year=2024,
            min_year=2020,
            max_year=2025,
            work_type="article",
            language="en",
            primary_source_id=venue_id,
            is_oa=True,
            min_citations=10,
        )

        # Check vector repository call
        mock_vec_repo.search_research_works.assert_called_once_with(
            session=mock_session,
            query_embedding=[0.05] * 384,
            limit=37,  # 15 * 2.5 = 37.5 -> 37
            exclude_work_id=source_id,
            publication_year=2024,
            min_year=2020,
            max_year=2025,
            work_type="article",
            language="en",
            primary_source_id=venue_id,
            is_oa=True,
            min_citations=10,
        )

        # Check lexical repository call
        mock_lex_repo.search_research_works.assert_called_once_with(
            session=mock_session,
            query="Filtered Query Work",
            limit=37,
            exclude_work_id=source_id,
            publication_year=2024,
            min_year=2020,
            max_year=2025,
            work_type="article",
            language="en",
            primary_source_id=venue_id,
            is_oa=True,
            min_citations=10,
        )

    def test_deterministic_tie_breaking(
        self, similar_service, mock_vec_repo, mock_lex_repo
    ):
        mock_session = MagicMock(spec=Session)
        source_id = uuid.uuid4()
        id_1 = uuid.UUID("00000000-0000-0000-0000-000000000001")
        id_2 = uuid.UUID("00000000-0000-0000-0000-000000000002")

        source_work = ResearchWorkModel(
            id=source_id,
            title="Tie Source",
            embedding=[0.05] * 384,
        )
        work_1 = ResearchWorkModel(id=id_1, title="Candidate 1")
        work_2 = ResearchWorkModel(id=id_2, title="Candidate 2")

        mock_session.get.return_value = source_work

        # Both have identical vector similarity and no lexical/topic
        mock_vec_repo.search_research_works.return_value = [
            VectorSearchResult(entity_id=id_2, similarity=0.85, distance=0.15, entity_type="research_work", entity=work_2),
            VectorSearchResult(entity_id=id_1, similarity=0.85, distance=0.15, entity_type="research_work", entity=work_1),
        ]
        mock_lex_repo.search_research_works.return_value = []

        results = similar_service.get_similar_research(mock_session, source_id)

        # Tie-breaker sorts by UUID string ascending
        assert len(results) == 2
        assert results[0].candidate_work_id == id_1
        assert results[1].candidate_work_id == id_2
        assert results[0].rank == 1
        assert results[1].rank == 2

    def test_custom_weights_and_limits(
        self, mock_vec_repo, mock_lex_repo
    ):
        custom_service = SimilarResearchService(
            vec_repo=mock_vec_repo,
            lex_repo=mock_lex_repo,
            semantic_weight=0.80,
            lexical_weight=0.10,
            topic_weight=0.10,
            default_limit=5,
            max_limit=50,
        )

        mock_session = MagicMock(spec=Session)
        source_id = uuid.uuid4()
        cand_id = uuid.uuid4()

        source_work = ResearchWorkModel(id=source_id, title="Custom Source", embedding=[0.05] * 384)
        cand_work = ResearchWorkModel(id=cand_id, title="Custom Candidate")
        mock_session.get.return_value = source_work

        mock_vec_repo.search_research_works.return_value = [
            VectorSearchResult(entity_id=cand_id, similarity=0.80, distance=0.20, entity_type="research_work", entity=cand_work),
        ]
        mock_lex_repo.search_research_works.return_value = [
            LexicalSearchResult(entity_id=cand_id, lexical_score=1.0, rank=1, entity_type="research_work", entity=cand_work),
        ]

        results = custom_service.get_similar_research(mock_session, source_id)
        assert len(results) == 1
        # sem: 0.80 * 0.80 = 0.64
        # lex: 0.10 * 0.50 = 0.05
        # topic: 0.10 * 0.0 = 0.0
        # total = 0.69
        assert results[0].combined_similarity == 0.69


# ── C. INTEGRATION TESTS (POSTGRESQL CONDITIONAL) ─────────────────────────────


def _is_postgres_available() -> bool:
    """Probe if local PostgreSQL database is reachable."""
    try:
        engine = create_engine(settings.database_url, connect_args={"connect_timeout": 2})
        with engine.connect() as conn:
            conn.execute(select(1))
        engine.dispose()
        return True
    except Exception:
        return False


POSTGRES_AVAILABLE = _is_postgres_available()


@pytest.mark.postgres_integration
@pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="PostgreSQL database not available")
class TestSimilarResearchPostgresIntegration:
    """PostgreSQL integration tests for SimilarResearchService."""

    @pytest.fixture
    def db_session(self):
        engine = create_engine(settings.database_url)
        session = Session(engine)
        yield session
        session.rollback()
        session.close()
        engine.dispose()

    def test_live_similar_research_execution(self, db_session):
        # Fetch an existing research work with an embedding from database
        stmt = (
            select(ResearchWorkModel)
            .where(ResearchWorkModel.embedding.is_not(None))
            .limit(1)
        )
        source_work = db_session.execute(stmt).scalar_one_or_none()

        if source_work is None:
            pytest.skip("No research work with embedding available in test DB")

        svc = SimilarResearchService()
        results = svc.get_similar_research(db_session, source_work.id, limit=5)

        assert isinstance(results, list)
        for res in results:
            assert isinstance(res, SimilarResearchResult)
            assert res.source_work_id == source_work.id
            assert res.candidate_work_id != source_work.id
            assert 0.0 <= res.combined_similarity <= 1.0
            assert 0.0 <= res.semantic_similarity <= 1.0
            assert 0.0 <= res.lexical_similarity <= 1.0
            assert 0.0 <= res.topic_similarity <= 1.0
