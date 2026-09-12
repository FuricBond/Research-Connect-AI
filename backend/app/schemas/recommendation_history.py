"""
Pydantic schemas for Phase 3.7 — Recommendation History.

Strict Architectural Boundaries:
  - Preserves point-in-time recommendation ranking outputs.
  - History is read-only and immutable.
  - Provides lightweight opportunity details for rendering without duplicate full records.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
import uuid

from pydantic import BaseModel, ConfigDict, Field


class RecommendationOpportunityBriefSchema(BaseModel):
    """
    Lightweight summary of recommended opportunity for history rendering.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Opportunity ID")
    title: str = Field(..., description="Opportunity title")
    opportunity_type: str | None = Field(None, description="Opportunity type (CONFERENCE, JOURNAL, etc.)")
    delivery_mode: str | None = Field(None, description="Delivery mode (ONLINE, OFFLINE, HYBRID)")
    organizer: str | None = Field(None, description="Organizer or publisher name")
    submission_deadline: datetime | None = Field(None, description="Normalized submission deadline")


class RecommendationItemSnapshotSchema(BaseModel):
    """
    Schema for an individual recommendation item within a snapshot.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Item snapshot ID")
    snapshot_id: uuid.UUID = Field(..., description="Parent snapshot ID")
    opportunity_id: uuid.UUID = Field(..., description="Opportunity ID")
    rank: int = Field(..., ge=1, description="1-indexed rank position at recommendation time")
    base_relevance_score: float = Field(..., ge=0.0, le=1.0, description="Phase 2 base relevance score")
    personalization_score: float = Field(..., ge=0.0, le=1.0, description="Phase 3.5 personalization score")
    behavioral_adjustment: float = Field(..., description="Phase 3.6 behavioral contribution")
    final_score: float = Field(..., ge=0.0, le=1.0, description="Composite final recommendation score")
    risk_level: str | None = Field(None, description="Phase 2.6 risk level snapshot")
    deadline_status: str | None = Field(None, description="Phase 2.7 deadline status snapshot")
    created_at: datetime = Field(..., description="Snapshot item creation timestamp")
    opportunity: RecommendationOpportunityBriefSchema | None = Field(
        None, description="Lightweight opportunity metadata if loaded"
    )
    user_feedback: list[str] = Field(
        default_factory=list,
        description="Active feedback actions recorded for this item (e.g. ['VIEW', 'SAVE'])",
    )


class RecommendationSnapshotResponseSchema(BaseModel):
    """
    Full snapshot response including ordered items and request context.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Snapshot ID")
    researcher_id: uuid.UUID = Field(..., description="Researcher profile ID")
    ranking_version: str = Field(..., description="Deterministic ranking algorithm version identifier")
    candidate_count: int = Field(..., description="Total candidates evaluated")
    returned_count: int = Field(..., description="Number of items returned in snapshot")
    request_context: dict[str, Any] | None = Field(default_factory=dict, description="Query context")
    created_at: datetime = Field(..., description="Timestamp when snapshot was recorded")
    items: list[RecommendationItemSnapshotSchema] = Field(
        default_factory=list, description="Ordered recommendation items"
    )


class RecommendationSnapshotSummarySchema(BaseModel):
    """
    Summary view of a snapshot for list endpoints.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Snapshot ID")
    researcher_id: uuid.UUID = Field(..., description="Researcher profile ID")
    ranking_version: str = Field(..., description="Deterministic ranking algorithm version")
    candidate_count: int = Field(..., description="Total candidates evaluated")
    returned_count: int = Field(..., description="Number of items returned")
    request_context: dict[str, Any] | None = Field(default_factory=dict, description="Query context")
    created_at: datetime = Field(..., description="Timestamp when snapshot was recorded")
    top_opportunity_titles: list[str] = Field(
        default_factory=list, description="Titles of top 3 recommended opportunities"
    )


class RecommendationHistoryListResponse(BaseModel):
    """
    Paginated response schema for researcher recommendation history.
    """

    model_config = ConfigDict(from_attributes=True)

    researcher_id: uuid.UUID = Field(..., description="Researcher profile ID")
    items: list[RecommendationSnapshotSummarySchema] = Field(
        default_factory=list, description="List of recommendation snapshots"
    )
    total: int = Field(..., description="Total snapshots matching filters")
    limit: int = Field(..., description="Pagination limit")
    offset: int = Field(..., description="Pagination offset")
