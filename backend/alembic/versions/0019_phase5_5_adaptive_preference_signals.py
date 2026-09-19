"""Phase 5.5 — Adaptive Preference Signal Aggregation & Personalization Bridge

Creates adaptive_preference_signals table:
  - id (UUID, primary key)
  - profile_id (UUID, foreign key to research_profiles.id, ondelete CASCADE)
  - dimension (VARCHAR 50, not null)
  - signal_value (VARCHAR 255, not null)
  - positive_evidence_count (INTEGER, not null, default 0)
  - negative_evidence_count (INTEGER, not null, default 0)
  - total_evidence_count (INTEGER, not null, default 0)
  - decay_adjusted_positive_weight (FLOAT, not null, default 0.0)
  - decay_adjusted_negative_weight (FLOAT, not null, default 0.0)
  - weighted_signal_strength (FLOAT, not null, default 0.0)
  - confidence (FLOAT, not null, default 0.0)
  - evidence_state (VARCHAR 50, not null, default 'INSUFFICIENT_EVIDENCE')
  - evidence_window_days (FLOAT, not null, default 180.0)
  - latest_evidence_timestamp (TIMESTAMP WITH TIME ZONE, nullable)
  - algorithm_version (VARCHAR 50, not null, default '5.5.1')
  - deterministic_explanation (TEXT, not null)
  - created_at (TIMESTAMP WITH TIME ZONE, not null, default now())
  - updated_at (TIMESTAMP WITH TIME ZONE, not null, default now())
  - Unique constraint on (profile_id, dimension, signal_value)
  - Indexes on profile_id + dimension, profile_id + evidence_state, and updated_at

Revision ID: 0019_phase5_5_adaptive_preference_signals
Revises:     0018_phase5_4_researcher_interactions
Create Date: 2026-09-19 23:45:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = "0019_phase5_5_adaptive_preference_signals"
down_revision: Union[str, None] = "0018_phase5_4_researcher_interactions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create adaptive_preference_signals table
    op.create_table(
        "adaptive_preference_signals",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "profile_id",
            UUID(as_uuid=True),
            sa.ForeignKey("research_profiles.id", ondelete="CASCADE"),
            nullable=False,
            comment="Associated ResearchProfileModel ID",
        ),
        sa.Column(
            "dimension",
            sa.String(50),
            nullable=False,
            comment="Attribute dimension (OPPORTUNITY_TYPE, RESEARCH_TOPIC, DELIVERY_MODE, LOCATION, PUBLISHER)",
        ),
        sa.Column(
            "signal_value",
            sa.String(255),
            nullable=False,
            comment="Attribute value for this signal",
        ),
        sa.Column(
            "positive_evidence_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Count of positive interactions",
        ),
        sa.Column(
            "negative_evidence_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Count of negative interactions",
        ),
        sa.Column(
            "total_evidence_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Sum of positive and negative interactions",
        ),
        sa.Column(
            "decay_adjusted_positive_weight",
            sa.Float(),
            nullable=False,
            server_default="0.0",
            comment="Exponential decay-adjusted sum of positive interaction weights",
        ),
        sa.Column(
            "decay_adjusted_negative_weight",
            sa.Float(),
            nullable=False,
            server_default="0.0",
            comment="Exponential decay-adjusted sum of negative interaction weights",
        ),
        sa.Column(
            "weighted_signal_strength",
            sa.Float(),
            nullable=False,
            server_default="0.0",
            comment="Bounded net signal strength in [-1.0, 1.0]",
        ),
        sa.Column(
            "confidence",
            sa.Float(),
            nullable=False,
            server_default="0.0",
            comment="Confidence metric in [0.0, 1.0]",
        ),
        sa.Column(
            "evidence_state",
            sa.String(50),
            nullable=False,
            server_default="INSUFFICIENT_EVIDENCE",
            comment="State: INSUFFICIENT_EVIDENCE, EMERGING, ESTABLISHED, STRONG",
        ),
        sa.Column(
            "evidence_window_days",
            sa.Float(),
            nullable=False,
            server_default="180.0",
            comment="Observation window horizon in days",
        ),
        sa.Column(
            "latest_evidence_timestamp",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp of latest interaction contributing to this signal",
        ),
        sa.Column(
            "algorithm_version",
            sa.String(50),
            nullable=False,
            server_default="5.5.1",
            comment="Aggregation algorithm and parameter version",
        ),
        sa.Column(
            "deterministic_explanation",
            sa.Text(),
            nullable=False,
            comment="Explainable natural language description of evidence basis",
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
        ),
        sa.UniqueConstraint(
            "profile_id",
            "dimension",
            "signal_value",
            name="uq_adaptive_signals_profile_dim_val",
        ),
    )

    # 2. Composite indexes
    op.create_index(
        "idx_adaptive_signals_profile_dim",
        "adaptive_preference_signals",
        ["profile_id", "dimension"],
    )
    op.create_index(
        "idx_adaptive_signals_profile_state",
        "adaptive_preference_signals",
        ["profile_id", "evidence_state"],
    )
    op.create_index(
        "idx_adaptive_signals_updated_at",
        "adaptive_preference_signals",
        ["updated_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_adaptive_signals_updated_at", table_name="adaptive_preference_signals")
    op.drop_index("idx_adaptive_signals_profile_state", table_name="adaptive_preference_signals")
    op.drop_index("idx_adaptive_signals_profile_dim", table_name="adaptive_preference_signals")
    op.drop_table("adaptive_preference_signals")
