"""
Phase 2.5G — Empirical Evaluation, Ablation & Benchmark Hardening Test Suite.

Verifies:
  1. Empirical metric calculations (HHI, pairwise Jaccard, cosine, novelty, Kendall tau, top-k overlap).
  2. Dataset quality audit, slice distributions, and ceiling effect warnings.
  3. Progressive ranking stages R0-R5 and relevance preservation.
  4. Systematic ablation of academic quality, cross-encoder, and diversity signals.
  5. Weight sensitivity sweeps and architectural boundary clamping (<= 0.15).
  6. Statistical significance tests (paired bootstrap, Wilcoxon signed-rank).
  7. Ranking stability and multi-key deterministic tie-breaking.
  8. Zero N+1 database queries verification during ranking and explainability.
  9. Production recommendation generation with strict evidence gates.
"""
import uuid
import pytest

from app.evaluation.benchmark_runner import BenchmarkRunner
from app.evaluation.metrics import (
    concentration_hhi,
    kendall_tau_correlation,
    mean_novelty_at_k,
    mean_pairwise_cosine,
    mean_pairwise_jaccard,
    mean_rank_displacement,
    min_novelty_at_k,
    paired_bootstrap_test,
    top_k_overlap_ratio,
    unique_elements_at_k,
    wilcoxon_signed_rank_test,
)
from app.ranking.diversity import (
    CandidateDiversityProfile,
    DiversityConfig,
    DiversityReranker,
    MAX_DIVERSITY_LAMBDA,
)
from app.ranking.hybrid_ranker import (
    HybridRanker,
    RankedCandidate,
    RankerWeights,
    RankingMode,
)


@pytest.fixture
def runner() -> BenchmarkRunner:
    return BenchmarkRunner()


# ── 1. Empirical List Quality & Stability Metric Tests ────────────────────────


def test_unique_elements_at_k():
    items = [["a", "b"], ["b", "c"], ["d"], ["a"]]
    assert unique_elements_at_k(items, k=2) == 3  # 'a', 'b', 'c'
    assert unique_elements_at_k(items, k=3) == 4  # 'a', 'b', 'c', 'd'
    assert unique_elements_at_k(items, k=10) == 4
    assert unique_elements_at_k([], k=5) == 0

    # Test single-item sequences
    single_items = ["ven1", "ven2", "ven1", "ven3"]
    assert unique_elements_at_k(single_items, k=2) == 2
    assert unique_elements_at_k(single_items, k=3) == 2


def test_concentration_hhi():
    # Perfectly dispersed: 4 unique items -> each share = 0.25 -> HHI = 4 * (0.25^2) = 0.25
    items = ["a", "b", "c", "d"]
    assert pytest.approx(concentration_hhi(items, k=4), abs=1e-3) == 0.25

    # Completely concentrated: 4 identical items -> share = 1.0 -> HHI = 1.0
    items_monopoly = ["a", "a", "a", "a"]
    assert pytest.approx(concentration_hhi(items_monopoly, k=4), abs=1e-3) == 1.0

    # Empty list
    assert concentration_hhi([], k=5) == 0.0


def test_pairwise_redundancy_metrics():
    # Jaccard sets
    identical_sets = [frozenset(["t1", "t2"]), frozenset(["t1", "t2"])]
    assert pytest.approx(mean_pairwise_jaccard(identical_sets, k=2), abs=1e-3) == 1.0

    disjoint_sets = [frozenset(["t1"]), frozenset(["t2"])]
    assert pytest.approx(mean_pairwise_jaccard(disjoint_sets, k=2), abs=1e-3) == 0.0

    # Cosine vectors
    v1 = (1.0, 0.0)
    v2 = (0.0, 1.0)
    assert pytest.approx(mean_pairwise_cosine([v1, v2], k=2), abs=1e-3) == 0.0

    v_same = (0.7071, 0.7071)
    assert pytest.approx(mean_pairwise_cosine([v_same, v_same], k=2), abs=1e-3) == 1.0


def test_novelty_metrics():
    scores = [1.0, 0.8, 0.6, 0.4]
    assert pytest.approx(mean_novelty_at_k(scores, k=3), abs=1e-3) == 0.8
    assert pytest.approx(min_novelty_at_k(scores, k=3), abs=1e-3) == 0.6
    assert mean_novelty_at_k([], k=5) == 0.0
    assert min_novelty_at_k([], k=5) == 0.0


def test_stability_metrics():
    list_a = ["id1", "id2", "id3", "id4", "id5"]
    list_b = ["id1", "id2", "id3", "id4", "id5"]
    list_rev = ["id5", "id4", "id3", "id2", "id1"]

    # Identical
    assert kendall_tau_correlation(list_a, list_b) == 1.0
    assert top_k_overlap_ratio(list_a, list_b, k=5) == 1.0
    assert mean_rank_displacement(list_a, list_b) == 0.0

    # Inverted
    assert kendall_tau_correlation(list_a, list_rev) == -1.0
    assert top_k_overlap_ratio(list_a, list_rev, k=5) == 1.0
    assert mean_rank_displacement(list_a, list_rev) == 2.4


# ── 2. Dataset Quality Audit Tests ────────────────────────────────────────────


def test_dataset_audit(runner: BenchmarkRunner):
    audit = runner.evaluate_dataset_audit()

    assert audit["total_queries"] == 108
    assert audit["total_candidates"] > 0
    assert len(audit["discipline_distribution"]) >= 6
    assert len(audit["difficulty_distribution"]) >= 3
    assert audit["slice_distribution"]["acronyms"]["count"] > 0
    assert audit["slice_distribution"]["interdisciplinary"]["count"] > 0
    assert audit["slice_distribution"]["ambiguous"]["count"] > 0

    # Ceiling effect check must be documented
    ceiling_info = audit["ceiling_effect_audit"]
    assert ceiling_info["has_ceiling_effect"] is True
    assert "primary_cause" in ceiling_info
    assert "evaluation_interpretation" in ceiling_info


