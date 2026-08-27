"""
Unit and Integration tests for ResearchOpportunityMatchingService in
app.services.research_opportunity_matching_service.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock
import uuid
import pytest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.opportunity import OpportunityModel, OpportunityTopicModel
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
from app.services.research_opportunity_matching_service import (
    ResearchOpportunityMatch,
    ResearchOpportunityMatchingService,
    calculate_topic_compatibility,
    calculate_type_compatibility,
)
from app.services.similar_research_service import (
    MissingEmbeddingError,
    ResearchWorkNotFoundError,
    normalize_lexical_score,
)
from ml.topic_analysis.taxonomy import TaxonomyService


# ── A. UNIT TESTS: PURE HELPER FUNCTIONS ─────────────────────────────────────


class TestMatchingHelpers:
    """Tests for pure scoring and compatibility helper functions."""

    def test_calculate_type_compatibility_standard_mappings(self):
        # article -> JOURNAL vs CONFERENCE
        assert calculate_type_compatibility("article", "JOURNAL") == 1.00
        assert calculate_type_compatibility("article", "SPECIAL_ISSUE") == 0.95
        assert calculate_type_compatibility("article", "CONFERENCE") == 0.70
        assert calculate_type_compatibility("article", "WORKSHOP") == 0.60

        # proceedings-article / conference-paper -> CONFERENCE vs JOURNAL
        assert calculate_type_compatibility("conference-paper", "CONFERENCE") == 1.00
        assert calculate_type_compatibility("proceedings-article", "CONFERENCE") == 1.00
        assert calculate_type_compatibility("conference-paper", "JOURNAL") == 0.65

        # preprint -> broad compatibility
        assert calculate_type_compatibility("preprint", "CONFERENCE") == 0.90
        assert calculate_type_compatibility("preprint", "JOURNAL") == 0.90

        # workshop-paper -> WORKSHOP
        assert calculate_type_compatibility("workshop-paper", "WORKSHOP") == 1.00

        # None / unknown fallback
        assert calculate_type_compatibility(None, "CONFERENCE") == 0.70
        assert calculate_type_compatibility("article", None) == 0.70
        assert calculate_type_compatibility("unknown_type", "UNKNOWN_OPP") == 0.70

    def test_calculate_topic_compatibility_empty(self):
        topic_comp, shared_ids, shared_names = calculate_topic_compatibility([], [])
        assert topic_comp == 0.0
        assert shared_ids == []
        assert shared_names == []

    def test_calculate_topic_compatibility_exact_and_primary_match(self):
        t1_id = uuid.uuid4()
        top1 = TopicModel(id=t1_id, name="Computer Vision", slug="computer-vision")

        work_topics = [
            ResearchWorkTopicModel(
                topic_id=t1_id,
                confidence_score=0.90,
                is_primary=True,
                topic=top1,
            )
        ]
        opp_topics = [
            OpportunityTopicModel(
                opportunity_id=uuid.uuid4(),
                topic_id=t1_id,
                confidence_score=0.90,
                is_primary=True,
                topic=top1,
            )
        ]

        topic_comp, shared_ids, shared_names = calculate_topic_compatibility(
            work_topics, opp_topics
        )
        assert t1_id in shared_ids
        assert "Computer Vision" in shared_names
        assert topic_comp > 0.80

    def test_calculate_topic_compatibility_dag_hierarchical_ancestor(self):
        t_ml_id = uuid.uuid4()
        t_cv_id = uuid.uuid4()

        top_ml = TopicModel(id=t_ml_id, name="Machine Learning", slug="machine-learning")
        top_cv = TopicModel(id=t_cv_id, name="Computer Vision", slug="computer-vision")

        work_topics = [
            ResearchWorkTopicModel(
                topic_id=t_ml_id,
                confidence_score=0.85,
                is_primary=True,
                topic=top_ml,
            )
        ]
        opp_topics = [
            OpportunityTopicModel(
                opportunity_id=uuid.uuid4(),
                topic_id=t_cv_id,
                confidence_score=0.85,
                is_primary=True,
                topic=top_cv,
            )
        ]

        tax_service = TaxonomyService()
        topic_comp, shared_ids, shared_names = calculate_topic_compatibility(
            work_topics, opp_topics, taxonomy_service=tax_service
        )
        # They both share parent 'artificial-intelligence' and root 'computer-science'
        assert shared_ids == []
        assert topic_comp > 0.0


# ── B. UNIT TESTS: RESEARCH OPPORTUNITY MATCHING SERVICE ──────────────────────


class TestResearchOpportunityMatchingServiceMocked:
    """Unit tests for ResearchOpportunityMatchingService with mocked repositories."""

    @pytest.fixture
    def mock_vec_repo(self) -> MagicMock:
        return MagicMock(spec=VectorRepository)

    @pytest.fixture
    def mock_lex_repo(self) -> MagicMock:
        return MagicMock(spec=LexicalRepository)

    @pytest.fixture
    def matching_service(
        self, mock_vec_repo, mock_lex_repo
    ) -> ResearchOpportunityMatchingService:
        return ResearchOpportunityMatchingService(
            vec_repo=mock_vec_repo,
            lex_repo=mock_lex_repo,
            default_limit=20,
            max_limit=100,
            candidate_multiplier=2.5,
            semantic_weight=0.50,
            lexical_weight=0.20,
            topic_weight=0.20,
            type_weight=0.10,
            embedding_dim=384,
        )

    def test_nonexistent_research_work_raises_error(self, matching_service):
        mock_session = MagicMock(spec=Session)
        mock_session.get.return_value = None

        work_id = uuid.uuid4()
        with pytest.raises(ResearchWorkNotFoundError, match="not found"):
            matching_service.match_opportunities(mock_session, work_id)

    def test_missing_embedding_mandatory_mode_raises_error(self, matching_service):
        mock_session = MagicMock(spec=Session)
        work_id = uuid.uuid4()
        source_work = ResearchWorkModel(id=work_id, title="Work Without Embedding", embedding=None)
        mock_session.get.return_value = source_work

        with pytest.raises(MissingEmbeddingError, match="does not have an embedding"):
            matching_service.match_opportunities(
                mock_session, work_id, require_embedding=True
            )

    def test_missing_embedding_graceful_degradation(
        self, matching_service, mock_vec_repo, mock_lex_repo
    ):
        mock_session = MagicMock(spec=Session)
        work_id = uuid.uuid4()
        opp_id = uuid.uuid4()
        source_work = ResearchWorkModel(
            id=work_id, title="Work Without Embedding", embedding=None, work_type="article"
        )
        opp = OpportunityModel(
            id=opp_id, title="Conference on Informatics", opportunity_type="CONFERENCE"
        )
        mock_session.get.return_value = source_work

        mock_lex_repo.search_opportunities.return_value = [
            LexicalSearchResult(entity_id=opp_id, lexical_score=1.0, rank=1, entity_type="opportunity", entity=opp)
        ]

        # In require_embedding=False (default), semantic search is skipped and lexical proceeds
        results = matching_service.match_opportunities(
            mock_session, work_id, require_embedding=False
        )

        mock_vec_repo.search_opportunities.assert_not_called()
        assert len(results) == 1
        assert results[0].opportunity_id == opp_id
        assert results[0].semantic_similarity == 0.0
        assert results[0].lexical_similarity == 0.50  # 1.0 / (1.0 + 1.0)
        assert results[0].retrieval_sources == ["lexical"]

    def test_invalid_embedding_dimension_raises_error(self, matching_service):
        mock_session = MagicMock(spec=Session)
        work_id = uuid.uuid4()
        source_work = ResearchWorkModel(id=work_id, title="Bad Dim", embedding=[0.1] * 128)
        mock_session.get.return_value = source_work

        with pytest.raises(VectorValidationError, match="dimension mismatch"):
            matching_service.match_opportunities(mock_session, work_id)

    def test_multi_channel_fusion_and_provenance(
        self, matching_service, mock_vec_repo, mock_lex_repo
    ):
        mock_session = MagicMock(spec=Session)
        work_id = uuid.uuid4()
        id_a = uuid.uuid4()
        id_b = uuid.uuid4()
        id_c = uuid.uuid4()

        source_work = ResearchWorkModel(
            id=work_id,
            title="Transformer Architectures for NLP",
            embedding=[0.05] * 384,
            work_type="conference-paper",
        )
        opp_a = OpportunityModel(id=id_a, title="ACL 2026", opportunity_type="CONFERENCE")
        opp_b = OpportunityModel(id=id_b, title="EMNLP 2026", opportunity_type="CONFERENCE")
        opp_c = OpportunityModel(id=id_c, title="IEEE Transactions", opportunity_type="JOURNAL")

        mock_session.get.return_value = source_work

        # Vector finds A (0.92) and B (0.75)
        mock_vec_repo.search_opportunities.return_value = [
            VectorSearchResult(entity_id=id_a, similarity=0.92, distance=0.08, entity_type="opportunity", entity=opp_a),
            VectorSearchResult(entity_id=id_b, similarity=0.75, distance=0.25, entity_type="opportunity", entity=opp_b),
        ]

        # Lexical finds A (score=1.5) and C (score=0.8)
        mock_lex_repo.search_opportunities.return_value = [
            LexicalSearchResult(entity_id=id_a, lexical_score=1.5, rank=1, entity_type="opportunity", entity=opp_a),
            LexicalSearchResult(entity_id=id_c, lexical_score=0.8, rank=2, entity_type="opportunity", entity=opp_c),
        ]

        results = matching_service.match_opportunities(mock_session, work_id, limit=10)

        assert len(results) == 3
        # Opp A is discovered in both channels
        assert results[0].opportunity_id == id_a
        assert results[0].rank == 1
        assert "semantic" in results[0].retrieval_sources
        assert "lexical" in results[0].retrieval_sources
        assert results[0].semantic_similarity == 0.92
        assert results[0].lexical_similarity == round(1.5 / 2.5, 6)
        assert results[0].type_compatibility == 1.00  # conference-paper -> CONFERENCE

    def test_filter_propagation(
        self, matching_service, mock_vec_repo, mock_lex_repo
    ):
        mock_session = MagicMock(spec=Session)
        work_id = uuid.uuid4()
        source_work = ResearchWorkModel(
            id=work_id,
            title="Medical Image Segmentation",
            embedding=[0.05] * 384,
            work_type="article",
        )
        mock_session.get.return_value = source_work
        mock_vec_repo.search_opportunities.return_value = []
        mock_lex_repo.search_opportunities.return_value = []

        deadline_filter = datetime(2026, 12, 31, tzinfo=timezone.utc)
        src_id = uuid.uuid4()

        matching_service.match_opportunities(
            mock_session,
            work_id,
            limit=10,
            opportunity_type="CONFERENCE",
            status="ACTIVE",
            delivery_mode="HYBRID",
            source_id=src_id,
            upcoming_only=True,
            submission_deadline_after=deadline_filter,
        )

        mock_vec_repo.search_opportunities.assert_called_once_with(
            session=mock_session,
            query_embedding=[0.05] * 384,
            limit=25,  # 10 * 2.5 = 25
            opportunity_type="CONFERENCE",
            status="ACTIVE",
            delivery_mode="HYBRID",
            source_id=src_id,
            upcoming_only=True,
            submission_deadline_after=deadline_filter,
        )

        mock_lex_repo.search_opportunities.assert_called_once_with(
            session=mock_session,
            query="Medical Image Segmentation",
            limit=25,
            opportunity_type="CONFERENCE",
            status="ACTIVE",
            delivery_mode="HYBRID",
            source_id=src_id,
            upcoming_only=True,
            submission_deadline_after=deadline_filter,
        )

    def test_deterministic_tie_breaking(
        self, matching_service, mock_vec_repo, mock_lex_repo
    ):
        mock_session = MagicMock(spec=Session)
        work_id = uuid.uuid4()
        id_1 = uuid.UUID("00000000-0000-0000-0000-000000000001")
        id_2 = uuid.UUID("00000000-0000-0000-0000-000000000002")

        source_work = ResearchWorkModel(
            id=work_id,
            title="Tie Breaking Test",
            embedding=[0.05] * 384,
            work_type="article",
        )
        opp_1 = OpportunityModel(id=id_1, title="Opp 1", opportunity_type="JOURNAL")
        opp_2 = OpportunityModel(id=id_2, title="Opp 2", opportunity_type="JOURNAL")

        mock_session.get.return_value = source_work

        # Identical vector similarity and type compatibility
        mock_vec_repo.search_opportunities.return_value = [
            VectorSearchResult(entity_id=id_2, similarity=0.80, distance=0.20, entity_type="opportunity", entity=opp_2),
            VectorSearchResult(entity_id=id_1, similarity=0.80, distance=0.20, entity_type="opportunity", entity=opp_1),
        ]
        mock_lex_repo.search_opportunities.return_value = []

        results = matching_service.match_opportunities(mock_session, work_id)

        # Tie-breaker sorts by UUID string ascending
        assert len(results) == 2
        assert results[0].opportunity_id == id_1
        assert results[1].opportunity_id == id_2
        assert results[0].rank == 1
        assert results[1].rank == 2

    def test_composite_score_formula_and_bounds(
        self, mock_vec_repo, mock_lex_repo
    ):
        custom_service = ResearchOpportunityMatchingService(
            vec_repo=mock_vec_repo,
            lex_repo=mock_lex_repo,
            semantic_weight=0.50,
            lexical_weight=0.20,
            topic_weight=0.20,
            type_weight=0.10,
            default_limit=10,
        )

        mock_session = MagicMock(spec=Session)
        work_id = uuid.uuid4()
        opp_id = uuid.uuid4()

        source_work = ResearchWorkModel(
            id=work_id, title="Reinforcement Learning in Robotics", embedding=[0.05] * 384, work_type="article"
        )
        opp = OpportunityModel(id=opp_id, title="Robotics Conference", opportunity_type="JOURNAL")
        mock_session.get.return_value = source_work

        mock_vec_repo.search_opportunities.return_value = [
            VectorSearchResult(entity_id=opp_id, similarity=0.80, distance=0.20, entity_type="opportunity", entity=opp)
        ]
        mock_lex_repo.search_opportunities.return_value = [
            LexicalSearchResult(entity_id=opp_id, lexical_score=1.0, rank=1, entity_type="opportunity", entity=opp)
        ]

        results = custom_service.match_opportunities(mock_session, work_id)
        assert len(results) == 1
        res = results[0]

        # sem: 0.50 * 0.80 = 0.40
        # lex: 0.20 * 0.50 = 0.10 (normalized 1.0/(1.0+1.0)=0.5)
        # top: 0.20 * 0.0 = 0.0 (no topics)
        # typ: 0.10 * 1.00 = 0.10 (article -> JOURNAL = 1.0)
        # total = 0.60
        assert res.match_score == 0.60
        assert 0.0 <= res.match_score <= 1.0
        assert 0.0 <= res.semantic_similarity <= 1.0
        assert 0.0 <= res.lexical_similarity <= 1.0
        assert 0.0 <= res.topic_similarity <= 1.0
        assert 0.0 <= res.type_compatibility <= 1.0


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
class TestResearchOpportunityMatchingPostgresIntegration:
    """PostgreSQL integration tests for ResearchOpportunityMatchingService."""

    @pytest.fixture
    def db_session(self):
        engine = create_engine(settings.database_url)
        session = Session(engine)
        yield session
        session.rollback()
        session.close()
        engine.dispose()

    def test_live_opportunity_matching_execution(self, db_session):
        # Fetch an existing research work with an embedding from database
        stmt = (
            select(ResearchWorkModel)
            .where(ResearchWorkModel.embedding.is_not(None))
            .limit(1)
        )
        source_work = db_session.execute(stmt).scalar_one_or_none()

        if source_work is None:
            pytest.skip("No research work with embedding available in test DB")

        svc = ResearchOpportunityMatchingService()
        results = svc.match_opportunities(db_session, source_work.id, limit=5)

        assert isinstance(results, list)
        for match in results:
            assert isinstance(match, ResearchOpportunityMatch)
            assert match.research_work_id == source_work.id
            assert 0.0 <= match.match_score <= 1.0
            assert 0.0 <= match.semantic_similarity <= 1.0
            assert 0.0 <= match.lexical_similarity <= 1.0
            assert 0.0 <= match.topic_similarity <= 1.0
            assert 0.0 <= match.type_compatibility <= 1.0
