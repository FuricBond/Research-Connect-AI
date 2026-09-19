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
    from app.models.research_profile import ResearchProfileModel


class AdaptiveSignalDimension(str, Enum):
    """Supported dimensions for adaptive preference aggregation (Phase 5.5)."""

    OPPORTUNITY_TYPE = "OPPORTUNITY_TYPE"
    RESEARCH_TOPIC = "RESEARCH_TOPIC"
    DELIVERY_MODE = "DELIVERY_MODE"
    LOCATION = "LOCATION"
    PUBLISHER = "PUBLISHER"


class AdaptiveEvidenceState(str, Enum):
    """Deterministic classification of evidence volume and reliability."""

    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    EMERGING = "EMERGING"
    ESTABLISHED = "ESTABLISHED"
    STRONG = "STRONG"


class AdaptivePreferenceSignalModel(Base):
    """
    Normalized persistent representation of an aggregated researcher adaptive preference signal (Phase 5.5).

    Answers:
      "Based on historical interaction behavior, what bounded affinity or aversion has
       this researcher demonstrated for this specific opportunity attribute?"

    Strict Architectural Boundaries:
      - Adaptive signals are behavioral evidence, NOT explicit declarations.
      - Explicit preferences (Phase 5.1) remain authoritative and are NEVER mutated.
      - Explicit exclusions always dominate positive adaptive signals.
      - Zero ML / Zero LLM / Zero collaborative filtering: 100% deterministic aggregation.
    """

    __tablename__ = "adaptive_preference_signals"
    __table_args__ = (
        UniqueConstraint(
            "profile_id",
            "dimension",
            "signal_value",
            name="uq_adaptive_signals_profile_dim_val",
        ),
        Index("idx_adaptive_signals_profile_dim", "profile_id", "dimension"),
        Index("idx_adaptive_signals_profile_state", "profile_id", "evidence_state"),
        Index("idx_adaptive_signals_updated_at", "updated_at"),
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

    # Signal dimension (e.g. OPPORTUNITY_TYPE, RESEARCH_TOPIC, DELIVERY_MODE, LOCATION, PUBLISHER)
    dimension: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Attribute dimension (OPPORTUNITY_TYPE, RESEARCH_TOPIC, DELIVERY_MODE, LOCATION, PUBLISHER)",
    )

    # Specific attribute value (e.g. 'CONFERENCE', 'Artificial Intelligence', 'ONLINE')
    signal_value: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="Attribute value for this signal",
    )

    # Distinct positive and negative evidence counts
    positive_evidence_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Count of positive interactions (SAVED, INTERESTED, APPLIED, SHARED, VIEWED, OPENED)",
    )
    negative_evidence_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Count of negative interactions (NOT_INTERESTED, DISMISSED, HIDDEN)",
    )
    total_evidence_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Sum of positive and negative interactions",
    )

    # Decay-adjusted weighted sums
    decay_adjusted_positive_weight: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="Exponential decay-adjusted sum of positive interaction weights",
    )
    decay_adjusted_negative_weight: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="Exponential decay-adjusted sum of negative interaction weights",
    )

    # Normalized net signal strength in [-1.0, 1.0]
    weighted_signal_strength: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="Bounded net signal strength in [-1.0, 1.0]",
    )

    # Bounded confidence in [0.0, 1.0]
    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="Confidence metric in [0.0, 1.0] reflecting volume, recency, and agreement",
    )

    # Evidence sufficiency state
    evidence_state: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="INSUFFICIENT_EVIDENCE",
        index=True,
        comment="State: INSUFFICIENT_EVIDENCE, EMERGING, ESTABLISHED, STRONG",
    )

    # Observation window (days)
    evidence_window_days: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=180.0,
        comment="Observation window horizon in days",
    )

    # Latest interaction timestamp contributing to this signal
    latest_evidence_timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp of latest interaction contributing to this signal",
    )

    # Version identifier of the aggregation algorithm
    algorithm_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="5.5.1",
        comment="Aggregation algorithm and parameter version",
    )

    # Human-readable deterministic explanation
    deterministic_explanation: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Explainable natural language description of evidence basis",
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
        back_populates="adaptive_signals",
    )