# ── 3. Progressive Ranking Stages & Relevance Preservation ────────────────────


def test_progressive_ranking_stages(runner: BenchmarkRunner):
    stages = runner.evaluate_progressive_ranking_stages()

    required_stages = [
        "R0_raw_retrieval",
        "R1_hybrid_relevance",
        "R2_hybrid_academic",
        "R3_hybrid_academic_rerank",
        "R4_hybrid_academic_diversity",
        "R5_hybrid_academic_div_novelty",
    ]
    for st in required_stages:
        assert st in stages
        data = stages[st]
        assert "mean_ndcg_at_5" in data
        assert "mean_mrr" in data
        assert "delta_ndcg_at_5_vs_r1" in data
        assert "relevance_preservation_passed" in data
        # Invariant: diversity and novelty must preserve relevance
        assert data["relevance_preservation_passed"] is True


# ── 4. Systematic Ablations ───────────────────────────────────────────────────


def test_systematic_ablations(runner: BenchmarkRunner):
    ablations = runner.evaluate_systematic_ablations()

    assert "baseline_relevance_only" in ablations
    assert "academic_combined" in ablations
    assert "cross_encoder_rerank" in ablations
    assert "diversity_combined" in ablations
    assert "diversity_plus_novelty" in ablations

    for k, res in ablations.items():
        assert 0.0 <= res["mean_ndcg_at_5"] <= 1.0
        assert 0.0 <= res["mean_mrr"] <= 1.0


# ── 5. Sensitivity & Clamping Tests ───────────────────────────────────────────


def test_weight_sensitivity_and_clamping(runner: BenchmarkRunner):
    sens = runner.evaluate_weight_sensitivity()

    # Academic quality mass sweep
    acad_sweep = sens["academic_quality_mass_sweep"]
    assert "mass_0.00" in acad_sweep
    assert "mass_0.15" in acad_sweep
    assert "mass_0.20" in acad_sweep
    # 0.20 must be clamped to 0.15 to preserve relevance dominance
    assert acad_sweep["mass_0.20"]["clamped_effective_mass"] == 0.15

    # Diversity lambda sweep
    div_sweep = sens["diversity_lambda_sweep"]
    assert "lambda_0.08" in div_sweep
    assert "lambda_0.20" in div_sweep
    assert div_sweep["lambda_0.20"]["clamped_effective_lambda"] == MAX_DIVERSITY_LAMBDA
    assert div_sweep["lambda_0.20"]["relevance_dominance_preserved"] is True

    # Novelty sweep
    nov_sweep = sens["novelty_beta_sweep"]
    assert "beta_0.02" in nov_sweep


# ── 6. Statistical Significance Tests ─────────────────────────────────────────


def test_statistical_significance_methods():
    # Test paired bootstrap
    scores_a = [0.9, 0.85, 0.88, 0.92, 0.87]
    scores_b = [0.91, 0.86, 0.89, 0.93, 0.88]

    b_res = paired_bootstrap_test(scores_a, scores_b, num_samples=200)
    assert "observed_mean_delta" in b_res
    assert "ci_lower" in b_res
    assert "ci_upper" in b_res
    assert "p_value" in b_res
    assert 0.0 <= b_res["p_value"] <= 1.0

    # Test Wilcoxon signed rank
    w_res = wilcoxon_signed_rank_test(scores_a, scores_b)
    assert "w_statistic" in w_res
    assert "p_value" in w_res


# ── 7. Ranking Stability & Determinism ─────────────────────────────────────────


def test_ranking_stability(runner: BenchmarkRunner):
    stability = runner.evaluate_ranking_stability()

    assert stability["is_deterministic_across_iterations"] is True
    assert stability["determinism_iterations_verified"] == 10
    assert stability["tie_breaking_strict_consistency"] is True


# ── 8. Zero Database Query Regression Tests ───────────────────────────────────


def test_zero_database_query_regressions(runner: BenchmarkRunner):
    db_audit = runner.verify_zero_database_query_regressions()

    assert db_audit["zero_n_plus_one_verified"] is True
    assert "batch_audits" in db_audit

    for batch_key in ["batch_10", "batch_50", "batch_100", "batch_200"]:
        assert batch_key in db_audit["batch_audits"]
        assert db_audit["batch_audits"][batch_key]["total_queries"] == 0
        assert db_audit["batch_audits"][batch_key]["n_plus_one_detected"] is False


# ── 9. Production Recommendations ─────────────────────────────────────────────


def test_production_recommendations(runner: BenchmarkRunner):
    prod_rec = runner.generate_production_recommendations()

    assert prod_rec["relevance_weights"]["decision"] == "KEEP"
    assert prod_rec["academic_quality_weights"]["decision"] == "KEEP"
    assert prod_rec["cross_encoder_reranker"]["decision"] == "KEEP"
    assert prod_rec["diversity_reranker"]["decision"] == "KEEP"
    assert prod_rec["novelty_reranker"]["decision"] == "KEEP"

    # Verify diversity lambda is within safe bounds
    div_lam = prod_rec["diversity_reranker"]["recommended_configuration"]["maximum_lambda"]
    assert 0.0 <= div_lam <= MAX_DIVERSITY_LAMBDA
