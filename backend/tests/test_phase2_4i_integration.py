"""
End-to-end and integration tests for Phase 2.4I: Full-Text GIN Indexing & Query Intelligence.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
import uuid
import pytest

from fastapi.testclient import TestClient

from app.main import app
from app.models.research_knowledge import ResearchWorkModel
from app.repositories.lexical_repository import LexicalSearchResult
from app.repositories.vector_repository import VectorSearchResult
from app.search.query_intelligence import (
    QueryIntelligenceResult,
    QueryIntelligenceService,
    query_intelligence_service,
)
from app.services.hybrid_search_service import (
    HybridSearchResult,
    HybridSearchService,
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


class TestPhase24IHybridSearchIntegration:
    """Integration of QueryIntelligence with HybridSearchService."""

    def test_acronym_expansion_dispatches_correct_queries(self):
        mock_lex_repo = MagicMock()
        mock_vec_repo = MagicMock()
        mock_embedding_svc = MagicMock()
        mock_embedding_svc.encode_one.return_value = [0.1] * 384

        mock_lex_repo.search_research_works.return_value = []
        mock_vec_repo.search_research_works.return_value = []

        service = HybridSearchService(
            lex_repo=mock_lex_repo,
            vec_repo=mock_vec_repo,
            embedding_service=mock_embedding_svc,
        )

        mock_session = MagicMock()
        query = "GNN for drug discovery"
        service.search_research_works(mock_session, query, limit=10)

        # Lexical search must receive the expanded query
        mock_lex_repo.search_research_works.assert_called_once()
        called_lex_query = mock_lex_repo.search_research_works.call_args[0][1]
        assert "GNN for drug discovery" in called_lex_query
        assert "Graph Neural Networks" in called_lex_query

        # Semantic embedding must receive the clean normalized query
        mock_embedding_svc.encode_one.assert_called_once_with("GNN for drug discovery")

    def test_non_acronym_query_passes_normalized_query(self):
        mock_lex_repo = MagicMock()
        mock_vec_repo = MagicMock()
        mock_embedding_svc = MagicMock()
        mock_embedding_svc.encode_one.return_value = [0.1] * 384

        mock_lex_repo.search_research_works.return_value = []
        mock_vec_repo.search_research_works.return_value = []

        service = HybridSearchService(
            lex_repo=mock_lex_repo,
            vec_repo=mock_vec_repo,
            embedding_service=mock_embedding_svc,
        )

        mock_session = MagicMock()
        query = "  Deep   Reinforcement   Learning  "
        service.search_research_works(mock_session, query, limit=10)

        mock_lex_repo.search_research_works.assert_called_once()
        called_lex_query = mock_lex_repo.search_research_works.call_args[0][1]
        assert called_lex_query == "Deep Reinforcement Learning"
        mock_embedding_svc.encode_one.assert_called_once_with("Deep Reinforcement Learning")


class TestPhase24IDiscoveryAPIRoutes:
    """Tests for discovery search API route with query intelligence."""

    @patch("app.api.v1.discovery.hybrid_search_service.search_research_works")
    def test_search_research_with_query_intelligence_enabled(self, mock_search, client):
        work_id = uuid.uuid4()
        work = ResearchWorkModel(
            id=work_id,
            title="Graph Neural Networks in Bioinformatics",
            cited_by_count=42,
            is_oa=True,
        )

        mock_search.return_value = [
            HybridSearchResult(
                entity_id=work_id,
                entity_type="research_work",
                hybrid_score=0.88,
                lexical_rank=1,
                vector_rank=1,
                lexical_score=0.65,
                vector_similarity=0.91,
                retrieval_sources=["lexical", "vector"],
                entity=work,
            )
        ]

        response = client.get(
            "/api/v1/discovery/research/search",
            params={
                "q": "GNN in bioinformatics",
                "include_query_intelligence": "true",
                "explain": "true",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["query"] == "GNN in bioinformatics"
        assert len(data["items"]) == 1

        # Query intelligence metadata should be present
        qi = data.get("query_intelligence")
        assert qi is not None
        assert qi["original_query"] == "GNN in bioinformatics"
        assert qi["normalized_query"] == "GNN in bioinformatics"
        assert "GNN" in qi["detected_acronyms"]
        assert "Graph Neural Networks" in qi["detected_terms"]
        assert qi["was_expanded"] is True

        # Explainability should also be present and deterministic
        explanation = data["items"][0]["explanation"]
        assert explanation is not None
        assert "strengths" in explanation
        assert "signal_contributions" in explanation

    @patch("app.api.v1.discovery.hybrid_search_service.search_research_works")
    def test_search_research_backward_compatibility_omits_qi_by_default(self, mock_search, client):
        work_id = uuid.uuid4()
        work = ResearchWorkModel(
            id=work_id,
            title="Standard Deep Learning Paper",
            cited_by_count=10,
            is_oa=False,
        )

        mock_search.return_value = [
            HybridSearchResult(
                entity_id=work_id,
                entity_type="research_work",
                hybrid_score=0.75,
                lexical_rank=1,
                vector_rank=2,
                lexical_score=0.45,
                vector_similarity=0.82,
                retrieval_sources=["lexical", "vector"],
                entity=work,
            )
        ]

        # By default, include_query_intelligence is False
        response = client.get(
            "/api/v1/discovery/research/search",
            params={"q": "deep learning"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["query_intelligence"] is None
        assert len(data["items"]) == 1
        assert data["items"][0]["work"]["title"] == "Standard Deep Learning Paper"
