from __future__ import annotations

from datetime import datetime
from typing import Any
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.personalization_transparency import (
    PersonalizationControlEventType,
    PersonalizationImpact,
)


class ResearcherPersonalizationSettingsSchema(BaseModel):
    """Researcher personalization behavior controls and state version (Phase 5.9)."""

    model_config = ConfigDict(from_attributes=True)

    profile_id: uuid.UUID = Field(..., description="Canonical ResearchProfileModel ID")
    personalization_enabled: bool = Field(
        default=True,
        description="Global toggle: whether personalization modifiers are applied",
    )
    adaptive_signals_enabled: bool = Field(
        default=True,
        description="Whether inferred behavioral signals may modify recommendations",
    )
    feedback_learning_enabled: bool = Field(
        default=True,
        description="Whether researcher feedback is aggregated into future adaptive signals",
    )
    personalization_state_version: int = Field(
        default=1,
        description="Monotonically increasing version; incremented on reset",
    )
    updated_at: datetime = Field(..., description="Timestamp of last settings modification")


class ResearcherPersonalizationSettingsUpdate(BaseModel):
    """Payload for modifying researcher personalization controls."""

    model_config = ConfigDict(extra="forbid")

    personalization_enabled: bool | None = Field(
        default=None,
        description="Toggle personalization on/off",
    )
    adaptive_signals_enabled: bool | None = Field(
        default=None,
        description="Toggle adaptive signals on/off",
    )
    feedback_learning_enabled: bool | None = Field(
        default=None,
        description="Toggle feedback learning on/off",
    )


class PersonalizationControlEventSchema(BaseModel):
    """Single auditable control change event."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Event UUID")
    profile_id: uuid.UUID = Field(..., description="Canonical ResearchProfileModel ID")
    event_type: PersonalizationControlEventType = Field(..., description="Control event type")
    previous_state: dict[str, Any] = Field(default_factory=dict, description="State before change")
    new_state: dict[str, Any] = Field(default_factory=dict, description="State after change")
    trigger_reason: str = Field(..., description="Reason for control action")
    algorithm_version: str = Field(default="5.9.1", description="Transparency algorithm version")
    created_at: datetime = Field(..., description="Timestamp when event occurred")


class PersonalizationControlHistoryResponse(BaseModel):
    """Paginated list of personalization control audit events."""

    model_config = ConfigDict(from_attributes=True)

    profile_id: uuid.UUID = Field(..., description="Canonical ResearchProfileModel ID")
    events: list[PersonalizationControlEventSchema] = Field(
        default_factory=list,
        description="Audit events list",
    )
    total: int = Field(..., description="Total event count")
    limit: int = Field(..., description="Pagination limit")
    offset: int = Field(..., description="Pagination offset")


class RecommendationPersonalizationExplanationResponse(BaseModel):
    """
    Transparent, deterministic explanation answering:
    'Why was this recommendation personalized, and what signals influenced it?'
    """

    model_config = ConfigDict(from_attributes=True)

    recommendation_id: uuid.UUID = Field(..., description="Recommendation Item or Opportunity ID")
    opportunity_id: uuid.UUID = Field(..., description="Target Opportunity ID")
    opportunity_title: str = Field(..., description="Title of the recommended opportunity")
    personalization_impact: PersonalizationImpact = Field(
        ...,
        description="Bounded classification: NO, LOW, MODERATE, STRONG, or SUPPRESSED",
    )
    base_relevance_score: float = Field(
        ...,
        description="Core Phase 2 hybrid relevance score in [0.0, 1.0]",
    )
    personalization_score: float = Field(
        ...,
        description="Personalization score contribution in [0.0, 1.0]",
    )
    final_score: float = Field(
        ...,
        description="Final composite recommendation score in [0.0, 1.0]",
    )
    explicit_preference_factors: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Contributing explicit preference matches (e.g. PREFERRED / EXCLUDED)",
    )
    adaptive_signal_factors: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Contributing inferred behavioral signals",
    )
    calibration_factors: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Calibration adjustments based on feedback history",
    )
    contextual_factors: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Contextual adaptations based on opportunity attributes",
    )
    governance_state: str = Field(
        ...,
        description="Phase 5.8 governance gate state: ALLOW, ALLOW_BOUNDED, HOLD, REDUCE, SUSPEND",
    )
    governance_multiplier: float = Field(
        ...,
        description="Active adaptation multiplier: 1.0, 0.5, 0.25, 0.0",
    )
    governance_notes: str | None = Field(
        default=None,
        description="Governance context explaining bounding or suspension if applicable",
    )
    deterministic_explanation: str = Field(
        ...,
        description="Synthesized deterministic natural language explanation",
    )
    contributing_factors_summary: list[str] = Field(
        default_factory=list,
        description="Ordered checklist of major contributing factors",
    )
    algorithm_version: str = Field(
        default="5.9.1",
        description="Deterministic transparency algorithm version",
    )
    evaluated_at: datetime = Field(
        ...,
        description="Evaluation timestamp",
    )
    personalization_state_version: int = Field(
        default=1,
        description="Researcher personalization state version at evaluation time",
    )


class PersonalizationResetResponse(BaseModel):
    """Deterministic summary of a personalization reset operation."""

    model_config = ConfigDict(from_attributes=True)

    status: str = Field(default="SUCCESS", description="Reset status: SUCCESS")
    personalization_state_version: int = Field(
        ...,
        description="New personalization state version after incrementing",
    )
    adaptive_signals_reset: int = Field(
        ...,
        description="Count of derived adaptive signals neutralized/reset",
    )
    calibration_states_reset: int = Field(
        ...,
        description="Count of calibration states neutralized/reset",
    )
    contextual_modifiers_reset: int = Field(
        ...,
        description="Count of contextual adaptations neutralized/reset",
    )
    explicit_preferences_changed: int = Field(
        default=0,
        description="Count of explicit preferences changed (always 0, strictly preserved)",
    )
    researcher_profile_changed: int = Field(
        default=0,
        description="Count of profile attributes changed (always 0, strictly preserved)",
    )
    message: str = Field(
        ...,
        description="Deterministic human-readable confirmation message",
    )
    timestamp: datetime = Field(
        ...,
        description="Timestamp when reset completed",
    )
