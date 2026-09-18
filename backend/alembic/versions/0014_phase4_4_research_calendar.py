"""Phase 4.4 — Research Calendar, Visual Deadline Planning & iCal Export

Creates research_calendars and research_calendar_events tables:
  - research_calendars:
      - id (UUID primary key)
      - user_id (UUID FK to users.id ON DELETE CASCADE)
      - profile_id (UUID FK to research_profiles.id ON DELETE CASCADE, nullable)
      - name (VARCHAR 255, not null, default 'Default Research Calendar')
      - description (TEXT, nullable)
      - timezone (VARCHAR 100, not null, default 'UTC')
      - is_default (BOOLEAN, not null, default true)
      - created_at (TIMESTAMPTZ, not null, default now())
      - updated_at (TIMESTAMPTZ, not null, default now())
  - research_calendar_events:
      - id (UUID primary key)
      - calendar_id (UUID FK to research_calendars.id ON DELETE CASCADE)
      - opportunity_id (UUID FK to opportunities.id ON DELETE CASCADE, nullable)
      - submission_id (UUID FK to research_submissions.id ON DELETE CASCADE, nullable)
      - title (VARCHAR 255, not null)
      - description (TEXT, nullable)
      - event_type (VARCHAR 50, not null, default 'RESEARCH_MILESTONE')
      - start_datetime (TIMESTAMPTZ, nullable)
      - end_datetime (TIMESTAMPTZ, nullable)
      - date_str (VARCHAR 50, nullable)
      - all_day (BOOLEAN, not null, default false)
      - timezone (VARCHAR 100, nullable)
      - is_canonical_projection (BOOLEAN, not null, default false)
      - provenance_metadata (JSONB, not null, default '{}')
      - status (VARCHAR 50, not null, default 'ACTIVE')
      - created_at (TIMESTAMPTZ, not null, default now())
      - updated_at (TIMESTAMPTZ, not null, default now())

Revision ID: 0014_phase4_4_research_calendar
Revises:     0013_phase4_3_submission_documents
Create Date: 2026-09-18 23:58:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0014_phase4_4_research_calendar"
down_revision: Union[str, None] = "0013_phase4_3_submission_documents"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create research_calendars table
    op.create_table(
        "research_calendars",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
            comment="Foreign key referencing owner user",
        ),
        sa.Column(
            "profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("research_profiles.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
            comment="Foreign key referencing canonical researcher profile",
        ),
        sa.Column(
            "name",
            sa.String(length=255),
            nullable=False,
            server_default="Default Research Calendar",
            comment="Calendar display name",
        ),
        sa.Column(
            "description",
            sa.Text(),
            nullable=True,
            comment="Optional calendar notes / description",
        ),
        sa.Column(
            "timezone",
            sa.String(length=100),
            nullable=False,
            server_default="UTC",
            comment="Preferred IANA display timezone",
        ),
        sa.Column(
            "is_default",
            sa.Boolean(),
            nullable=False,
            server_default="true",
            comment="Whether this is the user's primary/default research calendar",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )
    op.create_index(
        "idx_research_calendars_user",
        "research_calendars",
        ["user_id", "is_default"],
    )
    op.create_index(
        "idx_research_calendars_profile",
        "research_calendars",
        ["profile_id"],
    )

    # 2. Create research_calendar_events table
    op.create_table(
        "research_calendar_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "calendar_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("research_calendars.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
            comment="Foreign key referencing parent research calendar",
        ),
        sa.Column(
            "opportunity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("opportunities.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
            comment="Foreign key referencing opportunity if projected from canonical deadline",
        ),
        sa.Column(
            "submission_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("research_submissions.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
            comment="Foreign key referencing submission tracker if applicable",
        ),
        sa.Column(
            "title",
            sa.String(length=255),
            nullable=False,
            comment="Event title or display label",
        ),
        sa.Column(
            "description",
            sa.Text(),
            nullable=True,
            comment="Event description, notes, or instructions",
        ),
        sa.Column(
            "event_type",
            sa.String(length=50),
            nullable=False,
            server_default="RESEARCH_MILESTONE",
            comment="Event category: OPPORTUNITY_SUBMISSION, NOTIFICATION, etc.",
        ),
        sa.Column(
            "start_datetime",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Start timestamp with timezone if known",
        ),
        sa.Column(
            "end_datetime",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="End timestamp with timezone if applicable",
        ),
        sa.Column(
            "date_str",
            sa.String(length=50),
            nullable=True,
            comment="Date-only representation (e.g. '2026-08-20')",
        ),
        sa.Column(
            "all_day",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="Whether this event represents a full calendar day",
        ),
        sa.Column(
            "timezone",
            sa.String(length=100),
            nullable=True,
            comment="Original timezone string or null if unspecified",
        ),
        sa.Column(
            "is_canonical_projection",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="True if projected from Phase 2.7 canonical deadline intelligence",
        ),
        sa.Column(
            "provenance_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
            comment="Provenance trace: milestone type, authority, revisions, conflict state",
        ),
        sa.Column(
            "status",
            sa.String(length=50),
            nullable=False,
            server_default="ACTIVE",
            comment="Event lifecycle: ACTIVE, COMPLETED, CANCELLED, SUPERSEDED, CONFLICT",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.CheckConstraint(
            "event_type IN ('OPPORTUNITY_SUBMISSION', 'ABSTRACT_DEADLINE', 'NOTIFICATION', 'CAMERA_READY', 'REGISTRATION', 'EVENT_START', 'EVENT_END', 'RESEARCH_MILESTONE', 'CUSTOM')",
            name="chk_calendar_events_type",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'COMPLETED', 'CANCELLED', 'SUPERSEDED', 'CONFLICT')",
            name="chk_calendar_events_status",
        ),
    )
    op.create_index(
        "idx_calendar_events_calendar_start",
        "research_calendar_events",
        ["calendar_id", "start_datetime"],
    )
    op.create_index(
        "idx_calendar_events_calendar_type",
        "research_calendar_events",
        ["calendar_id", "event_type"],
    )
    op.create_index(
        "idx_calendar_events_opp",
        "research_calendar_events",
        ["calendar_id", "opportunity_id"],
    )
    op.create_index(
        "idx_calendar_events_submission",
        "research_calendar_events",
        ["calendar_id", "submission_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_calendar_events_submission", table_name="research_calendar_events")
    op.drop_index("idx_calendar_events_opp", table_name="research_calendar_events")
    op.drop_index("idx_calendar_events_calendar_type", table_name="research_calendar_events")
    op.drop_index("idx_calendar_events_calendar_start", table_name="research_calendar_events")
    op.drop_table("research_calendar_events")

    op.drop_index("idx_research_calendars_profile", table_name="research_calendars")
    op.drop_index("idx_research_calendars_user", table_name="research_calendars")
    op.drop_table("research_calendars")
