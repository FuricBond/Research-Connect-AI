"""
Phase 5.10 — Faculty Research Opportunities & Project Postings.

Where `OpportunityModel` represents an *externally ingested* call for papers, a posting is
authored *on the platform* by a faculty member or administrator: an open research slot, an
available thesis topic, or an invitation to collaborate. The two are deliberately separate
entities — a posting has an owner who is accountable for it, a lifecycle that owner drives,
and no ingestion provenance, deduplication, or predatory-risk assessment, because there is
no third-party source to distrust.

Strict boundaries:
  - Postings never enter the Phase 2 ingestion pipeline and are never risk-scored against
    Phase 2.6 heuristics designed for anonymous external venues.
  - Authorship is enforced server-side: only FACULTY and ADMIN accounts may create postings,
    and only the owning author (or an administrator) may modify one.
  - Visibility follows the lifecycle: only OPEN postings are publicly discoverable.
"""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.research_posting_application import ResearchPostingApplicationModel
    from app.models.research_profile import ResearchProfileModel
    from app.models.topic import TopicModel
    from app.models.user import UserModel


class PostingType(str, Enum):
    """
    Categories of platform-authored research posting.

    Phase 5.10 introduced the supervisor-led categories. Phase 5.11 adds the structured-opening
    categories, which are appointments with terms: they additionally carry compensation,
    commitment, duration and eligibility fields.
    """

    # Phase 5.10 — supervisor-led opportunities
    PROJECT = "PROJECT"
    THESIS_TOPIC = "THESIS_TOPIC"
    COLLABORATION = "COLLABORATION"
    LAB_ROTATION = "LAB_ROTATION"
    # Phase 5.11 — structured openings
    INTERNSHIP = "INTERNSHIP"
    RESEARCH_ASSISTANTSHIP = "RESEARCH_ASSISTANTSHIP"
    POSTDOC = "POSTDOC"

    @classmethod
    def structured_openings(cls) -> frozenset["PostingType"]:
        """
        Categories that represent a funded appointment rather than an open invitation.

        These are the types for which compensation and commitment are meaningful, and for
        which the platform accepts applications.
        """
        return frozenset({cls.INTERNSHIP, cls.RESEARCH_ASSISTANTSHIP, cls.POSTDOC})


class PostingStatus(str, Enum):
    """
    Deterministic posting lifecycle.

    DRAFT is private to the author. OPEN is publicly discoverable and accepts interest.
    CLOSED stops accepting interest while remaining visible to its author. FILLED records a
    successful outcome, which is distinct from CANCELLED (withdrawn without an outcome), and
    that distinction is what makes the state machine worth having rather than a boolean.
    ARCHIVED is the terminal resting state.
    """

    DRAFT = "DRAFT"
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    ARCHIVED = "ARCHIVED"


class PostingWorkMode(str, Enum):
    """Where the work is carried out."""

    ONSITE = "ONSITE"
    REMOTE = "REMOTE"
    HYBRID = "HYBRID"


