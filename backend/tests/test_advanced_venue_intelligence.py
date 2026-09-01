"""
Unit and Integration Tests for Phase 2.4L Advanced Venue Intelligence.
"""
from __future__ import annotations

from datetime import datetime, timezone
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.opportunity import OpportunityModel
from app.models.research_knowledge import ResearchWorkModel
from app.services.research_opportunity_matching_service import (
    ResearchOpportunityMatch,
    ResearchOpportunityMatchingService,
    calculate_delivery_mode_alignment,
    extract_apc_amount,
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


class TestApcExtractionAndFiltering:
    """Test suite verifying APC extraction, bounds, and neutral missing-data policy."""

    def test_extract_apc_amount_various_formats(self) -> None:
        """Verify robust parsing of various JSONB apc_or_fee dictionary formats."""
        assert extract_apc_amount(None) is None
        assert extract_apc_amount({}) is None
        assert extract_apc_amount({"has_fee": False}) == 0.0
        assert extract_apc_amount({"amount": 500, "currency": "USD"}) == 500.0
        assert extract_apc_amount({"fee": 1200.50}) == 1200.50
        assert extract_apc_amount({"apc": "800"}) == 800.0
        assert extract_apc_amount({"price": 0}) == 0.0
        assert extract_apc_amount(450) == 450.0
        assert extract_apc_amount(0.0) == 0.0
        assert extract_apc_amount({"invalid": "text"}) is None

    def test_delivery_mode_alignment_scoring(self) -> None:
        """Verify delivery mode alignment soft scoring logic."""
        assert calculate_delivery_mode_alignment(None, "ONLINE") == 1.0
        assert calculate_delivery_mode_alignment("ONLINE", None) == 1.0
        assert calculate_delivery_mode_alignment("ONLINE", "ONLINE") == 1.0
        assert calculate_delivery_mode_alignment("OFFLINE", "OFFLINE") == 1.0
        assert calculate_delivery_mode_alignment("HYBRID", "ONLINE") == 0.85
        assert calculate_delivery_mode_alignment("ONLINE", "HYBRID") == 0.85
        assert calculate_delivery_mode_alignment("OFFLINE", "ONLINE") == 0.50

    def test_apc_filter_excludes_expensive_retains_affordable(self) -> None:
        """Verify max_apc_usd hard filter excludes opportunities exceeding budget."""
        now = datetime.now(timezone.utc)
        work_id = uuid.uuid4()
        work = ResearchWorkModel(
            id=work_id,
            title="Graph Representation Learning",
            work_type="article",
            created_at=now,
            updated_at=now,
        )

        opp_cheap = OpportunityModel(
            id=uuid.uuid4(),
            title="Affordable Journal",
            opportunity_type="JOURNAL",
            delivery_mode="ONLINE",
            apc_or_fee={"amount": 400, "currency": "USD"},
            created_at=now,
            updated_at=now,
        )
        opp_expensive = OpportunityModel(
            id=uuid.uuid4(),
            title="Expensive Gold Open Access Journal",
            opportunity_type="JOURNAL",
            delivery_mode="ONLINE",
            apc_or_fee={"amount": 2500, "currency": "USD"},
            created_at=now,
            updated_at=now,
        )
        opp_unknown = OpportunityModel(
            id=uuid.uuid4(),
            title="Society Journal with Unknown Fee",
            opportunity_type="JOURNAL",
            delivery_mode="ONLINE",
            apc_or_fee=None,
            created_at=now,
            updated_at=now,
        )

        mock_session = MagicMock()
        mock_session.get.return_value = work

        vec_repo = MagicMock()
        vec_repo.search_opportunities.return_value = []

        from app.repositories.lexical_repository import LexicalSearchResult

        lex_repo = MagicMock()
        lex_repo.search_opportunities.return_value = [
            LexicalSearchResult(entity_id=opp_cheap.id, entity_type="opportunity", lexical_score=1.5, rank=1, entity=opp_cheap),
            LexicalSearchResult(entity_id=opp_expensive.id, entity_type="opportunity", lexical_score=1.4, rank=2, entity=opp_expensive),
            LexicalSearchResult(entity_id=opp_unknown.id, entity_type="opportunity", lexical_score=1.3, rank=3, entity=opp_unknown),
        ]

        service = ResearchOpportunityMatchingService(vec_repo=vec_repo, lex_repo=lex_repo)

        # Budget = 1000 USD, default require_known_apc=False
        matches = service.match_opportunities(
            session=mock_session,
            work_id=work_id,
            max_apc_usd=1000.0,
            require_known_apc=False,
        )

        matched_ids = {m.opportunity_id for m in matches}
        assert opp_cheap.id in matched_ids, "Cheap venue ($400) should be included under $1000 limit"
        assert opp_expensive.id not in matched_ids, "Expensive venue ($2500) should be excluded"
        assert opp_unknown.id in matched_ids, "Unknown fee should be retained under neutral policy"

        # Now test with require_known_apc=True (Strict policy)
        strict_matches = service.match_opportunities(
            session=mock_session,
            work_id=work_id,
            max_apc_usd=1000.0,
            require_known_apc=True,
        )
        strict_matched_ids = {m.opportunity_id for m in strict_matches}
        assert opp_cheap.id in strict_matched_ids
        assert opp_expensive.id not in strict_matched_ids
        assert opp_unknown.id not in strict_matched_ids, "Unknown fee must be excluded when require_known_apc=True"

    def test_location_filtering(self) -> None:
        """Verify location substring filtering on candidate opportunities."""
        now = datetime.now(timezone.utc)
        work_id = uuid.uuid4()
        work = ResearchWorkModel(
            id=work_id,
            title="Robotics & Control",
            work_type="article",
            created_at=now,
            updated_at=now,
        )

        opp_tokyo = OpportunityModel(
            id=uuid.uuid4(),
            title="IEEE ICRA Tokyo",
            opportunity_type="CONFERENCE",
            delivery_mode="OFFLINE",
            location="Tokyo, Japan",
            created_at=now,
            updated_at=now,
        )
        opp_london = OpportunityModel(
            id=uuid.uuid4(),
            title="European Robotics Forum",
            opportunity_type="CONFERENCE",
            delivery_mode="OFFLINE",
            location="London, United Kingdom",
            created_at=now,
            updated_at=now,
        )

        mock_session = MagicMock()
        mock_session.get.return_value = work

        from app.repositories.lexical_repository import LexicalSearchResult

        vec_repo = MagicMock()
        vec_repo.search_opportunities.return_value = []
        lex_repo = MagicMock()
        lex_repo.search_opportunities.return_value = [
            LexicalSearchResult(entity_id=opp_tokyo.id, entity_type="opportunity", lexical_score=1.5, rank=1, entity=opp_tokyo),
            LexicalSearchResult(entity_id=opp_london.id, entity_type="opportunity", lexical_score=1.4, rank=2, entity=opp_london),
        ]

        service = ResearchOpportunityMatchingService(vec_repo=vec_repo, lex_repo=lex_repo)

        tokyo_matches = service.match_opportunities(
            session=mock_session,
            work_id=work_id,
            location="Japan",
        )
        tokyo_ids = [m.opportunity_id for m in tokyo_matches]
        assert tokyo_ids == [opp_tokyo.id]

    def test_eighty_five_percent_relevance_dominance_guarantee(self) -> None:
        """Verify that relevance signals dominate over delivery mode and venue metadata."""
        now = datetime.now(timezone.utc)
        work_id = uuid.uuid4()
        work = ResearchWorkModel(
            id=work_id,
            title="Deep Residual Learning for Image Recognition",
            work_type="article",
            created_at=now,
            updated_at=now,
        )

        # Candidate A: Highly relevant semantically and lexically, but OFFLINE
        opp_relevant = OpportunityModel(
            id=uuid.uuid4(),
            title="CVPR Conference on Computer Vision",
            opportunity_type="CONFERENCE",
            delivery_mode="OFFLINE",
            location="Seattle, USA",
            created_at=now,
            updated_at=now,
        )

        # Candidate B: Irrelevant topic, but matches preferred delivery mode ONLINE perfectly
        opp_irrelevant = OpportunityModel(
            id=uuid.uuid4(),
            title="Ancient History Seminar",
            opportunity_type="WORKSHOP",
            delivery_mode="ONLINE",
            created_at=now,
            updated_at=now,
        )

        mock_session = MagicMock()
        mock_session.get.return_value = work

        from app.repositories.lexical_repository import LexicalSearchResult

        vec_repo = MagicMock()
        vec_repo.search_opportunities.return_value = []
        lex_repo = MagicMock()
        lex_repo.search_opportunities.return_value = [
            LexicalSearchResult(entity_id=opp_relevant.id, entity_type="opportunity", lexical_score=10.0, rank=1, entity=opp_relevant),
            LexicalSearchResult(entity_id=opp_irrelevant.id, entity_type="opportunity", lexical_score=0.1, rank=2, entity=opp_irrelevant),
        ]

        service = ResearchOpportunityMatchingService(vec_repo=vec_repo, lex_repo=lex_repo)

        # User prefers ONLINE
        matches = service.match_opportunities(
            session=mock_session,
            work_id=work_id,
            preferred_delivery_mode="ONLINE",
        )

        assert len(matches) == 2
        # Relevant CVPR conference must rank #1 despite user preferring ONLINE mode
        assert matches[0].opportunity_id == opp_relevant.id
        assert matches[0].match_score > matches[1].match_score


class TestOpportunityApiWithVenueIntelligence:
    """Integration test verifying discovery endpoint handles APC and location query parameters."""

    def test_discovery_api_supports_apc_and_location_params(self, client: TestClient) -> None:
        """Verify GET /api/v1/discovery/research/{work_id}/opportunities with max_apc_usd and location."""
        work_id = uuid.uuid4()
        opp_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        mock_opp = OpportunityModel(
            id=opp_id,
            title="ACM Conference on Computer and Communications Security",
            opportunity_type="CONFERENCE",
            delivery_mode="HYBRID",
            location="Salt Lake City, USA",
            apc_or_fee={"amount": 650, "currency": "USD"},
            is_predatory_flag=False,
            status="VERIFIED",
            created_at=now,
            updated_at=now,
        )

        with patch("app.api.v1.discovery.research_opportunity_matching_service.match_opportunities") as mock_match, \
             patch("app.api.v1.discovery.get_db") as mock_db:
            mock_db.return_value = MagicMock()
            mock_match.return_value = [
                ResearchOpportunityMatch(
                    research_work_id=work_id,
                    opportunity_id=opp_id,
                    match_score=0.92,
                    semantic_similarity=0.90,
                    lexical_similarity=0.85,
                    topic_similarity=0.88,
                    type_compatibility=1.0,
                    rank=1,
                    opportunity=mock_opp,
                )
            ]

            response = client.get(
                f"/api/v1/discovery/research/{work_id}/opportunities",
                params={
                    "max_apc_usd": 1000.0,
                    "location": "USA",
                    "explain": "true",
                },
                headers={"X-Bypass-Rate-Limit": "true", "Cache-Control": "no-cache"},
            )

            assert response.status_code == 200, response.text
            data = response.json()
            assert data["total"] == 1
            assert len(data["items"]) == 1
            item = data["items"][0]
            assert item["opportunity"]["title"] == "ACM Conference on Computer and Communications Security"
            assert item["opportunity"]["apc_or_fee"]["amount"] == 650
            assert item["opportunity"]["location"] == "Salt Lake City, USA"
