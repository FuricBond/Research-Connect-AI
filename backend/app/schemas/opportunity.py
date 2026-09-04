from datetime import date, datetime
from decimal import Decimal
from enum import Enum
import uuid

from typing import Any
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.deadline import OpportunityDeadlineSchema


class OpportunityFee(BaseModel):
    """Fee/APC information for an opportunity."""
    has_fee: bool = False
    amount: float | None = None
    currency: str | None = None
    fee_type: str | None = None


# ── Risk Explainability API Schemas (Phase 2.6F) ──────────────────────────────


class RiskEvidenceItemSchema(BaseModel):
    """Structured evidence item with provenance and contribution."""
    model_config = ConfigDict(from_attributes=True)

    signal: str
    category: str
    strength: str
    confidence: str
    provenance: str
    source_field: str
    matched_value: str | None = None
    explanation: str = ""
    is_present: bool = True
    contribution: float = 0.0
    severity: str = "NEUTRAL"
    evidence_type: str = "DIRECT_METADATA"
    metadata: dict[str, Any] = Field(default_factory=dict)


class RiskExplanationSchema(BaseModel):
    """Complete machine- and human-readable risk explanation container."""
    model_config = ConfigDict(from_attributes=True)

    opportunity_id: str | None = None
    risk_score: float = 0.0
    risk_level: str = "LOW_RISK"
    risk_confidence: float = 0.0
    evidence_sufficiency: str = "SUFFICIENT"
    is_predatory_flag: bool = False
    summary: str = ""
    positive_trust_signals: list[RiskEvidenceItemSchema] = Field(default_factory=list)
    suspicious_signals: list[RiskEvidenceItemSchema] = Field(default_factory=list)
    neutral_signals: list[RiskEvidenceItemSchema] = Field(default_factory=list)
    graph_signals: list[RiskEvidenceItemSchema] = Field(default_factory=list)
    venue_signals: list[RiskEvidenceItemSchema] = Field(default_factory=list)
    publisher_signals: list[RiskEvidenceItemSchema] = Field(default_factory=list)
    evidence_items: list[RiskEvidenceItemSchema] = Field(default_factory=list)
    risk_reasons: list[str] = Field(default_factory=list)
    provenance_summary: dict[str, int] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
    gross_negative_score: float = 0.0
    trust_mitigation_score: float = 0.0
    resolved_entity: dict[str, Any] | None = None


class OpportunityBase(BaseModel):
    """Shared fields for opportunity read responses."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    opportunity_type: str
    slug: str | None = None

    # Organizational
    publisher: str | None = None
    organizer: str | None = None
    series_name: str | None = None
    edition: str | None = None

    # Content
    summary: str | None = None
    description: str | None = None

    # Access & Location
    website_url: str | None = None
    submission_url: str | None = None
    delivery_mode: str
    location: str | None = None

    # Dates
    submission_deadline: datetime | None = None
    notification_date: datetime | None = None
    camera_ready_deadline: datetime | None = None
    event_start_date: date | None = None
    event_end_date: date | None = None

    # Quality, Trust & Risk
    indexing: list[str] | None = None
    apc_or_fee: dict | None = None
    is_predatory_flag: bool
    risk_score: Decimal | None = None
    risk_reasons: list[str] | None = None
    risk_level: str | None = None
    risk_confidence: float | None = None
    risk_explanation: RiskExplanationSchema | None = None
    deadline_intelligence: OpportunityDeadlineSchema | None = None

    # Status & Lifecycle
    status: str
    source_id: uuid.UUID | None = None
    last_verified_at: datetime | None = None
    last_seen_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class OpportunityRead(OpportunityBase):
    """Full opportunity response schema."""
    pass


class OpportunityListItem(BaseModel):
    """Lighter schema for list responses — omits large text fields."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    opportunity_type: str
    publisher: str | None = None
    organizer: str | None = None
    summary: str | None = None
    delivery_mode: str
    location: str | None = None
    submission_deadline: datetime | None = None
    event_start_date: date | None = None
    event_end_date: date | None = None
    indexing: list[str] | None = None
    website_url: str | None = None
    submission_url: str | None = None
    is_predatory_flag: bool
    risk_score: Decimal | None = None
    risk_level: str | None = None
    risk_confidence: float | None = None
    deadline_intelligence: OpportunityDeadlineSchema | None = None
    status: str
    last_seen_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class OpportunityListResponse(BaseModel):
    """Paginated list response envelope for opportunities."""
    items: list[OpportunityListItem]
    page: int
    page_size: int
    total: int


class IngestionRunStatus(str, Enum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class IngestionRunRead(BaseModel):
    """Schema for ingestion run audit log records."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_id: uuid.UUID
    status: IngestionRunStatus
    topic: str | None = None
    pages_fetched: int
    records_parsed: int
    records_valid: int
    records_invalid: int
    records_inserted: int
    records_updated: int
    records_unchanged: int
    duplicates_detected: int
    potential_duplicates_detected: int
    records_expired: int
    error_message: str | None = None
    metrics_detail: dict | None = None
    started_at: datetime
    completed_at: datetime | None = None
