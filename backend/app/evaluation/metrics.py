"""
Information Retrieval (IR) Evaluation Metrics for Phase 2.4H.

Provides deterministic mathematical functions for evaluating retrieval and ranking quality:
  - Precision@K
  - Recall@K
  - HitRate@K
  - Reciprocal Rank (RR) / Mean Reciprocal Rank (MRR)
  - Discounted Cumulative Gain (DCG@K)
  - Normalized Discounted Cumulative Gain (NDCG@K) with graded relevance
"""
from __future__ import annotations

import math
from typing import Any, Mapping, Sequence, Set


def precision_at_k(
    retrieved_ids: Sequence[Any],
    relevant_ids: Set[Any] | Sequence[Any],
    k: int,
) -> float:
    """
    Calculate Precision@K: proportion of top-k retrieved items that are relevant.

    Parameters
    ----------
    retrieved_ids:
        Ordered list of candidate IDs returned by retrieval/ranking.
    relevant_ids:
        Set of known relevant IDs (ground truth).
    k:
        Rank cutoff (k >= 1).

    Returns
    -------
    float in range [0.0, 1.0].
    """
    if k <= 0:
        raise ValueError("Cutoff k must be a positive integer (k >= 1).")
    if not retrieved_ids:
        return 0.0

    target_set = set(relevant_ids)
    if not target_set:
        return 0.0

    top_k = retrieved_ids[:k]
    num_relevant = sum(1 for item_id in top_k if item_id in target_set)
    return float(num_relevant) / float(k)


def recall_at_k(
    retrieved_ids: Sequence[Any],
    relevant_ids: Set[Any] | Sequence[Any],
    k: int,
) -> float:
    """
    Calculate Recall@K: proportion of known relevant items that appear in top-k.

    Parameters
    ----------
    retrieved_ids:
        Ordered list of candidate IDs returned by retrieval/ranking.
    relevant_ids:
        Set of known relevant IDs (ground truth).
    k:
        Rank cutoff (k >= 1).

    Returns
    -------
    float in range [0.0, 1.0].
    """
    if k <= 0:
        raise ValueError("Cutoff k must be a positive integer (k >= 1).")

    target_set = set(relevant_ids)
    if not target_set:
        return 0.0
    if not retrieved_ids:
        return 0.0

    top_k = retrieved_ids[:k]
    num_relevant = sum(1 for item_id in top_k if item_id in target_set)
    return float(num_relevant) / float(len(target_set))


def hit_rate_at_k(
    retrieved_ids: Sequence[Any],
    relevant_ids: Set[Any] | Sequence[Any],
    k: int,
) -> float:
    """
    Calculate HitRate@K (1.0 if at least one relevant item in top-k, else 0.0).

    Parameters
    ----------
    retrieved_ids:
        Ordered list of candidate IDs returned by retrieval/ranking.
    relevant_ids:
        Set of known relevant IDs.
    k:
        Rank cutoff (k >= 1).

    Returns
    -------
    1.0 if any relevant item is found in top-k, else 0.0.
    """
    if k <= 0:
        raise ValueError("Cutoff k must be a positive integer (k >= 1).")

    target_set = set(relevant_ids)
    if not target_set or not retrieved_ids:
        return 0.0

    top_k = retrieved_ids[:k]
    for item_id in top_k:
        if item_id in target_set:
            return 1.0
    return 0.0


def reciprocal_rank(
    retrieved_ids: Sequence[Any],
    relevant_ids: Set[Any] | Sequence[Any],
) -> float:
    """
    Calculate Reciprocal Rank (RR): 1.0 / rank of the first relevant item (1-indexed).

    Parameters
    ----------
    retrieved_ids:
        Ordered list of candidate IDs returned by retrieval/ranking.
    relevant_ids:
        Set of known relevant IDs.

    Returns
    -------
    float in range [0.0, 1.0]. (0.0 if no relevant items are retrieved).
    """
    target_set = set(relevant_ids)
    if not target_set or not retrieved_ids:
        return 0.0

    for idx, item_id in enumerate(retrieved_ids, start=1):
        if item_id in target_set:
            return 1.0 / float(idx)
    return 0.0


