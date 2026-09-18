"""
Pydantic v2 Schemas for Phase 4.1 Opportunity Workspace.
"""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.deadline import OpportunityDeadlineSchema
from app.schemas.opportunity import RiskExplanationSchema


class WorkspaceStatus(str, Enum):
    """Supported deterministic workspace workflow stages (Phase 4.1)."""

    SAVED = "SAVED"
    CONSIDERING = "CONSIDERING"
    PLANNING = "PLANNING"
    APPLIED = "APPLIED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    ARCHIVED = "ARCHIVED"


class WorkspacePriority(str, Enum):
    """Researcher workspace urgency / priority rating."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"


class WorkspaceOpportunitySummary(BaseModel):
    """Compact canonical opportunity view attached to a workspace item."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    opportunity_type: str
    delivery_mode: str = "OFFLINE"
    publisher: str | None = None
    organizer: str | None = None
    submission_deadline: datetime | None = None
    notification_date: datetime | None = None
    camera_ready_deadline: datetime | None = None
    event_start_date: date | None = None
    location: str | None = None
    website_url: str | None = None
    status: str = "ACTIVE"
    risk_score: float | None = None
    is_predatory_flag: bool = False
    deadline_intelligence: OpportunityDeadlineSchema | None = None
    risk_explanation: RiskExplanationSchema | None = None


class WorkspaceItemCreate(BaseModel):
    """Payload to add an opportunity to the researcher workspace."""

    opportunity_id: uuid.UUID
    status: WorkspaceStatus = WorkspaceStatus.SAVED
    priority: WorkspacePriority = WorkspacePriority.MEDIUM
    tags: list[str] = Field(default_factory=list)
    notes: str | None = None


class WorkspaceItemUpdate(BaseModel):
    """Payload to partially update workspace item metadata."""

    priority: WorkspacePriority | None = None
    tags: list[str] | None = None
    notes: str | None = None


class WorkspaceStatusTransition(BaseModel):
    """Payload to execute an explicit workflow status transition."""

    target_status: WorkspaceStatus
    notes: str | None = None


class WorkspaceItemRead(BaseModel):
    """Full serialized workspace item including canonical opportunity context."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    opportunity_id: uuid.UUID
    status: WorkspaceStatus
    priority: WorkspacePriority
    tags: list[str] = Field(default_factory=list)
    notes: str | None = None
    created_at: datetime
    updated_at: datetime
    status_updated_at: datetime
    archived_at: datetime | None = None
    allowed_transitions: list[WorkspaceStatus] = Field(default_factory=list)
    opportunity: WorkspaceOpportunitySummary


class WorkspaceListResponse(BaseModel):
    """Paginated or filtered list of workspace items with summary aggregates."""

    items: list[WorkspaceItemRead]
    total_count: int
    active_count: int
    archived_count: int
    counts_by_status: dict[str, int]
    counts_by_priority: dict[str, int]


class WorkspaceSummaryResponse(BaseModel):
    """Statistical overview of researcher's workspace."""

    total_count: int
    active_count: int
    archived_count: int
    counts_by_status: dict[str, int]
    counts_by_priority: dict[str, int]
