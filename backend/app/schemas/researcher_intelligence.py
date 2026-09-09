from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
import uuid

from pydantic import BaseModel, ConfigDict, Field


class ExpertiseClassification(str, Enum):
    """Deterministic expertise and interest tiers."""

    PRIMARY_EXPERTISE = "PRIMARY_EXPERTISE"
    SECONDARY_EXPERTISE = "SECONDARY_EXPERTISE"
    EMERGING_INTEREST = "EMERGING_INTEREST"
    WEAK_INTEREST = "WEAK_INTEREST"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class SupportingWorkReferenceSchema(BaseModel):
    """Summary reference to a scholarly work supporting a researcher topic."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    doi: str | None = None
    publication_year: int | None = None
    work_type: str | None = None
    author_position: str | None = None
    is_corresponding: bool = False
    cited_by_count: int = 0
    topic_confidence: float | None = None


class ResearcherInterestItemSchema(BaseModel):
    """
    Structured academic interest / expertise representation (Phase 3.2).
    
    Contains deterministic strength, confidence, bounded recency, classification,
    and explainable provenance with zero LLM dependency.
    """

    model_config = ConfigDict(from_attributes=True)

    topic_id: uuid.UUID | None = None
    topic_name: str
    topic_slug: str
    topic_category: str | None = None

    # Deterministic metrics: strictly bounded in [0.0, 1.0]
    strength: float = Field(..., ge=0.0, le=1.0, description="Topic strength score in [0.0, 1.0]")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Evidence certainty score in [0.0, 1.0]")
    evidence_count: int = Field(..., ge=1, description="Number of distinct supporting works or declared items")
    recency_score: float = Field(..., ge=0.0, le=1.0, description="Publication recency signal score in [0.0, 1.0]")

    # Classification
    classification: ExpertiseClassification
    is_primary_expertise: bool = False

    # Temporal observation bounds
    first_observed_year: int | None = None
    last_observed_year: int | None = None

    # Provenance
    source: str = "SCHOLARLY_WORKS"
    provenance_reasons: list[str] = Field(default_factory=list, description="Deterministic explanatory reasons")
    supporting_works: list[SupportingWorkReferenceSchema] = Field(
        default_factory=list, description="Academic publications supporting this interest"
    )


class ResearcherIntelligenceSummarySchema(BaseModel):
    """High-level summary metrics of researcher intelligence."""

    model_config = ConfigDict(from_attributes=True)

    total_topics_analyzed: int = 0
    primary_expertise_count: int = 0
    secondary_expertise_count: int = 0
    emerging_interest_count: int = 0
    total_works_analyzed: int = 0
    active_years_span: str | None = None
    has_profile_keywords: bool = False


class ResearcherIntelligenceResponse(BaseModel):
    """
    Complete structured researcher intelligence response.
    
    Strict Phase Boundary:
      Descriptive intelligence only. No recommendation ranking or preference inference.
    """

    model_config = ConfigDict(from_attributes=True)

    researcher_id: uuid.UUID
    profile_id: uuid.UUID | None = None
    canonical_researcher_id: uuid.UUID | None = None
    display_name: str

    interests: list[ResearcherInterestItemSchema] = Field(default_factory=list)
    expertise: list[ResearcherInterestItemSchema] = Field(default_factory=list)
    emerging: list[ResearcherInterestItemSchema] = Field(default_factory=list)

    summary: ResearcherIntelligenceSummarySchema
    generated_at: datetime
