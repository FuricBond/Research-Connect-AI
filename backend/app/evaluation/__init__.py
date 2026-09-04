"""
Evaluation and Benchmarking Package for Phase 2.4H.
"""
from app.evaluation.benchmark_dataset import (
    BenchmarkQueryScenario,
    GroundTruthCategory,
    get_benchmark_dataset,
)
from app.evaluation.benchmark_runner import BenchmarkRunner
from app.evaluation.metrics import (
    concentration_hhi,
    discounted_cumulative_gain_at_k,
    hit_rate_at_k,
    kendall_tau_correlation,
    mean_average_precision,
    mean_novelty_at_k,
    mean_pairwise_cosine,
    mean_pairwise_jaccard,
    mean_rank_displacement,
    mean_reciprocal_rank,
    min_novelty_at_k,
    normalized_discounted_cumulative_gain_at_k,
    paired_bootstrap_test,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
    top_k_overlap_ratio,
    unique_elements_at_k,
    wilcoxon_signed_rank_test,
)

__all__ = [
    "BenchmarkRunner",
    "BenchmarkQueryScenario",
    "GroundTruthCategory",
    "get_benchmark_dataset",
    "precision_at_k",
    "recall_at_k",
    "hit_rate_at_k",
    "reciprocal_rank",
    "mean_reciprocal_rank",
    "mean_average_precision",
    "discounted_cumulative_gain_at_k",
    "normalized_discounted_cumulative_gain_at_k",
    "paired_bootstrap_test",
    "wilcoxon_signed_rank_test",
    "unique_elements_at_k",
    "concentration_hhi",
    "mean_pairwise_jaccard",
    "mean_pairwise_cosine",
    "mean_novelty_at_k",
    "min_novelty_at_k",
    "kendall_tau_correlation",
    "top_k_overlap_ratio",
    "mean_rank_displacement",
]
