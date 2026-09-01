"""
Inter-Annotator Agreement Metrics for Phase 2.4M.

Provides mathematical statistical agreement calculators for relevance annotations:
- Raw Percentage Agreement
- Cohen's Kappa (for 2 annotators)
- Fleiss' Kappa (for arbitrary N annotators)
- Confusion Matrix & Disciplinary Agreement Breakdown
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence


def calculate_raw_agreement(
    rater_a: Sequence[int | float],
    rater_b: Sequence[int | float],
) -> float:
    """
    Calculate simple observed agreement proportion between two raters.
    """
    if len(rater_a) != len(rater_b):
        raise ValueError("Rater sequences must have identical lengths.")
    if not rater_a:
        return 0.0

    agreements = sum(1 for a, b in zip(rater_a, rater_b) if int(round(a)) == int(round(b)))
    return float(agreements) / float(len(rater_a))


def cohens_kappa(
    rater_a: Sequence[int | float],
    rater_b: Sequence[int | float],
    categories: Sequence[int] = (0, 1, 2, 3),
) -> float:
    """
    Calculate Cohen's Kappa coefficient (kappa) between two annotators:
        kappa = (P_o - P_e) / (1 - P_e)

    Parameters
    ----------
    rater_a:
        Relevance scores assigned by first rater.
    rater_b:
        Relevance scores assigned by second rater.
    categories:
        Distinct ordinal category labels (default 0, 1, 2, 3).

    Returns
    -------
    float kappa in range [-1.0, 1.0].
    """
    if len(rater_a) != len(rater_b):
        raise ValueError("Rater sequences must have identical lengths.")
    n = len(rater_a)
    if n == 0:
        return 0.0

    cat_list = list(categories)
    # Observed agreement
    p_o = calculate_raw_agreement(rater_a, rater_b)

    # Expected agreement by chance
    p_e = 0.0
    for cat in cat_list:
        p_a = sum(1 for a in rater_a if int(round(a)) == cat) / n
        p_b = sum(1 for b in rater_b if int(round(b)) == cat) / n
        p_e += (p_a * p_b)

    if p_e >= 1.0:
        return 1.0 if p_o >= 1.0 else 0.0

    kappa = (p_o - p_e) / (1.0 - p_e)
    return max(-1.0, min(1.0, round(kappa, 4)))


def fleiss_kappa(ratings_matrix: Sequence[Sequence[int]]) -> float:
    """
    Calculate Fleiss' Kappa for inter-rater reliability across multiple raters.

    Parameters
    ----------
    ratings_matrix:
        Matrix of shape (N, k) where N is the number of items and k is the number of categories.
        Entry (i, j) is the count of raters who assigned item i to category j.

    Returns
    -------
    float Fleiss' kappa in range [-1.0, 1.0].
    """
    if not ratings_matrix:
        return 0.0

    n_items = len(ratings_matrix)
    n_categories = len(ratings_matrix[0])
    if n_items == 0 or n_categories == 0:
        return 0.0

    # Number of raters per item (must be constant)
    n_raters = sum(ratings_matrix[0])
    if n_raters <= 1:
        return 1.0

    # Proportion of all assignments to category j
    p_j = [0.0] * n_categories
    total_assignments = n_items * n_raters

    for row in ratings_matrix:
        for j in range(n_categories):
            p_j[j] += row[j]
    p_j = [count / total_assignments for count in p_j]

    # Item extent of agreement P_i
    p_i = []
    for row in ratings_matrix:
        sum_sq = sum(count * (count - 1) for count in row)
        p_i.append(sum_sq / (n_raters * (n_raters - 1)))

    p_bar = sum(p_i) / n_items
    p_bar_e = sum(p * p for p in p_j)

    if p_bar_e >= 1.0:
        return 1.0 if p_bar >= 1.0 else 0.0

    kappa = (p_bar - p_bar_e) / (1.0 - p_bar_e)
    return max(-1.0, min(1.0, round(kappa, 4)))


def compute_confusion_matrix(
    rater_a: Sequence[int | float],
    rater_b: Sequence[int | float],
    categories: Sequence[int] = (0, 1, 2, 3),
) -> dict[str, Any]:
    """
    Generate an NxN confusion matrix between two raters.
    """
    cats = list(categories)
    matrix = {c_a: {c_b: 0 for c_b in cats} for c_a in cats}

    for a, b in zip(rater_a, rater_b):
        ca = int(round(a))
        cb = int(round(b))
        if ca in matrix and cb in matrix[ca]:
            matrix[ca][cb] += 1

    return {
        "categories": cats,
        "matrix": matrix,
        "raw_agreement": calculate_raw_agreement(rater_a, rater_b),
        "cohens_kappa": cohens_kappa(rater_a, rater_b, cats),
    }


def calculate_discipline_agreement(
    discipline_ratings: Mapping[str, Sequence[tuple[int | float, int | float]]],
) -> dict[str, dict[str, float]]:
    """
    Calculate agreement metrics broken down per academic discipline.
    """
    report: dict[str, dict[str, float]] = {}

    for disc, pairs in discipline_ratings.items():
        if not pairs:
            continue
        rater_a = [p[0] for p in pairs]
        rater_b = [p[1] for p in pairs]
        report[disc] = {
            "num_judgments": len(pairs),
            "raw_agreement": calculate_raw_agreement(rater_a, rater_b),
            "cohens_kappa": cohens_kappa(rater_a, rater_b),
        }

    return report
