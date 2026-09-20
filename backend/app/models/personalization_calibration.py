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
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.adaptive_signal import AdaptivePreferenceSignalModel
    from app.models.opportunity import OpportunityModel
    from app.models.research_profile import ResearchProfileModel
    from app.models.researcher_interaction import ResearcherInteractionModel


class CalibrationState(str, Enum):
    """Deterministic classification of calibration evidence volume and agreement."""

    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    EARLY_SIGNAL = "EARLY_SIGNAL"
    CALIBRATING = "CALIBRATING"
    STABLE = "STABLE"
    CONFLICTED = "CONFLICTED"


class AttributionConfidence(str, Enum):
    """Deterministic attribution confidence tier between recommendation and subsequent interaction."""

    DIRECT = "DIRECT"
    LIKELY = "LIKELY"
    WEAK = "WEAK"
    UNATTRIBUTED = "UNATTRIBUTED"


class FeedbackOutcomeType(str, Enum):
    """Deterministic classification of post-recommendation researcher engagement."""

    STRONG_POSITIVE = "STRONG_POSITIVE"
    MODERATE_POSITIVE = "MODERATE_POSITIVE"
    WEAK_POSITIVE = "WEAK_POSITIVE"
    NEGATIVE = "NEGATIVE"
    NEUTRAL = "NEUTRAL"


class PersonalizationCalibrationModel(Base):
    """
    Normalized persistent representation of an aggregated personalization calibration record (Phase 5.6).

    Answers:
      "When this personalization signal influenced recommendations for this researcher,
       what subsequent feedback was observed, and what bounded modifier should be applied?"

    Strict Architectural Boundaries:
      - Calibration evidence is derived performance measurement, NOT a new preference.
      - Calibration evidence NEVER mutates explicit preferences in ResearcherPreferenceModel.
      - Explicit exclusions always dominate (final score = 0.0).
      - Calibration modifier is strictly clamped to [-0.05, +0.05].
      - Total adaptive contribution remains strictly clamped to [-0.10, +0.10].
      - Zero ML / Zero LLM / Zero collaborative filtering: 100% deterministic calculation.
    """

    __tablename__ = "personalization_calibrations"
    __table_args__ = (
        UniqueConstraint(
            "profile_id",
            "dimension",
            "signal_value",
            name="uq_personalization_calibrations_profile_dim_val",
        ),
        Index("idx_calibrations_profile_dim", "profile_id", "dimension"),
        Index("idx_calibrations_profile_state", "profile_id", "calibration_state"),
        Index("idx_calibrations_updated_at", "updated_at"),
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

    # Signal dimension (e.g. OPPORTUNITY_TYPE, RESEARCH_TOPIC, DELIVERY_MODE, LOCATION, PUBLISHER)
    dimension: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Attribute dimension for the calibrated signal",
    )

    # Specific attribute value (e.g. 'CONFERENCE', 'Artificial Intelligence', 'ONLINE')
    signal_value: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="Attribute value for the calibrated signal",
    )

    # Number of recommendations influenced by this signal
    recommendations_influenced_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Count of presented recommendations influenced by this signal",
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

    # Accumulated decay-adjusted weights
    accumulated_positive_weight: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="Decay and confidence adjusted positive feedback weight",
    )
    accumulated_negative_weight: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="Decay and confidence adjusted negative feedback weight",
    )

    # Bounded calibration modifier clamped in [-0.05, +0.05]
    net_calibration_modifier: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="Bounded additive calibration modifier in [-0.05, +0.05]",
    )

    # Bounded calibration confidence in [0.0, 1.0]
    calibration_confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="Confidence metric in [0.0, 1.0] reflecting evidence volume, recency, and outcome agreement",
    )

    # Evidence sufficiency state
    calibration_state: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="INSUFFICIENT_DATA",
        index=True,
        comment="State: INSUFFICIENT_DATA, EARLY_SIGNAL, CALIBRATING, STABLE, CONFLICTED",
    )

    # Version identifier of the calibration algorithm
    algorithm_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="5.6.1",
        comment="Calibration algorithm and parameter version",
    )

    # Human-readable deterministic explanation
    deterministic_explanation: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Explainable natural language description of calibration evidence",
    )

    # Timestamp of latest feedback contributing to this calibration
    latest_feedback_timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp of latest feedback event contributing to calibration",
    )

    # Lifecycle timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    researcher_profile: Mapped["ResearchProfileModel"] = relationship(
        back_populates="personalization_calibrations",
    )
    adaptive_signal: Mapped[Optional["AdaptivePreferenceSignalModel"]] = relationship()


class RecommendationFeedbackAttributionModel(Base):
    """
    Granular, auditable attribution event linking a recommendation exposure to a subsequent researcher interaction (Phase 5.6).

    Answers:
      "Which specific recommendation exposure was associated with this researcher interaction,
       which signal was evaluated, and what weight did it contribute to calibration?"
    """

    __tablename__ = "recommendation_feedback_attributions"
    __table_args__ = (
        Index("idx_attributions_profile_opp", "profile_id", "opportunity_id"),
        Index("idx_attributions_profile_signal", "profile_id", "dimension", "signal_value"),
        Index("idx_attributions_interaction_time", "interaction_timestamp"),
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

    # Opportunity identity
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("opportunities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Associated OpportunityModel ID",
    )

    # Optional interaction link
    interaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("researcher_interactions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Associated ResearcherInteractionModel ID if linked",
    )

    # Signal dimension & value
    dimension: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Signal dimension (OPPORTUNITY_TYPE, RESEARCH_TOPIC, etc.)",
    )
    signal_value: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="Signal value for this attribution",
    )

    # Personalization contribution that influenced this recommendation
    personalization_contribution: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="Personalization contribution of this signal at recommendation time",
    )

    # Interaction type and outcome classification
    interaction_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Interaction type (e.g. SAVED, INTERESTED, DISMISSED, VIEWED)",
    )
    outcome_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Outcome type (STRONG_POSITIVE, MODERATE_POSITIVE, WEAK_POSITIVE, NEGATIVE, NEUTRAL)",
    )

    # Attribution confidence tier and weight
    attribution_confidence: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="DIRECT",
        comment="Attribution tier: DIRECT, LIKELY, WEAK, UNATTRIBUTED",
    )
    attribution_weight: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=1.0,
        comment="Attribution confidence multiplier in [0.0, 1.0]",
    )
    decay_adjusted_weight: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="Final weight combining outcome weight, attribution confidence, and temporal decay",
    )

    # Timestamps
    recommendation_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Timestamp when recommendation exposure occurred",
    )
    interaction_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Timestamp when subsequent interaction occurred",
    )

    # Version identifier
    algorithm_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="5.6.1",
        comment="Attribution algorithm version",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    researcher_profile: Mapped["ResearchProfileModel"] = relationship()
    opportunity: Mapped["OpportunityModel"] = relationship()
    interaction: Mapped[Optional["ResearcherInteractionModel"]] = relationship()
