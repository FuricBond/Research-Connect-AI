"""
Lightweight Cross-Encoder Reranker for Phase 2.4M.

Provides optional neural cross-encoder reranking over top-N candidates produced
by the deterministic hybrid ranker.

Key Architectural Guarantees:
1. Purely Additive & Optional: Default is disabled (reranker_enabled=False).
2. 85% Relevance Dominance Guarantee: Reranker weight is bounded (default w=0.10),
   guaranteeing core relevance retains >= 85% score dominance.
3. Strict Determinism & Graceful Fallback: Model absence, execution timeout,
   or runtime exceptions automatically fall back to baseline ranking without failing requests.
4. Top-N Candidate Limiting: Only candidates within top_k (default 20) are reranked.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import replace
import logging
import math
from typing import Any, Callable, Sequence
import uuid

from app.core.config import settings
from app.ranking.hybrid_ranker import RankedCandidate

logger = logging.getLogger(__name__)


def sigmoid_normalize(raw_score: float) -> float:
    """
    Apply standard logistic sigmoid transformation to map unbounded logit scores to [0.0, 1.0].
    """
    try:
        if raw_score >= 40.0:
            return 1.0
        if raw_score <= -40.0:
            return 0.0
        return 1.0 / (1.0 + math.exp(-raw_score))
    except (OverflowError, ValueError):
        return 0.5 if raw_score == 0.0 else (1.0 if raw_score > 0 else 0.0)


class CrossEncoderReranker:
    """
    Cross-Encoder Reranker that scores (query, document) pairs for top candidates.
    """

    def __init__(
        self,
        model_name: str | None = None,
        enabled: bool | None = None,
        top_k: int | None = None,
        weight: float | None = None,
        timeout_ms: int | None = None,
        max_batch_size: int | None = None,
        model_instance: Any | None = None,
    ) -> None:
        self.model_name = model_name or getattr(settings, "reranker_model", "BAAI/bge-reranker-base")
        self.enabled = enabled if enabled is not None else getattr(settings, "reranker_enabled", False)
        self.top_k = top_k if top_k is not None else getattr(settings, "reranker_top_k", 20)
        self.weight = min(0.15, max(0.0, weight if weight is not None else getattr(settings, "reranker_weight", 0.10)))
        self.timeout_ms = timeout_ms if timeout_ms is not None else getattr(settings, "reranker_timeout_ms", 200)
        self.max_batch_size = max_batch_size if max_batch_size is not None else getattr(settings, "reranker_max_batch_size", 32)
        
        self._model = model_instance
        self._model_load_attempted = False
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="CrossEncoderWorker")

    def _get_model(self) -> Any | None:
        """Lazy loader for SentenceTransformer CrossEncoder model."""
        if self._model is not None:
            return self._model
        if self._model_load_attempted:
            return None

        self._model_load_attempted = True
        try:
            from sentence_transformers import CrossEncoder  # type: ignore[import-untyped]
            logger.info("Initializing CrossEncoder model: %s", self.model_name)
            self._model = CrossEncoder(self.model_name)
            return self._model
        except Exception as exc:
            logger.warning("Could not load CrossEncoder model '%s': %s", self.model_name, exc)
            return None

    def _extract_document_text(self, candidate: RankedCandidate) -> str:
        """Extract title and abstract snippet from ranked candidate."""
        cand_obj = candidate.candidate
        if cand_obj is None:
            return ""

        # Check if dictionary fixture
        if isinstance(cand_obj, dict):
            title = cand_obj.get("title", "")
            abstract = cand_obj.get("abstract", "") or cand_obj.get("summary", "")
            return f"{title}. {abstract}".strip()

        # Check ORM attributes
        title = getattr(cand_obj, "title", "") or ""
        abstract = getattr(cand_obj, "abstract", "") or getattr(cand_obj, "summary", "") or getattr(cand_obj, "description", "") or ""
        return f"{title}. {abstract}".strip()

    def rerank(
        self,
        query: str,
        candidates: Sequence[RankedCandidate],
        top_k: int | None = None,
        weight: float | None = None,
        force_enabled: bool = False,
    ) -> list[RankedCandidate]:
        """
        Rerank top-N candidate results with the cross-encoder model.

        Parameters
        ----------
        query:
            Target search query or source paper title/abstract text.
        candidates:
            Pre-ranked candidates from HybridRanker.
        top_k:
            Override candidate count to rerank.
        weight:
            Override reranker weight (strictly clamped to <= 0.15 to preserve 85% dominance).
        force_enabled:
            If True, attempt reranking even if global self.enabled is False.

        Returns
        -------
        list[RankedCandidate]
            Ranked candidates with updated final_score and reranker_adjustment metadata.
        """
        if not candidates or not query or not query.strip():
            return list(candidates)

        is_active = self.enabled or force_enabled
        if not is_active:
            return list(candidates)

        model = self._get_model()
        if model is None:
            logger.debug("Cross-encoder model unavailable, skipping rerank and retaining baseline.")
            return list(candidates)

        active_top_k = top_k if top_k is not None else self.top_k
        active_weight = min(0.15, max(0.0, weight if weight is not None else self.weight))
        timeout_sec = max(0.01, float(self.timeout_ms) / 1000.0)

        # Slice top-N candidates for reranking
        selected_candidates = list(candidates[:active_top_k])
        unselected_candidates = list(candidates[active_top_k:])

        # Build pair inputs: (query, doc_text)
        pairs: list[tuple[str, str]] = []
        valid_indices: list[int] = []
        clean_query = query.strip()

        for idx, cand in enumerate(selected_candidates):
            doc_text = self._extract_document_text(cand)
            if doc_text:
                pairs.append((clean_query, doc_text))
                valid_indices.append(idx)

        if not pairs:
            return list(candidates)

        # Execute prediction with timeout protection
        try:
            future = self._executor.submit(
                model.predict,
                pairs[: self.max_batch_size],
            )
            raw_scores = future.result(timeout=timeout_sec)
        except FuturesTimeoutError:
            logger.warning(
                "CrossEncoder inference timed out after %d ms. Falling back to baseline.",
                self.timeout_ms,
            )
            return list(candidates)
        except Exception as exc:
            logger.warning("CrossEncoder prediction failed: %s. Falling back to baseline.", exc)
            return list(candidates)

        # Apply bounded score combination
        # final_score = (1 - w) * baseline + w * sigmoid(raw_score)
        reranked_pool: list[RankedCandidate] = []

        for pair_idx, cand_idx in enumerate(valid_indices):
            cand = selected_candidates[cand_idx]
            raw_s = float(raw_scores[pair_idx])
            norm_s = sigmoid_normalize(raw_s)

            baseline_score = cand.final_score
            combined_score = round(
                (1.0 - active_weight) * baseline_score + active_weight * norm_s,
                6,
            )
            adjustment = round(combined_score - baseline_score, 6)

            reranked_pool.append(
                replace(
                    cand,
                    final_score=combined_score,
                    reranker_adjustment=adjustment,
                    raw_reranker_score=round(raw_s, 4),
                )
            )

        # Include any selected candidates that lacked text
        for idx, cand in enumerate(selected_candidates):
            if idx not in valid_indices:
                reranked_pool.append(cand)

        # Deterministic Sort
        # Primary: final_score DESC
        # Secondary: semantic_score DESC
        # Tertiary: topic_score DESC
        # Quaternary: lexical_score DESC
        # Tie-breaker: entity_id ASC
        reranked_pool.sort(
            key=lambda c: (
                -c.final_score,
                -c.semantic_score,
                -c.topic_score,
                -c.lexical_score,
                str(c.entity_id),
            )
        )

        # Combine with unselected tail candidates
        final_list = reranked_pool + unselected_candidates

        # Reassign 1-indexed ranks
        return [
            replace(c, rank=new_rank)
            for new_rank, c in enumerate(final_list, start=1)
        ]


# Singleton reranker instance
cross_encoder_reranker = CrossEncoderReranker()
