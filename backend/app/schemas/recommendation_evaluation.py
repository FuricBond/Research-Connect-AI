"""
Pydantic schemas for Phase 3.7 — Recommendation Evaluation.

Strict Architectural Boundaries:
  - Read-only outcome and offline evaluation metrics.
  - Does NOT alter recommendation ranking weights or preferences.
  - Declares explicit data sufficiency states (SUFFICIENT_DATA, INSUFFICIENT_DATA, NO_FEEDBACK, NO_HISTORY).
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
import uuid

from pydantic import BaseModel, ConfigDict, Field


class DataSufficiencyStatus(str, Enum):
    """
    Explicit data sufficiency classification for evaluation metrics.
    """

    SUFFICIENT_DATA = "SUFFICIENT_DATA"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    NO_FEEDBACK = "NO_FEEDBACK"
    NO_HISTORY = "NO_HISTORY"


class EvaluationMetricsSchema(BaseModel):
    """
    Standardized Information Retrieval (IR) and outcome rate metrics.
    """

    model_config = ConfigDict(from_attributes=True)

    # IR metrics (Top-K)
    precision_at_5: float | None = Field(
        None, description="Precision@5 (proportion of top 5 items with positive feedback)"
    )
    precision_at_10: float | None = Field(
        None, description="Precision@10 (proportion of top 10 items with positive feedback)"
    )
    recall_at_5: float | None = Field(
        None, description="Recall@5 (relevant items retrieved in top 5 / all known relevant items)"
    )
    recall_at_10: float | None = Field(
        None, description="Recall@10 (relevant items retrieved in top 10 / all known relevant items)"
    )
    hit_rate_at_5: float | None = Field(
        None, description="HitRate@5 (1.0 if at least one relevant item in top 5, else 0.0)"
    )
    hit_rate_at_10: float | None = Field(
        None, description="HitRate@10 (1.0 if at least one relevant item in top 10, else 0.0)"
    )
    ndcg_at_5: float | None = Field(
        None, description="NDCG@5 (Normalized Discounted Cumulative Gain at 5 with graded relevance)"
    )
    ndcg_at_10: float | None = Field(
        None, description="NDCG@10 (Normalized Discounted Cumulative Gain at 10 with graded relevance)"
    )

    # Outcome rates
    save_rate: float | None = Field(
        None, description="Save Rate (saved recommended opportunities / recommended opportunities shown)"
    )
    engagement_rate: float | None = Field(
        None, description="Engagement Rate (engaged [VIEW, SAVE, INTERESTED, APPLY] / shown)"
    )
    dismissal_rate: float | None = Field(
        None, description="Dismissal Rate (dismissed [DISMISS, NOT_INTERESTED] / shown)"
    )

    # Data sufficiency evidence
    data_status: DataSufficiencyStatus = Field(
        ..., description="Data sufficiency status for this metric set"
    )
    sample_size: int = Field(
        ..., ge=0, description="Total unique recommended items evaluated"
    )
    feedback_count: int = Field(
        ..., ge=0, description="Total feedback events linked to evaluated items"
    )
    notes: str | None = Field(
        None, description="Contextual explanation of data sufficiency or limitations"
    )


class VersionComparisonSummary(BaseModel):
    """
    Comparative metric summary for a specific ranking algorithm version.
    """

    model_config = ConfigDict(from_attributes=True)

    ranking_version: str = Field(..., description="Algorithm version identifier")
    display_name: str = Field(..., description="Friendly display name (e.g. 'R0 Baseline', 'R1 Personalized')")
    sample_size: int = Field(..., description="Sample size for this version")
    data_status: DataSufficiencyStatus = Field(..., description="Data sufficiency status")
    metrics: EvaluationMetricsSchema = Field(..., description="Metrics for this version")


class RecommendationEvaluationResponse(BaseModel):
    """
    Complete recommendation evaluation response schema.
    """

    model_config = ConfigDict(from_attributes=True)

    researcher_id: uuid.UUID = Field(..., description="Researcher profile ID")
    ranking_version: str | None = Field(None, description="Evaluated ranking version filter, or None if aggregate")
    total_snapshots: int = Field(..., ge=0, description="Total snapshots in evaluation window")
    total_recommendations: int = Field(..., ge=0, description="Total recommendation item impressions")
    total_feedback_events: int = Field(..., ge=0, description="Total feedback events linked to recommendations")
    data_status: DataSufficiencyStatus = Field(..., description="Overall data sufficiency classification")
    metrics: EvaluationMetricsSchema = Field(..., description="Primary evaluation metrics")
    ranking_comparison: dict[str, VersionComparisonSummary] | None = Field(
        default_factory=dict,
        description="Comparative breakdown by ranking version (R0 vs R1 vs R2) if historical data exists",
    )
    evaluated_at: datetime = Field(..., description="Timestamp of offline evaluation run")
