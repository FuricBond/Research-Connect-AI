from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.calendar import ResearchCalendarEventModel
    from app.models.opportunity import OpportunityModel
    from app.models.research_profile import ResearchProfileModel
    from app.models.research_submission import ResearchSubmissionModel


class NotificationType(str, Enum):
    """Categorization for research notifications and deadline alerts (Phase 4.5)."""

    DEADLINE_UPCOMING = "DEADLINE_UPCOMING"
    DEADLINE_TODAY = "DEADLINE_TODAY"
    DEADLINE_EXTENDED = "DEADLINE_EXTENDED"
    DEADLINE_MOVED_EARLIER = "DEADLINE_MOVED_EARLIER"
    DEADLINE_CONFLICT = "DEADLINE_CONFLICT"
    CALENDAR_EVENT_UPCOMING = "CALENDAR_EVENT_UPCOMING"
    SUBMISSION_STATUS_CHANGE = "SUBMISSION_STATUS_CHANGE"
    SYSTEM = "SYSTEM"
    WORKSPACE_INVITATION = "WORKSPACE_INVITATION"
    INVITATION_ACCEPTED = "INVITATION_ACCEPTED"
    MEMBER_ROLE_CHANGED = "MEMBER_ROLE_CHANGED"
    MEMBER_REMOVED = "MEMBER_REMOVED"
    TASK_ASSIGNED = "TASK_ASSIGNED"
    TASK_COMPLETED = "TASK_COMPLETED"
    DOCUMENT_UPDATED = "DOCUMENT_UPDATED"
    COLLABORATION_ACTIVITY = "COLLABORATION_ACTIVITY"


class DeliveryChannel(str, Enum):
    """Supported delivery channels for notifications and reminders."""

    IN_APP = "IN_APP"
    EMAIL = "EMAIL"
    PUSH = "PUSH"


class DeliveryStatus(str, Enum):
    """Delivery status of a notification."""

    PENDING = "PENDING"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    SKIPPED = "SKIPPED"


class OffsetUnit(str, Enum):
    """Time offset unit for reminder rules."""

    DAYS = "DAYS"
    HOURS = "HOURS"
    MINUTES = "MINUTES"


class NotificationPreferenceModel(Base):
    """
    Researcher notification preferences entity (Phase 4.5).

    Governs delivery channels and feature opt-ins for a researcher.
    """

    __tablename__ = "researcher_notification_preferences"
    __table_args__ = (
        Index("idx_notification_preferences_profile", "profile_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research_profiles.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
        comment="Associated researcher profile ID",
    )
    email_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        comment="Whether email notifications are enabled",
    )
    in_app_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        comment="Whether in-app notification center alerts are enabled",
    )
    deadline_reminders_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        comment="Whether advance deadline reminder alerts are enabled",
    )
    extension_notifications_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        comment="Whether notifications for deadline extensions are enabled",
    )
    conflict_notifications_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        comment="Whether notifications for unresolved deadline conflicts are enabled",
    )
    calendar_event_reminders_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        comment="Whether reminders for user-created calendar planning events are enabled",
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

    # Relationships
    profile: Mapped[ResearchProfileModel] = relationship(
        "ResearchProfileModel",
        backref="notification_preference",
    )

    def __repr__(self) -> str:
        return (
            f"<NotificationPreference(id={self.id}, profile_id={self.profile_id}, "
            f"email={self.email_enabled}, in_app={self.in_app_enabled})>"
        )


class ReminderRuleModel(Base):
    """
    User-configurable reminder rule entity (Phase 4.5).

    Defines when and how a researcher wants to receive advance reminders for deadlines.
    """

    __tablename__ = "reminder_rules"
    __table_args__ = (
        CheckConstraint(
            "offset_unit IN ('DAYS', 'HOURS', 'MINUTES')",
            name="chk_reminder_rules_offset_unit",
        ),
        CheckConstraint(
            "delivery_channel IN ('IN_APP', 'EMAIL', 'PUSH')",
            name="chk_reminder_rules_channel",
        ),
        CheckConstraint(
            "offset_amount > 0",
            name="chk_reminder_rules_positive_offset",
        ),
        UniqueConstraint(
            "profile_id",
            "event_type",
            "offset_amount",
            "offset_unit",
            "delivery_channel",
            name="uq_reminder_rules_profile_type_offset_channel",
        ),
        Index("idx_reminder_rules_profile_active", "profile_id", "is_active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Associated researcher profile ID",
    )
    event_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Target milestone type or None for all milestones",
    )
    offset_amount: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Offset duration amount (e.g. 14, 7, 3, 24)",
    )
    offset_unit: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=OffsetUnit.DAYS.value,
        server_default="DAYS",
        comment="Unit of offset: DAYS, HOURS, MINUTES",
    )
    delivery_channel: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=DeliveryChannel.IN_APP.value,
        server_default="IN_APP",
        comment="Delivery channel: IN_APP, EMAIL, PUSH",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        comment="Whether this rule is actively evaluated",
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

    # Relationships
    profile: Mapped[ResearchProfileModel] = relationship(
        "ResearchProfileModel",
        backref="reminder_rules",
    )

    def __repr__(self) -> str:
        return (
            f"<ReminderRule(id={self.id}, profile_id={self.profile_id}, "
            f"offset={self.offset_amount} {self.offset_unit}, channel={self.delivery_channel})>"
        )


