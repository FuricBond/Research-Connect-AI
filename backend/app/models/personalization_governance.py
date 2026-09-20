from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional
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
    from app.models.research_profile import ResearchProfileModel


class PersonalizationHealthState(str, Enum):
    """Overall health state of the personalization system for a researcher."""

    HEALTHY = "HEALTHY"
    STABLE = "STABLE"
    DEGRADED = "DEGRADED"
    DRIFTING = "DRIFTING"
    SUSPENDED = "SUSPENDED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class GovernanceGateState(str, Enum):
    """Active decision state of the personalization governance gate."""

    ALLOW = "ALLOW"
    ALLOW_BOUNDED = "ALLOW_BOUNDED"
    HOLD = "HOLD"
    REDUCE = "REDUCE"
    SUSPEND = "SUSPEND"


class AdaptationState(str, Enum):
    """Operational state of contextual and behavioral adaptation."""

    ACTIVE = "ACTIVE"
    BOUNDED = "BOUNDED"
    CONSERVATIVE = "CONSERVATIVE"
    HELD = "HELD"
    DAMPENED = "DAMPENED"
    SUSPENDED = "SUSPENDED"


class DriftType(str, Enum):
    """Deterministic classification of behavioral signal drift."""

    STABLE = "STABLE"
    EMERGING = "EMERGING"
    PERSISTENT = "PERSISTENT"
    REVERSING = "REVERSING"
    UNKNOWN = "UNKNOWN"


class EvidenceStrength(str, Enum):
    """Deterministic evidence strength classification based on measurable sample size."""

    INSUFFICIENT = "INSUFFICIENT"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class SignalFreshnessState(str, Enum):
    """Freshness state of behavioral interaction evidence."""

    HEALTHY = "HEALTHY"
    STABLE = "STABLE"
    AGING = "AGING"
    STALE = "STALE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class PreferenceAlignmentState(str, Enum):
    """Alignment between explicit researcher preferences and observed behavioral trends."""

    ALIGNED = "ALIGNED"
    DIVERGENT = "DIVERGENT"
    DIVERGING = "DIVERGING"
    CONFLICTED = "CONFLICTED"
    NEUTRAL = "NEUTRAL"
    UNEVALUATED = "UNEVALUATED"


class GovernanceEventType(str, Enum):
    """Classification of auditable personalization governance events."""

    STATE_CHANGE = "STATE_CHANGE"
    GATE_TRANSITION = "GATE_TRANSITION"
    SUSPENSION = "SUSPENSION"
    ADAPTATION_SUSPENSION = "ADAPTATION_SUSPENSION"
    RECOVERY = "RECOVERY"
    ADAPTATION_RECOVERY = "ADAPTATION_RECOVERY"
    DRIFT_DETECTED = "DRIFT_DETECTED"
    SIGNAL_STALE = "SIGNAL_STALE"
    STALENESS_DETECTED = "STALENESS_DETECTED"
    PREFERENCE_PROTECTION_TRIGGERED = "PREFERENCE_PROTECTION_TRIGGERED"
    EVALUATION_TRIGGERED = "EVALUATION_TRIGGERED"


