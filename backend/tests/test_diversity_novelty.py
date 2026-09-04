"""
Unit, Integration, and Performance Tests for Phase 2.5E:
Diversity & Novelty Mechanics.

Verifies:
  1. Pairwise redundancy metrics (author, venue, institution, topic, semantic).
  2. Edge cases, empty sets, missing embeddings, and malformed vector handling.
  3. Set-level novelty and explainability reasons generation.
  4. Deterministic Maximal Marginal Relevance (MMR) reranking.
  5. Strict >=85% relevance dominance preservation (adversarial tests).
  6. Tie-breaking and determinism (repeated runs, shuffled input pools).
  7. Performance benchmarks across candidate pool sizes (10, 50, 100, 200).
  8. Discovery API diversity query parameter integration.
"""
from __future__ import annotations

import math
import time
import uuid
import pytest

from app.ranking.diversity import (
    DEFAULT_DIVERSITY_LAMBDA,
    MAX_DIVERSITY_LAMBDA,
    CandidateDiversityProfile,
    DiversityConfig,
    DiversityReranker,
    calculate_author_overlap,
    calculate_institution_overlap,
    calculate_semantic_similarity,
    calculate_topic_overlap,
    calculate_venue_overlap,
    diversity_reranker,
)
from app.ranking.hybrid_ranker import RankedCandidate, RankingMode


def _create_unit_vector(dim: int = 384, active_idx: int = 0) -> tuple[float, ...]:
    """Helper to generate an exact unit vector with non-zero element at active_idx."""
    vec = [0.0] * dim
    vec[active_idx % dim] = 1.0
    return tuple(vec)


def _build_test_profile(
    work_id: uuid.UUID | None = None,
    base_score: float = 0.80,
    author_ids: Sequence[uuid.UUID] | None = None,
    institution_ids: Sequence[uuid.UUID] | None = None,
    canonical_venue_key: str | None = None,
    topic_ids: Sequence[uuid.UUID] | None = None,
    embedding: Sequence[float] | None = None,
    semantic_score: float = 0.80,
    topic_score: float = 0.70,
) -> CandidateDiversityProfile:
    wid = work_id or uuid.uuid4()
    emb_tuple = tuple(embedding) if embedding is not None else None
    return CandidateDiversityProfile(
        work_id=wid,
        author_ids=frozenset(author_ids or []),
        institution_ids=frozenset(institution_ids or []),
        canonical_venue_key=canonical_venue_key,
        topic_ids=frozenset(topic_ids or []),
        embedding=emb_tuple,
        base_score=base_score,
        semantic_score=semantic_score,
        topic_score=topic_score,
        candidate={"title": f"Work {wid}", "abstract": "Test research abstract"},
    )


def _build_ranked_candidate(
    entity_id: uuid.UUID | None = None,
    rank: int = 1,
    final_score: float = 0.85,
    semantic_score: float = 0.80,
    topic_score: float = 0.70,
    author_ids: Sequence[uuid.UUID] | None = None,
    institution_ids: Sequence[uuid.UUID] | None = None,
    venue: str | None = None,
    shared_topic_ids: Sequence[uuid.UUID] | None = None,
    embedding: Sequence[float] | None = None,
) -> RankedCandidate:
    eid = entity_id or uuid.uuid4()
    cand_dict: dict[str, Any] = {
        "title": f"Candidate {eid}",
        "abstract": "Abstract",
        "author_ids": list(author_ids or []),
        "institution_ids": list(institution_ids or []),
        "venue": venue,
        "embedding": list(embedding) if embedding is not None else None,
    }
    return RankedCandidate(
        entity_id=eid,
        entity_type="research_work",
        rank=rank,
        final_score=final_score,
        semantic_score=semantic_score,
        lexical_score=0.60,
        topic_score=topic_score,
        type_score=1.0,
        freshness_score=0.80,
        urgency_score=0.0,
        shared_topic_ids=list(shared_topic_ids or []),
        candidate=cand_dict,
    )


