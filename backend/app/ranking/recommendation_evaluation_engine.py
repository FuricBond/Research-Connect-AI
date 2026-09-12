"""
Phase 3.7 — Recommendation Evaluation Engine.

Provides deterministic mathematical functions and offline evaluation metrics for
measuring recommendation quality against researcher feedback:
  - Precision@K (Proportion of top-K recommendations with positive feedback)
  - Recall@K (Proportion of known relevant opportunities retrieved in top-K)
  - HitRate@K (Binary indicator if at least one relevant opportunity in top-K)
  - NDCG@K (Normalized Discounted Cumulative Gain with graded relevance)
  - Save Rate (Saved recommendations / recommended opportunities shown)
  - Engagement Rate (Engaged [VIEW, SAVE, INTERESTED, APPLY] / shown)
  - Dismissal Rate (Dismissed [DISMISS, NOT_INTERESTED] / shown)

Strict Architectural Boundaries:
  - Evaluation is 100% deterministic and reproducible.
  - Evaluation is read-only: NEVER modifies recommendation weights, candidate pools, or preferences.
  - Declares explicit data sufficiency states (SUFFICIENT_DATA, INSUFFICIENT_DATA, NO_FEEDBACK, NO_HISTORY).
  - Never returns 0.0 when the correct interpretation is insufficient data or no feedback.
"""
from __future__ import annotations

import math
from typing import Any, Mapping, Sequence, Set
import uuid

from app.evaluation.metrics import (
    discounted_cumulative_gain_at_k,
    hit_rate_at_k,
    normalized_discounted_cumulative_gain_at_k,
    precision_at_k,
    recall_at_k,
)
from app.schemas.recommendation_evaluation import (
    DataSufficiencyStatus,
    EvaluationMetricsSchema,
)

# ── Ground-Truth Relevance Mapping from Phase 3.6 Feedback Semantics ──────────
# Consistent with Phase 3.6 event weights:
# APPLY (strongest positive) > INTERESTED > SAVE > VIEW (weak positive) > DISMISS / NOT_INTERESTED (negative)
GRADED_RELEVANCE_MAP: dict[str, float] = {
    "APPLY": 4.0,           # Highest graded relevance
    "INTERESTED": 3.0,      # High graded relevance
    "SAVE": 2.0,            # Positive graded relevance
    "VIEW": 1.0,            # Weak positive graded relevance
    "DISMISS": 0.0,         # Negative / not relevant
    "NOT_INTERESTED": 0.0,  # Negative / not relevant
}

# Positive feedback events constituting binary relevance for Precision@K / Recall@K / HitRate@K
BINARY_RELEVANT_FEEDBACK_TYPES: frozenset[str] = frozenset({"SAVE", "INTERESTED", "APPLY"})

# All interactive engagement events
ENGAGEMENT_FEEDBACK_TYPES: frozenset[str] = frozenset({"VIEW", "SAVE", "INTERESTED", "APPLY"})

# Explicit dismissal/negative events
DISMISSAL_FEEDBACK_TYPES: frozenset[str] = frozenset({"DISMISS", "NOT_INTERESTED"})

# Minimum unique items needed to consider evaluation data statistically meaningful
MIN_EVALUATION_ITEMS_THRESHOLD: int = 5