def mean_reciprocal_rank(
    query_evaluations: Sequence[tuple[Sequence[Any], Set[Any] | Sequence[Any]]],
) -> float:
    """
    Calculate Mean Reciprocal Rank (MRR) across a collection of queries.

    Parameters
    ----------
    query_evaluations:
        Sequence of (retrieved_ids, relevant_ids) tuples for multiple queries.

    Returns
    -------
    float in range [0.0, 1.0].
    """
    if not query_evaluations:
        return 0.0

    total_rr = sum(
        reciprocal_rank(retrieved, relevant)
        for retrieved, relevant in query_evaluations
    )
    return float(total_rr) / float(len(query_evaluations))


def discounted_cumulative_gain_at_k(
    retrieved_ids: Sequence[Any],
    graded_relevance: Mapping[Any, float],
    k: int,
) -> float:
    """
    Calculate DCG@K using standard logarithmic position discounting:
        DCG@K = sum_{i=1}^K ( (2^{rel_i} - 1) / log2(i + 1) )

    Parameters
    ----------
    retrieved_ids:
        Ordered list of candidate IDs.
    graded_relevance:
        Mapping from item_id to non-negative numerical relevance score (e.g. 0 to 3).
    k:
        Rank cutoff (k >= 1).

    Returns
    -------
    float non-negative DCG value.
    """
    if k <= 0:
        raise ValueError("Cutoff k must be a positive integer (k >= 1).")
    if not retrieved_ids:
        return 0.0

    dcg = 0.0
    for idx, item_id in enumerate(retrieved_ids[:k], start=1):
        rel = float(graded_relevance.get(item_id, 0.0))
        if rel > 0.0:
            gain = (2.0 ** rel) - 1.0
            discount = math.log2(float(idx) + 1.0)
            dcg += gain / discount
    return dcg


def normalized_discounted_cumulative_gain_at_k(
    retrieved_ids: Sequence[Any],
    graded_relevance: Mapping[Any, float],
    k: int,
) -> float:
    """
    Calculate NDCG@K: DCG@K / IDCG@K, where IDCG is the ideal discounted cumulative gain.

    Parameters
    ----------
    retrieved_ids:
        Ordered list of candidate IDs.
    graded_relevance:
        Mapping from item_id to numerical relevance score.
    k:
        Rank cutoff (k >= 1).

    Returns
    -------
    float in range [0.0, 1.0].
    """
    if k <= 0:
        raise ValueError("Cutoff k must be a positive integer (k >= 1).")
    if not graded_relevance or not retrieved_ids:
        return 0.0

    actual_dcg = discounted_cumulative_gain_at_k(retrieved_ids, graded_relevance, k)
    if actual_dcg <= 0.0:
        return 0.0

    # Ideal ranking is all known graded items sorted descending by relevance score
    ideal_scores = sorted(graded_relevance.values(), reverse=True)
    if not ideal_scores or ideal_scores[0] <= 0.0:
        return 0.0

    idcg = 0.0
    for idx, rel in enumerate(ideal_scores[:k], start=1):
        if rel > 0.0:
            gain = (2.0 ** rel) - 1.0
            discount = math.log2(float(idx) + 1.0)
            idcg += gain / discount

    if idcg <= 0.0:
        return 0.0

    return min(1.0, actual_dcg / idcg)


def average_precision(
    retrieved_ids: Sequence[Any],
    relevant_ids: Set[Any] | Sequence[Any],
) -> float:
    """
    Calculate Average Precision (AP) for a single query ranking.
    """
    target_set = set(relevant_ids)
    if not target_set or not retrieved_ids:
        return 0.0

    running_relevant = 0
    precision_sum = 0.0

    for idx, item_id in enumerate(retrieved_ids, start=1):
        if item_id in target_set:
            running_relevant += 1
            precision_sum += float(running_relevant) / float(idx)

    return precision_sum / float(len(target_set))


def mean_average_precision(
    query_evaluations: Sequence[tuple[Sequence[Any], Set[Any] | Sequence[Any]]],
) -> float:
    """
    Calculate Mean Average Precision (MAP) across multiple queries.
    """
    if not query_evaluations:
        return 0.0
    total_ap = sum(average_precision(r, rel) for r, rel in query_evaluations)
    return float(total_ap) / float(len(query_evaluations))