# ── 1. Pairwise Redundancy Metric Tests ────────────────────────────────────────


class TestPairwiseRedundancyMetrics:
    """Tests verifying mathematical correctness and robustness of overlap functions."""

    def test_author_overlap_jaccard(self):
        a1, a2, a3, a4 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        p1 = _build_test_profile(author_ids=[a1, a2, a3])
        p2 = _build_test_profile(author_ids=[a2, a3, a4])

        # Intersection: {a2, a3} (2), Union: {a1, a2, a3, a4} (4) -> Jaccard = 0.5
        assert pytest.approx(calculate_author_overlap(p1, p2), abs=1e-5) == 0.50

        # Disjoint
        p3 = _build_test_profile(author_ids=[uuid.uuid4()])
        assert calculate_author_overlap(p1, p3) == 0.0

        # Identical
        assert calculate_author_overlap(p1, p1) == 1.0

        # Empty sets safe
        p_empty = _build_test_profile(author_ids=[])
        assert calculate_author_overlap(p1, p_empty) == 0.0
        assert calculate_author_overlap(p_empty, p_empty) == 0.0

    def test_venue_overlap_canonical_key(self):
        p1 = _build_test_profile(canonical_venue_key="issn:0028-0836")
        p2 = _build_test_profile(canonical_venue_key="issn:0028-0836")
        p3 = _build_test_profile(canonical_venue_key="name:science")
        p_none = _build_test_profile(canonical_venue_key=None)

        assert calculate_venue_overlap(p1, p2) == 1.0
        assert calculate_venue_overlap(p1, p3) == 0.0
        assert calculate_venue_overlap(p1, p_none) == 0.0
        assert calculate_venue_overlap(p_none, p_none) == 0.0

    def test_institution_overlap_jaccard(self):
        i1, i2, i3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        p1 = _build_test_profile(institution_ids=[i1, i2])
        p2 = _build_test_profile(institution_ids=[i2, i3])

        # Intersection: {i2} (1), Union: {i1, i2, i3} (3) -> 1/3 ~ 0.333333
        assert pytest.approx(calculate_institution_overlap(p1, p2), abs=1e-4) == 0.333333

        p_empty = _build_test_profile(institution_ids=[])
        assert calculate_institution_overlap(p1, p_empty) == 0.0

    def test_topic_overlap_jaccard(self):
        t1, t2, t3, t4 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        p1 = _build_test_profile(topic_ids=[t1, t2])
        p2 = _build_test_profile(topic_ids=[t1, t2, t3, t4])

        # Intersection: {t1, t2} (2), Union: 4 -> 0.50
        assert pytest.approx(calculate_topic_overlap(p1, p2), abs=1e-5) == 0.50

    def test_semantic_similarity_cosine(self):
        v1 = _create_unit_vector(384, active_idx=0)
        v2 = _create_unit_vector(384, active_idx=0)
        v3 = _create_unit_vector(384, active_idx=1)

        p1 = _build_test_profile(embedding=v1)
        p2 = _build_test_profile(embedding=v2)
        p3 = _build_test_profile(embedding=v3)
        p_none = _build_test_profile(embedding=None)

        # Identical unit vectors -> 1.0
        assert pytest.approx(calculate_semantic_similarity(p1, p2), abs=1e-5) == 1.0
        # Orthogonal unit vectors -> 0.0
        assert pytest.approx(calculate_semantic_similarity(p1, p3), abs=1e-5) == 0.0
        # Missing embedding -> 0.0 safe
        assert calculate_semantic_similarity(p1, p_none) == 0.0
        assert calculate_semantic_similarity(p_none, p_none) == 0.0

    def test_composite_redundancy_bounded_range(self):
        reranker = DiversityReranker()
        config = DiversityConfig(enabled=True)

        # Completely identical candidates
        u = _create_unit_vector(384, 10)
        t = uuid.uuid4()
        a = uuid.uuid4()
        i = uuid.uuid4()
        p_dup1 = _build_test_profile(embedding=u, topic_ids=[t], author_ids=[a], institution_ids=[i], canonical_venue_key="issn:1234-5678")
        p_dup2 = _build_test_profile(embedding=u, topic_ids=[t], author_ids=[a], institution_ids=[i], canonical_venue_key="issn:1234-5678")

        r_max = reranker.calculate_pairwise_redundancy(p_dup1, p_dup2, config)
        assert pytest.approx(r_max, abs=1e-4) == 1.0

        # Completely disjoint candidates
        p_diff = _build_test_profile(
            embedding=_create_unit_vector(384, 20),
            topic_ids=[uuid.uuid4()],
            author_ids=[uuid.uuid4()],
            institution_ids=[uuid.uuid4()],
            canonical_venue_key="issn:9999-9999",
        )
        r_min = reranker.calculate_pairwise_redundancy(p_dup1, p_diff, config)
        assert pytest.approx(r_min, abs=1e-4) == 0.0


