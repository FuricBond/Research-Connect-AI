"""
Research Submission Schemas (Phase 4.2).

Pydantic v2 validation models for research submission lifecycle,
metadata updates, state transitions, and enriched deadline context.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.research_submission import SubmissionStatus, SubmissionType


class SubmissionDeadlineContext(BaseModel):
    """Canonical Phase 2.7 deadline intelligence grounded from the parent opportunity."""

    model_config = ConfigDict(from_attributes=True)

    submission_deadline: datetime | None = None
    days_remaining: float | None = None
    urgency_tier: str | None = None
    is_aoe: bool = False
    has_extension: bool = False
    has_conflict: bool = False
    summary: str | None = None


class ResearchSubmissionCreate(BaseModel):
    """Payload for creating a new research submission draft linked to a workspace opportunity."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    workspace_item_id: uuid.UUID = Field(
        ...,
        description="ID of the parent workspace item (saved_opportunities.id)",
    )
    title: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Title of the manuscript or application proposal",
    )
    abstract: str | None = Field(
        None,
        description="Abstract text or proposal summary",
    )
    submission_type: SubmissionType = Field(
        default=SubmissionType.FULL_PAPER,
        description="Type of submission (e.g. FULL_PAPER, SHORT_PAPER, POSTER)",
    )
    external_submission_id: str | None = Field(
        None,
        max_length=255,
        description="External tracking ID (e.g. OpenReview #142, EasyChair #56)",
    )
    venue: str | None = Field(
        None,
        max_length=255,
        description="Target venue or conference/journal name if overriding opportunity name",
    )
    submission_url: str | None = Field(
        None,
        max_length=1000,
        description="URL of submission portal or submitted paper page",
    )
    notes: str | None = Field(
        None,
        description="Personal notes, co-author tasks, or submission reminders",
    )


class ResearchSubmissionUpdate(BaseModel):
    """Payload for partially updating draft submission metadata."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    title: str | None = Field(
        None,
        min_length=1,
        max_length=500,
        description="Updated manuscript title",
    )
    abstract: str | None = Field(
        None,
        description="Updated abstract or proposal summary",
    )
    submission_type: SubmissionType | None = Field(
        None,
        description="Updated submission format type",
    )
    external_submission_id: str | None = Field(
        None,
        max_length=255,
        description="Updated external tracking ID",
    )
    venue: str | None = Field(
        None,
        max_length=255,
        description="Updated target venue or conference/journal name",
    )
    submission_url: str | None = Field(
        None,
        max_length=1000,
        description="Updated portal URL",
    )
    notes: str | None = Field(
        None,
        description="Updated notes",
    )


class SubmissionStatusTransition(BaseModel):
    """Payload for executing a deterministic submission status transition."""

    model_config = ConfigDict(from_attributes=True)

    target_status: SubmissionStatus = Field(
        ...,
        description="Target lifecycle state: DRAFT, READY, SUBMITTED, UNDER_REVIEW, ACCEPTED, REJECTED, WITHDRAWN",
    )
    notes: str | None = Field(
        None,
        description="Optional transition notes or reviewer feedback",
    )


class ResearchSubmissionRead(BaseModel):
    """Full read schema for a research submission record with contextual metadata."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_item_id: uuid.UUID
    title: str
    abstract: str | None = None
    submission_type: SubmissionType
    status: SubmissionStatus
    external_submission_id: str | None = None
    venue: str | None = None
    submission_url: str | None = None
    notes: str | None = None
    submitted_at: datetime | None = None
    decision_at: datetime | None = None
    status_updated_at: datetime
    created_at: datetime
    updated_at: datetime
    allowed_transitions: list[SubmissionStatus] = Field(default_factory=list)

    # Linked Opportunity / Workspace Summary
    workspace_status: str
    opportunity_id: uuid.UUID
    opportunity_title: str
    venue_name: str | None = None
    deadline_context: SubmissionDeadlineContext | None = None


class ResearchSubmissionListResponse(BaseModel):
    """Paginated and aggregated list response for research submissions."""

    model_config = ConfigDict(from_attributes=True)

    items: list[ResearchSubmissionRead]
    total_count: int
    counts_by_status: dict[str, int]
    counts_by_type: dict[str, int]


class SubmissionSummaryResponse(BaseModel):
    """Aggregated statistics across all submissions for an authenticated researcher."""

    model_config = ConfigDict(from_attributes=True)

    total_submissions: int
    active_submissions: int
    accepted_submissions: int
    rejected_submissions: int
    withdrawn_submissions: int
    counts_by_status: dict[str, int]
    counts_by_type: dict[str, int]