class RecommendationEvaluationEngine:
    """
    Offline evaluation engine for recommendation history and feedback.
    """

    @classmethod
    def get_graded_relevance_for_opportunity(
        cls, feedback_types: Sequence[str]
    ) -> float:
        """
        Derive highest graded relevance score for an opportunity from researcher actions.
        """
        if not feedback_types:
            return 0.0
        return max(GRADED_RELEVANCE_MAP.get(ft.upper(), 0.0) for ft in feedback_types)

    @classmethod
    def is_binary_relevant(cls, feedback_types: Sequence[str]) -> bool:
        """
        Determine if feedback on an opportunity represents a positive endorsement.
        """
        upper_types = {ft.upper() for ft in feedback_types}
        return bool(upper_types & BINARY_RELEVANT_FEEDBACK_TYPES)

    @classmethod
    def evaluate_snapshot(
        cls,
        ordered_opportunity_ids: Sequence[uuid.UUID],
        feedback_by_opp: Mapping[uuid.UUID, Sequence[str]],
        all_known_relevant_ids: Set[uuid.UUID],
    ) -> dict[str, Any]:
        """
        Calculate per-snapshot IR metrics (Precision@5/10, Recall@10, HitRate@5/10, NDCG@5/10).

        Parameters
        ----------
        ordered_opportunity_ids : Sequence[uuid.UUID]
            Recommended opportunities in presented rank order.
        feedback_by_opp : Mapping[uuid.UUID, Sequence[str]]
            Mapping of opportunity_id -> list of feedback type strings for this researcher.
        all_known_relevant_ids : Set[uuid.UUID]
            All opportunities with confirmed positive feedback for this researcher.
        """
        if not ordered_opportunity_ids:
            return {
                "precision_at_5": None,
                "precision_at_10": None,
                "recall_at_5": None,
                "recall_at_10": None,
                "hit_rate_at_5": None,
                "hit_rate_at_10": None,
                "ndcg_at_5": None,
                "ndcg_at_10": None,
            }

        # Snapshot-local relevant opportunities
        local_relevant_ids = {
            opp_id
            for opp_id in ordered_opportunity_ids
            if cls.is_binary_relevant(feedback_by_opp.get(opp_id, []))
        }

        # Graded relevance mapping for NDCG
        graded_map = {
            opp_id: cls.get_graded_relevance_for_opportunity(feedback_by_opp.get(opp_id, []))
            for opp_id in ordered_opportunity_ids
        }

        p5 = precision_at_k(ordered_opportunity_ids, local_relevant_ids, k=5)
        p10 = precision_at_k(ordered_opportunity_ids, local_relevant_ids, k=10)

        # Recall@5 and Recall@10: proportion of all known relevant opportunities retrieved in top K
        if len(all_known_relevant_ids) > 0:
            rec5 = recall_at_k(ordered_opportunity_ids, all_known_relevant_ids, k=5)
            rec10 = recall_at_k(ordered_opportunity_ids, all_known_relevant_ids, k=10)
        else:
            rec5 = None
            rec10 = None

        hr5 = hit_rate_at_k(ordered_opportunity_ids, local_relevant_ids, k=5)
        hr10 = hit_rate_at_k(ordered_opportunity_ids, local_relevant_ids, k=10)

        # NDCG@K
        has_any_graded = any(score > 0.0 for score in graded_map.values())
        if has_any_graded:
            ndcg5 = normalized_discounted_cumulative_gain_at_k(ordered_opportunity_ids, graded_map, k=5)
            ndcg10 = normalized_discounted_cumulative_gain_at_k(ordered_opportunity_ids, graded_map, k=10)
        else:
            ndcg5 = 0.0
            ndcg10 = 0.0

        return {
            "precision_at_5": round(p5, 4),
            "precision_at_10": round(p10, 4),
            "recall_at_5": round(rec5, 4) if rec5 is not None else None,
            "recall_at_10": round(rec10, 4) if rec10 is not None else None,
            "hit_rate_at_5": round(hr5, 4),
            "hit_rate_at_10": round(hr10, 4),
            "ndcg_at_5": round(ndcg5, 4),
            "ndcg_at_10": round(ndcg10, 4),
        }

    @classmethod
    def calculate_aggregate_metrics(
        cls,
        snapshots_with_ordered_items: Sequence[Sequence[uuid.UUID]],
        feedback_by_opp: Mapping[uuid.UUID, Sequence[str]],
        all_researcher_relevant_ids: Set[uuid.UUID],
    ) -> EvaluationMetricsSchema:
        """
        Aggregate evaluation metrics across multiple recommendation snapshots.

        Parameters
        ----------
        snapshots_with_ordered_items : Sequence[Sequence[uuid.UUID]]
            List of snapshots, where each snapshot is an ordered list of opportunity IDs.
        feedback_by_opp : Mapping[uuid.UUID, Sequence[str]]
            Mapping from opportunity ID to feedback types for this researcher.
        all_researcher_relevant_ids : Set[uuid.UUID]
            Set of all opportunities positively endorsed by this researcher.
        """
        # Collect all unique opportunities shown across snapshots
        all_shown_opp_ids: set[uuid.UUID] = set()
        for snap_items in snapshots_with_ordered_items:
            all_shown_opp_ids.update(snap_items)

        total_sample_size = len(all_shown_opp_ids)

        # ── Data Sufficiency Check: Zero History ───────────────────────────────
        if not snapshots_with_ordered_items or total_sample_size == 0:
            return EvaluationMetricsSchema(
                precision_at_5=None,
                precision_at_10=None,
                recall_at_5=None,
                recall_at_10=None,
                hit_rate_at_5=None,
                hit_rate_at_10=None,
                ndcg_at_5=None,
                ndcg_at_10=None,
                save_rate=None,
                engagement_rate=None,
                dismissal_rate=None,
                data_status=DataSufficiencyStatus.NO_HISTORY,
                sample_size=0,
                feedback_count=0,
                notes="No recommendation history exists for this researcher.",
            )

        # Count feedback events associated with recommended items
        feedback_events_count = sum(
            len(feedback_by_opp.get(opp_id, [])) for opp_id in all_shown_opp_ids
        )

        # ── Data Sufficiency Check: Zero Feedback ─────────────────────────────
        if feedback_events_count == 0:
            return EvaluationMetricsSchema(
                precision_at_5=None,
                precision_at_10=None,
                recall_at_5=None,
                recall_at_10=None,
                hit_rate_at_5=None,
                hit_rate_at_10=None,
                ndcg_at_5=None,
                ndcg_at_10=None,
                save_rate=0.0,
                engagement_rate=0.0,
                dismissal_rate=0.0,
                data_status=DataSufficiencyStatus.NO_FEEDBACK,
                sample_size=total_sample_size,
                feedback_count=0,
                notes="Recommendations have been served, but researcher has not recorded any interaction feedback yet.",
            )

        # ── Calculate Global Outcome Rates ────────────────────────────────────
        saved_count = 0
        engaged_count = 0
        dismissed_count = 0

        for opp_id in all_shown_opp_ids:
            fb_list = [ft.upper() for ft in feedback_by_opp.get(opp_id, [])]
            if "SAVE" in fb_list:
                saved_count += 1
            if any(ft in ENGAGEMENT_FEEDBACK_TYPES for ft in fb_list):
                engaged_count += 1
            if any(ft in DISMISSAL_FEEDBACK_TYPES for ft in fb_list):
                dismissed_count += 1

        save_rate = round(saved_count / float(total_sample_size), 4)
        engagement_rate = round(engaged_count / float(total_sample_size), 4)
        dismissal_rate = round(dismissed_count / float(total_sample_size), 4)

        # ── Calculate IR Metrics across Snapshots ─────────────────────────────
        p5_scores: list[float] = []
        p10_scores: list[float] = []
        rec5_scores: list[float] = []
        rec10_scores: list[float] = []
        hr5_scores: list[float] = []
        hr10_scores: list[float] = []
        ndcg5_scores: list[float] = []
        ndcg10_scores: list[float] = []

        for snap_items in snapshots_with_ordered_items:
            res = cls.evaluate_snapshot(
                snap_items,
                feedback_by_opp=feedback_by_opp,
                all_known_relevant_ids=all_researcher_relevant_ids,
            )
            if res["precision_at_5"] is not None:
                p5_scores.append(res["precision_at_5"])
            if res["precision_at_10"] is not None:
                p10_scores.append(res["precision_at_10"])
            if res["recall_at_5"] is not None:
                rec5_scores.append(res["recall_at_5"])
            if res["recall_at_10"] is not None:
                rec10_scores.append(res["recall_at_10"])
            if res["hit_rate_at_5"] is not None:
                hr5_scores.append(res["hit_rate_at_5"])
            if res["hit_rate_at_10"] is not None:
                hr10_scores.append(res["hit_rate_at_10"])
            if res["ndcg_at_5"] is not None:
                ndcg5_scores.append(res["ndcg_at_5"])
            if res["ndcg_at_10"] is not None:
                ndcg10_scores.append(res["ndcg_at_10"])

        avg_p5 = round(sum(p5_scores) / len(p5_scores), 4) if p5_scores else None
        avg_p10 = round(sum(p10_scores) / len(p10_scores), 4) if p10_scores else None
        avg_rec5 = round(sum(rec5_scores) / len(rec5_scores), 4) if rec5_scores else None
        avg_rec10 = round(sum(rec10_scores) / len(rec10_scores), 4) if rec10_scores else None
        avg_hr5 = round(sum(hr5_scores) / len(hr5_scores), 4) if hr5_scores else None
        avg_hr10 = round(sum(hr10_scores) / len(hr10_scores), 4) if hr10_scores else None
        avg_ndcg5 = round(sum(ndcg5_scores) / len(ndcg5_scores), 4) if ndcg5_scores else None
        avg_ndcg10 = round(sum(ndcg10_scores) / len(ndcg10_scores), 4) if ndcg10_scores else None

        # ── Data Sufficiency Classification ───────────────────────────────────
        if total_sample_size < MIN_EVALUATION_ITEMS_THRESHOLD:
            status = DataSufficiencyStatus.INSUFFICIENT_DATA
            notes = (
                f"Sample size ({total_sample_size} items) is below statistical threshold "
                f"({MIN_EVALUATION_ITEMS_THRESHOLD} items). Metrics may have high variance."
            )
        elif len(all_researcher_relevant_ids) == 0:
            status = DataSufficiencyStatus.INSUFFICIENT_DATA
            notes = "No positive ground-truth feedback recorded yet; Recall cannot be calculated."
        else:
            status = DataSufficiencyStatus.SUFFICIENT_DATA
            notes = (
                f"Sufficient feedback data ({feedback_events_count} events across "
                f"{total_sample_size} unique items). Evaluation is statistically grounded."
            )

        return EvaluationMetricsSchema(
            precision_at_5=avg_p5,
            precision_at_10=avg_p10,
            recall_at_5=avg_rec5,
            recall_at_10=avg_rec10,
            hit_rate_at_5=avg_hr5,
            hit_rate_at_10=avg_hr10,
            ndcg_at_5=avg_ndcg5,
            ndcg_at_10=avg_ndcg10,
            save_rate=save_rate,
            engagement_rate=engagement_rate,
            dismissal_rate=dismissal_rate,
            data_status=status,
            sample_size=total_sample_size,
            feedback_count=feedback_events_count,
            notes=notes,
        )
