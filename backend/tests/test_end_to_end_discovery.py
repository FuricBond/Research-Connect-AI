"""
End-to-End Discovery Pipeline Integration & Resilience Tests for Phase 2.4H.

Validates the full discovery lifecycle:
  HTTP Request -> FastAPI Route -> Retrieval Service -> Repositories ->
  Hybrid Ranker -> Result Explainer -> Pydantic Schema Response
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.evaluation.benchmark_dataset import get_benchmark_dataset
from app.evaluation.benchmark_runner import BenchmarkRunner
from app.main import app
from app.models.opportunity import OpportunityModel
from app.models.research_knowledge import ResearchWorkModel
from app.ranking.hybrid_ranker import RankingMode
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
    return MagicMock(spec=Session)


@pytest.fixture
def client(mock_db_session) -> TestClient:
    app.dependency_overrides[get_db] = lambda: mock_db_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ── 1. End-to-End Research Search ─────────────────────────────────────────────


class TestEndToEndResearchSearch:
    """End-to-end tests for Research Search pipeline."""

    def test_full_search_with_ranking_and_explain(self, client):
        work_1_id = uuid.uuid4()
        work_2_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        work_1 = ResearchWorkModel(
            id=work_1_id,
            title="Contrastive Learning for Visual Representations (SimCLR)",
            abstract="A simple framework for contrastive learning of visual representations...",
            publication_year=2020,
            work_type="article",
            cited_by_count=25000,
            is_oa=True,
            created_at=now,
            updated_at=now,
        )
        work_2 = ResearchWorkModel(
            id=work_2_id,
            title="Momentum Contrast for Unsupervised Visual Representation Learning (MoCo)",
            abstract="We present Momentum Contrast (MoCo) for unsupervised visual representation learning...",
            publication_year=2020,
            work_type="article",
            cited_by_count=18000,
            is_oa=True,
            created_at=now,
            updated_at=now,
        )

        candidates = [
            HybridSearchResult(
                entity_id=work_1_id,
                entity_type="research_work",
                hybrid_score=0.033,
                vector_similarity=0.92,
                lexical_score=2.0,
                retrieval_sources=["vector", "lexical"],
                entity=work_1,
            ),
            HybridSearchResult(
                entity_id=work_2_id,
                entity_type="research_work",
                hybrid_score=0.031,
                vector_similarity=0.88,
                lexical_score=1.5,
                retrieval_sources=["vector", "lexical"],
                entity=work_2,
            ),
        ]

        with patch("app.api.v1.discovery.hybrid_search_service.search_research_works", return_value=candidates):
            response = client.get(
                "/api/v1/discovery/research/search",
                params={
                    "q": "contrastive visual representation learning",
                    "ranking_mode": "general",
                    "explain": "true",
                    "limit": 5,
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["query"] == "contrastive visual representation learning"
        assert data["total"] == 2
        assert len(data["items"]) == 2

        # Check rank ordering (SimCLR with 0.92 vector sim should be rank 1)
        item_1 = data["items"][0]
        assert item_1["rank"] == 1
        assert item_1["work"]["id"] == str(work_1_id)
        assert item_1["work"]["title"] == "Contrastive Learning for Visual Representations (SimCLR)"
        assert item_1["final_score"] >= data["items"][1]["final_score"]

        # Check explainability payload
        expl = item_1["explanation"]
        assert expl is not None
        assert "summary" in expl
        assert "semantic_similarity" in expl["signal_contributions"]
        contrib = expl["signal_contributions"]["semantic_similarity"]
        assert contrib["score"] == 0.92
        assert contrib["is_primary_driver"] is True


# ── 2. End-to-End Similar Research ───────────────────────────────────────────


class TestEndToEndSimilarResearch:
    """End-to-end tests for Similar Research pipeline."""

    def test_full_similar_research_pipeline(self, client):
        source_id = uuid.uuid4()
        cand_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        cand_work = ResearchWorkModel(
            id=cand_id,
            title="Self-Supervised Learning of Pretext-Invariant Representations",
            publication_year=2021,
            work_type="article",
            cited_by_count=3500,
            is_oa=True,
            created_at=now,
            updated_at=now,
        )

        sim_cand = SimilarResearchResult(
            source_work_id=source_id,
            candidate_work_id=cand_id,
            combined_similarity=0.87,
            semantic_similarity=0.91,
            lexical_similarity=0.65,
            topic_similarity=0.80,
            rank=1,
            shared_topic_ids=[uuid.uuid4()],
            shared_topic_names=["Computer Vision", "Self-Supervised Learning"],
            retrieval_sources=["semantic", "lexical"],
            candidate_work=cand_work,
        )

        with patch("app.api.v1.discovery.similar_research_service.get_similar_research", return_value=[sim_cand]):
            response = client.get(
                f"/api/v1/discovery/research/{source_id}/similar",
                params={"explain": "true"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["source_work_id"] == str(source_id)
        assert len(data["items"]) == 1

        item = data["items"][0]
        assert item["work"]["id"] == str(cand_id)
        assert item["semantic_similarity"] == 0.91
        assert item["topic_similarity"] == 0.80
        assert item["shared_topic_names"] == ["Computer Vision", "Self-Supervised Learning"]
        assert item["explanation"]["topic_evidence"]["topic_similarity"] == 0.80


# ── 3. End-to-End Opportunity Matching ────────────────────────────────────────


class TestEndToEndOpportunityMatching:
    """End-to-end tests for Research ↔ Opportunity Matching pipeline."""

    def test_full_opportunity_matching_pipeline(self, client):
        source_id = uuid.uuid4()
        opp_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        deadline = now + timedelta(days=20)

        opp = OpportunityModel(
            id=opp_id,
            title="CVPR 2027: Conference on Computer Vision and Pattern Recognition",
            opportunity_type="CONFERENCE",
            delivery_mode="HYBRID",
            submission_deadline=deadline,
            is_predatory_flag=False,
            status="ACTIVE",
            created_at=now,
            updated_at=now,
        )

        match_cand = ResearchOpportunityMatch(
            research_work_id=source_id,
            opportunity_id=opp_id,
            match_score=0.91,
            semantic_similarity=0.93,
            lexical_similarity=0.75,
            topic_similarity=0.90,
            type_compatibility=1.00,
            rank=1,
            shared_topic_ids=[uuid.uuid4()],
            shared_topic_names=["Computer Vision"],
            retrieval_sources=["semantic", "lexical"],
            opportunity=opp,
        )

        with patch("app.api.v1.discovery.research_opportunity_matching_service.match_opportunities", return_value=[match_cand]):
            response = client.get(
                f"/api/v1/discovery/research/{source_id}/opportunities",
                params={"ranking_mode": "research_opportunity", "explain": "true"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["research_work_id"] == str(source_id)
        assert len(data["items"]) == 1

        item = data["items"][0]
        assert item["opportunity"]["id"] == str(opp_id)
        assert item["type_compatibility"] == 1.00
        assert item["explanation"] is not None
        assert "type_compatibility" in item["explanation"]["signal_contributions"]


# ── 4. Resilience and Degraded Signal Tests ───────────────────────────────────


class TestEndToEndResilienceAndDegradedSignals:
    """Resilience tests ensuring missing metadata or channel failures degrade gracefully."""

    def test_missing_embedding_graceful_degradation(self, client):
        source_id = uuid.uuid4()
        cand_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        # Candidate has NO embedding (semantic = 0.0, retrieval via lexical + topic)
        cand_work = ResearchWorkModel(
            id=cand_id,
            title="Pure Textual Analysis Without Vectors",
            publication_year=2023,
            work_type="article",
            created_at=now,
            updated_at=now,
        )

        sim_cand = SimilarResearchResult(
            source_work_id=source_id,
            candidate_work_id=cand_id,
            combined_similarity=0.60,
            semantic_similarity=0.0,
            lexical_similarity=0.85,
            topic_similarity=0.90,
            rank=1,
            shared_topic_ids=[],
            shared_topic_names=["Linguistics"],
            retrieval_sources=["lexical", "topic"],
            candidate_work=cand_work,
        )

        with patch("app.api.v1.discovery.similar_research_service.get_similar_research", return_value=[sim_cand]):
            response = client.get(
                f"/api/v1/discovery/research/{source_id}/similar",
                params={"explain": "true"},
            )

        assert response.status_code == 200
        data = response.json()
        item = data["items"][0]
        assert item["semantic_similarity"] == 0.0
        assert item["lexical_similarity"] == 0.85

        # In explanation, semantic similarity should be marked is_available=False
        sem_contrib = item["explanation"]["signal_contributions"]["semantic_similarity"]
        assert sem_contrib["is_available"] is False

    def test_missing_topic_metadata_resilience(self, client):
        source_id = uuid.uuid4()
        cand_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        cand_work = ResearchWorkModel(
            id=cand_id,
            title="Isolated Research Work Without Topics",
            publication_year=2024,
            work_type="article",
            created_at=now,
            updated_at=now,
        )

        sim_cand = SimilarResearchResult(
            source_work_id=source_id,
            candidate_work_id=cand_id,
            combined_similarity=0.70,
            semantic_similarity=0.92,
            lexical_similarity=0.50,
            topic_similarity=0.0,
            rank=1,
            shared_topic_ids=[],
            shared_topic_names=[],
            retrieval_sources=["semantic"],
            candidate_work=cand_work,
        )

        with patch("app.api.v1.discovery.similar_research_service.get_similar_research", return_value=[sim_cand]):
            response = client.get(
                f"/api/v1/discovery/research/{source_id}/similar",
                params={"explain": "true"},
            )

        assert response.status_code == 200
        data = response.json()
        item = data["items"][0]
        assert item["topic_similarity"] == 0.0
        assert item["shared_topic_names"] == []
        assert "unavailable" in item["explanation"]["topic_evidence"]["description"].lower()

    def test_empty_results_handling(self, client):
        with patch("app.api.v1.discovery.hybrid_search_service.search_research_works", return_value=[]):
            response = client.get(
                "/api/v1/discovery/research/search",
                params={"q": "completely empty non-matching query"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["items"] == []
        assert data["has_more"] is False

    def test_benchmark_runner_full_execution(self):
        """Execute the automated BenchmarkRunner and verify structured report."""
        runner = BenchmarkRunner()
        report = runner.run_full_benchmark()

        assert report["benchmark_phase"].startswith("Phase 2.4H")
        assert "retrieval_evaluation" in report
        assert "ranking_evaluation" in report
        assert "explainability_evaluation" in report
        assert "api_latencies" in report
        assert "concurrency_profile" in report

        # Verify ranking determinism
        assert report["ranking_evaluation"]["is_deterministic_across_iterations"] is True
        # Verify attribution rate is 100%
        assert report["explainability_evaluation"]["attribution_accuracy_rate"] == 1.0
