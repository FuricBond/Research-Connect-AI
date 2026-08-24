from datetime import date, datetime
from typing import TYPE_CHECKING, Optional
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.types import Vector
from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.saved_opportunity import SavedOpportunityModel
    from app.models.source import SourceModel
    from app.models.topic import TopicModel


class OpportunityModel(Base, TimestampMixin):
    """Unified core opportunity model (Conferences, Journals, Workshops, CFPs, Special Issues)."""

    __tablename__ = "opportunities"
    __table_args__ = (
        UniqueConstraint("source_id", "raw_source_id", name="uq_opportunities_source_raw_id"),
        CheckConstraint(
            "opportunity_type IN ('CONFERENCE', 'JOURNAL', 'WORKSHOP', 'CALL_FOR_PAPERS', 'SPECIAL_ISSUE')",
            name="chk_opportunities_type",
        ),
        CheckConstraint(
            "delivery_mode IN ('ONLINE', 'OFFLINE', 'HYBRID')",
            name="chk_opportunities_delivery_mode",
        ),
        CheckConstraint(
            "status IN ('ACTIVE', 'EXPIRED', 'ARCHIVED', 'DRAFT', 'UNVERIFIED')",
            name="chk_opportunities_status",
        ),
        Index("idx_opportunities_type_status", "opportunity_type", "status"),
        Index("idx_opportunities_deadline", "submission_deadline"),
        Index("idx_opportunities_last_seen", "last_seen_at"),
    )

    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Core metadata
    title: Mapped[str] = mapped_column(Text, nullable=False)
    opportunity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    slug: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    # Organizational details
    publisher: Mapped[str | None] = mapped_column(String(255), nullable=True)
    organizer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    series_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    edition: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Content
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Access & Location
    website_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    submission_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivery_mode: Mapped[str] = mapped_column(String(50), default="OFFLINE", nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Deadlines & Event dates
    submission_deadline: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    notification_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    camera_ready_deadline: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    event_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    event_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Quality, Indexing & Risk Assessment
    indexing: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True, default=list)
    apc_or_fee: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    is_predatory_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    risk_score: Mapped[float | None] = mapped_column(Numeric(3, 2), default=0.00, nullable=True)
    risk_reasons: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True, default=list)

    # Ingestion & Lifecycle status
    status: Mapped[str] = mapped_column(String(50), default="ACTIVE", nullable=False, index=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sources.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    raw_source_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # AI / Embedding (384-dimensional for all-MiniLM-L6-v2, optional)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(384), nullable=True)

    # Relationships
    source: Mapped[Optional["SourceModel"]] = relationship(
        back_populates="opportunities",
    )
    topic_associations: Mapped[list["OpportunityTopicModel"]] = relationship(
        back_populates="opportunity",
        cascade="all, delete-orphan",
    )
    saved_by_users: Mapped[list["SavedOpportunityModel"]] = relationship(
        back_populates="opportunity",
        cascade="all, delete-orphan",
    )


class OpportunityTopicModel(Base):
    """Many-to-many junction model linking Opportunities to Topics with extraction confidence."""

    __tablename__ = "opportunity_topics"

    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("opportunities.id", ondelete="CASCADE"),
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
        default=1.00,
        nullable=False,
    )
    is_primary: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    opportunity: Mapped["OpportunityModel"] = relationship(
        back_populates="topic_associations",
    )
    topic: Mapped["TopicModel"] = relationship(
        back_populates="opportunity_associations",
    )
