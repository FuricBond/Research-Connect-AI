"""
API and Integration tests for FastAPI Discovery Layer in app.api.v1.discovery.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.main import app
from app.models.opportunity import OpportunityModel
from app.models.research_knowledge import ResearchWorkModel
from app.ranking.hybrid_ranker import RankedCandidate, RankingMode
from app.services.hybrid_search_service import HybridSearchResult
from app.services.research_opportunity_matching_service import (
    ResearchOpportunityMatch,
)
from app.services.similar_research_service import (
    MissingEmbeddingError,
    ResearchWorkNotFoundError,
    SimilarResearchResult,
)


@pytest.fixture
def mock_db_session() -> MagicMock:
    """Mock database session dependency."""
    return MagicMock(spec=Session)


@pytest.fixture
def client(mock_db_session) -> TestClient:
    """FastAPI TestClient with overridden get_db dependency."""
    app.dependency_overrides[get_db] = lambda: mock_db_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ── A. RESEARCH SEARCH ENDPOINT TESTS ─────────────────────────────────────────


class TestResearchSearchEndpoint:
    """Tests for GET /api/v1/discovery/research/search."""

    def test_successful_search_without_explain(self, client):
        work_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        mock_work = ResearchWorkModel(
            id=work_id,
            title="Deep Residual Learning for Image Recognition",
            abstract="Deeper neural networks are more difficult to train...",
            publication_year=2016,
            work_type="article",
            cited_by_count=50000,
            is_oa=True,
            created_at=now,
            updated_at=now,
        )

        mock_candidate = HybridSearchResult(
            entity_id=work_id,
            entity_type="research_work",
            hybrid_score=0.033,
            vector_similarity=0.92,
            lexical_score=1.5,
            retrieval_sources=["vector", "lexical"],
            entity=mock_work,
        )

        with patch("app.api.v1.discovery.hybrid_search_service.search_research_works") as mock_search:
            mock_search.return_value = [mock_candidate]

            response = client.get(
                "/api/v1/discovery/research/search",
                params={"q": "residual networks", "limit": 10, "offset": 0},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["query"] == "residual networks"
        assert data["total"] == 1
        assert data["limit"] == 10
        assert data["offset"] == 0
        assert data["has_more"] is False
        assert len(data["items"]) == 1

        item = data["items"][0]
        assert item["work"]["id"] == str(work_id)
        assert item["work"]["title"] == "Deep Residual Learning for Image Recognition"
        assert item["rank"] == 1
        assert 0.0 <= item["final_score"] <= 1.0
        assert "lexical" in item["retrieval_sources"]
        assert item["explanation"] is None

    def test_successful_search_with_explain(self, client):
        work_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        mock_work = ResearchWorkModel(
            id=work_id,
            title="Attention Is All You Need",
            abstract="The dominant sequence transduction models...",
            publication_year=2017,
            work_type="article",
            cited_by_count=80000,
            is_oa=True,
            created_at=now,
            updated_at=now,
        )

        mock_candidate = HybridSearchResult(
            entity_id=work_id,
            entity_type="research_work",
            hybrid_score=0.033,
            vector_similarity=0.95,
            lexical_score=2.0,
            retrieval_sources=["vector", "lexical"],
            entity=mock_work,
        )

        with patch("app.api.v1.discovery.hybrid_search_service.search_research_works") as mock_search:
            mock_search.return_value = [mock_candidate]

            response = client.get(
                "/api/v1/discovery/research/search",
                params={"q": "transformer attention", "explain": "true"},
            )

        assert response.status_code == 200
        data = response.json()
        item = data["items"][0]
        assert item["explanation"] is not None
        assert "summary" in item["explanation"]
        assert len(item["explanation"]["strengths"]) > 0
        assert "semantic_similarity" in item["explanation"]["signal_contributions"]

    def test_search_validation_errors(self, client):
        # Empty query
        res_empty = client.get("/api/v1/discovery/research/search", params={"q": ""})
        assert res_empty.status_code == 422

        # Missing query
        res_missing = client.get("/api/v1/discovery/research/search")
        assert res_missing.status_code == 422

        # Invalid limit > 100
        res_limit_high = client.get(
            "/api/v1/discovery/research/search", params={"q": "test", "limit": 101}
        )
        assert res_limit_high.status_code == 422

        # Invalid limit < 1
        res_limit_low = client.get(
            "/api/v1/discovery/research/search", params={"q": "test", "limit": 0}
        )
        assert res_limit_low.status_code == 422

        # Negative offset
        res_offset_neg = client.get(
            "/api/v1/discovery/research/search", params={"q": "test", "offset": -1}
        )
        assert res_offset_neg.status_code == 422

    def test_search_internal_error_handling(self, client):
        with patch("app.api.v1.discovery.hybrid_search_service.search_research_works") as mock_search:
            mock_search.side_effect = RuntimeError("Database connection died")

            response = client.get(
                "/api/v1/discovery/research/search", params={"q": "test query"}
            )

        assert response.status_code == 500
        assert "error occurred" in response.json()["detail"].lower()


# ── B. SIMILAR RESEARCH ENDPOINT TESTS ─────────────────────────────────────────


class TestSimilarResearchEndpoint:
    """Tests for GET /api/v1/discovery/research/{work_id}/similar."""

    def test_successful_similar_research_retrieval(self, client):
        source_id = uuid.uuid4()
        cand_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        cand_work = ResearchWorkModel(
            id=cand_id,
            title="BERT: Pre-training of Deep Bidirectional Transformers",
            publication_year=2019,
            work_type="article",
            cited_by_count=40000,
            is_oa=True,
            created_at=now,
            updated_at=now,
        )

        sim_result = SimilarResearchResult(
            source_work_id=source_id,
            candidate_work_id=cand_id,
            combined_similarity=0.88,
            semantic_similarity=0.92,
            lexical_similarity=0.60,
            topic_similarity=0.85,
            rank=1,
            shared_topic_ids=[uuid.uuid4()],
            shared_topic_names=["Natural Language Processing"],
            retrieval_sources=["semantic", "lexical"],
            candidate_work=cand_work,
        )

        with patch("app.api.v1.discovery.similar_research_service.get_similar_research") as mock_sim:
            mock_sim.return_value = [sim_result]

            response = client.get(f"/api/v1/discovery/research/{source_id}/similar")

        assert response.status_code == 200
        data = response.json()
        assert data["source_work_id"] == str(source_id)
        assert data["total"] == 1
        assert len(data["items"]) == 1

        item = data["items"][0]
        assert item["work"]["id"] == str(cand_id)
        assert item["work"]["title"] == "BERT: Pre-training of Deep Bidirectional Transformers"
        assert item["semantic_similarity"] == 0.92
        assert item["shared_topic_names"] == ["Natural Language Processing"]

    def test_similar_research_not_found(self, client):
        nonexistent_id = uuid.uuid4()

        with patch("app.api.v1.discovery.similar_research_service.get_similar_research") as mock_sim:
            mock_sim.side_effect = ResearchWorkNotFoundError(f"Research work '{nonexistent_id}' not found")

            response = client.get(f"/api/v1/discovery/research/{nonexistent_id}/similar")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_similar_research_missing_embedding_error(self, client):
        work_id = uuid.uuid4()

        with patch("app.api.v1.discovery.similar_research_service.get_similar_research") as mock_sim:
            mock_sim.side_effect = MissingEmbeddingError(f"Work '{work_id}' has no embedding")

            response = client.get(
                f"/api/v1/discovery/research/{work_id}/similar",
                params={"require_embedding": "true"},
            )

        assert response.status_code == 422
        assert "embedding" in response.json()["detail"].lower()

    def test_similar_research_invalid_uuid(self, client):
        response = client.get("/api/v1/discovery/research/invalid-uuid-123/similar")
        assert response.status_code == 422


# ── C. RESEARCH ↔ OPPORTUNITY MATCHING ENDPOINT TESTS ─────────────────────────


class TestOpportunityMatchingEndpoint:
    """Tests for GET /api/v1/discovery/research/{work_id}/opportunities."""

    def test_successful_opportunity_matching(self, client):
        source_id = uuid.uuid4()
        opp_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        mock_opp = OpportunityModel(
            id=opp_id,
            title="NeurIPS 2026: Conference on Neural Information Processing Systems",
            opportunity_type="CONFERENCE",
            delivery_mode="HYBRID",
            is_predatory_flag=False,
            status="ACTIVE",
            created_at=now,
            updated_at=now,
        )

        match_result = ResearchOpportunityMatch(
            research_work_id=source_id,
            opportunity_id=opp_id,
            match_score=0.89,
            semantic_similarity=0.91,
            lexical_similarity=0.70,
            topic_similarity=0.85,
            type_compatibility=1.00,
            rank=1,
            shared_topic_ids=[uuid.uuid4()],
            shared_topic_names=["Machine Learning"],
            retrieval_sources=["semantic", "lexical"],
            opportunity=mock_opp,
        )

        with patch("app.api.v1.discovery.research_opportunity_matching_service.match_opportunities") as mock_match:
            mock_match.return_value = [match_result]

            response = client.get(f"/api/v1/discovery/research/{source_id}/opportunities")

        assert response.status_code == 200
        data = response.json()
        assert data["research_work_id"] == str(source_id)
        assert data["total"] == 1
        assert len(data["items"]) == 1

        item = data["items"][0]
        assert item["opportunity"]["id"] == str(opp_id)
        assert item["opportunity"]["title"] == "NeurIPS 2026: Conference on Neural Information Processing Systems"
        assert item["type_compatibility"] == 1.00
        assert item["shared_topic_names"] == ["Machine Learning"]

    def test_opportunity_matching_with_filters(self, client):
        source_id = uuid.uuid4()

        with patch("app.api.v1.discovery.research_opportunity_matching_service.match_opportunities") as mock_match:
            mock_match.return_value = []

            response = client.get(
                f"/api/v1/discovery/research/{source_id}/opportunities",
                params={
                    "opportunity_type": "CONFERENCE",
                    "status": "ACTIVE",
                    "delivery_mode": "HYBRID",
                    "upcoming_only": "true",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []

    def test_opportunity_matching_not_found(self, client):
        nonexistent_id = uuid.uuid4()

        with patch("app.api.v1.discovery.research_opportunity_matching_service.match_opportunities") as mock_match:
            mock_match.side_effect = ResearchWorkNotFoundError("Not found")

            response = client.get(
                f"/api/v1/discovery/research/{nonexistent_id}/opportunities"
            )

        assert response.status_code == 404


# ── D. OPENAPI SCHEMA VERIFICATION ────────────────────────────────────────────


class TestOpenAPISchema:
    """Verifies that discovery endpoints are registered and documented in OpenAPI."""

    def test_discovery_routes_registered_in_openapi(self):
        openapi = app.openapi()
        paths = openapi["paths"]

        assert "/api/v1/discovery/research/search" in paths
        assert "/api/v1/discovery/research/{work_id}/similar" in paths
        assert "/api/v1/discovery/research/{work_id}/opportunities" in paths

        # Verify operations
        search_op = paths["/api/v1/discovery/research/search"]["get"]
        assert search_op["summary"] == "Search Research Works"

        similar_op = paths["/api/v1/discovery/research/{work_id}/similar"]["get"]
        assert similar_op["summary"] == "Retrieve Similar Research Works"

        opp_op = paths["/api/v1/discovery/research/{work_id}/opportunities"]["get"]
        assert opp_op["summary"] == "Match Academic Opportunities for Research Work"
