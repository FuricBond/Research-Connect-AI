from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional
import uuid

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.adaptive_signal import AdaptivePreferenceSignalModel
    from app.models.research_profile import ResearchProfileModel


class QualityEvaluationState(str, Enum):
    """Deterministic classification of personalization quality evaluation evidence and outcome tendency."""

    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    EARLY_SIGNAL = "EARLY_SIGNAL"
    EVALUATING = "EVALUATING"
    STABLE = "STABLE"
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    MIXED = "MIXED"


class ContextualFallbackLevel(str, Enum):
    """Deterministic hierarchy level used for contextual adaptation fallback."""

    RESEARCHER_EXACT_CONTEXT = "RESEARCHER_EXACT_CONTEXT"
    RESEARCHER_BROAD_CONTEXT = "RESEARCHER_BROAD_CONTEXT"
    GLOBAL_SIGNAL_CALIBRATION = "GLOBAL_SIGNAL_CALIBRATION"
    NEUTRAL = "NEUTRAL"

    # Aliases
    EXACT_CONTEXT = "RESEARCHER_EXACT_CONTEXT"
    BROAD_CONTEXT = "RESEARCHER_BROAD_CONTEXT"
    GLOBAL_SIGNAL = "GLOBAL_SIGNAL_CALIBRATION"


class PersonalizationQualityEvaluationModel(Base):
    """
    Normalized persistent representation of an aggregated personalization quality evaluation (Phase 5.7).

    Answers:
      "Is personalization actually improving the usefulness of recommendations for this researcher,
       and what is the observed engagement rate, positive feedback rate, and observed personalization lift?"

    Strict Architectural Boundaries:
      - Read-only evaluation of recommendation performance against subsequent feedback.
      - Never mutates explicit preferences in ResearcherPreferenceModel.
      - Explicit exclusions always dominate (final score = 0.0).
      - Zero ML / Zero LLM / Zero collaborative filtering: 100% deterministic calculation.
    """

    __tablename__ = "personalization_quality_evaluations"
    __table_args__ = (
        UniqueConstraint(
            "profile_id",
            "algorithm_version",
            name="uq_personalization_quality_profile_version",
        ),
        Index("idx_quality_eval_profile_state", "profile_id", "evaluation_state"),
        Index("idx_quality_eval_updated_at", "updated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Link to canonical research profile
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Associated ResearchProfileModel ID",
    )

    # Evaluation horizon in days (default 30.0)
    evaluation_window_days: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=30.0,
        comment="Evaluation window horizon in days",
    )

    # Evaluation timestamp
    evaluation_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Reference timestamp when quality evaluation was performed",
    )

    # Evaluated volume counts
    total_recommendations_evaluated: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Count of distinct recommended opportunities evaluated in the window",
    )
    total_attributed_interactions: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Count of interactions attributed to recommendations in the window",
    )

    # Outcome counts
    positive_outcome_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Count of positive attributed outcomes (APPLIED, INTERESTED, SAVED, SHARED, OPENED, VIEWED)",
    )
    negative_outcome_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Count of negative attributed outcomes (NOT_INTERESTED, DISMISSED, HIDDEN)",
    )
    neutral_outcome_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Count of neutral or unengaged attributed recommendations",
    )

    # Quality metrics
    engagement_rate: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Engaged recommendations / eligible exposed recommendations",
    )
    positive_feedback_rate: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Positive outcomes / total attributed interactions",
    )
    negative_feedback_rate: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Negative outcomes / total attributed interactions",
    )
    observed_personalization_lift: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Observed difference in positive engagement between personalized and baseline recommendations",
    )
    calibration_agreement_rate: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Proportion of cases where calibration direction matched subsequent feedback",
    )
    recommendation_diversity_score: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Normalized recommendation diversity across opportunity types and domains",
    )
    novelty_rate: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Proportion of newly surfaced opportunities vs previously seen/interacted ones",
    )
    repeated_exposure_ratio: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Ratio of opportunities presented multiple times in the evaluation window",
    )

    # Evaluation confidence in [0.0, 1.0]
    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="Evaluation confidence in [0.0, 1.0] reflecting evidence volume and outcome consistency",
    )

    # Evaluation state: INSUFFICIENT_DATA, EARLY_SIGNAL, EVALUATING, STABLE, POSITIVE, NEGATIVE, MIXED
    evaluation_state: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="INSUFFICIENT_DATA",
        index=True,
        comment="Evaluation state classification",
    )

    # Algorithm version
    algorithm_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="5.7.1",
        comment="Evaluation algorithm and configuration version",
    )

    # Human-readable deterministic explanation
    deterministic_explanation: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Explainable natural language description of personalization quality",
    )

    # Structured metrics breakdown
    quality_metrics_breakdown: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Detailed JSON metrics breakdown by context, dimension, and signal",
    )

    # Lifecycle timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Evaluation creation timestamp",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="Evaluation last update timestamp",
    )

    # Relationships
    profile: Mapped[Optional["ResearchProfileModel"]] = relationship(
        foreign_keys=[profile_id],
        back_populates="quality_evaluations",
    )