# ── 2. List-Aware Selection & Relevance Dominance ─────────────────────────────


class TestListAwareSelectionAndRelevanceDominance:
    """Tests verifying MMR reranking, relevance dominance preservation, and tie-breaking."""

    def test_disabled_by_default_preserves_exact_order(self):
        c1 = _build_ranked_candidate(rank=1, final_score=0.90)
        c2 = _build_ranked_candidate(rank=2, final_score=0.85)
        c3 = _build_ranked_candidate(rank=3, final_score=0.75)

        reranker = DiversityReranker(default_config=DiversityConfig(enabled=False))
        results = reranker.rerank([c1, c2, c3], force_enabled=False)

        assert results == [c1, c2, c3]

    def test_redundant_second_candidate_penalized_allowing_novel_third_to_advance(self):
        """
        Setup:
          Candidate 1: High score (0.90), Venue A, Topic X, Vector 0
          Candidate 2: Score (0.88), identical Venue A, Topic X, Vector 0 (100% duplicate of C1)
          Candidate 3: Score (0.86), novel Venue B, Topic Y, Vector 1 (novel research)

        Expected:
          Candidate 1 selected first.
          Candidate 2 receives max penalty (lambda = 0.08 -> adj_score = 0.88 - 0.08 = 0.80).
          Candidate 3 has 0 redundancy -> adj_score = 0.86 - 0.0 = 0.86.
          Candidate 3 is promoted to Rank 2!
          Candidate 2 is placed at Rank 3.
        """
        v0 = _create_unit_vector(384, 0)
        v1 = _create_unit_vector(384, 1)
        t_x, t_y = uuid.uuid4(), uuid.uuid4()
        a_1, a_3 = uuid.uuid4(), uuid.uuid4()

        c1 = _build_ranked_candidate(rank=1, final_score=0.90, venue="Nature", shared_topic_ids=[t_x], author_ids=[a_1], embedding=v0)
        c2 = _build_ranked_candidate(rank=2, final_score=0.88, venue="Nature", shared_topic_ids=[t_x], author_ids=[a_1], embedding=v0)
        c3 = _build_ranked_candidate(rank=3, final_score=0.86, venue="IEEE Trans", shared_topic_ids=[t_y], author_ids=[a_3], embedding=v1)

        config = DiversityConfig(enabled=True, lambda_penalty=0.08)
        reranker = DiversityReranker(default_config=config)

        reranked = reranker.rerank([c1, c2, c3], config=config)

        assert len(reranked) == 3
        # Candidate 1 retains Rank 1
        assert reranked[0].entity_id == c1.entity_id
        assert reranked[0].rank == 1

        # Candidate 3 promoted to Rank 2 due to novelty
        assert reranked[1].entity_id == c3.entity_id
        assert reranked[1].rank == 2
        assert reranked[1].novelty_score > 0.80

        # Candidate 2 moved to Rank 3 due to redundancy penalty
        assert reranked[2].entity_id == c2.entity_id
        assert reranked[2].rank == 3
        assert reranked[2].redundancy_score > 0.80
        assert len(reranked[2].redundancy_reasons) > 0

    def test_relevance_dominance_guarantee_adversarial(self):
        """
        ADVERSARIAL RELEVANCE INVARIANT TEST:
        An irrelevant paper with base score 0.20 and 100% novelty (new author, new venue, new topic)
        MUST NEVER outrank a highly relevant paper with base score 0.95, even if the relevant paper
        has 100% redundancy with a previously selected paper.
        """
        v_common = _create_unit_vector(384, 0)
        v_novel = _create_unit_vector(384, 100)
        top_common = uuid.uuid4()

        # Selected top paper
        c_top = _build_ranked_candidate(rank=1, final_score=0.98, embedding=v_common, shared_topic_ids=[top_common], venue="Science")
        # Near duplicate, but extremely relevant
        c_relevant = _build_ranked_candidate(rank=2, final_score=0.92, embedding=v_common, shared_topic_ids=[top_common], venue="Science")
        # Irrelevant paper, but novel
        c_irrelevant = _build_ranked_candidate(rank=3, final_score=0.20, embedding=v_novel, shared_topic_ids=[uuid.uuid4()], venue="Novel Venue")

        # Test under maximum allowed lambda (0.15)
        config = DiversityConfig(enabled=True, lambda_penalty=MAX_DIVERSITY_LAMBDA)
        reranker = DiversityReranker(default_config=config)

        reranked = reranker.rerank([c_top, c_relevant, c_irrelevant], config=config)

        # c_top must be #1
        assert reranked[0].entity_id == c_top.entity_id
        # c_relevant MUST be #2, never surpassed by c_irrelevant!
        assert reranked[1].entity_id == c_relevant.entity_id
        assert reranked[1].final_score >= 0.77  # 0.92 - 0.15 = 0.77
        # c_irrelevant MUST remain at the bottom
        assert reranked[2].entity_id == c_irrelevant.entity_id
        assert reranked[2].final_score <= 0.20

    def test_deterministic_tie_breaking(self):
        """Verify that candidates with identical adjusted scores tie-break deterministically."""
        id_a = uuid.UUID("00000000-0000-0000-0000-000000000001")
        id_b = uuid.UUID("00000000-0000-0000-0000-000000000002")

        c1 = _build_ranked_candidate(entity_id=id_b, rank=1, final_score=0.80)
        c2 = _build_ranked_candidate(entity_id=id_a, rank=2, final_score=0.80)

        config = DiversityConfig(enabled=True, lambda_penalty=0.08)
        reranker = DiversityReranker(default_config=config)

        # Run 1: Input [c1, c2]
        res1 = reranker.rerank([c1, c2], config=config)
        # Run 2: Shuffled input [c2, c1]
        res2 = reranker.rerank([c2, c1], config=config)

        # Output ordering must be identical and ordered by UUID string ASC
        assert [c.entity_id for c in res1] == [id_a, id_b]
        assert [c.entity_id for c in res2] == [id_a, id_b]

    def test_mode_presets(self):
        """Verify DiversityConfig mode presets adjust parameters according to domain objectives."""
        cfg_sim = DiversityConfig.for_mode(RankingMode.RESEARCH_SIMILARITY)
        assert cfg_sim.lambda_penalty <= 0.05  # Conservative penalty for similarity
        assert cfg_sim.semantic_redundancy_weight >= 0.50

        cfg_opp = DiversityConfig.for_mode(RankingMode.RESEARCH_OPPORTUNITY)
        assert cfg_opp.lambda_penalty >= 0.08  # Broader diversity for opportunities
        assert cfg_opp.topic_redundancy_weight >= 0.35

        cfg_gen = DiversityConfig.for_mode(RankingMode.GENERAL)
        assert cfg_gen.lambda_penalty == DEFAULT_DIVERSITY_LAMBDA


