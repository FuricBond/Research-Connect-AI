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
