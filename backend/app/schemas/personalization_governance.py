from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.personalization_governance import (
    AdaptationState,
    DriftType,
    EvidenceStrength,
    GovernanceEventType,
    GovernanceGateState,
    PersonalizationHealthState,
    PreferenceAlignmentState,
    SignalFreshnessState,
)


class SignalDriftItem(BaseModel):
    """Detailed drift status and historical comparison for an individual behavioral signal."""

    model_config = ConfigDict(from_attributes=True)

    dimension: str
    signal_value: str
    historical_strength: float = 0.0
    recent_strength: float = 0.0
    difference: float = 0.0
    evidence_strength: EvidenceStrength = EvidenceStrength.INSUFFICIENT
    drift_type: DriftType = DriftType.UNKNOWN
    is_stale: bool = False
    last_evidence_timestamp: Optional[datetime] = None
    explanation: str


class PersonalizationDriftEvaluationSchema(BaseModel):
    """Domain representation of a persistent drift evaluation and health snapshot."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    profile_id: uuid.UUID
    evaluation_timestamp: datetime
    historical_window_days: float = 60.0
    recent_window_days: float = 14.0
    overall_health_state: PersonalizationHealthState
    governance_state: GovernanceGateState
    adaptation_state: AdaptationState
    signal_freshness: SignalFreshnessState
    evidence_sufficiency: EvidenceStrength
    quality_stability: str
    context_stability: str
    preference_alignment: PreferenceAlignmentState
    recommendation_diversity: str
    drifting_signals_count: int = 0
    stale_signals_count: int = 0
    active_signals_count: int = 0
    drift_details: list[SignalDriftItem] = Field(default_factory=list)
    health_summary: str
    governance_explanation: str
    algorithm_version: str = "5.8.1"
    created_at: datetime
    updated_at: datetime


class PersonalizationGovernanceEventSchema(BaseModel):
    """Domain representation of an immutable governance audit log event."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    profile_id: uuid.UUID
    event_type: GovernanceEventType
    previous_state: Optional[str] = None
    new_state: str
    reason: str
    affected_dimension: Optional[str] = None
    affected_signal_value: Optional[str] = None
    evidence_count: int = 0
    reference_time: datetime
    algorithm_version: str = "5.8.1"
    created_at: datetime


class PersonalizationHealthResponse(BaseModel):
    """Top-level response for researcher personalization health and governance gate."""

    model_config = ConfigDict(from_attributes=True)

    profile_id: uuid.UUID
    evaluation: PersonalizationDriftEvaluationSchema
    overall_health_state: PersonalizationHealthState
    governance_state: GovernanceGateState
    adaptation_state: AdaptationState
    drifting_signals_count: int
    stale_signals_count: int
    health_summary: str
    governance_explanation: str


class PersonalizationDriftResponse(BaseModel):
    """Response containing granular signal-level drift classifications."""

    model_config = ConfigDict(from_attributes=True)

    profile_id: uuid.UUID
    drifting_signals: list[SignalDriftItem] = Field(default_factory=list)
    stale_signals: list[SignalDriftItem] = Field(default_factory=list)
    stable_signals: list[SignalDriftItem] = Field(default_factory=list)
    total_signals: int = 0


class PersonalizationGovernanceHistoryResponse(BaseModel):
    """Paginated response containing governance audit events."""

    model_config = ConfigDict(from_attributes=True)

    profile_id: uuid.UUID
    items: list[PersonalizationGovernanceEventSchema] = Field(default_factory=list)
    total_count: int = 0


class GovernanceRecomputeRequest(BaseModel):
    """Payload for triggering on-demand governance and drift evaluation recomputation."""

    reference_time: Optional[datetime] = Field(
        default=None,
        description="Explicit reference timestamp for deterministic temporal evaluation. Defaults to current UTC time.",
    )
    historical_window_days: Optional[float] = Field(
        default=None,
        ge=14.0,
        le=365.0,
        description="Historical observation window in days (default: 60.0).",
    )
    recent_window_days: Optional[float] = Field(
        default=None,
        ge=3.0,
        le=60.0,
        description="Recent observation window in days (default: 14.0).",
    )
    force_recompute: bool = Field(
        default=False,
        description="Whether to force recalculation.",
    )
