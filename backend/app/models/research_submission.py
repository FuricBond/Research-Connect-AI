from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING
import uuid

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.saved_opportunity import SavedOpportunityModel


class SubmissionStatus(str, Enum):
    """Supported deterministic submission lifecycle stages (Phase 4.2)."""

    DRAFT = "DRAFT"
    READY = "READY"
    SUBMITTED = "SUBMITTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"


class SubmissionType(str, Enum):
    """Academic submission manuscript/proposal format."""

    FULL_PAPER = "FULL_PAPER"
    SHORT_PAPER = "SHORT_PAPER"
    EXTENDED_ABSTRACT = "EXTENDED_ABSTRACT"
    POSTER = "POSTER"
    WORKSHOP_PAPER = "WORKSHOP_PAPER"
    GRANT_PROPOSAL = "GRANT_PROPOSAL"
    OTHER = "OTHER"


class ResearchSubmissionModel(Base):
    """
    Research Submission tracking entity (Phase 4.2).
    
    Tracks manuscript/proposal preparation, submission, peer review, and
    decision outcomes for an academic opportunity in the researcher's workspace.
    """

    __tablename__ = "research_submissions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT', 'READY', 'SUBMITTED', 'UNDER_REVIEW', 'ACCEPTED', 'REJECTED', 'WITHDRAWN')",
            name="chk_research_submissions_status",
        ),
        CheckConstraint(
            "submission_type IN ('FULL_PAPER', 'SHORT_PAPER', 'EXTENDED_ABSTRACT', 'POSTER', 'WORKSHOP_PAPER', 'GRANT_PROPOSAL', 'OTHER')",
            name="chk_research_submissions_type",
        ),
        Index("idx_research_submissions_workspace_item", "workspace_item_id"),
        Index("idx_research_submissions_status", "status"),
        Index("idx_research_submissions_updated", "updated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    workspace_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("saved_opportunities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Manuscript / Proposal Details
    title: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Manuscript or application title",
    )
    abstract: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Abstract text or proposal summary",
    )
    submission_type: Mapped[str] = mapped_column(
        String(50),
        default=SubmissionType.FULL_PAPER.value,
        server_default=SubmissionType.FULL_PAPER.value,
        nullable=False,
        comment="Submission type: FULL_PAPER, SHORT_PAPER, POSTER, etc.",
    )

    # Lifecycle State Machine
    status: Mapped[str] = mapped_column(
        String(50),
        default=SubmissionStatus.DRAFT.value,
        server_default=SubmissionStatus.DRAFT.value,
        nullable=False,
        index=True,
        comment="Status: DRAFT, READY, SUBMITTED, UNDER_REVIEW, ACCEPTED, REJECTED, WITHDRAWN",
    )

    # External Portal Tracking
    external_submission_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="External tracking ID (e.g. OpenReview #142, EasyChair #56)",
    )
    venue: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Venue or conference/journal name if overriding opportunity name",
    )
    submission_url: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
        comment="URL of the submission portal or submitted paper page",
    )
    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Researcher personal notes, co-author tasks, or reviewer comments",
    )

    # Lifecycle Event Timestamps
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when officially submitted",
    )
    decision_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when decision (ACCEPTED or REJECTED) was received",
    )
    status_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Timestamp of latest status transition",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationship to Workspace item
    workspace_item: Mapped["SavedOpportunityModel"] = relationship(
        back_populates="submissions",
    )
