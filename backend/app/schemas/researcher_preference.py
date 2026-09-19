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
    KEYWORD = "KEYWORD"
    RESEARCH_DOMAIN = "RESEARCH_DOMAIN"
    COUNTRY = "COUNTRY"
    REGION = "REGION"
    INSTITUTION = "INSTITUTION"
    FUNDING = "FUNDING"
    ACADEMIC_LEVEL = "ACADEMIC_LEVEL"
    CAREER_STAGE = "CAREER_STAGE"


class PreferenceType(str, Enum):
    """Orientation of an explicit preference (Phase 5.1)."""

    PREFERRED = "PREFERRED"
    EXCLUDED = "EXCLUDED"


class PreferenceState(str, Enum):
    """3-state semantic model: Preferred vs Neutral/Unspecified vs Excluded."""

    PREFERRED = "PREFERRED"
    NEUTRAL = "NEUTRAL"
    EXCLUDED = "EXCLUDED"


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
    preference_type: str = "PREFERRED"
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
    preference_type: PreferenceType = PreferenceType.PREFERRED
    preference_key: str | None = None
    preference_value: str = Field(..., min_length=1, max_length=255)
    display_label: str | None = Field(None, max_length=255)
    canonical_id: uuid.UUID | None = None
    strength: float = Field(1.0, ge=0.0, le=1.0)
    is_active: bool = True


class ResearcherPreferenceUpdateSchema(BaseModel):
    """Partial update payload for a preference item."""

    preference_type: PreferenceType | None = None
    preference_value: str | None = Field(None, min_length=1, max_length=255)
    display_label: str | None = Field(None, max_length=255)
    strength: float | None = Field(None, ge=0.0, le=1.0)
    is_active: bool | None = None


class BulkPreferenceItemSchema(BaseModel):
    """Single item in a bulk preference sync."""

    category: PreferenceCategory
    preference_type: PreferenceType = PreferenceType.PREFERRED
    preference_key: str | None = None
    preference_value: str = Field(..., min_length=1, max_length=255)
    display_label: str | None = Field(None, max_length=255)
    canonical_id: uuid.UUID | None = None
    strength: float = Field(1.0, ge=0.0, le=1.0)
    is_active: bool = True


class BulkPreferencesUpdateSchema(BaseModel):
    """Payload for synchronizing multiple preferences in one atomic transaction."""

    preferences: list[BulkPreferenceItemSchema] = Field(default_factory=list)
    replace_existing: bool = False


class StructuredResearchInterestsSchema(BaseModel):
    """Research interest preferences."""

    research_domains: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    subfields: list[str] = Field(default_factory=list)


class StructuredOpportunityPreferencesSchema(BaseModel):
    """Opportunity format & type preferences."""

    preferred_types: list[str] = Field(default_factory=list)
    excluded_types: list[str] = Field(default_factory=list)
    delivery_modes: list[str] = Field(default_factory=list)


class StructuredGeographicPreferencesSchema(BaseModel):
    """Geographic preferences and exclusions."""

    preferred_countries: list[str] = Field(default_factory=list)
    excluded_countries: list[str] = Field(default_factory=list)
    preferred_regions: list[str] = Field(default_factory=list)
    excluded_regions: list[str] = Field(default_factory=list)
    preferred_institutions: list[str] = Field(default_factory=list)
    excluded_institutions: list[str] = Field(default_factory=list)


class StructuredFundingPreferencesSchema(BaseModel):
    """Funding requirement and boundary preferences."""

    funding_required: bool = False
    min_funding_amount: float | None = None
    max_funding_amount: float | None = None
    currency: str = "USD"


class StructuredAcademicPreferencesSchema(BaseModel):
    """Academic level and career stage preferences."""

    academic_level: str | None = None
    career_stage: str | None = None
    target_categories: list[str] = Field(default_factory=list)


class StructuredExclusionsSchema(BaseModel):
    """Explicitly excluded dimensions."""

    excluded_opportunity_types: list[str] = Field(default_factory=list)
    excluded_topics: list[str] = Field(default_factory=list)
    excluded_regions: list[str] = Field(default_factory=list)
    excluded_countries: list[str] = Field(default_factory=list)
    excluded_institutions: list[str] = Field(default_factory=list)


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


class StructuredPreferencesResponseSchema(BaseModel):
    """Structured hierarchical representation of researcher preferences (Phase 5.1)."""

    model_config = ConfigDict(from_attributes=True)

    profile_id: uuid.UUID
    user_id: uuid.UUID
    interests: StructuredResearchInterestsSchema = Field(default_factory=StructuredResearchInterestsSchema)
    opportunities: StructuredOpportunityPreferencesSchema = Field(default_factory=StructuredOpportunityPreferencesSchema)
    geography: StructuredGeographicPreferencesSchema = Field(default_factory=StructuredGeographicPreferencesSchema)
    funding: StructuredFundingPreferencesSchema = Field(default_factory=StructuredFundingPreferencesSchema)
    academic: StructuredAcademicPreferencesSchema = Field(default_factory=StructuredAcademicPreferencesSchema)
    exclusions: StructuredExclusionsSchema = Field(default_factory=StructuredExclusionsSchema)
    raw_preferences: list[ResearcherPreferenceItemSchema] = Field(default_factory=list)
    summary: PreferenceIntelligenceSummarySchema = Field(default_factory=PreferenceIntelligenceSummarySchema)
    completeness: PreferenceCompletenessSchema = Field(
        default_factory=lambda: PreferenceCompletenessSchema(score=0.0, percentage=0)
    )
    updated_at: datetime | None = None



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
