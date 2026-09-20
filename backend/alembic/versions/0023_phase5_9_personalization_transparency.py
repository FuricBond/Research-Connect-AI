"""Phase 5.9 — Personalization Transparency, Researcher Controls & Explanation Layer

Creates:
  1. researcher_personalization_settings table:
     - id (UUID, primary key)
     - profile_id (UUID, foreign key to research_profiles.id, ondelete CASCADE, unique)
     - personalization_enabled (BOOLEAN, not null, default true)
     - adaptive_signals_enabled (BOOLEAN, not null, default true)
     - feedback_learning_enabled (BOOLEAN, not null, default true)
     - personalization_state_version (INTEGER, not null, default 1)
     - created_at (TIMESTAMP WITH TIME ZONE, not null, default now())
     - updated_at (TIMESTAMP WITH TIME ZONE, not null, default now())
     - Index on profile_id (unique)

  2. personalization_control_events table:
     - id (UUID, primary key)
     - profile_id (UUID, foreign key to research_profiles.id, ondelete CASCADE)
     - event_type (VARCHAR 50, not null)
     - previous_state (JSONB, not null, default '{}')
     - new_state (JSONB, not null, default '{}')
     - trigger_reason (TEXT, not null)
     - algorithm_version (VARCHAR 50, not null, default '5.9.1')
     - created_at (TIMESTAMP WITH TIME ZONE, not null, default now())
     - Indexes on profile_id + created_at, profile_id + event_type

Revision ID: 0023_phase5_9_personalization_transparency
Revises:     0022_phase5_8_personalization_governance
Create Date: 2026-09-20 22:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


# revision identifiers, used by Alembic.
revision: str = "0023_phase5_9_personalization_transparency"
down_revision: Union[str, None] = "0022_phase5_8_personalization_governance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create researcher_personalization_settings table
    op.create_table(
        "researcher_personalization_settings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "profile_id",
            UUID(as_uuid=True),
            sa.ForeignKey("research_profiles.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
            index=True,
        ),
        sa.Column("personalization_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("adaptive_signals_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("feedback_learning_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("personalization_state_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_index(
        "idx_pers_settings_profile_id",
        "researcher_personalization_settings",
        ["profile_id"],
        unique=True,
    )

    # 2. Create personalization_control_events table
    op.create_table(
        "personalization_control_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "profile_id",
            UUID(as_uuid=True),
            sa.ForeignKey("research_profiles.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("previous_state", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("new_state", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("trigger_reason", sa.Text(), nullable=False),
        sa.Column("algorithm_version", sa.String(50), nullable=False, server_default="5.9.1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_index(
        "idx_pers_control_events_profile_created",
        "personalization_control_events",
        ["profile_id", "created_at"],
    )
    op.create_index(
        "idx_pers_control_events_profile_type",
        "personalization_control_events",
        ["profile_id", "event_type"],
    )


def downgrade() -> None:
    op.drop_index("idx_pers_control_events_profile_type", table_name="personalization_control_events")
    op.drop_index("idx_pers_control_events_profile_created", table_name="personalization_control_events")
    op.drop_table("personalization_control_events")

    op.drop_index("idx_pers_settings_profile_id", table_name="researcher_personalization_settings")
    op.drop_table("researcher_personalization_settings")
