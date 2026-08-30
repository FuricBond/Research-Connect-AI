"""
Unit tests for Information Retrieval evaluation metrics in app.evaluation.metrics.
"""
from __future__ import annotations

import math
import pytest

from app.evaluation.metrics import (
    discounted_cumulative_gain_at_k,
    hit_rate_at_k,
    mean_reciprocal_rank,
    normalized_discounted_cumulative_gain_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)


class TestEvaluationMetrics:
    """Tests for individual IR evaluation metrics."""

    def test_precision_at_k(self):
        retrieved = ["doc1", "doc2", "doc3", "doc4", "doc5"]
        relevant = {"doc1", "doc3", "doc7"}

        # P@1 = 1 / 1 = 1.0
        assert precision_at_k(retrieved, relevant, k=1) == 1.0
        # P@2 = 1 / 2 = 0.5
        assert precision_at_k(retrieved, relevant, k=2) == 0.5
        # P@3 = 2 / 3
        assert math.isclose(precision_at_k(retrieved, relevant, k=3), 2.0 / 3.0)
        # P@5 = 2 / 5 = 0.4
        assert precision_at_k(retrieved, relevant, k=5) == 0.4

        # Empty cases
        assert precision_at_k([], relevant, k=5) == 0.0
        assert precision_at_k(retrieved, set(), k=5) == 0.0

        with pytest.raises(ValueError):
            precision_at_k(retrieved, relevant, k=0)

    def test_recall_at_k(self):
        retrieved = ["doc1", "doc2", "doc3", "doc4", "doc5"]
        relevant = {"doc1", "doc3", "doc7", "doc8"}  # 4 relevant docs total

        # R@1 = 1 / 4 = 0.25
        assert recall_at_k(retrieved, relevant, k=1) == 0.25
        # R@3 = 2 / 4 = 0.50
        assert recall_at_k(retrieved, relevant, k=3) == 0.50
        # R@5 = 2 / 4 = 0.50
        assert recall_at_k(retrieved, relevant, k=5) == 0.50

        # Empty cases
        assert recall_at_k([], relevant, k=5) == 0.0
        assert recall_at_k(retrieved, set(), k=5) == 0.0

        with pytest.raises(ValueError):
            recall_at_k(retrieved, relevant, k=-1)

    def test_hit_rate_at_k(self):
        retrieved = ["doc1", "doc2", "doc3"]
        relevant = {"doc2"}

        assert hit_rate_at_k(retrieved, relevant, k=1) == 0.0
        assert hit_rate_at_k(retrieved, relevant, k=2) == 1.0
        assert hit_rate_at_k(retrieved, relevant, k=3) == 1.0

        # Non-overlapping
        assert hit_rate_at_k(retrieved, {"doc99"}, k=3) == 0.0

    def test_reciprocal_rank_and_mrr(self):
        retrieved_1 = ["doc1", "doc2", "doc3"]
        relevant_1 = {"doc2"}  # First relevant at rank 2 -> RR = 0.5

        retrieved_2 = ["docA", "docB", "docC"]
        relevant_2 = {"docA"}  # First relevant at rank 1 -> RR = 1.0

        retrieved_3 = ["docX", "docY"]
        relevant_3 = {"docZ"}  # Not found -> RR = 0.0

        assert reciprocal_rank(retrieved_1, relevant_1) == 0.5
        assert reciprocal_rank(retrieved_2, relevant_2) == 1.0
        assert reciprocal_rank(retrieved_3, relevant_3) == 0.0

        # MRR = (0.5 + 1.0 + 0.0) / 3 = 0.5
        mrr = mean_reciprocal_rank([
            (retrieved_1, relevant_1),
            (retrieved_2, relevant_2),
            (retrieved_3, relevant_3),
        ])
        assert math.isclose(mrr, 0.5)

    def test_dcg_and_ndcg(self):
        retrieved = ["doc1", "doc2", "doc3"]
        # Graded relevance: doc1=3.0, doc2=2.0, doc3=0.0
        graded_rel = {"doc1": 3.0, "doc2": 2.0, "doc3": 0.0}

        # Perfect ranking -> NDCG should be 1.0
        ndcg_perfect = normalized_discounted_cumulative_gain_at_k(retrieved, graded_rel, k=3)
        assert math.isclose(ndcg_perfect, 1.0, abs_tol=1e-4)

        # Inverted ranking -> doc2 before doc1
        inverted = ["doc2", "doc1", "doc3"]
        ndcg_inv = normalized_discounted_cumulative_gain_at_k(inverted, graded_rel, k=3)
        assert 0.0 < ndcg_inv < 1.0

        # Empty cases
        assert normalized_discounted_cumulative_gain_at_k([], graded_rel, k=3) == 0.0
        assert normalized_discounted_cumulative_gain_at_k(retrieved, {}, k=3) == 0.0