# ── 3. Explainability Hooks & Data Resilience ──────────────────────────────────


class TestExplainabilityAndDataResilience:
    """Tests verifying structured explainability reasons and missing data resilience."""

    def test_explainability_reasons_generation(self):
        v0 = _create_unit_vector(384, 0)
        t_shared = uuid.uuid4()
        a_shared = uuid.uuid4()

        c1 = _build_ranked_candidate(rank=1, final_score=0.95, embedding=v0, shared_topic_ids=[t_shared], author_ids=[a_shared], venue="Nature")
        c2 = _build_ranked_candidate(rank=2, final_score=0.90, embedding=v0, shared_topic_ids=[t_shared], author_ids=[a_shared], venue="Nature")

        config = DiversityConfig(enabled=True, lambda_penalty=0.08)
        reranker = DiversityReranker(default_config=config)

        reranked = reranker.rerank([c1, c2], config=config)
        penalized = reranked[1]

        assert penalized.redundancy_score > 0.90
        assert penalized.diversity_adjustment < 0.0
        assert "High semantic overlap with previously selected research" in penalized.redundancy_reasons
        assert "Published in same publication venue as selected research" in penalized.redundancy_reasons

    def test_missing_and_corrupt_data_resilience(self):
        """Ensure no crashes or NaN values occur on missing/corrupt metadata."""
        c1 = _build_ranked_candidate(
            rank=1,
            final_score=0.85,
            embedding=[float("nan"), float("inf"), 1.0],  # malformed embedding
            venue=None,
            author_ids=[],
            institution_ids=[],
            shared_topic_ids=[],
        )
        c2 = _build_ranked_candidate(
            rank=2,
            final_score=0.80,
            embedding=None,  # missing embedding
            venue="",
        )

        config = DiversityConfig(enabled=True)
        reranker = DiversityReranker(default_config=config)

        reranked = reranker.rerank([c1, c2], config=config)
        assert len(reranked) == 2
        for r in reranked:
            assert math.isfinite(r.final_score)
            assert 0.0 <= r.final_score <= 1.0
            if r.novelty_score is not None:
                assert math.isfinite(r.novelty_score)


