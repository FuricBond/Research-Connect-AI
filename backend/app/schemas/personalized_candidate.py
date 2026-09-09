"""
Pydantic schemas for Phase 3.4 — Personalized Candidate Generation.

Strict Architectural Boundaries:
  - Phase 3.4 produces a personalized candidate set, NOT a final ranked recommendation list.
  - Phase 2 matching, ranking, trust/risk, and deadline intelligence remain authoritative.
  - Personalized ranking is strictly NOT implemented here (deferred to Phase 3.5).
  - Preserves full provenance for each candidate (why it entered the pool).
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
import uuid

from pydantic import BaseModel, ConfigDict, Field


class CandidateSourceType(str, Enum):
    """Origin sources indicating why an opportunity entered the candidate pool."""

    EXPLICIT_PREFERENCE = "EXPLICIT_PREFERENCE"
    INFERRED_PREFERENCE = "INFERRED_PREFERENCE"
    RESEARCH_EXPERTISE = "RESEARCH_EXPERTISE"
    RESEARCH_INTEREST = "RESEARCH_INTEREST"
    PROFILE_KEYWORD = "PROFILE_KEYWORD"
    COLD_START_FALLBACK = "COLD_START_FALLBACK"


class CandidateProvenanceSchema(BaseModel):
    """
    Explainable evidence trace for candidate pool entry.

    Answers: "Why was this specific opportunity selected for the personalized candidate pool?"
    """

    model_config = ConfigDict(from_attributes=True)

    candidate_id: uuid.UUID = Field(..., description="Unique ID for this candidate item")
    opportunity_id: uuid.UUID = Field(..., description="Canonical OpportunityModel ID")
    sources: list[CandidateSourceType] = Field(
        default_factory=list,
        description="All sources that surfaced this opportunity (merged on deduplication)",
    )
    matched_topics: list[str] = Field(
        default_factory=list,
        description="Matched topic names (from preferences, expertise, or profile)",
    )
    matched_preferences: list[str] = Field(
        default_factory=list,
        description="Specific preference dimensions matched (e.g. 'Conference', 'Hybrid')",
    )
    matched_expertise: list[str] = Field(
        default_factory=list,
        description="Scholarly expertise topics matched from Phase 3.2 intelligence",
    )
    reasons: list[str] = Field(
        default_factory=list,
        description="Deterministic human-readable explanation sentences",
    )
    retrieval_channels: list[str] = Field(
        default_factory=list,
        description="Underlying retrieval mechanisms (e.g. 'topic_association', 'lexical', 'vector', 'metadata')",
    )


class PersonalizedCandidateOpportunitySchema(BaseModel):
    """
    Lightweight canonical opportunity metadata attached to candidate, including
    Phase 2.6 risk and Phase 2.7 deadline intelligence.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Canonical opportunity ID")
    title: str = Field(..., description="Opportunity title")
    opportunity_type: str = Field(..., description="CONFERENCE, JOURNAL, WORKSHOP, etc.")
    delivery_mode: str = Field(..., description="ONLINE, OFFLINE, HYBRID")
    location: str | None = Field(None, description="Event or publisher location")
    organizer: str | None = Field(None, description="Organizer or publisher name")
    submission_deadline: datetime | None = Field(None, description="Normalized submission deadline")
    website_url: str | None = Field(None, description="Official opportunity or submission URL")
    topics: list[str] = Field(default_factory=list, description="Canonical topic names")
    status: str = Field(..., description="Lifecycle status (ACTIVE, UNVERIFIED, etc.)")

    # Phase 2.6 Trust & Risk Intelligence Preservation
    is_predatory_flag: bool = Field(False, description="Predatory venue flag")
    risk_level: str | None = Field(None, description="Risk level (LOW_RISK, MODERATE_RISK, HIGH_RISK, etc.)")
    risk_score: float | None = Field(None, description="Bounded risk score in [0.00, 1.00]")
    risk_reasons: list[str] = Field(default_factory=list, description="Phase 2.6 risk reasons")

    # Phase 2.7 Deadline Intelligence Preservation
    deadline_status: str | None = Field(None, description="UPCOMING, DUE_TODAY, EXPIRED, MISSING")
    days_remaining: float | None = Field(None, description="Signed days remaining until deadline")
    urgency_tier: str | None = Field(None, description="CRITICAL, URGENT, APPROACHING, DISTANT, etc.")
    deadline_explanation: str | None = Field(None, description="Human-readable deadline timing explanation")


class PersonalizedCandidateItemSchema(BaseModel):
    """
    Individual personalized candidate with opportunity details, provenance, and eligibility.
    """

    model_config = ConfigDict(from_attributes=True)

    candidate_id: uuid.UUID = Field(..., description="Unique candidate entry identifier")
    opportunity: PersonalizedCandidateOpportunitySchema = Field(..., description="Canonical opportunity details")
    provenance: CandidateProvenanceSchema = Field(..., description="Traceable provenance")
    eligibility_passed: bool = Field(True, description="Whether opportunity passed eligibility criteria")
    eligibility_reasons: list[str] = Field(
        default_factory=list,
        description="Eligibility assessment notes (e.g. active status, deadline valid)",
    )


class CandidateSourceCoverageSchema(BaseModel):
    """
    Diagnostic summary of candidate-source contributions.
    """

    model_config = ConfigDict(from_attributes=True)

    explicit_preference_count: int = Field(0, description="Candidates surfaced via explicit preferences")
    inferred_preference_count: int = Field(0, description="Candidates surfaced via inferred preferences")
    expertise_count: int = Field(0, description="Candidates surfaced via scholarly expertise")
    profile_count: int = Field(0, description="Candidates surfaced via profile keywords/types")
    fallback_count: int = Field(0, description="Candidates surfaced via cold-start / general fallback")
    unique_candidate_count: int = Field(0, description="Total deduplicated candidate count")
    deduplication_ratio: float = Field(
        0.0,
        description="Ratio of duplicate candidate instances merged across sources",
    )


class PersonalizedCandidateSetResponse(BaseModel):
    """
    Authoritative response envelope for Phase 3.4 Personalized Candidate Generation.
    """

    model_config = ConfigDict(from_attributes=True)

    researcher_id: uuid.UUID = Field(..., description="Target researcher profile ID")
    candidate_count: int = Field(..., description="Number of personalized candidates in this set")
    is_cold_start: bool = Field(..., description="True if fallback retrieval was required due to sparse data")
    coverage: CandidateSourceCoverageSchema = Field(..., description="Source distribution diagnostics")
    candidates: list[PersonalizedCandidateItemSchema] = Field(
        ...,
        description="Deduplicated, eligibility-verified candidate pool with complete provenance",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Deterministic execution metadata and configuration limits",
    )
