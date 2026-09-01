"""
End-to-end integration tests for Phase 2.4J — Ranking Hardening & Opportunity Quality Signals.

Validates the full pipeline:
  1. Opportunity Models with Quality Metadata (Scopus indexing, predatory flag, risk scores)
  2. Research ↔ Opportunity Matching Service candidate generation
  3. HybridRanker candidate scoring and quality-weighted ranking
  4. ResultExplainer quality attribution and risk reasoning
  5. Discovery API (/api/v1/discovery/research/{work_id}/opportunities) contract with quality_score
"""
from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.opportunity import OpportunityModel
from app.models.research_knowledge import ResearchWorkModel
from app.ranking.hybrid_ranker import HybridRanker, RankedCandidate, RankingMode
from app.ranking.signals import calculate_opportunity_quality


client = TestClient(app)


def test_discovery_opportunity_matching_includes_quality_score() -> None:
    """Test that discovery API endpoint /research/{work_id}/opportunities returns quality_score and quality explanation."""
    work_id = uuid.uuid4()
    opp_1_id = uuid.uuid4()
    opp_2_id = uuid.uuid4()

    mock_opp_1 = OpportunityModel(
        id=opp_1_id,
        title="IEEE International Conference on Data Engineering",
        opportunity_type="CONFERENCE",
        delivery_mode="HYBRID",
        is_predatory_flag=False,
        indexing=["IEEE", "Scopus"],
        status="VERIFIED",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    mock_opp_2 = OpportunityModel(
        id=opp_2_id,
        title="Unverified Fast Review Conference",
        opportunity_type="CONFERENCE",
        delivery_mode="ONLINE",
        is_predatory_flag=False,
        indexing=[],
        status="UNVERIFIED",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    with patch("app.api.v1.discovery.research_opportunity_matching_service.match_opportunities") as mock_match:
        from app.services.research_opportunity_matching_service import ResearchOpportunityMatch

        mock_match.return_value = [
            ResearchOpportunityMatch(
                research_work_id=work_id,
                opportunity_id=opp_1_id,
                match_score=0.85,
                semantic_similarity=0.88,
                lexical_similarity=0.70,
                topic_similarity=0.80,
                type_compatibility=0.90,
                rank=1,
                opportunity=mock_opp_1,
            ),
            ResearchOpportunityMatch(
                research_work_id=work_id,
                opportunity_id=opp_2_id,
                match_score=0.85,
                semantic_similarity=0.88,
                lexical_similarity=0.70,
                topic_similarity=0.80,
                type_compatibility=0.90,
                rank=2,
                opportunity=mock_opp_2,
            ),
        ]

        with patch("app.api.v1.discovery.get_db") as mock_db:
            mock_db.return_value = MagicMock()
            response = client.get(
                f"/api/v1/discovery/research/{work_id}/opportunities",
                params={"explain": "true"},
            )

            assert response.status_code == 200, f"Error: {response.text}"
            data = response.json()
            assert "items" in data
            assert len(data["items"]) == 2

            # First item should be the IEEE Scopus verified venue
            item1 = data["items"][0]
            assert item1["opportunity"]["id"] == str(opp_1_id)
            assert item1["quality_score"] == 1.00
            assert item1["explanation"] is not None
            assert "opportunity_quality" in item1["explanation"]["signal_contributions"]
            assert item1["explanation"]["signal_contributions"]["opportunity_quality"]["score"] == 1.00

            # Second item should have lower quality score
            item2 = data["items"][1]
            assert item2["opportunity"]["id"] == str(opp_2_id)
            assert item2["quality_score"] < item1["quality_score"]


def test_predatory_opportunity_downranked_in_api() -> None:
    """Test that a predatory venue is severely downranked in the API."""
    work_id = uuid.uuid4()
    clean_id = uuid.uuid4()
    pred_id = uuid.uuid4()

    mock_clean = OpportunityModel(
        id=clean_id,
        title="ACM SIGMOD International Conference",
        opportunity_type="CONFERENCE",
        delivery_mode="HYBRID",
        is_predatory_flag=False,
        indexing=["ACM", "Scopus"],
        status="VERIFIED",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    mock_predatory = OpportunityModel(
        id=pred_id,
        title="Predatory Quick Review Journal",
        opportunity_type="JOURNAL",
        delivery_mode="ONLINE",
        is_predatory_flag=True,
        risk_score=0.95,
        indexing=["Google Scholar"],
        status="ACTIVE",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    with patch("app.api.v1.discovery.research_opportunity_matching_service.match_opportunities") as mock_match:
        from app.services.research_opportunity_matching_service import ResearchOpportunityMatch

        mock_match.return_value = [
            ResearchOpportunityMatch(
                research_work_id=work_id,
                opportunity_id=pred_id,
                match_score=0.85,
                semantic_similarity=0.82,  # slightly higher semantic match
                lexical_similarity=0.65,
                topic_similarity=0.78,
                type_compatibility=0.85,
                rank=1,
                opportunity=mock_predatory,
            ),
            ResearchOpportunityMatch(
                research_work_id=work_id,
                opportunity_id=clean_id,
                match_score=0.80,
                semantic_similarity=0.80,
                lexical_similarity=0.60,
                topic_similarity=0.75,
                type_compatibility=0.85,
                rank=2,
                opportunity=mock_clean,
            ),
        ]

        with patch("app.api.v1.discovery.get_db") as mock_db:
            mock_db.return_value = MagicMock()
            response = client.get(
                f"/api/v1/discovery/research/{work_id}/opportunities",
                params={"explain": "true"},
            )

            assert response.status_code == 200
            data = response.json()
            assert len(data["items"]) == 2

            # Clean verified venue outranks predatory venue
            assert data["items"][0]["opportunity"]["id"] == str(clean_id)
            assert data["items"][1]["opportunity"]["id"] == str(pred_id)

            # Check explanation contains predatory warning
            pred_expl = data["items"][1]["explanation"]
            assert pred_expl is not None
            assert any("predatory" in limit.lower() for limit in pred_expl["limitations"])