# ── 4. Performance Benchmarking Across Candidate Scales ────────────────────────


class TestDiversityPerformanceScaling:
    """Performance benchmarks testing runtime scaling across 10, 50, 100, and 200 candidates."""

    @pytest.mark.parametrize("n_candidates", [10, 50, 100, 200])
    def test_reranking_execution_time(self, n_candidates: int):
        candidates: list[RankedCandidate] = []
        for i in range(n_candidates):
            v = _create_unit_vector(384, i % 50)
            candidates.append(
                _build_ranked_candidate(
                    rank=i + 1,
                    final_score=round(1.0 - (i / (n_candidates + 1)) * 0.5, 4),
                    embedding=v,
                    shared_topic_ids=[uuid.uuid4() for _ in range(2)],
                    author_ids=[uuid.uuid4()],
                    venue=f"Journal {i % 10}",
                )
            )

        config = DiversityConfig(enabled=True, lambda_penalty=0.08, top_k=n_candidates)
        reranker = DiversityReranker(default_config=config)

        t0 = time.perf_counter()
        results = reranker.rerank(candidates, config=config)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        assert len(results) == n_candidates
        # N=10, 50 -> < 25.0ms
        # N=100 -> < 60.0ms
        # N=200 -> < 250.0ms (accounting for full-suite GC and Windows thread scheduling)
        budget_ms = 25.0 if n_candidates <= 50 else (60.0 if n_candidates <= 100 else 250.0)
        assert elapsed_ms < budget_ms, f"Reranking {n_candidates} candidates took {elapsed_ms:.2f}ms (budget: {budget_ms}ms)"