def paired_bootstrap_test(
    baseline_scores: Sequence[float],
    treatment_scores: Sequence[float],
    num_samples: int = 1000,
    alpha: float = 0.05,
    seed: int = 42,
) -> dict[str, Any]:
    """
    Perform paired bootstrap hypothesis test and confidence interval estimation.

    Parameters
    ----------
    baseline_scores:
        List of per-query metric scores for baseline model.
    treatment_scores:
        List of per-query metric scores for treatment/reranked model.
    num_samples:
        Number of bootstrap iterations (default 1000).
    alpha:
        Significance level (default 0.05 for 95% CI).

    Returns
    -------
    dict with mean delta, relative delta, confidence interval [ci_lower, ci_upper], p-value, and significance.
    """
    if len(baseline_scores) != len(treatment_scores):
        raise ValueError("Baseline and treatment scores must have identical sample lengths.")
    n = len(baseline_scores)
    if n == 0:
        return {"mean_delta": 0.0, "is_significant": False, "p_value": 1.0}

    import random
    rng = random.Random(seed)

    deltas = [t - b for b, t in zip(baseline_scores, treatment_scores)]
    observed_mean_delta = sum(deltas) / n
    base_mean = sum(baseline_scores) / n
    rel_delta = (observed_mean_delta / base_mean) if base_mean > 0 else 0.0

    bootstrap_means: list[float] = []
    for _ in range(num_samples):
        sample = [rng.choice(deltas) for _ in range(n)]
        bootstrap_means.append(sum(sample) / n)

    bootstrap_means.sort()
    lower_idx = int((alpha / 2.0) * num_samples)
    upper_idx = int((1.0 - alpha / 2.0) * num_samples)

    ci_lower = bootstrap_means[max(0, lower_idx)]
    ci_upper = bootstrap_means[min(num_samples - 1, upper_idx)]

    # Two-sided empirical p-value
    if observed_mean_delta >= 0:
        p_val = sum(1 for m in bootstrap_means if m <= 0.0) / float(num_samples)
    else:
        p_val = sum(1 for m in bootstrap_means if m >= 0.0) / float(num_samples)
    two_sided_p = min(1.0, 2.0 * p_val)

    is_significant = (ci_lower > 0.0 or ci_upper < 0.0) and two_sided_p < alpha

    return {
        "observed_mean_delta": round(observed_mean_delta, 4),
        "relative_delta_pct": round(rel_delta * 100, 2),
        "ci_lower": round(ci_lower, 4),
        "ci_upper": round(ci_upper, 4),
        "confidence_level": round((1.0 - alpha) * 100, 1),
        "p_value": round(two_sided_p, 4),
        "is_significant": is_significant,
    }


def wilcoxon_signed_rank_test(
    baseline_scores: Sequence[float],
    treatment_scores: Sequence[float],
) -> dict[str, Any]:
    """
    Calculate Wilcoxon Signed-Rank Test for paired ordinal ranking scores.
    """
    if len(baseline_scores) != len(treatment_scores):
        raise ValueError("Score lengths must match.")
    
    diffs = [t - b for b, t in zip(baseline_scores, treatment_scores)]
    non_zero_diffs = [d for d in diffs if abs(d) > 1e-7]
    n = len(non_zero_diffs)
    if n == 0:
        return {"w_statistic": 0.0, "p_value": 1.0, "is_significant": False}

    # Sort absolute differences
    ranked_diffs = sorted(non_zero_diffs, key=lambda d: abs(d))
    w_plus = 0.0
    w_minus = 0.0

    for rank, d in enumerate(ranked_diffs, start=1):
        if d > 0:
            w_plus += rank
        else:
            w_minus += rank

    w_stat = min(w_plus, w_minus)
    # Normal approximation for n >= 10
    mean_w = (n * (n + 1)) / 4.0
    std_w = math.sqrt((n * (n + 1) * (2 * n + 1)) / 24.0)

    if std_w > 0:
        z = (w_stat - mean_w) / std_w
        # Two-tailed normal cdf approximation
        p_value = 2.0 * (0.5 * math.erfc(abs(z) / math.sqrt(2.0)))
    else:
        z = 0.0
        p_value = 1.0

    return {
        "w_statistic": round(w_stat, 2),
        "z_score": round(z, 3),
        "p_value": round(p_value, 4),
        "is_significant": p_value < 0.05,
    }

