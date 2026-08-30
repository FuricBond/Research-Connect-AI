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
    discounted_cumulative_gain_at_k,
    hit_rate_at_k,
    mean_reciprocal_rank,
    normalized_discounted_cumulative_gain_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
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
    "discounted_cumulative_gain_at_k",
    "normalized_discounted_cumulative_gain_at_k",
]
