"""
Unit and Integration tests for HybridRanker in app.ranking.hybrid_ranker.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math
from unittest.mock import MagicMock
import uuid
import pytest

from app.models.opportunity import OpportunityModel
from app.models.research_knowledge import ResearchWorkModel
from app.ranking.hybrid_ranker import (
    HybridRanker,
    RankedCandidate,
    RankerWeights,
    RankingMode,
    hybrid_ranker,
)
from app.repositories.lexical_repository import LexicalSearchResult
from app.repositories.vector_repository import (
    VectorSearchResult,
    VectorValidationError,
)
from app.services.hybrid_search_service import HybridSearchResult
from app.services.research_opportunity_matching_service import ResearchOpportunityMatch
from app.services.similar_research_service import SimilarResearchResult


# ── A. RANKER WEIGHTS TESTS ───────────────────────────────────────────────────


class TestRankerWeights:
    """Tests for RankerWeights validation and normalization."""

    def test_default_weights_and_validation(self):
        weights = RankerWeights(
            semantic_weight=0.5,
            lexical_weight=0.2,
            topic_weight=0.2,
            freshness_weight=0.1,
        )
        weights.validate()
        norm = weights.normalized()
        assert norm.semantic_weight == 0.5
        assert norm.lexical_weight == 0.2
        assert norm.topic_weight == 0.2
        assert norm.freshness_weight == 0.1
        total = (
            norm.semantic_weight
            + norm.lexical_weight
            + norm.topic_weight
            + norm.type_weight
            + norm.freshness_weight
            + norm.urgency_weight
        )
        assert math.isclose(total, 1.0, abs_tol=1e-5)

    def test_normalization_with_unscaled_weights(self):
        # Weights summing to 2.0 -> scaled by 0.5
        weights = RankerWeights(
            semantic_weight=1.0,
            lexical_weight=0.4,
            topic_weight=0.4,
            freshness_weight=0.2,
        )
        norm = weights.normalized()
        assert norm.semantic_weight == 0.5
        assert norm.lexical_weight == 0.2
        assert norm.topic_weight == 0.2
        assert norm.freshness_weight == 0.1

    def test_all_zero_weights_safe(self):
        weights = RankerWeights()
        weights.validate()
        norm = weights.normalized()
        assert norm.semantic_weight == 0.0

    def test_negative_weights_raise_error(self):
        weights = RankerWeights(semantic_weight=-0.5, lexical_weight=0.5)
        with pytest.raises(ValueError, match="cannot be negative"):
            weights.validate()

    def test_nan_and_inf_weights_raise_error(self):
        with pytest.raises(ValueError, match="cannot be NaN"):
            RankerWeights(semantic_weight=float("nan")).validate()
        with pytest.raises(ValueError, match="cannot be infinite"):
            RankerWeights(semantic_weight=float("inf")).validate()

    def test_non_numeric_weights_raise_error(self):
        with pytest.raises(ValueError, match="must be numeric"):
            RankerWeights(semantic_weight=True).validate()  # type: ignore
        with pytest.raises(ValueError, match="must be numeric"):
            RankerWeights(semantic_weight="0.5").validate()  # type: ignore


# ── B. HYBRID RANKER CORE TESTS ───────────────────────────────────────────────


class TestHybridRanker:
    """Tests for HybridRanker candidate ranking, scoring, tie-breaking, and limits."""

    @pytest.fixture
    def ranker(self) -> HybridRanker:
        return HybridRanker(default_limit=10, max_limit=50)

    def test_empty_candidates_returns_empty_list(self, ranker):
        assert ranker.rank([]) == []

    def test_mathematical_composite_scoring(self, ranker):
        # Explicit test with exact math verification
        # sem: 0.8, lex: 0.6, top: 1.0, freshness: 0.5
        # weights: sem 0.5, lex 0.2, top 0.2, freshness 0.1 (sum = 1.0)
        # final = 0.5*0.8 + 0.2*0.6 + 0.2*1.0 + 0.1*0.5
        # final = 0.40 + 0.12 + 0.20 + 0.05 = 0.77
        cand_id = uuid.uuid4()
        cand = {
            "entity_id": cand_id,
            "entity_type": "research_work",
            "semantic_similarity": 0.8,
            "lexical_similarity": 0.6,
            "topic_similarity": 1.0,
            "freshness": 0.5,
            "retrieval_sources": ["semantic", "lexical"],
        }

        custom_weights = RankerWeights(
            semantic_weight=0.5,
            lexical_weight=0.2,
            topic_weight=0.2,
            freshness_weight=0.1,
        )

        results = ranker.rank([cand], weights=custom_weights)
        assert len(results) == 1
        res = results[0]
        assert res.entity_id == cand_id
        assert res.rank == 1
        assert res.final_score == 0.77
        assert res.semantic_score == 0.8
        assert res.lexical_score == 0.6
        assert res.topic_score == 1.0
        assert res.freshness_score == 0.5
        assert res.retrieval_sources == ["lexical", "semantic"]  # sorted

    def test_opportunity_mode_with_type_and_urgency(self, ranker):
        opp_id = uuid.uuid4()
        ref_time = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
        opp_model = OpportunityModel(
            id=opp_id,
            title="IEEE Conference on AI",
            opportunity_type="CONFERENCE",
            submission_deadline=datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc),  # 9 days remaining -> urgency 0.9 (window 90)
        )

        match_cand = ResearchOpportunityMatch(
            research_work_id=uuid.uuid4(),
            opportunity_id=opp_id,
            match_score=0.70,
            semantic_similarity=0.80,
            lexical_similarity=0.50,
            topic_similarity=0.70,
            type_compatibility=1.00,
            rank=1,
            retrieval_sources=["semantic"],
            opportunity=opp_model,
        )

        # Default opportunity weights (Phase 2.4J): sem 0.40, lex 0.15, top 0.20, type 0.10, urg 0.05, qual 0.10 (sum 1.0)
        # quality for active status + neutral indexing = 0.56
        # final = 0.40*0.80 + 0.15*0.50 + 0.20*0.70 + 0.10*1.00 + 0.05*0.90 + 0.10*0.56
        # final = 0.32 + 0.075 + 0.14 + 0.10 + 0.045 + 0.056 = 0.736
        results = ranker.rank(
            [match_cand],
            mode=RankingMode.RESEARCH_OPPORTUNITY,
            reference_time=ref_time,
            urgency_window_days=90.0,
        )

        assert len(results) == 1
        res = results[0]
        assert res.entity_id == opp_id
        assert res.entity_type == "opportunity"
        assert math.isclose(res.final_score, 0.736, abs_tol=1e-4)
        assert res.semantic_score == 0.80
        assert res.lexical_score == 0.50
        assert res.topic_score == 0.70
        assert res.type_score == 1.00
        assert math.isclose(res.urgency_score, 0.90, abs_tol=1e-4)
        assert res.retrieval_sources == ["semantic"]

    def test_similar_research_mode_with_freshness(self, ranker):
        cand_id = uuid.uuid4()
        work_model = ResearchWorkModel(
            id=cand_id,
            title="Transformer Networks",
            publication_year=2021,  # 5 years old in 2026 -> freshness 0.5 (half-life 5)
        )

        sim_cand = SimilarResearchResult(
            source_work_id=uuid.uuid4(),
            candidate_work_id=cand_id,
            combined_similarity=0.85,
            semantic_similarity=0.90,
            lexical_similarity=0.60,
            topic_similarity=0.80,
            rank=1,
            retrieval_sources=["semantic", "lexical"],
            candidate_work=work_model,
        )

        # Default research similarity weights: sem 0.50, lex 0.20, top 0.20, freshness 0.10 (sum 1.0)
        # final = 0.50*0.90 + 0.20*0.60 + 0.20*0.80 + 0.10*0.50
        # final = 0.45 + 0.12 + 0.16 + 0.05 = 0.78
        results = ranker.rank(
            [sim_cand],
            mode=RankingMode.RESEARCH_SIMILARITY,
            reference_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
            half_life_years=5.0,
        )

        assert len(results) == 1
        res = results[0]
        assert res.entity_id == cand_id
        assert res.final_score == 0.78
        assert res.semantic_score == 0.90
        assert res.lexical_score == 0.60
        assert res.topic_score == 0.80
        assert math.isclose(res.freshness_score, 0.50, abs_tol=1e-4)
        assert res.retrieval_sources == ["lexical", "semantic"]

    def test_adaptation_of_vector_and_lexical_and_hybrid_results(self, ranker):
        v_id = uuid.uuid4()
        l_id = uuid.uuid4()
        h_id = uuid.uuid4()

        vec_res = VectorSearchResult(entity_id=v_id, similarity=0.85, distance=0.15, entity_type="research_work")
        lex_res = LexicalSearchResult(entity_id=l_id, lexical_score=3.0, rank=1, entity_type="research_work")  # 3/(3+1)=0.75
        hyb_res = HybridSearchResult(entity_id=h_id, hybrid_score=0.03, vector_similarity=0.9, lexical_score=0.6, entity_type="research_work")

        candidates = [vec_res, lex_res, hyb_res]
        results = ranker.rank(candidates, mode=RankingMode.GENERAL)

        assert len(results) == 3
        ids = {r.entity_id for r in results}
        assert ids == {v_id, l_id, h_id}
        for r in results:
            assert 0.0 <= r.final_score <= 1.0

    def test_re_ranking_of_ranked_candidates(self, ranker):
        c_id = uuid.uuid4()
        first_ranked = RankedCandidate(
            entity_id=c_id,
            entity_type="research_work",
            rank=1,
            final_score=0.70,
            semantic_score=0.90,
            lexical_score=0.50,
            topic_score=0.60,
            type_score=0.0,
            freshness_score=0.40,
            urgency_score=0.0,
            retrieval_sources=["semantic"],
        )

        # Re-rank with pure semantic weight
        pure_sem_weights = RankerWeights(semantic_weight=1.0)
        re_ranked = ranker.rank([first_ranked], weights=pure_sem_weights)

        assert len(re_ranked) == 1
        assert re_ranked[0].entity_id == c_id
        assert re_ranked[0].final_score == 0.90

    def test_deterministic_tie_breaking(self, ranker):
        # Two candidates with exact identical scores -> broken by UUID string ascending
        id_1 = uuid.UUID("00000000-0000-0000-0000-000000000001")
        id_2 = uuid.UUID("00000000-0000-0000-0000-000000000002")

        cand1 = {"entity_id": id_1, "semantic_similarity": 0.8, "lexical_similarity": 0.5}
        cand2 = {"entity_id": id_2, "semantic_similarity": 0.8, "lexical_similarity": 0.5}

        # Input cand2 before cand1
        results = ranker.rank([cand2, cand1], mode=RankingMode.GENERAL)

        assert len(results) == 2
        assert results[0].entity_id == id_1
        assert results[1].entity_id == id_2
        assert results[0].rank == 1
        assert results[1].rank == 2

    def test_secondary_score_tie_breaking(self, ranker):
        # Same final score, but cand_a has higher semantic similarity
        id_a = uuid.uuid4()
        id_b = uuid.uuid4()

        # Custom weights: sem 0.5, lex 0.5
        # cand_a: sem 0.8, lex 0.2 -> 0.4 + 0.1 = 0.5
        # cand_b: sem 0.6, lex 0.4 -> 0.3 + 0.2 = 0.5
        cand_a = {"entity_id": id_a, "semantic_similarity": 0.8, "lexical_similarity": 0.2}
        cand_b = {"entity_id": id_b, "semantic_similarity": 0.6, "lexical_similarity": 0.4}

        weights = RankerWeights(semantic_weight=0.5, lexical_weight=0.5)
        results = ranker.rank([cand_b, cand_a], weights=weights)

        assert len(results) == 2
        assert results[0].entity_id == id_a
        assert results[1].entity_id == id_b
        assert results[0].final_score == results[1].final_score
        assert results[0].semantic_score > results[1].semantic_score

    def test_limits_enforcement(self, ranker):
        cands = [
            {"entity_id": uuid.uuid4(), "semantic_similarity": float(i) / 20.0}
            for i in range(20)
        ]

        # Default limit (10 in test fixture)
        res_default = ranker.rank(cands)
        assert len(res_default) == 10

        # Custom limit
        res_custom = ranker.rank(cands, limit=5)
        assert len(res_custom) == 5

        # Limit exceeds max_limit (50 in test fixture) -> capped to candidate count
        res_large = ranker.rank(cands, limit=999)
        assert len(res_large) == 20

        # Invalid limit raises VectorValidationError
        with pytest.raises(VectorValidationError, match="positive integer"):
            ranker.rank(cands, limit=-5)

    def test_missing_signals_graceful_degradation(self, ranker):
        cand_id = uuid.uuid4()
        # Candidate with no signals at all
        cand = {"entity_id": cand_id}
        results = ranker.rank([cand], mode=RankingMode.GENERAL)

        assert len(results) == 1
        res = results[0]
        assert res.final_score == 0.0
        assert res.semantic_score == 0.0
        assert res.lexical_score == 0.0
        assert res.topic_score == 0.0
        assert res.freshness_score == 0.0
        assert res.urgency_score == 0.0

    def test_singleton_instance_available(self):
        assert isinstance(hybrid_ranker, HybridRanker)