class NotificationModel(Base):
    """
    Notification entity (Phase 4.5).

    Represents a discrete notification generated for a researcher.
    Guarantees idempotency via unique deduplication_key.
    """

    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint(
            "notification_type IN ('DEADLINE_UPCOMING', 'DEADLINE_TODAY', 'DEADLINE_EXTENDED', 'DEADLINE_MOVED_EARLIER', 'DEADLINE_CONFLICT', 'CALENDAR_EVENT_UPCOMING', 'SUBMISSION_STATUS_CHANGE', 'SYSTEM', 'WORKSPACE_INVITATION', 'INVITATION_ACCEPTED', 'MEMBER_ROLE_CHANGED', 'MEMBER_REMOVED', 'TASK_ASSIGNED', 'TASK_COMPLETED', 'DOCUMENT_UPDATED', 'COLLABORATION_ACTIVITY')",
            name="chk_notifications_type",
        ),
        CheckConstraint(
            "delivery_status IN ('PENDING', 'DELIVERED', 'FAILED', 'CANCELLED', 'SKIPPED')",
            name="chk_notifications_status",
        ),
        CheckConstraint(
            "delivery_channel IN ('IN_APP', 'EMAIL', 'PUSH')",
            name="chk_notifications_channel",
        ),
        UniqueConstraint(
            "deduplication_key",
            name="uq_notifications_deduplication_key",
        ),
        Index("idx_notifications_profile_status", "profile_id", "delivery_status"),
        Index("idx_notifications_profile_read", "profile_id", "read_at"),
        Index("idx_notifications_scheduled_status", "scheduled_for", "delivery_status"),
        Index("idx_notifications_opp", "opportunity_id"),
        Index("idx_notifications_cal_event", "calendar_event_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Recipient researcher profile ID",
    )
    notification_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Type of notification",
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Notification headline/title",
    )
    body: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Notification message body / content",
    )
    source_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="OPPORTUNITY",
        server_default="OPPORTUNITY",
        comment="Source entity type: OPPORTUNITY, CALENDAR_EVENT, SUBMISSION, SYSTEM",
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="Primary entity ID corresponding to source_type",
    )
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("opportunities.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="Associated opportunity ID if applicable",
    )
    calendar_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research_calendar_events.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="Associated calendar event ID if applicable",
    )
    submission_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research_submissions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="Associated research submission ID if applicable",
    )
    deadline_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Canonical deadline milestone type (e.g. SUBMISSION, ABSTRACT)",
    )
    scheduled_for: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        comment="Target instant when this notification was scheduled for delivery",
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Instant when notification was successfully delivered",
    )
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Instant when researcher marked notification as read",
    )
    delivery_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=DeliveryStatus.PENDING.value,
        server_default="PENDING",
        comment="Delivery lifecycle status",
    )
    delivery_channel: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=DeliveryChannel.IN_APP.value,
        server_default="IN_APP",
        comment="Delivery channel",
    )
    deduplication_key: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        unique=True,
        comment="Deterministic hash preventing duplicate generation",
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
        comment="Contextual metadata, opportunity title, venue, timezone, revisions",
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

    # Relationships
    profile: Mapped[ResearchProfileModel] = relationship(
        "ResearchProfileModel",
        backref="notifications",
    )
    opportunity: Mapped[OpportunityModel | None] = relationship(
        "OpportunityModel",
    )
    calendar_event: Mapped[ResearchCalendarEventModel | None] = relationship(
        "ResearchCalendarEventModel",
    )
    submission: Mapped[ResearchSubmissionModel | None] = relationship(
        "ResearchSubmissionModel",
    )
    delivery_attempts: Mapped[list[NotificationDeliveryAttemptModel]] = relationship(
        "NotificationDeliveryAttemptModel",
        back_populates="notification",
        cascade="all, delete-orphan",
        order_by="NotificationDeliveryAttemptModel.attempt_number.asc()",
    )

    def __repr__(self) -> str:
        return (
            f"<Notification(id={self.id}, type='{self.notification_type}', "
            f"profile_id={self.profile_id}, status='{self.delivery_status}', channel='{self.delivery_channel}')>"
        )


class NotificationDeliveryAttemptModel(Base):
    """
    Audit log record for a notification delivery attempt (Phase 4.5).
    """

    __tablename__ = "notification_delivery_attempts"
    __table_args__ = (
        Index("idx_delivery_attempts_notif", "notification_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    notification_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("notifications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Associated notification ID",
    )
    channel: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Delivery channel attempted",
    )
    attempt_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="Sequential attempt number",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Result of attempt: SUCCESS, FAILED, RETRYING",
    )
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    provider_reference: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Provider message ID or dispatch reference",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Diagnostic error message if attempt failed",
    )

    # Relationships
    notification: Mapped[NotificationModel] = relationship(
        "NotificationModel",
        back_populates="delivery_attempts",
    )

    def __repr__(self) -> str:
        return (
            f"<NotificationDeliveryAttempt(id={self.id}, notif_id={self.notification_id}, "
            f"channel='{self.channel}', status='{self.status}', attempt={self.attempt_number})>"
        )