class PersonalizationDriftEvaluationModel(Base):
    """
    Persistent snapshot of a researcher's personalization health, behavioral drift,
    and governance gate state (Phase 5.8).

    Answers:
      "Is personalization currently behaving reliably for this researcher,
       are behavioral signals drifting from historical patterns or explicit preferences,
       and what adaptation level is safely permitted?"

    Strict Invariants:
      - Read-only evaluation of signals, interactions, and explicit preferences.
      - Explicit preferences can NEVER be overwritten or superseded by behavioral drift.
      - Zero ML / Zero LLM / Zero vector DBs: 100% deterministic calculation.
    """

    __tablename__ = "personalization_drift_evaluations"
    __table_args__ = (
        UniqueConstraint(
            "profile_id",
            "algorithm_version",
            name="uq_personalization_drift_profile_version",
        ),
        Index("idx_drift_eval_profile_health", "profile_id", "overall_health_state"),
        Index("idx_drift_eval_profile_gov", "profile_id", "governance_state"),
        Index("idx_drift_eval_updated_at", "updated_at"),
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

    evaluation_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Explicit reference timestamp used for deterministic evaluation",
    )

    historical_window_days: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=60.0,
        comment="Historical behavioral observation window in days",
    )

    recent_window_days: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=14.0,
        comment="Recent behavioral observation window in days",
    )

    overall_health_state: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=PersonalizationHealthState.INSUFFICIENT_DATA.value,
        comment="Aggregate personalization health state",
    )

    governance_state: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=GovernanceGateState.HOLD.value,
        comment="Active governance decision state (ALLOW, ALLOW_BOUNDED, HOLD, REDUCE, SUSPEND)",
    )

    adaptation_state: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=AdaptationState.BOUNDED.value,
        comment="Active adaptation behavior state (ACTIVE, BOUNDED, HELD, DAMPENED, SUSPENDED)",
    )

    signal_freshness: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=SignalFreshnessState.INSUFFICIENT_DATA.value,
        comment="Freshness of behavioral interaction evidence",
    )

    evidence_sufficiency: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=EvidenceStrength.INSUFFICIENT.value,
        comment="Evidence volume sufficiency",
    )

    quality_stability: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="INSUFFICIENT_DATA",
        comment="Stability of recommendation quality outcomes",
    )

    context_stability: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="INSUFFICIENT_DATA",
        comment="Stability across contextual facets",
    )

    preference_alignment: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=PreferenceAlignmentState.NEUTRAL.value,
        comment="Alignment between explicit preferences and recent behavior",
    )

    recommendation_diversity: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="INSUFFICIENT_DATA",
        comment="Diversity stability metric status",
    )

    drifting_signals_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Count of signals exhibiting emerging, persistent, or reversing drift",
    )

    stale_signals_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Count of signals with stale evidence (> 180 days)",
    )

    active_signals_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Total evaluated behavioral signals",
    )

    drift_details: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        comment="Serialized granular drift records per signal dimension and value",
    )

    health_summary: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Deterministic natural language summary of personalization health",
    )

    governance_explanation: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Deterministic explanation of governance gate decision and adaptation level",
    )

    algorithm_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="5.8.1",
        comment="Deterministic governance algorithm version",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    profile: Mapped[ResearchProfileModel] = relationship(
        "ResearchProfileModel",
        back_populates="drift_evaluations",
    )


class PersonalizationGovernanceEventModel(Base):
    """
    Append-only, immutable audit trail of personalization governance events (Phase 5.8).

    Records state transitions, suspensions, recoveries, and threshold breaches.
    Answers:
      "Why was personalization adaptation suspended or modified, and what evidence triggered it?"
    """

    __tablename__ = "personalization_governance_events"
    __table_args__ = (
        Index("idx_gov_events_profile_created", "profile_id", "created_at"),
        Index("idx_gov_events_profile_type", "profile_id", "event_type"),
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
        comment="Type of governance event (e.g. STATE_CHANGE, SUSPENSION, RECOVERY)",
    )

    previous_state: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="Previous governance gate state",
    )

    new_state: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="New governance gate state",
    )

    reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Deterministic explanation for the state change or action",
    )

    affected_dimension: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="Affected signal dimension (if event is signal-specific)",
    )

    affected_signal_value: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Affected signal value (if event is signal-specific)",
    )

    evidence_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Count of relevant interactions or evidence items supporting decision",
    )

    reference_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Deterministic reference timestamp at time of event evaluation",
    )

    algorithm_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="5.8.1",
        comment="Governance algorithm version",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        comment="Point-in-time immutable event creation timestamp",
    )

    # Relationships
    profile: Mapped[ResearchProfileModel] = relationship(
        "ResearchProfileModel",
        back_populates="governance_events",
    )
