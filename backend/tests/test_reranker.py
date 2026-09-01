"""
Unit and Integration Tests for Phase 2.4M Lightweight Cross-Encoder Reranker.
"""
from __future__ import annotations

import time
import uuid
from unittest.mock import MagicMock

import pytest

from app.ranking.hybrid_ranker import RankedCandidate
from app.ranking.reranker import CrossEncoderReranker, sigmoid_normalize


class DummyMockModel:
    """Mock CrossEncoder model producing deterministic scores for testing."""

    def __init__(self, scores: list[float] | None = None, delay_sec: float = 0.0) -> None:
        self.scores = scores or [2.5, -1.0, 0.5]
        self.delay_sec = delay_sec

    def predict(self, pairs: list[tuple[str, str]]) -> list[float]:
        if self.delay_sec > 0:
            time.sleep(self.delay_sec)
        return self.scores[: len(pairs)]


def _build_test_candidate(
    cand_id: uuid.UUID,
    rank: int,
    final_score: float,
    title: str = "Test Title",
    abstract: str = "Test Abstract",
) -> RankedCandidate:
    return RankedCandidate(
        entity_id=cand_id,
        entity_type="research_work",
        rank=rank,
        final_score=final_score,
        semantic_score=final_score,
        lexical_score=final_score,
        topic_score=final_score,
        type_score=1.0,
        freshness_score=0.9,
        urgency_score=0.0,
        quality_score=0.8,
        candidate={"title": title, "abstract": abstract},
    )


class TestCrossEncoderReranker:
    """Test suite verifying CrossEncoder reranker behavior, safety, fallback, and dominance."""

    def test_sigmoid_normalization_bounds(self) -> None:
        """Verify sigmoid function maps logits cleanly to [0.0, 1.0]."""
        assert sigmoid_normalize(0.0) == 0.5
        assert sigmoid_normalize(10.0) > 0.99
        assert sigmoid_normalize(-10.0) < 0.01
        assert sigmoid_normalize(50.0) == 1.0
        assert sigmoid_normalize(-50.0) == 0.0

    def test_disabled_by_default_returns_exact_baseline(self) -> None:
        """Verify reranker returns candidates untouched when enabled=False."""
        c1 = _build_test_candidate(uuid.uuid4(), 1, 0.90)
        c2 = _build_test_candidate(uuid.uuid4(), 2, 0.80)

        reranker = CrossEncoderReranker(enabled=False, model_instance=DummyMockModel())
        results = reranker.rerank("quantum computing", [c1, c2])

        assert results == [c1, c2]

    def test_top_k_candidate_selection_and_reranking(self) -> None:
        """Verify reranker modifies scores for top-N candidates and respects bounds."""
        id1, id2, id3, id4 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        c1 = _build_test_candidate(id1, 1, 0.85, "Candidate 1", "Abstract 1")
        c2 = _build_test_candidate(id2, 2, 0.84, "Candidate 2", "Abstract 2")
        c3 = _build_test_candidate(id3, 3, 0.83, "Candidate 3", "Abstract 3")
        c4 = _build_test_candidate(id4, 4, 0.50, "Candidate 4", "Abstract 4")

        # Mock model gives candidate 2 a very high cross-encoder score (+5.0 -> norm ~0.993)
        # and candidate 1 a low cross-encoder score (-2.0 -> norm ~0.119)
        mock_model = DummyMockModel(scores=[-2.0, 5.0, 0.0])

        reranker = CrossEncoderReranker(
            enabled=True,
            top_k=3,
            weight=0.10,
            model_instance=mock_model,
        )

        results = reranker.rerank("test query", [c1, c2, c3, c4])

        assert len(results) == 4
        # Candidate 2 should rise to rank 1 due to high cross-encoder score
        assert results[0].entity_id == id2
        assert results[0].rank == 1
        assert results[0].reranker_adjustment is not None
        assert results[0].reranker_adjustment > 0

        # Candidate 4 was outside top_k=3, so remained untouched at the bottom
        assert results[3].entity_id == id4
        assert results[3].rank == 4
        assert results[3].reranker_adjustment is None

    def test_eighty_five_percent_relevance_dominance_guaranteed(self) -> None:
        """Verify that a candidate with poor baseline relevance cannot overtake a strong candidate."""
        id_strong = uuid.uuid4()
        id_weak = uuid.uuid4()

        c_strong = _build_test_candidate(id_strong, 1, 0.95, "Strong Match", "Exact relevant concepts")
        c_weak = _build_test_candidate(id_weak, 2, 0.30, "Weak Match", "Irrelevant context")

        # Even with max cross-encoder score (+10.0) for weak, and min (-10.0) for strong:
        mock_model = DummyMockModel(scores=[-10.0, 10.0])

        # Reranker weight capped at 0.10
        reranker = CrossEncoderReranker(
            enabled=True,
            weight=0.10,
            model_instance=mock_model,
        )

        results = reranker.rerank("query", [c_strong, c_weak])

        # Strong candidate must remain #1:
        # Strong: 0.90 * 0.95 + 0.10 * 0.0 = 0.855
        # Weak: 0.90 * 0.30 + 0.10 * 1.0 = 0.370
        assert results[0].entity_id == id_strong
        assert results[0].final_score > results[1].final_score

    def test_timeout_fallback_to_baseline(self) -> None:
        """Verify that model execution exceeding timeout_ms cleanly falls back to baseline."""
        c1 = _build_test_candidate(uuid.uuid4(), 1, 0.88)
        c2 = _build_test_candidate(uuid.uuid4(), 2, 0.77)

        # Mock model introduces 0.3s delay while timeout is set to 50ms (0.05s)
        slow_model = DummyMockModel(delay_sec=0.3)

        reranker = CrossEncoderReranker(
            enabled=True,
            timeout_ms=50,
            model_instance=slow_model,
        )

        results = reranker.rerank("query", [c1, c2])

        # Must fall back gracefully without raising exceptions
        assert len(results) == 2
        assert results[0].final_score == 0.88
        assert results[1].final_score == 0.77
        assert results[0].reranker_adjustment is None

    def test_model_exception_fallback(self) -> None:
        """Verify that runtime errors in model prediction fall back safely to baseline."""
        c1 = _build_test_candidate(uuid.uuid4(), 1, 0.90)

        failing_model = MagicMock()
        failing_model.predict.side_effect = RuntimeError("CUDA Out of Memory simulation")

        reranker = CrossEncoderReranker(
            enabled=True,
            model_instance=failing_model,
        )

        results = reranker.rerank("query", [c1])
        assert results == [c1]