class PersonalizationContextualAdaptationModel(Base):
    """
    Granular, bounded contextual adaptation record per signal and context dimension (Phase 5.7).

    Answers:
      "For this researcher and personalization signal, how does it perform in specific contexts
       (e.g., NEAR deadline, HYBRID delivery, CONFERENCE type), and what bounded contextual modifier should be applied?"
    """

    __tablename__ = "personalization_contextual_adaptations"
    __table_args__ = (
        UniqueConstraint(
            "profile_id",
            "signal_dimension",
            "signal_value",
            "context_type",
            "context_value",
            name="uq_contextual_adaptations_profile_signal_context",
        ),
        Index("idx_context_adapt_profile_signal", "profile_id", "signal_dimension", "signal_value"),
        Index("idx_context_adapt_context", "profile_id", "context_type", "context_value"),
        Index("idx_context_adapt_updated_at", "updated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Link to canonical research profile
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Associated ResearchProfileModel ID",
    )

    # Optional foreign key to active adaptive signal
    signal_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("adaptive_preference_signals.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Associated AdaptivePreferenceSignalModel ID if present",
    )

    # Signal dimension & value
    signal_dimension: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Signal dimension (e.g. OPPORTUNITY_TYPE, RESEARCH_TOPIC, DELIVERY_MODE)",
    )
    signal_value: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="Signal value (e.g. 'CONFERENCE', 'Artificial Intelligence')",
    )

    # Context dimension & value
    context_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Context dimension (e.g. DEADLINE_HORIZON, DELIVERY_MODE, RISK_TIER, OPPORTUNITY_TYPE)",
    )
    context_value: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="Context value (e.g. 'NEAR', 'HYBRID', 'LOW')",
    )

    # Context evidence counts
    recommendations_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Count of recommendations presented in this specific context",
    )
    positive_outcome_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Positive outcomes in this specific context",
    )
    negative_outcome_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Negative outcomes in this specific context",
    )

    # Context-specific performance metrics
    context_engagement_rate: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Engagement rate observed in this specific context",
    )
    contextual_lift: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Observed personalization lift in this specific context vs baseline",
    )

    # Bounded contextual modifier clamped in [-0.03, +0.03]
    contextual_modifier: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="Bounded contextual adaptation modifier in [-0.03, +0.03]",
    )

    # Confidence in [0.0, 1.0]
    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="Confidence metric for this context slice",
    )

    # Adaptation state
    adaptation_state: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="INSUFFICIENT_DATA",
        comment="State: INSUFFICIENT_DATA, EARLY_SIGNAL, EVALUATING, STABLE, POSITIVE, NEGATIVE, MIXED",
    )

    # Hierarchical fallback level used
    fallback_level: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="EXACT_CONTEXT",
        comment="Fallback level: EXACT_CONTEXT, BROAD_CONTEXT, GLOBAL_SIGNAL, NEUTRAL",
    )

    # Human-readable deterministic explanation
    deterministic_explanation: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Explainable natural language description of contextual adaptation",
    )

    # Algorithm version
    algorithm_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="5.7.1",
        comment="Contextual adaptation algorithm and version",
    )

    # Lifecycle timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Adaptation creation timestamp",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="Adaptation last update timestamp",
    )

    # Relationships
    profile: Mapped[Optional["ResearchProfileModel"]] = relationship(
        foreign_keys=[profile_id],
        back_populates="contextual_adaptations",
    )
    adaptive_signal: Mapped[Optional["AdaptivePreferenceSignalModel"]] = relationship(
        foreign_keys=[signal_id],
    )
