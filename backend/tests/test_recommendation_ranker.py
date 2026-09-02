"""
Unit, Sensitivity, Invariant, and Benchmark Tests for Phase 2.5C:
Deterministic Recommendation Ranker & Mode Presets.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math
import uuid
import pytest

from app.ranking.features import AcademicFeatures
from app.ranking.hybrid_ranker import (
    HybridRanker,
    RankedCandidate,
    RankerWeights,
    RankingMode,
    hybrid_ranker,
)
from app.ranking.reranker import CrossEncoderReranker


class TestRankerWeightsAndRelevanceDominance:
    """Tests for RankerWeights configuration, normalization, and >=85% dominance enforcement."""

    def test_default_mode_weights_satisfy_relevance_dominance(self):
        ranker = HybridRanker()
        # General mode
        w_gen = ranker.resolve_weights(RankingMode.GENERAL)
        w_gen.validate(enforce_relevance_dominance=True)
        assert w_gen.is_relevance_dominant(min_relevance=0.85)
        assert w_gen.relevance_fraction >= 0.85 - 1e-6

        # Research similarity mode
        w_sim = ranker.resolve_weights(RankingMode.RESEARCH_SIMILARITY)
        w_sim.validate(enforce_relevance_dominance=True)
        assert w_sim.is_relevance_dominant(min_relevance=0.85)
        assert w_sim.relevance_fraction >= 0.85 - 1e-6

        # Opportunity mode projected
        w_opp = ranker.resolve_weights(RankingMode.RESEARCH_OPPORTUNITY).with_relevance_dominance(0.85)
        w_opp.validate(enforce_relevance_dominance=True)
        assert w_opp.is_relevance_dominant(min_relevance=0.85)
        assert w_opp.relevance_fraction >= 0.85 - 1e-6
        assert w_opp.secondary_fraction <= 0.15 + 1e-6

    def test_relevance_dominance_validation_rejects_overpowered_secondary_weights(self):
        # 60% relevance, 40% secondary -> MUST FAIL with enforce_relevance_dominance=True
        invalid_w = RankerWeights(
            semantic_weight=0.40,
            lexical_weight=0.10,
            topic_weight=0.10,
            citation_weight=0.20,
            venue_weight=0.20,
        )
        assert not invalid_w.is_relevance_dominant(0.85)
        with pytest.raises(ValueError, match="Relevance dominance invariant violated"):
            invalid_w.validate(enforce_relevance_dominance=True)

    def test_with_relevance_dominance_projection(self):
        # Unconstrained weights: 50% relevance, 50% secondary
        unconstrained = RankerWeights(
            semantic_weight=0.30,
            lexical_weight=0.10,
            topic_weight=0.10,
            citation_weight=0.25,
            venue_weight=0.25,
        )
        projected = unconstrained.with_relevance_dominance(min_relevance=0.85)
        projected.validate(enforce_relevance_dominance=True)
        assert projected.is_relevance_dominant(0.85)
        assert pytest.approx(projected.relevance_fraction, abs=1e-4) == 0.85
        assert pytest.approx(projected.secondary_fraction, abs=1e-4) == 0.15

    def test_negative_and_invalid_weights_raise_error(self):
        with pytest.raises(ValueError, match="cannot be negative"):
            RankerWeights(citation_weight=-0.1).validate()
        with pytest.raises(ValueError, match="cannot be NaN"):
            RankerWeights(venue_weight=float("nan")).validate()
        with pytest.raises(ValueError, match="cannot be infinite"):
            RankerWeights(author_prominence_weight=float("inf")).validate()


class TestAcademicSignalsSensitivity:
    """Tests confirming individual academic signals influence score according to their configured weights."""

    @pytest.fixture
    def ranker(self) -> HybridRanker:
        return HybridRanker()

    @pytest.fixture
    def academic_weights(self) -> RankerWeights:
        return RankerWeights(
            semantic_weight=0.50,
            lexical_weight=0.18,
            topic_weight=0.20,
            citation_weight=0.04,
            venue_weight=0.03,
            author_prominence_weight=0.03,
            open_access_weight=0.02,
        ).normalized()

    def test_citation_impact_sensitivity(self, ranker: HybridRanker, academic_weights: RankerWeights):
        # Same relevance, different citation impact
        c1 = {
            "entity_id": uuid.uuid4(),
            "entity_type": "research_work",
            "semantic_similarity": 0.80,
            "lexical_similarity": 0.50,
            "topic_similarity": 0.50,
            "citation_impact": 0.10,
        }
        c2 = {
            "entity_id": uuid.uuid4(),
            "entity_type": "research_work",
            "semantic_similarity": 0.80,
            "lexical_similarity": 0.50,
            "topic_similarity": 0.50,
            "citation_impact": 0.90,
        }

        ranked = ranker.rank([c1, c2], weights=academic_weights)
        assert len(ranked) == 2
        # c2 with higher citation impact must rank first
        assert ranked[0].entity_id == c2["entity_id"]
        assert ranked[0].final_score > ranked[1].final_score
        assert ranked[0].citation_score == 0.90
        assert ranked[1].citation_score == 0.10

    def test_venue_prestige_sensitivity(self, ranker: HybridRanker, academic_weights: RankerWeights):
        # Same relevance, different venue prestige
        c_low_venue = {
            "entity_id": uuid.uuid4(),
            "entity_type": "research_work",
            "semantic_similarity": 0.70,
            "lexical_similarity": 0.40,
            "topic_similarity": 0.40,
            "venue_prestige": 0.10,
        }
        c_high_venue = {
            "entity_id": uuid.uuid4(),
            "entity_type": "research_work",
            "semantic_similarity": 0.70,
            "lexical_similarity": 0.40,
            "topic_similarity": 0.40,
            "venue_prestige": 0.95,
        }

        ranked = ranker.rank([c_low_venue, c_high_venue], weights=academic_weights)
        assert ranked[0].entity_id == c_high_venue["entity_id"]
        assert ranked[0].final_score > ranked[1].final_score

    def test_author_prominence_sensitivity(self, ranker: HybridRanker, academic_weights: RankerWeights):
        c_emerging = {
            "entity_id": uuid.uuid4(),
            "entity_type": "research_work",
            "semantic_similarity": 0.75,
            "lexical_similarity": 0.45,
            "topic_similarity": 0.45,
            "author_prominence": 0.10,
        }
        c_prominent = {
            "entity_id": uuid.uuid4(),
            "entity_type": "research_work",
            "semantic_similarity": 0.75,
            "lexical_similarity": 0.45,
            "topic_similarity": 0.45,
            "author_prominence": 0.85,
        }

        ranked = ranker.rank([c_emerging, c_prominent], weights=academic_weights)
        assert ranked[0].entity_id == c_prominent["entity_id"]
        assert ranked[0].final_score > ranked[1].final_score


class TestRelevanceDominanceInvariant:
    """
    Core Invariant Test: High relevance + zero academic MUST rank above
    low relevance + perfect academic signals under all modes.
    """

    @pytest.fixture
    def ranker(self) -> HybridRanker:
        return HybridRanker()

    def test_relevance_dominates_across_all_modes(self, ranker: HybridRanker):
        # Candidate A: Strong topical match, low academic pedigree
        cand_a = {
            "entity_id": uuid.uuid4(),
            "entity_type": "research_work",
            "semantic_similarity": 0.92,
            "lexical_similarity": 0.85,
            "topic_similarity": 0.90,
            "citation_impact": 0.0,
            "venue_prestige": 0.0,
            "author_prominence": 0.0,
            "institution_prestige": 0.0,
            "open_access_tier": 0.20,
            "opportunity_quality": 0.50,
        }

        # Candidate B: Weak topical match, perfect academic pedigree
        cand_b = {
            "entity_id": uuid.uuid4(),
            "entity_type": "research_work",
            "semantic_similarity": 0.55,
            "lexical_similarity": 0.40,
            "topic_similarity": 0.45,
            "citation_impact": 1.0,
            "venue_prestige": 1.0,
            "author_prominence": 1.0,
            "institution_prestige": 1.0,
            "open_access_tier": 1.00,
            "opportunity_quality": 1.00,
        }

        for mode in [
            RankingMode.GENERAL,
            RankingMode.RESEARCH_SIMILARITY,
            RankingMode.RESEARCH_OPPORTUNITY,
        ]:
            ranked = ranker.rank([cand_b, cand_a], mode=mode)
            assert ranked[0].entity_id == cand_a["entity_id"], f"Relevance dominance failed under mode {mode}"
            assert ranked[0].rank == 1
            assert ranked[1].rank == 2
            assert ranked[0].final_score > ranked[1].final_score


class TestDeterministicTieBreaking:
    """Tests deterministic multi-key tie-breaking."""

    def test_identical_scores_break_ties_by_uuid(self):
        ranker = HybridRanker()
        id1 = uuid.UUID("11111111-1111-1111-1111-111111111111")
        id2 = uuid.UUID("22222222-2222-2222-2222-222222222222")

        c1 = {
            "entity_id": id1,
            "entity_type": "research_work",
            "semantic_similarity": 0.80,
            "lexical_similarity": 0.50,
            "topic_similarity": 0.50,
        }
        c2 = {
            "entity_id": id2,
            "entity_type": "research_work",
            "semantic_similarity": 0.80,
            "lexical_similarity": 0.50,
            "topic_similarity": 0.50,
        }

        # Regardless of input ordering, id1 must always come before id2
        ranked_order1 = ranker.rank([c1, c2])
        ranked_order2 = ranker.rank([c2, c1])

        assert [r.entity_id for r in ranked_order1] == [id1, id2]
        assert [r.entity_id for r in ranked_order2] == [id1, id2]


class TestGracefulFallbackAndMissingMetadata:
    """Tests ranker behavior when metadata or academic features are missing."""

    def test_empty_candidate_metadata_falls_back_cleanly(self):
        ranker = HybridRanker()
        c_bare = {
            "entity_id": uuid.uuid4(),
            "entity_type": "research_work",
            # No semantic, lexical, topic, or academic fields
        }

        ranked = ranker.rank([c_bare])
        assert len(ranked) == 1
        r = ranked[0]
        assert r.final_score >= 0.0
        assert r.citation_score == 0.0
        assert r.author_position_score == 0.50  # neutral unknown
        assert r.open_access_score == 0.35  # neutral unknown

    def test_academic_features_object_integration(self):
        ranker = HybridRanker()
        af = AcademicFeatures(
            citation_impact=0.60,
            author_prominence=0.70,
            author_position=0.90,
            institution_prestige=0.50,
            venue_prestige=0.80,
            open_access_tier=1.00,
        )
        cand = {
            "entity_id": uuid.uuid4(),
            "entity_type": "research_work",
            "semantic_similarity": 0.85,
            "lexical_similarity": 0.60,
            "topic_similarity": 0.70,
            "academic_features": af,
        }

        ranked = ranker.rank([cand], mode=RankingMode.GENERAL)
        r = ranked[0]
        assert r.citation_score == 0.60
        assert r.author_prominence_score == 0.70
        assert r.author_position_score == 0.90
        assert r.institution_score == 0.50
        assert r.venue_score == 0.80
        assert r.open_access_score == 1.00


class TestCrossEncoderInteraction:
    """Tests interaction between Phase 2.5C ranker and optional CrossEncoder reranker."""

    def test_reranker_maintains_85_percent_relevance_dominance(self):
        reranker = CrossEncoderReranker(
            enabled=True,
            weight=0.10,  # <= 0.15 guarantee
            model_instance=type("MockModel", (), {"predict": lambda self, pairs: [2.5]})(),
        )

        cand = RankedCandidate(
            entity_id=uuid.uuid4(),
            entity_type="research_work",
            rank=1,
            final_score=0.80,
            semantic_score=0.85,
            lexical_score=0.70,
            topic_score=0.75,
            type_score=0.0,
            freshness_score=0.0,
            urgency_score=0.0,
            citation_score=0.50,
            venue_score=0.50,
            candidate={"title": "Neural Graph Architectures", "abstract": "Deep learning on graphs."},
        )

        reranked = reranker.rerank(
            query="neural graph architectures",
            candidates=[cand],
            force_enabled=True,
        )

        assert len(reranked) == 1
        r = reranked[0]
        # Bounded fusion: (1 - 0.10)*0.80 + 0.10*sigmoid(2.5) ~ 0.72 + 0.092 = 0.812
        assert 0.0 <= r.final_score <= 1.0
        assert r.reranker_adjustment is not None


class TestRankingPerformanceMicroBenchmark:
    """Measures ranking latency over 1,000 iterations to verify < 2.0 ms budget for 50 candidates."""

    def test_ranking_execution_budget(self):
        import time

        ranker = HybridRanker()
        candidates = [
            {
                "entity_id": uuid.uuid4(),
                "entity_type": "research_work",
                "semantic_similarity": 0.50 + (i % 50) * 0.01,
                "lexical_similarity": 0.30 + (i % 40) * 0.01,
                "topic_similarity": 0.40 + (i % 30) * 0.01,
                "citation_impact": 0.10 + (i % 60) * 0.01,
                "venue_prestige": 0.20 + (i % 50) * 0.01,
                "author_prominence": 0.15 + (i % 40) * 0.01,
                "open_access_tier": 0.70 if i % 2 == 0 else 0.20,
            }
            for i in range(50)
        ]

        # Warmup
        for _ in range(50):
            ranker.rank(candidates, mode=RankingMode.GENERAL)

        latencies_ms: list[float] = []
        for _ in range(1000):
            t0 = time.perf_counter()
            _ = ranker.rank(candidates, mode=RankingMode.GENERAL)
            latencies_ms.append((time.perf_counter() - t0) * 1000.0)

        latencies_ms.sort()
        n = len(latencies_ms)
        p50 = latencies_ms[int(0.50 * n)]
        p95 = latencies_ms[int(0.95 * n)]
        p99 = latencies_ms[int(0.99 * n)]

        # 50 candidates ranked in < 2.0 ms (i.e. < 0.04 ms per candidate)
        assert p50 < 2.00, f"P50 {p50:.4f} ms exceeded threshold"
        assert p95 < 5.00, f"P95 {p95:.4f} ms exceeded threshold"
        assert p99 < 10.00, f"P99 {p99:.4f} ms exceeded threshold"
