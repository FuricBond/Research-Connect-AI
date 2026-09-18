from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, TYPE_CHECKING
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.opportunity import OpportunityModel
    from app.models.research_profile import ResearchProfileModel
    from app.models.research_submission import ResearchSubmissionModel
    from app.models.user import UserModel


class CalendarEventType(str, Enum):
    """Categorization for research calendar events and milestones (Phase 4.4)."""

    OPPORTUNITY_SUBMISSION = "OPPORTUNITY_SUBMISSION"
    ABSTRACT_DEADLINE = "ABSTRACT_DEADLINE"
    NOTIFICATION = "NOTIFICATION"
    CAMERA_READY = "CAMERA_READY"
    REGISTRATION = "REGISTRATION"
    EVENT_START = "EVENT_START"
    EVENT_END = "EVENT_END"
    RESEARCH_MILESTONE = "RESEARCH_MILESTONE"
    CUSTOM = "CUSTOM"


class CalendarEventStatus(str, Enum):
    """Planning and lifecycle status of a calendar event (Phase 4.4)."""

    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    SUPERSEDED = "SUPERSEDED"
    CONFLICT = "CONFLICT"


class ResearchCalendarModel(Base):
    """
    Research Calendar entity (Phase 4.4).

    Represents a researcher's planning calendar. Serves as a projection layer
    for canonical opportunity deadlines and user-defined research milestones.
    """

    __tablename__ = "research_calendars"
    __table_args__ = (
        Index("idx_research_calendars_user", "user_id", "is_default"),
        Index("idx_research_calendars_profile", "profile_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Owner user ID",
    )
    profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research_profiles.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="Associated canonical research profile if established",
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="Default Research Calendar",
        server_default="Default Research Calendar",
        comment="Display name of the research calendar",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Optional calendar description or context",
    )
    timezone: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="UTC",
        server_default="UTC",
        comment="Preferred IANA display timezone for this calendar",
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        comment="Whether this is the primary/default calendar for the user",
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

    # 1:N events relationship
    events: Mapped[list[ResearchCalendarEventModel]] = relationship(
        "ResearchCalendarEventModel",
        back_populates="calendar",
        cascade="all, delete-orphan",
        order_by="ResearchCalendarEventModel.start_datetime.asc()",
    )

    def __repr__(self) -> str:
        return f"<ResearchCalendar(id={self.id}, user_id={self.user_id}, name='{self.name}', tz='{self.timezone}')>"


class ResearchCalendarEventModel(Base):
    """
    Research Calendar Event entity (Phase 4.4).

    Represents a discrete planning event, milestone, or projected canonical deadline.
    Preserves opportunity/submission provenance when projected from Phase 2.7 deadline intelligence.
    """

    __tablename__ = "research_calendar_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('OPPORTUNITY_SUBMISSION', 'ABSTRACT_DEADLINE', 'NOTIFICATION', 'CAMERA_READY', 'REGISTRATION', 'EVENT_START', 'EVENT_END', 'RESEARCH_MILESTONE', 'CUSTOM')",
            name="chk_calendar_events_type",
        ),
        CheckConstraint(
            "status IN ('ACTIVE', 'COMPLETED', 'CANCELLED', 'SUPERSEDED', 'CONFLICT')",
            name="chk_calendar_events_status",
        ),
        Index("idx_calendar_events_calendar_start", "calendar_id", "start_datetime"),
        Index("idx_calendar_events_calendar_type", "calendar_id", "event_type"),
        Index("idx_calendar_events_opp", "calendar_id", "opportunity_id"),
        Index("idx_calendar_events_submission", "calendar_id", "submission_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    calendar_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research_calendars.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Parent calendar ID",
    )
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("opportunities.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="Associated opportunity ID when projected from canonical deadline intelligence",
    )
    submission_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research_submissions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="Associated submission tracker ID if tied to a submission workflow",
    )

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Event title or display label",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Event description, notes, or contextual instructions",
    )
    event_type: Mapped[str] = mapped_column(
        String(50),
        default=CalendarEventType.RESEARCH_MILESTONE.value,
        server_default=CalendarEventType.RESEARCH_MILESTONE.value,
        nullable=False,
        comment="Event category: OPPORTUNITY_SUBMISSION, NOTIFICATION, etc.",
    )
    start_datetime: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Start timestamp with UTC timezone if known; null if unparseable/missing",
    )
    end_datetime: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="End timestamp with UTC timezone if applicable",
    )
    date_str: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Date-only representation (e.g. '2026-08-20') preserving date-only semantics",
    )
    all_day: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
        comment="Whether the event represents a full calendar day",
    )
    timezone: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Original timezone (e.g. 'AoE', 'America/New_York', 'UTC') or null if unspecified",
    )
    is_canonical_projection: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
        comment="True if projected from Phase 2.7 canonical deadline intelligence; False for user events",
    )
    provenance_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        server_default="{}",
        nullable=False,
        comment="Full provenance trace: raw date string, milestone type, authority, revisions, conflict status",
    )
    status: Mapped[str] = mapped_column(
        String(50),
        default=CalendarEventStatus.ACTIVE.value,
        server_default=CalendarEventStatus.ACTIVE.value,
        nullable=False,
        comment="Event lifecycle: ACTIVE, COMPLETED, CANCELLED, SUPERSEDED, CONFLICT",
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

    calendar: Mapped[ResearchCalendarModel] = relationship(
        "ResearchCalendarModel",
        back_populates="events",
    )

    def __repr__(self) -> str:
        return f"<ResearchCalendarEvent(id={self.id}, type='{self.event_type}', title='{self.title}', start='{self.start_datetime}')>"
