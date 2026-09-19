"""
Pydantic Schemas for Phase 4.7 — Research Intelligence Integration & Production Hardening.

Defines typed schemas for:
  - Structured signal provenance (explicit vs inferred, confidence, strength, evidence, contributing entity)
  - Unified researcher context (complete, partial, cold-start, identity resolution)
  - Multi-tier explainability containers (relevance, researcher, interest, preference, deadline, risk, workspace)
  - Unified recommendation responses combining Phases 2, 3, and 4
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.deadline import OpportunityDeadlineSchema
from app.schemas.opportunity import RiskExplanationSchema
from app.schemas.personalized_ranking import (
    AblationSummarySchema,
    PersonalizationScoreBreakdownSchema,
)
from app.schemas.recommendation_explanation import (
    ExplanationFactorSchema,
    RecommendationExplanationSchema,
)


class SignalProvenanceType(str, Enum):
    """Categorization of research intelligence signals."""

    EXPLICIT_PREFERENCE = "EXPLICIT_PREFERENCE"
    INFERRED_PREFERENCE = "INFERRED_PREFERENCE"
    SCHOLARLY_EXPERTISE = "SCHOLARLY_EXPERTISE"
    EMERGING_INTEREST = "EMERGING_INTEREST"
    PROFILE_ATTRIBUTE = "PROFILE_ATTRIBUTE"
    WORKSPACE_WORKFLOW = "WORKSPACE_WORKFLOW"
    SUBMISSION_READINESS = "SUBMISSION_READINESS"
    BASE_RELEVANCE = "BASE_RELEVANCE"
    DEADLINE_TEMPORAL = "DEADLINE_TEMPORAL"
    RISK_SAFETY = "RISK_SAFETY"
    COLLABORATIVE_TASK = "COLLABORATIVE_TASK"


class SignalSource(str, Enum):
    """Authoritative source system generating or recording the signal."""

    USER_DECLARED = "USER_DECLARED"
    RESEARCH_PROFILE = "RESEARCH_PROFILE"
    OPENALEX_KNOWLEDGE = "OPENALEX_KNOWLEDGE"
    BEHAVIORAL_FEEDBACK = "BEHAVIORAL_FEEDBACK"
    WORKSPACE_SERVICE = "WORKSPACE_SERVICE"
    SUBMISSION_ENGINE = "SUBMISSION_ENGINE"
    HYBRID_SEARCH = "HYBRID_SEARCH"
    DEADLINE_ENGINE = "DEADLINE_ENGINE"
    RISK_ENGINE = "RISK_ENGINE"
    COLLABORATION_SERVICE = "COLLABORATION_SERVICE"


class EvidenceTierType(str, Enum):
    """Semantic evidence tier for explainability breakdown."""

    OPPORTUNITY_RELEVANCE = "OPPORTUNITY_RELEVANCE"
    RESEARCHER_EVIDENCE = "RESEARCHER_EVIDENCE"
    RESEARCH_INTEREST_EVIDENCE = "RESEARCH_INTEREST_EVIDENCE"
    PREFERENCE_EVIDENCE = "PREFERENCE_EVIDENCE"
    DEADLINE_EVIDENCE = "DEADLINE_EVIDENCE"
    RISK_EVIDENCE = "RISK_EVIDENCE"
    WORKSPACE_CONTEXT = "WORKSPACE_CONTEXT"


class ResearchIntelligenceSignalSchema(BaseModel):
    """
    Structured research intelligence signal with strict provenance tracking.
    Guarantees zero evidence loss and zero mathematical fabrication.
    """

    model_config = ConfigDict(from_attributes=True)

    signal_id: str = Field(
        default_factory=lambda: f"sig-{uuid.uuid4().hex[:12]}",
        description="Unique signal identifier",
    )
    signal_type: SignalProvenanceType = Field(..., description="Semantic type of the signal")
    source: SignalSource = Field(..., description="Authoritative origin of the signal")
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score of the signal in [0.0, 1.0]",
    )
    strength: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Magnitude or weight of the signal in [0.0, 1.0]",
    )
    evidence: str = Field(..., description="Human-readable and auditable evidence description")
    contributing_entity_id: str | None = Field(
        None,
        description="Identifier of entity that generated the signal (work, topic, preference, etc.)",
    )
    contributing_entity_type: str | None = Field(
        None,
        description="Entity type (e.g. topic, preference, submission, opportunity)",
    )
    is_explicit: bool = Field(
        True,
        description="True if explicitly declared by the researcher; False if inferred",
    )
    observed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when the signal was recorded or verified",
    )
    metadata_payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Lossless structured signal metadata",
    )


class IdentityResolutionStatus(str, Enum):
    """Classification of canonical researcher identity resolution."""

    RESOLVED = "RESOLVED"
    UNRESOLVED = "UNRESOLVED"
    AMBIGUOUS = "AMBIGUOUS"
    SELF_DECLARED_ONLY = "SELF_DECLARED_ONLY"


class UnifiedResearcherContextSchema(BaseModel):
    """
    Consolidated researcher context across profile, knowledge, preferences, and Phase 4 workspace.
    Explicitly distinguishes complete, partial, cold-start, and ambiguous profiles.
    """

    model_config = ConfigDict(from_attributes=True)

    profile_id: uuid.UUID = Field(..., description="Canonical ResearchProfileModel ID")
    user_id: uuid.UUID = Field(..., description="Associated UserModel ID")
    full_name: str = Field(..., description="Researcher full name")
    academic_status: str = Field("UNKNOWN", description="Academic status (FACULTY, STUDENT, etc.)")
    institution_name: str | None = Field(None, description="Primary institutional affiliation")
    department: str | None = Field(None, description="Academic department")
    
    # Identity Resolution (Zero Fabrication)
    identity_status: IdentityResolutionStatus = Field(
        IdentityResolutionStatus.SELF_DECLARED_ONLY,
        description="Resolution status of canonical scholarly identity",
    )
    canonical_researcher_id: uuid.UUID | None = Field(None, description="Canonical researcher ID (researchers.id)")
    orcid: str | None = Field(None, description="ORCID iD if verified")
    openalex_id: str | None = Field(None, description="OpenAlex author ID if verified")
    is_identity_ambiguous: bool = Field(
        False,
        description="True if multiple potential scholarly entities matched without resolution",
    )
    
    # Profile Completeness & Cold-Start Classification
    completeness_score: float = Field(0.0, ge=0.0, le=1.0, description="Completeness score in [0.0, 1.0]")
    is_cold_start: bool = Field(True, description="True if no interests, preferences, or feedback exist")
    is_partial_profile: bool = Field(False, description="True if only a subset of profile fields are provided")
    
    # Provenance Signals
    signals: list[ResearchIntelligenceSignalSchema] = Field(
        default_factory=list,
        description="All active structured signals derived from the researcher's context",
    )
    active_interests_count: int = Field(0, description="Count of active topic interests")
    explicit_preferences_count: int = Field(0, description="Count of explicit preferences")
    inferred_preferences_count: int = Field(0, description="Count of inferred preferences")
    
    # Phase 4 Workflow State
    saved_opportunities_count: int = Field(0, description="Total opportunities in researcher workspace")
    active_submissions_count: int = Field(0, description="Active manuscript submissions in progress")
    upcoming_tasks_count: int = Field(0, description="Incomplete collaborative tasks assigned to researcher")
    calendar_events_count: int = Field(0, description="Projected deadlines and custom milestones")


class OpportunityWorkspaceContextSchema(BaseModel):
    """Contextual Phase 4 workflow status for an opportunity relative to the researcher."""

    model_config = ConfigDict(from_attributes=True)

    is_saved: bool = Field(False, description="True if opportunity is in researcher workspace")
    workspace_item_id: uuid.UUID | None = Field(None, description="SavedOpportunityModel ID if present")
    workspace_status: str | None = Field(
        None,
        description="Workflow status: SAVED, CONSIDERING, PLANNING, APPLIED, ACCEPTED, REJECTED, ARCHIVED",
    )
    workspace_priority: str | None = Field(None, description="Priority: LOW, MEDIUM, HIGH, URGENT")
    tags: list[str] = Field(default_factory=list, description="Custom researcher tags")
    notes: str | None = Field(None, description="Researcher personal notes")
    has_active_submission: bool = Field(False, description="True if an active submission is attached")
    submission_id: uuid.UUID | None = Field(None, description="ResearchSubmissionModel ID if present")
    submission_status: str | None = Field(None, description="Submission state: DRAFT, READY, SUBMITTED, etc.")
    submission_readiness_score: float | None = Field(None, description="Document readiness percentage (0-100)")
    task_count: int = Field(0, description="Number of collaborative tasks linked to this workspace item")


class EvidenceTierBreakdownSchema(BaseModel):
    """Structured breakdown across the 6 authoritative evidence tiers."""

    model_config = ConfigDict(from_attributes=True)

    tier: EvidenceTierType = Field(..., description="Evidence tier type")
    title: str = Field(..., description="Human-readable tier title")
    summary: str = Field(..., description="Summary of evidence in this tier")
    is_active: bool = Field(True, description="True if evidence was found and evaluated")
    score_or_status: str = Field(..., description="Score value, status tier, or classification label")
    contributing_factors: list[str] = Field(
        default_factory=list,
        description="Individual evidence points in this tier",
    )
    signals: list[ResearchIntelligenceSignalSchema] = Field(
        default_factory=list,
        description="Structured signals associated with this tier",
    )


class UnifiedRecommendationItemSchema(BaseModel):
    """
    An individual opportunity recommendation combining Phase 2 relevance,
    Phase 3 personalization, Phase 4 workspace context, risk, deadline, and multi-tier explainability.
    """

    model_config = ConfigDict(from_attributes=True)

    opportunity_id: uuid.UUID = Field(..., description="Canonical opportunity identifier")
    title: str = Field(..., description="Opportunity title")
    opportunity_type: str = Field(..., description="Category: CONFERENCE, JOURNAL, WORKSHOP, etc.")
    delivery_mode: str = Field(..., description="Delivery mode: ONLINE, OFFLINE, HYBRID")
    publisher: str | None = Field(None, description="Publisher name")
    organizer: str | None = Field(None, description="Organizer name")
    submission_deadline: datetime | None = Field(None, description="Canonical submission deadline")
    location: str | None = Field(None, description="Event location")
    website_url: str | None = Field(None, description="Official opportunity website")

    # Ranking & Relevance (Phase 2.5 + Phase 3.5)
    rank: int = Field(..., ge=1, description="1-based final recommendation rank")
    base_rank: int = Field(..., ge=1, description="1-based Phase 2 base rank (R0)")
    rank_delta: int = Field(0, description="Rank movement (base_rank - rank)")
    final_score: float = Field(..., ge=0.0, le=1.0, description="Composite score in [0.0, 1.0]")
    base_relevance_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Authoritative Phase 2 base relevance (dominant >= 0.85)",
    )
    personalization_score: float = Field(
        0.0,
        ge=0.0,
        le=1.0,
        description="Raw composite personalization score in [0.0, 1.0]",
    )
    personalization_adjustment: float = Field(
        0.0,
        ge=0.0,
        le=0.15,
        description="Bounded personalization adjustment (strictly capped at 0.15)",
    )
    score_breakdown: PersonalizationScoreBreakdownSchema = Field(
        ...,
        description="Component-level score attribution",
    )

    # Orthogonal Context (Phase 2.6 Risk & Phase 2.7 Deadline)
    risk_explanation: RiskExplanationSchema | None = Field(
        None,
        description="Phase 2.6 publication integrity and predatory risk assessment",
    )
    deadline_intelligence: OpportunityDeadlineSchema | None = Field(
        None,
        description="Phase 2.7 canonical deadline intelligence and urgency analysis",
    )

    # Phase 4 Workspace & Workflow Context
    workspace_context: OpportunityWorkspaceContextSchema = Field(
        default_factory=OpportunityWorkspaceContextSchema,
        description="Current workspace and submission state for this opportunity",
    )

    # Multi-Tier Explainability (Phase 4.7)
    evidence_tiers: list[EvidenceTierBreakdownSchema] = Field(
        default_factory=list,
        description="Structured breakdown across the 6 distinct evidence tiers",
    )
    explanation: RecommendationExplanationSchema | None = Field(
        None,
        description="Phase 3.8 structured explanation",
    )


class UnifiedRecommendationResponseSchema(BaseModel):
    """Paginated response container for unified research intelligence recommendations."""

    model_config = ConfigDict(from_attributes=True)

    items: list[UnifiedRecommendationItemSchema] = Field(
        default_factory=list,
        description="Ranked recommendation items",
    )
    total_count: int = Field(..., description="Total recommendations available")
    limit: int = Field(..., description="Requested page limit")
    offset: int = Field(..., description="Requested page offset")
    researcher_context: UnifiedResearcherContextSchema = Field(
        ...,
        description="Context of the researcher evaluated for these recommendations",
    )
    ablation_summary: AblationSummarySchema | None = Field(
        None,
        description="R0 vs R1 ablation comparison metrics",
    )
    execution_time_ms: float = Field(
        0.0,
        description="Total pipeline execution latency in milliseconds",
    )
    invariants_verified: bool = Field(
        True,
        description="True if all Phase 2.5, 2.6, 2.7, 3.5, and 4.7 invariants held during execution",
    )


class UnifiedOpportunityIntelligenceSchema(BaseModel):
    """
    Detailed intelligence container for a single opportunity in relation to a researcher,
    exposing all signal provenance and multi-tier evidence.
    """

    model_config = ConfigDict(from_attributes=True)

    opportunity_id: uuid.UUID = Field(..., description="Canonical opportunity identifier")
    profile_id: uuid.UUID = Field(..., description="Researcher profile identifier")
    title: str = Field(..., description="Opportunity title")
    base_relevance_score: float = Field(..., description="Phase 2 base relevance")
    personalization_adjustment: float = Field(..., description="Phase 3.5 personalization adjustment")
    final_score: float = Field(..., description="Composite recommendation score")
    
    signals: list[ResearchIntelligenceSignalSchema] = Field(
        default_factory=list,
        description="All contributing signals with provenance",
    )
    evidence_tiers: list[EvidenceTierBreakdownSchema] = Field(
        default_factory=list,
        description="Authoritative 6-tier evidence breakdown",
    )
    workspace_context: OpportunityWorkspaceContextSchema = Field(
        default_factory=OpportunityWorkspaceContextSchema,
        description="Current workspace status",
    )
    risk_explanation: RiskExplanationSchema | None = Field(None, description="Risk intelligence")
    deadline_intelligence: OpportunityDeadlineSchema | None = Field(None, description="Deadline intelligence")
