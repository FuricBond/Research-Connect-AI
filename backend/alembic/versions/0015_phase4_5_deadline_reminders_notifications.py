"""Phase 4.5 — Deadline Reminders, Notifications & Scheduled Alerts

Creates tables for notification preferences, reminder rules, notifications, and delivery attempts:
  - researcher_notification_preferences:
      - id (UUID primary key)
      - profile_id (UUID FK to research_profiles.id ON DELETE CASCADE, unique)
      - email_enabled (BOOLEAN, not null, default true)
      - in_app_enabled (BOOLEAN, not null, default true)
      - deadline_reminders_enabled (BOOLEAN, not null, default true)
      - extension_notifications_enabled (BOOLEAN, not null, default true)
      - conflict_notifications_enabled (BOOLEAN, not null, default true)
      - calendar_event_reminders_enabled (BOOLEAN, not null, default true)
      - created_at (TIMESTAMPTZ, not null, default now())
      - updated_at (TIMESTAMPTZ, not null, default now())
  - reminder_rules:
      - id (UUID primary key)
      - profile_id (UUID FK to research_profiles.id ON DELETE CASCADE)
      - event_type (VARCHAR 50, nullable)
      - offset_amount (INTEGER, not null)
      - offset_unit (VARCHAR 20, not null, default 'DAYS')
      - delivery_channel (VARCHAR 20, not null, default 'IN_APP')
      - is_active (BOOLEAN, not null, default true)
      - created_at (TIMESTAMPTZ, not null, default now())
      - updated_at (TIMESTAMPTZ, not null, default now())
  - notifications:
      - id (UUID primary key)
      - profile_id (UUID FK to research_profiles.id ON DELETE CASCADE)
      - notification_type (VARCHAR 50, not null)
      - title (VARCHAR 255, not null)
      - body (TEXT, not null)
      - source_type (VARCHAR 50, not null, default 'OPPORTUNITY')
      - source_id (UUID, nullable)
      - opportunity_id (UUID FK to opportunities.id ON DELETE CASCADE, nullable)
      - calendar_event_id (UUID FK to research_calendar_events.id ON DELETE CASCADE, nullable)
      - submission_id (UUID FK to research_submissions.id ON DELETE CASCADE, nullable)
      - deadline_type (VARCHAR 50, nullable)
      - scheduled_for (TIMESTAMPTZ, not null)
      - delivered_at (TIMESTAMPTZ, nullable)
      - read_at (TIMESTAMPTZ, nullable)
      - delivery_status (VARCHAR 20, not null, default 'PENDING')
      - delivery_channel (VARCHAR 20, not null, default 'IN_APP')
      - deduplication_key (VARCHAR 500, not null, unique)
      - metadata_json (JSONB, not null, default '{}')
      - created_at (TIMESTAMPTZ, not null, default now())
      - updated_at (TIMESTAMPTZ, not null, default now())
  - notification_delivery_attempts:
      - id (UUID primary key)
      - notification_id (UUID FK to notifications.id ON DELETE CASCADE)
      - channel (VARCHAR 20, not null)
      - attempt_number (INTEGER, not null, default 1)
      - status (VARCHAR 20, not null)
      - attempted_at (TIMESTAMPTZ, not null, default now())
      - provider_reference (VARCHAR 255, nullable)
      - error_message (TEXT, nullable)

Revision ID: 0015_phase4_5_deadline_reminders_notifications
Revises:     0014_phase4_4_research_calendar
Create Date: 2026-09-19 13:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0015_phase4_5_deadline_reminders_notifications"
down_revision: Union[str, None] = "0014_phase4_4_research_calendar"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create researcher_notification_preferences
    op.create_table(
        "researcher_notification_preferences",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("research_profiles.id", ondelete="CASCADE"),
            unique=True,
            nullable=False,
            comment="Associated researcher profile ID",
        ),
        sa.Column(
            "email_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
            comment="Whether email notifications are enabled",
        ),
        sa.Column(
            "in_app_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
            comment="Whether in-app notification center alerts are enabled",
        ),
        sa.Column(
            "deadline_reminders_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
            comment="Whether advance deadline reminder alerts are enabled",
        ),
        sa.Column(
            "extension_notifications_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
            comment="Whether notifications for deadline extensions are enabled",
        ),
        sa.Column(
            "conflict_notifications_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
            comment="Whether notifications for unresolved deadline conflicts are enabled",
        ),
        sa.Column(
            "calendar_event_reminders_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
            comment="Whether reminders for user-created calendar planning events are enabled",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_notification_preferences_profile",
        "researcher_notification_preferences",
        ["profile_id"],
    )

    # 2. Create reminder_rules
    op.create_table(
        "reminder_rules",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("research_profiles.id", ondelete="CASCADE"),
            nullable=False,
            comment="Associated researcher profile ID",
        ),
        sa.Column(
            "event_type",
            sa.String(50),
            nullable=True,
            comment="Target milestone type or None for all milestones",
        ),
        sa.Column(
            "offset_amount",
            sa.Integer(),
            nullable=False,
            comment="Offset duration amount (e.g. 14, 7, 3, 24)",
        ),
        sa.Column(
            "offset_unit",
            sa.String(20),
            nullable=False,
            server_default="DAYS",
            comment="Unit of offset: DAYS, HOURS, MINUTES",
        ),
        sa.Column(
            "delivery_channel",
            sa.String(20),
            nullable=False,
            server_default="IN_APP",
            comment="Delivery channel: IN_APP, EMAIL, PUSH",
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
            comment="Whether this rule is actively evaluated",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "offset_unit IN ('DAYS', 'HOURS', 'MINUTES')",
            name="chk_reminder_rules_offset_unit",
        ),
        sa.CheckConstraint(
            "delivery_channel IN ('IN_APP', 'EMAIL', 'PUSH')",
            name="chk_reminder_rules_channel",
        ),
        sa.CheckConstraint(
            "offset_amount > 0",
            name="chk_reminder_rules_positive_offset",
        ),
        sa.UniqueConstraint(
            "profile_id",
            "event_type",
            "offset_amount",
            "offset_unit",
            "delivery_channel",
            name="uq_reminder_rules_profile_type_offset_channel",
        ),
    )
    op.create_index(
        "idx_reminder_rules_profile_active",
        "reminder_rules",
        ["profile_id", "is_active"],
    )

    # 3. Create notifications
    op.create_table(
        "notifications",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("research_profiles.id", ondelete="CASCADE"),
            nullable=False,
            comment="Recipient researcher profile ID",
        ),
        sa.Column(
            "notification_type",
            sa.String(50),
            nullable=False,
            comment="Type of notification",
        ),
        sa.Column(
            "title",
            sa.String(255),
            nullable=False,
            comment="Notification headline/title",
        ),
        sa.Column(
            "body",
            sa.Text(),
            nullable=False,
            comment="Notification message body / content",
        ),
        sa.Column(
            "source_type",
            sa.String(50),
            nullable=False,
            server_default="OPPORTUNITY",
            comment="Source entity type: OPPORTUNITY, CALENDAR_EVENT, SUBMISSION, SYSTEM",
        ),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Primary entity ID corresponding to source_type",
        ),
        sa.Column(
            "opportunity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("opportunities.id", ondelete="CASCADE"),
            nullable=True,
            comment="Associated opportunity ID if applicable",
        ),
        sa.Column(
            "calendar_event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("research_calendar_events.id", ondelete="CASCADE"),
            nullable=True,
            comment="Associated calendar event ID if applicable",
        ),
        sa.Column(
            "submission_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("research_submissions.id", ondelete="CASCADE"),
            nullable=True,
            comment="Associated research submission ID if applicable",
        ),
        sa.Column(
            "deadline_type",
            sa.String(50),
            nullable=True,
            comment="Canonical deadline milestone type (e.g. SUBMISSION, ABSTRACT)",
        ),
        sa.Column(
            "scheduled_for",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="Target instant when this notification was scheduled for delivery",
        ),
        sa.Column(
            "delivered_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Instant when notification was successfully delivered",
        ),
        sa.Column(
            "read_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Instant when researcher marked notification as read",
        ),
        sa.Column(
            "delivery_status",
            sa.String(20),
            nullable=False,
            server_default="PENDING",
            comment="Delivery lifecycle status",
        ),
        sa.Column(
            "delivery_channel",
            sa.String(20),
            nullable=False,
            server_default="IN_APP",
            comment="Delivery channel",
        ),
        sa.Column(
            "deduplication_key",
            sa.String(500),
            nullable=False,
            unique=True,
            comment="Deterministic hash preventing duplicate generation",
        ),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
            comment="Contextual metadata, opportunity title, venue, timezone, revisions",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "notification_type IN ('DEADLINE_UPCOMING', 'DEADLINE_TODAY', 'DEADLINE_EXTENDED', 'DEADLINE_MOVED_EARLIER', 'DEADLINE_CONFLICT', 'CALENDAR_EVENT_UPCOMING', 'SUBMISSION_STATUS_CHANGE', 'SYSTEM')",
            name="chk_notifications_type",
        ),
        sa.CheckConstraint(
            "delivery_status IN ('PENDING', 'DELIVERED', 'FAILED', 'CANCELLED', 'SKIPPED')",
            name="chk_notifications_status",
        ),
        sa.CheckConstraint(
            "delivery_channel IN ('IN_APP', 'EMAIL', 'PUSH')",
            name="chk_notifications_channel",
        ),
    )
    op.create_index(
        "idx_notifications_profile_status",
        "notifications",
        ["profile_id", "delivery_status"],
    )
    op.create_index(
        "idx_notifications_profile_read",
        "notifications",
        ["profile_id", "read_at"],
    )
    op.create_index(
        "idx_notifications_scheduled_status",
        "notifications",
        ["scheduled_for", "delivery_status"],
    )
    op.create_index(
        "idx_notifications_opp",
        "notifications",
        ["opportunity_id"],
    )
    op.create_index(
        "idx_notifications_cal_event",
        "notifications",
        ["calendar_event_id"],
    )

    # 4. Create notification_delivery_attempts
    op.create_table(
        "notification_delivery_attempts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "notification_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("notifications.id", ondelete="CASCADE"),
            nullable=False,
            comment="Associated notification ID",
        ),
        sa.Column(
            "channel",
            sa.String(20),
            nullable=False,
            comment="Delivery channel attempted",
        ),
        sa.Column(
            "attempt_number",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
            comment="Sequential attempt number",
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            comment="Result of attempt: SUCCESS, FAILED, RETRYING",
        ),
        sa.Column(
            "attempted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "provider_reference",
            sa.String(255),
            nullable=True,
            comment="Provider message ID or dispatch reference",
        ),
        sa.Column(
            "error_message",
            sa.Text(),
            nullable=True,
            comment="Diagnostic error message if attempt failed",
        ),
    )
    op.create_index(
        "idx_delivery_attempts_notif",
        "notification_delivery_attempts",
        ["notification_id"],
    )


def downgrade() -> None:
    op.drop_table("notification_delivery_attempts")
    op.drop_table("notifications")
    op.drop_table("reminder_rules")
    op.drop_table("researcher_notification_preferences")