class ResearchPostingModel(Base, TimestampMixin):
    """A research opportunity authored on the platform by a faculty member (Phase 5.10)."""

    __tablename__ = "research_postings"
    __table_args__ = (
        CheckConstraint(
            "posting_type IN ('PROJECT', 'THESIS_TOPIC', 'COLLABORATION', 'LAB_ROTATION', "
            "'INTERNSHIP', 'RESEARCH_ASSISTANTSHIP', 'POSTDOC')",
            name="chk_research_postings_type",
        ),
        CheckConstraint(
            "status IN ('DRAFT', 'OPEN', 'CLOSED', 'FILLED', 'CANCELLED', 'ARCHIVED')",
            name="chk_research_postings_status",
        ),
        CheckConstraint(
            "work_mode IN ('ONSITE', 'REMOTE', 'HYBRID')",
            name="chk_research_postings_work_mode",
        ),
        CheckConstraint(
            "positions_available >= 1",
            name="chk_research_postings_positions_positive",
        ),
        # Phase 5.11 — structured opening terms
        CheckConstraint(
            "compensation_type IN ('STIPEND', 'SALARY', 'HOURLY', 'SCHOLARSHIP', "
            "'GRANT_FUNDED', 'UNPAID', 'UNSPECIFIED')",
            name="chk_research_postings_compensation_type",
        ),
        CheckConstraint(
            "commitment_type IS NULL OR commitment_type IN ('FULL_TIME', 'PART_TIME', 'FLEXIBLE')",
            name="chk_research_postings_commitment_type",
        ),
        CheckConstraint(
            "duration_months IS NULL OR duration_months >= 1",
            name="chk_research_postings_duration_positive",
        ),
        CheckConstraint(
            "compensation_amount IS NULL OR compensation_amount >= 0",
            name="chk_research_postings_compensation_non_negative",
        ),
        Index("idx_research_postings_status_type", "status", "posting_type"),
        Index("idx_research_postings_author", "author_profile_id"),
        Index("idx_research_postings_deadline", "application_deadline"),
        Index("idx_research_postings_status_deadline", "status", "application_deadline"),
        Index("idx_research_postings_created", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # ── Authorship ────────────────────────────────────────────────────────────
    # Both the profile (the academic identity shown to readers) and the user (the account
    # that authorization is checked against) are recorded. Keeping the user id denormalized
    # here lets ownership be verified without joining through the profile on every request.
    author_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Authoring ResearchProfileModel ID",
    )
    author_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Authoring UserModel ID, used for ownership authorization",
    )

    # ── Core content ──────────────────────────────────────────────────────────
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    posting_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=PostingStatus.DRAFT.value,
        server_default=PostingStatus.DRAFT.value,
        index=True,
    )
    summary: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # Free-text expectations. Deliberately unstructured: supervisors describe requirements in
    # prose, and forcing a taxonomy on them would lose meaning without improving matching.
    required_skills: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True, default=list)
    preferred_qualifications: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Placement ─────────────────────────────────────────────────────────────
    institution: Mapped[str | None] = mapped_column(String(255), nullable=True)
    department: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    country: Mapped[str | None] = mapped_column(String(2), nullable=True, comment="ISO 3166-1 alpha-2")
    work_mode: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=PostingWorkMode.ONSITE.value,
        server_default=PostingWorkMode.ONSITE.value,
    )

    # ── Capacity and timing ───────────────────────────────────────────────────
    positions_available: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
    )
    application_deadline: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="Applications close at this instant; NULL means open-ended",
    )
    expected_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expected_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # ── Contact and links ─────────────────────────────────────────────────────
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Lifecycle audit ───────────────────────────────────────────────────────
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="First transition into OPEN",
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status_note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Author's reason recorded on the most recent status transition",
    )

    # Denormalized counter maintained by the application workflow (Phase 5.11) so listings do
    # not need a correlated subquery per posting.
    application_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    # ── Phase 5.11 — structured opening terms ─────────────────────────────────
    # Meaningful for internships, assistantships and post-docs. Left at UNSPECIFIED / NULL for
    # the Phase 5.10 supervisor-led categories, where there is no appointment to fund.
    compensation_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="UNSPECIFIED",
        server_default="UNSPECIFIED",
        comment="How the appointment is funded; UNPAID is stated explicitly, never implied by a blank",
    )
    compensation_amount: Mapped[float | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
        comment="Amount per compensation_period in compensation_currency",
    )
    compensation_currency: Mapped[str | None] = mapped_column(
        String(3),
        nullable=True,
        comment="ISO 4217 currency code",
    )
    compensation_period: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="Period the amount covers, e.g. MONTH, YEAR, HOUR, TOTAL",
    )
    commitment_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    hours_per_week: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    eligibility_requirements: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Formal eligibility, e.g. enrolment status, visa or degree requirements",
    )
    accepts_applications: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment=(
            "Whether applications are handled on the platform. When false, applicants are "
            "directed to contact_email or external_url instead."
        ),
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    author_profile: Mapped["ResearchProfileModel"] = relationship(
        back_populates="research_postings",
    )
    author_user: Mapped["UserModel"] = relationship()
    topic_associations: Mapped[list["ResearchPostingTopicModel"]] = relationship(
        back_populates="posting",
        cascade="all, delete-orphan",
    )
    applications: Mapped[list["ResearchPostingApplicationModel"]] = relationship(
        back_populates="posting",
        cascade="all, delete-orphan",
    )


class ResearchPostingTopicModel(Base):
    """
    Links a posting to canonical taxonomy topics (Phase 5.10).

    Mirrors `OpportunityTopicModel` so postings participate in the same taxonomy-aware
    filtering and peer/interest matching as ingested opportunities, rather than being matched
    on free-text alone.
    """

    __tablename__ = "research_posting_topics"
    __table_args__ = (
        UniqueConstraint("posting_id", "topic_id", name="uq_research_posting_topics"),
        Index("idx_research_posting_topics_topic", "topic_id"),
    )

    posting_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research_postings.id", ondelete="CASCADE"),
        primary_key=True,
    )
    topic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("topics.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )
    confidence_score: Mapped[float] = mapped_column(
        Numeric(3, 2),
        nullable=False,
        default=1.00,
        server_default="1.00",
    )
    is_primary: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    posting: Mapped["ResearchPostingModel"] = relationship(back_populates="topic_associations")
    topic: Mapped["TopicModel"] = relationship()
