"""Phase 5.8 — Personalization Governance, Drift Detection & Adaptation Safety

Creates:
  1. personalization_drift_evaluations table:
     - id (UUID, primary key)
     - profile_id (UUID, foreign key to research_profiles.id, ondelete CASCADE)
     - evaluation_timestamp (TIMESTAMP WITH TIME ZONE, not null)
     - historical_window_days (FLOAT, not null, default 60.0)
     - recent_window_days (FLOAT, not null, default 14.0)
     - overall_health_state (VARCHAR 50, not null, default 'INSUFFICIENT_DATA')
     - governance_state (VARCHAR 50, not null, default 'HOLD')
     - adaptation_state (VARCHAR 50, not null, default 'BOUNDED')
     - signal_freshness (VARCHAR 50, not null, default 'INSUFFICIENT_DATA')
     - evidence_sufficiency (VARCHAR 50, not null, default 'INSUFFICIENT')
     - quality_stability (VARCHAR 50, not null, default 'INSUFFICIENT_DATA')
     - context_stability (VARCHAR 50, not null, default 'INSUFFICIENT_DATA')
     - preference_alignment (VARCHAR 50, not null, default 'NEUTRAL')
     - recommendation_diversity (VARCHAR 50, not null, default 'INSUFFICIENT_DATA')
     - drifting_signals_count (INTEGER, not null, default 0)
     - stale_signals_count (INTEGER, not null, default 0)
     - active_signals_count (INTEGER, not null, default 0)
     - drift_details (JSONB, not null, default '[]')
     - health_summary (TEXT, not null)
     - governance_explanation (TEXT, not null)
     - algorithm_version (VARCHAR 50, not null, default '5.8.1')
     - created_at (TIMESTAMP WITH TIME ZONE, not null, default now())
     - updated_at (TIMESTAMP WITH TIME ZONE, not null, default now())
     - Unique constraint on (profile_id, algorithm_version)
     - Indexes on profile_id + overall_health_state, profile_id + governance_state, updated_at

  2. personalization_governance_events table:
     - id (UUID, primary key)
     - profile_id (UUID, foreign key to research_profiles.id, ondelete CASCADE)
     - event_type (VARCHAR 50, not null)
     - previous_state (VARCHAR 50, nullable)
     - new_state (VARCHAR 50, not null)
     - reason (TEXT, not null)
     - affected_dimension (VARCHAR 50, nullable)
     - affected_signal_value (VARCHAR 255, nullable)
     - evidence_count (INTEGER, not null, default 0)
     - reference_time (TIMESTAMP WITH TIME ZONE, not null)
     - algorithm_version (VARCHAR 50, not null, default '5.8.1')
     - created_at (TIMESTAMP WITH TIME ZONE, not null, default now())
     - Indexes on profile_id + created_at, profile_id + event_type

Revision ID: 0022_phase5_8_personalization_governance
Revises:     0021_phase5_7_personalization_quality
Create Date: 2026-09-20 20:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


# revision identifiers, used by Alembic.
revision: str = "0022_phase5_8_personalization_governance"
down_revision: Union[str, None] = "0021_phase5_7_personalization_quality"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create personalization_drift_evaluations table
    op.create_table(
        "personalization_drift_evaluations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "profile_id",
            UUID(as_uuid=True),
            sa.ForeignKey("research_profiles.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("evaluation_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("historical_window_days", sa.Float(), nullable=False, server_default="60.0"),
        sa.Column("recent_window_days", sa.Float(), nullable=False, server_default="14.0"),
        sa.Column("overall_health_state", sa.String(50), nullable=False, server_default="INSUFFICIENT_DATA"),
        sa.Column("governance_state", sa.String(50), nullable=False, server_default="HOLD"),
        sa.Column("adaptation_state", sa.String(50), nullable=False, server_default="BOUNDED"),
        sa.Column("signal_freshness", sa.String(50), nullable=False, server_default="INSUFFICIENT_DATA"),
        sa.Column("evidence_sufficiency", sa.String(50), nullable=False, server_default="INSUFFICIENT"),
        sa.Column("quality_stability", sa.String(50), nullable=False, server_default="INSUFFICIENT_DATA"),
        sa.Column("context_stability", sa.String(50), nullable=False, server_default="INSUFFICIENT_DATA"),
        sa.Column("preference_alignment", sa.String(50), nullable=False, server_default="NEUTRAL"),
        sa.Column("recommendation_diversity", sa.String(50), nullable=False, server_default="INSUFFICIENT_DATA"),
        sa.Column("drifting_signals_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stale_signals_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active_signals_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("drift_details", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("health_summary", sa.Text(), nullable=False),
        sa.Column("governance_explanation", sa.Text(), nullable=False),
        sa.Column("algorithm_version", sa.String(50), nullable=False, server_default="5.8.1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("profile_id", "algorithm_version", name="uq_personalization_drift_profile_version"),
    )

    op.create_index(
        "idx_drift_eval_profile_health",
        "personalization_drift_evaluations",
        ["profile_id", "overall_health_state"],
    )
    op.create_index(
        "idx_drift_eval_profile_gov",
        "personalization_drift_evaluations",
        ["profile_id", "governance_state"],
    )
    op.create_index(
        "idx_drift_eval_updated_at",
        "personalization_drift_evaluations",
        ["updated_at"],
    )

    # 2. Create personalization_governance_events table
    op.create_table(
        "personalization_governance_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "profile_id",
            UUID(as_uuid=True),
            sa.ForeignKey("research_profiles.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("previous_state", sa.String(50), nullable=True),
        sa.Column("new_state", sa.String(50), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("affected_dimension", sa.String(50), nullable=True),
        sa.Column("affected_signal_value", sa.String(255), nullable=True),
        sa.Column("evidence_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reference_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("algorithm_version", sa.String(50), nullable=False, server_default="5.8.1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_index(
        "idx_gov_events_profile_created",
        "personalization_governance_events",
        ["profile_id", "created_at"],
    )
    op.create_index(
        "idx_gov_events_profile_type",
        "personalization_governance_events",
        ["profile_id", "event_type"],
    )


def downgrade() -> None:
    op.drop_index("idx_gov_events_profile_type", table_name="personalization_governance_events")
    op.drop_index("idx_gov_events_profile_created", table_name="personalization_governance_events")
    op.drop_table("personalization_governance_events")

    op.drop_index("idx_drift_eval_updated_at", table_name="personalization_drift_evaluations")
    op.drop_index("idx_drift_eval_profile_gov", table_name="personalization_drift_evaluations")
    op.drop_index("idx_drift_eval_profile_health", table_name="personalization_drift_evaluations")
    op.drop_table("personalization_drift_evaluations")
