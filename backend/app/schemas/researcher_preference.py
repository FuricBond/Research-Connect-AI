from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
import uuid

from pydantic import BaseModel, ConfigDict, Field


class PreferenceCategory(str, Enum):
    """Supported preference categories mapped directly to canonical repository schema."""

    OPPORTUNITY_TYPE = "OPPORTUNITY_TYPE"
    DELIVERY_MODE = "DELIVERY_MODE"
    TOPIC = "TOPIC"
    LOCATION = "LOCATION"
    DEADLINE_WINDOW = "DEADLINE_WINDOW"
    OPEN_ACCESS = "OPEN_ACCESS"
    VENUE = "VENUE"


class PreferenceSource(str, Enum):
    """Provenance origin of a preference."""

    EXPLICIT = "EXPLICIT"
    INFERRED = "INFERRED"
    DERIVED_FROM_EXPERTISE = "DERIVED_FROM_EXPERTISE"


class PreferenceConflictSchema(BaseModel):
    """Structured representation of contradictory or conflicting preferences."""

    model_config = ConfigDict(from_attributes=True)

    category: str
    conflicting_values: list[str]
    reason: str
    is_critical: bool = False


class PreferenceCompletenessSchema(BaseModel):
    """Deterministic completeness representation across preference dimensions."""

    model_config = ConfigDict(from_attributes=True)

    score: float = Field(..., ge=0.0, le=1.0, description="Completeness score in [0.0, 1.0]")
    percentage: int = Field(..., ge=0, le=100, description="Completeness percentage [0, 100]")
    is_complete: bool = False
    missing_dimensions: list[str] = Field(default_factory=list)
    dimension_breakdown: dict[str, bool] = Field(default_factory=dict)


class ResearcherPreferenceItemSchema(BaseModel):
    """
    Structured representation of a single researcher preference item.

    Supports explicit user declarations, verified inferred preferences from
    saved opportunities, and derived suggestions from scholarly expertise.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    profile_id: uuid.UUID
    category: str
    preference_key: str
    preference_value: str
    display_label: str
    canonical_id: uuid.UUID | None = None

    strength: float = Field(..., ge=0.0, le=1.0, description="Preference strength in [0.0, 1.0]")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence certainty in [0.0, 1.0]")
    source: str = "EXPLICIT"
    is_active: bool = True
    recency_score: float = Field(1.0, ge=0.0, le=1.0, description="Recency score in [0.0, 1.0]")

    provenance: dict[str, Any] | None = None
    provenance_reasons: list[str] = Field(
        default_factory=list, description="Deterministic explanatory reasons"
    )
    last_observed_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ResearcherPreferenceCreateSchema(BaseModel):
    """Payload to declare or record an explicit researcher preference."""

    category: PreferenceCategory
    preference_key: str | None = None
    preference_value: str = Field(..., min_length=1, max_length=255)
    display_label: str | None = Field(None, max_length=255)
    canonical_id: uuid.UUID | None = None
    strength: float = Field(1.0, ge=0.0, le=1.0)
    is_active: bool = True


class ResearcherPreferenceUpdateSchema(BaseModel):
    """Partial update payload for a preference item."""

    preference_value: str | None = Field(None, min_length=1, max_length=255)
    display_label: str | None = Field(None, max_length=255)
    strength: float | None = Field(None, ge=0.0, le=1.0)
    is_active: bool | None = None


class PreferenceIntelligenceSummarySchema(BaseModel):
    """High-level summary of preference intelligence."""

    model_config = ConfigDict(from_attributes=True)

    total_preferences: int = 0
    explicit_count: int = 0
    inferred_count: int = 0
    derived_count: int = 0
    has_conflicts: bool = False
    confidence_level: str = "HIGH"
    completeness_percentage: int = 0


class ResearcherPreferenceIntelligenceResponse(BaseModel):
    """
    Canonical response for Phase 3.3 Personal Preference Intelligence.

    Strict Boundaries:
      - Descriptive and preference-specific only.
      - Never includes candidate opportunities or personalized ranking scores.
    """

    model_config = ConfigDict(from_attributes=True)

    profile_id: uuid.UUID
    user_id: uuid.UUID
    display_name: str

    explicit_preferences: list[ResearcherPreferenceItemSchema] = Field(default_factory=list)
    inferred_preferences: list[ResearcherPreferenceItemSchema] = Field(default_factory=list)
    derived_candidates: list[ResearcherPreferenceItemSchema] = Field(default_factory=list)

    conflicts: list[PreferenceConflictSchema] = Field(default_factory=list)
    completeness: PreferenceCompletenessSchema
    summary: PreferenceIntelligenceSummarySchema
    generated_at: datetime
