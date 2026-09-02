"""
Pydantic API Schemas for Discovery Layer (Phase 2.4G).

Defines structured response and item models for:
  - Research search
  - Similar research retrieval
  - Research ↔ opportunity matching
  - Explainable result attributions
"""
from __future__ import annotations

from datetime import datetime
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.opportunity import OpportunityListItem, OpportunityRead


# ── Research Work Read Schema ─────────────────────────────────────────────────


class ResearchWorkRead(BaseModel):
    """Clean representation of ResearchWorkModel omitting internal embeddings."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    openalex_id: str | None = None
    doi: str | None = None
    title: str
    abstract: str | None = None
    publication_year: int | None = None
    publication_date: str | None = None
    work_type: str | None = None
    language: str | None = None
    cited_by_count: int | None = 0
    is_oa: bool | None = False
    oa_status: str | None = None
    landing_page_url: str | None = None
    volume: str | None = None
    issue: str | None = None
    page: str | None = None
    article_number: str | None = None
    license_url: str | None = None
    primary_source_id: uuid.UUID | None = None
    ingestion_source_id: uuid.UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


# ── Explainability Schemas ────────────────────────────────────────────────────


class SignalContributionSchema(BaseModel):
    """Structured attribution for an individual ranking signal."""

    model_config = ConfigDict(from_attributes=True)

    signal_name: str
    score: float
    weight: float
    contribution: float
    qualitative_assessment: str
    is_available: bool = True
    is_primary_driver: bool = False


class TopicEvidenceSchema(BaseModel):
    """Structured evidence of canonical topic overlap."""

    model_config = ConfigDict(from_attributes=True)

    shared_topic_ids: list[uuid.UUID] = Field(default_factory=list)
    shared_topic_names: list[str] = Field(default_factory=list)
    topic_similarity: float = 0.0
    description: str = ""


class ProvenanceEvidenceSchema(BaseModel):
    """Structured evidence of retrieval channel provenance."""

    model_config = ConfigDict(from_attributes=True)

    retrieval_sources: list[str] = Field(default_factory=list)
    description: str = ""


class ExplanationSchema(BaseModel):
    """Complete machine- and human-readable explanation container."""

    model_config = ConfigDict(from_attributes=True)

    summary: str
    strengths: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    signal_contributions: dict[str, SignalContributionSchema] = Field(
        default_factory=dict
    )
    topic_evidence: TopicEvidenceSchema = Field(default_factory=TopicEvidenceSchema)
    provenance_evidence: ProvenanceEvidenceSchema = Field(
        default_factory=ProvenanceEvidenceSchema
    )
    primary_factors: list[str] = Field(default_factory=list)
    final_score: float = 0.0
    rank: int = 0


# ── 1. Research Search Response Models ────────────────────────────────────────


class QueryIntelligenceSchema(BaseModel):
    """Structured academic query intelligence metadata."""

    model_config = ConfigDict(from_attributes=True)

    original_query: str
    normalized_query: str
    expanded_query: str
    was_expanded: bool = False
    detected_acronyms: list[str] = Field(default_factory=list)
    detected_terms: list[str] = Field(default_factory=list)
    transformations: list[str] = Field(default_factory=list)


class ResearchSearchResultItem(BaseModel):
    """Individual item in research search results."""

    model_config = ConfigDict(from_attributes=True)

    work: ResearchWorkRead
    rank: int
    final_score: float
    semantic_score: float | None = None
    lexical_score: float | None = None
    topic_score: float | None = None
    freshness_score: float | None = None
    quality_score: float | None = None
    retrieval_sources: list[str] = Field(default_factory=list)
    explanation: ExplanationSchema | None = None
    diversity_adjustment: float | None = None
    novelty_score: float | None = None
    redundancy_score: float | None = None


class ResearchSearchResponse(BaseModel):
    """Paginated search response envelope for research works."""

    model_config = ConfigDict(from_attributes=True)

    query: str
    items: list[ResearchSearchResultItem]
    total: int
    limit: int
    offset: int
    has_more: bool
    ranking_mode: str
    query_intelligence: QueryIntelligenceSchema | None = None


# ── 2. Similar Research Response Models ───────────────────────────────────────


class SimilarResearchItem(BaseModel):
    """Individual item in similar research results."""

    model_config = ConfigDict(from_attributes=True)

    work: ResearchWorkRead
    rank: int
    combined_similarity: float
    semantic_similarity: float
    lexical_similarity: float
    topic_similarity: float
    freshness: float | None = None
    shared_topic_ids: list[uuid.UUID] = Field(default_factory=list)
    shared_topic_names: list[str] = Field(default_factory=list)
    retrieval_sources: list[str] = Field(default_factory=list)
    explanation: ExplanationSchema | None = None
    diversity_adjustment: float | None = None
    novelty_score: float | None = None
    redundancy_score: float | None = None


class SimilarResearchResponse(BaseModel):
    """Paginated response envelope for similar research works."""

    model_config = ConfigDict(from_attributes=True)

    source_work_id: uuid.UUID
    items: list[SimilarResearchItem]
    total: int
    limit: int
    offset: int
    has_more: bool
    ranking_mode: str


# ── 3. Research ↔ Opportunity Match Response Models ───────────────────────────


class OpportunityMatchItem(BaseModel):
    """Individual item in research-to-opportunity matching results."""

    model_config = ConfigDict(from_attributes=True)

    opportunity: OpportunityRead
    rank: int
    match_score: float
    semantic_similarity: float
    lexical_similarity: float
    topic_similarity: float
    type_compatibility: float
    urgency: float | None = None
    quality_score: float | None = None
    shared_topic_ids: list[uuid.UUID] = Field(default_factory=list)
    shared_topic_names: list[str] = Field(default_factory=list)
    retrieval_sources: list[str] = Field(default_factory=list)
    explanation: ExplanationSchema | None = None
    diversity_adjustment: float | None = None
    novelty_score: float | None = None
    redundancy_score: float | None = None


class OpportunityMatchResponse(BaseModel):
    """Paginated response envelope for matched academic opportunities."""

    model_config = ConfigDict(from_attributes=True)

    research_work_id: uuid.UUID
    items: list[OpportunityMatchItem]
    total: int
    limit: int
    offset: int
    has_more: bool
    ranking_mode: str
