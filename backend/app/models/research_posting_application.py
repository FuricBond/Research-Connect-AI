"""
Phase 5.11 — Research Internships, RA Openings & the Application Workflow.

Phase 5.10 gave faculty a way to publish an opening. This phase makes an opening something a
researcher can act on: it adds the structured terms that distinguish a funded appointment from
an open-ended invitation (compensation, duration, commitment, eligibility) and the application
record that connects an applicant to a posting.

An application is a two-sided object. The applicant owns their submission and may withdraw it;
the posting's author owns the review decision. Neither side may act on the other's half, and
both sides see the same auditable status history, so a decision can never be silently revised.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any
import uuid

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.research_posting import ResearchPostingModel
    from app.models.research_profile import ResearchProfileModel
    from app.models.user import UserModel


class ApplicationStatus(str, Enum):
    """
    Deterministic application lifecycle.

    SUBMITTED is the applicant's act. UNDER_REVIEW, SHORTLISTED, OFFERED and REJECTED are the
    author's decisions. ACCEPTED and DECLINED are the applicant's response to an offer, and
    WITHDRAWN is the applicant leaving the process at any earlier point. Keeping the two sides'
    terminal states distinct is what lets a supervisor tell "we said no" from "they said no",
    which a single CLOSED state would erase.
    """

    SUBMITTED = "SUBMITTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    SHORTLISTED = "SHORTLISTED"
    OFFERED = "OFFERED"
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"


class CompensationType(str, Enum):
    """How an appointment is funded. UNPAID is stated explicitly rather than left blank."""

    STIPEND = "STIPEND"
    SALARY = "SALARY"
    HOURLY = "HOURLY"
    SCHOLARSHIP = "SCHOLARSHIP"
    GRANT_FUNDED = "GRANT_FUNDED"
    UNPAID = "UNPAID"
    UNSPECIFIED = "UNSPECIFIED"


class CommitmentType(str, Enum):
    """Expected time commitment."""

    FULL_TIME = "FULL_TIME"
    PART_TIME = "PART_TIME"
    FLEXIBLE = "FLEXIBLE"


class ResearchPostingApplicationModel(Base, TimestampMixin):
    """An applicant's submission against a research posting (Phase 5.11)."""

    __tablename__ = "research_posting_applications"
    __table_args__ = (
        # One application per researcher per posting. Re-applying after withdrawal reuses this
        # row rather than accumulating duplicates, so the author sees one history per person.
        UniqueConstraint(
            "posting_id", "applicant_profile_id", name="uq_posting_application_applicant"
        ),
        CheckConstraint(
            "status IN ('SUBMITTED', 'UNDER_REVIEW', 'SHORTLISTED', 'OFFERED', 'ACCEPTED', "
            "'DECLINED', 'REJECTED', 'WITHDRAWN')",
            name="chk_posting_applications_status",
        ),
        Index("idx_posting_applications_posting_status", "posting_id", "status"),
        Index("idx_posting_applications_applicant", "applicant_profile_id"),
        Index("idx_posting_applications_submitted", "submitted_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    posting_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research_postings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    applicant_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    applicant_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Applicant UserModel ID, used for ownership authorization",
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=ApplicationStatus.SUBMITTED.value,
        server_default=ApplicationStatus.SUBMITTED.value,
        index=True,
    )

    # ── Applicant's submission ────────────────────────────────────────────────
    cover_note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Applicant's statement of interest",
    )
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    portfolio_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Link to a CV, portfolio or publication list supplied by the applicant",
    )

    # ── Author's review ───────────────────────────────────────────────────────
    # Kept separate from the applicant's fields, and never exposed to the applicant, so a
    # supervisor can record a candid assessment without it becoming feedback.
    reviewer_note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Author's private note; never returned to the applicant",
    )
    decision_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Reason shared with the applicant on the most recent decision",
    )

    # ── Auditable history ─────────────────────────────────────────────────────
    # Append-only list of {from, to, actor_role, at, reason} entries. Both sides read the same
    # history, so neither can claim a decision was different from what was recorded.
    status_history: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
    )

    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the author last recorded a decision",
    )
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── Relationships ─────────────────────────────────────────────────────────
    posting: Mapped["ResearchPostingModel"] = relationship(back_populates="applications")
    applicant_profile: Mapped["ResearchProfileModel"] = relationship(
        back_populates="posting_applications",
    )
    applicant_user: Mapped["UserModel"] = relationship()
