from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any
import uuid

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.research_profile import ResearchProfileModel


class PersonalizationImpact(str, Enum):
    """Bounded classification of how much personalization influenced a recommendation."""

    NO_PERSONALIZATION = "NO_PERSONALIZATION"
    LOW_PERSONALIZATION = "LOW_PERSONALIZATION"
    MODERATE_PERSONALIZATION = "MODERATE_PERSONALIZATION"
    STRONG_PERSONALIZATION = "STRONG_PERSONALIZATION"
    PERSONALIZATION_SUPPRESSED = "PERSONALIZATION_SUPPRESSED"


class PersonalizationControlEventType(str, Enum):
    """Auditable researcher-facing personalization control events."""

    PERSONALIZATION_ENABLED = "PERSONALIZATION_ENABLED"
    PERSONALIZATION_DISABLED = "PERSONALIZATION_DISABLED"
    ADAPTIVE_SIGNALS_ENABLED = "ADAPTIVE_SIGNALS_ENABLED"
    ADAPTIVE_SIGNALS_DISABLED = "ADAPTIVE_SIGNALS_DISABLED"
    FEEDBACK_LEARNING_ENABLED = "FEEDBACK_LEARNING_ENABLED"
    FEEDBACK_LEARNING_DISABLED = "FEEDBACK_LEARNING_DISABLED"
    PERSONALIZATION_RESET = "PERSONALIZATION_RESET"


class ResearcherPersonalizationSettingsModel(Base, TimestampMixin):
    """
    Persistent settings controlling personalization behavior for a researcher (Phase 5.9).

    Enforces the strict hierarchy:
      system safety constraints > eligibility > core relevance > explicit preferences >
      researcher personalization controls > adaptive signals > calibration > contextual adaptation.

    Strict Invariants:
      - Disabling personalization never weakens core relevance (>= 0.85) or safety rules.
      - Explicit EXCLUDED preferences cannot be bypassed by any control setting.
      - Resetting derived personalization increments personalization_state_version and neutralizes
        derived signals without deleting accounts, profiles, or explicit preferences.
    """

    __tablename__ = "researcher_personalization_settings"
    __table_args__ = (
        Index("idx_pers_settings_profile_id", "profile_id", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research_profiles.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
        comment="Associated ResearchProfileModel ID",
    )

    personalization_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Global toggle: whether personalization modifiers are applied to recommendations",
    )

    adaptive_signals_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Whether inferred behavioral/adaptive signals may modify recommendations",
    )

    feedback_learning_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Whether new researcher feedback is aggregated into future adaptive signals",
    )

    personalization_state_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="Monotonically increasing version; incremented on personalization reset to invalidate prior derived state",
    )

    # Relationships
    researcher_profile: Mapped["ResearchProfileModel"] = relationship(
        back_populates="personalization_settings",
    )


class PersonalizationControlEventModel(Base):
    """
    Append-only audit trail recording all researcher-initiated personalization control changes (Phase 5.9).
    """

    __tablename__ = "personalization_control_events"
    __table_args__ = (
        Index("idx_pers_control_events_profile_id", "profile_id"),
        Index("idx_pers_control_events_created_at", "created_at"),
        Index("idx_pers_control_events_type", "event_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Associated ResearchProfileModel ID",
    )

    event_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Type of control event: e.g. PERSONALIZATION_ENABLED, PERSONALIZATION_RESET",
    )

    previous_state: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="Snapshot of settings before this control action",
    )

    new_state: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="Snapshot of settings after this control action",
    )

    trigger_reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Deterministic explanation or user-supplied reason for this control action",
    )

    algorithm_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="5.9.1",
        comment="Deterministic transparency algorithm version",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        comment="Timestamp when the control action occurred",
    )

    # Relationships
    researcher_profile: Mapped["ResearchProfileModel"] = relationship(
        back_populates="personalization_control_events",
    )
