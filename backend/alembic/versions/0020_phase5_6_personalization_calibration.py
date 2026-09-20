"""Phase 5.6 — Adaptive Personalization Calibration & Recommendation Feedback Loop

Creates:
  1. personalization_calibrations table:
     - id (UUID, primary key)
     - profile_id (UUID, foreign key to research_profiles.id, ondelete CASCADE)
     - signal_id (UUID, foreign key to adaptive_preference_signals.id, ondelete SET NULL, nullable)
     - dimension (VARCHAR 50, not null)
     - signal_value (VARCHAR 255, not null)
     - recommendations_influenced_count (INTEGER, not null, default 0)
     - positive_outcome_count (INTEGER, not null, default 0)
     - negative_outcome_count (INTEGER, not null, default 0)
     - neutral_outcome_count (INTEGER, not null, default 0)
     - accumulated_positive_weight (FLOAT, not null, default 0.0)
     - accumulated_negative_weight (FLOAT, not null, default 0.0)
     - net_calibration_modifier (FLOAT, not null, default 0.0)
     - calibration_confidence (FLOAT, not null, default 0.0)
     - calibration_state (VARCHAR 50, not null, default 'INSUFFICIENT_DATA')
     - algorithm_version (VARCHAR 50, not null, default '5.6.1')
     - deterministic_explanation (TEXT, not null)
     - latest_feedback_timestamp (TIMESTAMP WITH TIME ZONE, nullable)
     - created_at (TIMESTAMP WITH TIME ZONE, not null, default now())
     - updated_at (TIMESTAMP WITH TIME ZONE, not null, default now())
     - Unique constraint on (profile_id, dimension, signal_value)
     - Indexes on profile_id + dimension, profile_id + calibration_state, and updated_at

  2. recommendation_feedback_attributions table:
     - id (UUID, primary key)
     - profile_id (UUID, foreign key to research_profiles.id, ondelete CASCADE)
     - opportunity_id (UUID, foreign key to opportunities.id, ondelete CASCADE)
     - interaction_id (UUID, foreign key to researcher_interactions.id, ondelete SET NULL, nullable)
     - dimension (VARCHAR 50, not null)
     - signal_value (VARCHAR 255, not null)
     - personalization_contribution (FLOAT, not null, default 0.0)
     - interaction_type (VARCHAR 50, not null)
     - outcome_type (VARCHAR 50, not null)
     - attribution_confidence (VARCHAR 50, not null, default 'DIRECT')
     - attribution_weight (FLOAT, not null, default 1.0)
     - decay_adjusted_weight (FLOAT, not null, default 0.0)
     - recommendation_timestamp (TIMESTAMP WITH TIME ZONE, not null)
     - interaction_timestamp (TIMESTAMP WITH TIME ZONE, not null)
     - algorithm_version (VARCHAR 50, not null, default '5.6.1')
     - created_at (TIMESTAMP WITH TIME ZONE, not null, default now())
     - Indexes on profile_id + opportunity_id, profile_id + dimension + signal_value, interaction_timestamp

Revision ID: 0020_phase5_6_personalization_calibration
Revises:     0019_phase5_5_adaptive_preference_signals
Create Date: 2026-09-20 19:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = "0020_phase5_6_personalization_calibration"
down_revision: Union[str, None] = "0019_phase5_5_adaptive_preference_signals"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create personalization_calibrations table
    op.create_table(
        "personalization_calibrations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "profile_id",
            UUID(as_uuid=True),
            sa.ForeignKey("research_profiles.id", ondelete="CASCADE"),
            nullable=False,
            comment="Associated ResearchProfileModel ID",
        ),
        sa.Column(
            "signal_id",
            UUID(as_uuid=True),
            sa.ForeignKey("adaptive_preference_signals.id", ondelete="SET NULL"),
            nullable=True,
            comment="Associated AdaptivePreferenceSignalModel ID if present",
        ),
        sa.Column(
            "dimension",
            sa.String(50),
            nullable=False,
            comment="Attribute dimension for the calibrated signal",
        ),
        sa.Column(
            "signal_value",
            sa.String(255),
            nullable=False,
            comment="Attribute value for the calibrated signal",
        ),
        sa.Column(
            "recommendations_influenced_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Count of presented recommendations influenced by this signal",
        ),
        sa.Column(
            "positive_outcome_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Count of positive attributed outcomes",
        ),
        sa.Column(
            "negative_outcome_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Count of negative attributed outcomes",
        ),
        sa.Column(
            "neutral_outcome_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Count of neutral or unengaged attributed recommendations",
        ),
        sa.Column(
            "accumulated_positive_weight",
            sa.Float(),
            nullable=False,
            server_default="0.0",
            comment="Decay and confidence adjusted positive feedback weight",
        ),
        sa.Column(
            "accumulated_negative_weight",
            sa.Float(),
            nullable=False,
            server_default="0.0",
            comment="Decay and confidence adjusted negative feedback weight",
        ),
        sa.Column(
            "net_calibration_modifier",
            sa.Float(),
            nullable=False,
            server_default="0.0",
            comment="Bounded additive calibration modifier in [-0.05, +0.05]",
        ),
        sa.Column(
            "calibration_confidence",
            sa.Float(),
            nullable=False,
            server_default="0.0",
            comment="Confidence metric in [0.0, 1.0]",
        ),
        sa.Column(
            "calibration_state",
            sa.String(50),
            nullable=False,
            server_default="INSUFFICIENT_DATA",
            comment="State: INSUFFICIENT_DATA, EARLY_SIGNAL, CALIBRATING, STABLE, CONFLICTED",
        ),
        sa.Column(
            "algorithm_version",
            sa.String(50),
            nullable=False,
            server_default="5.6.1",
            comment="Calibration algorithm and parameter version",
        ),
        sa.Column(
            "deterministic_explanation",
            sa.Text(),
            nullable=False,
            comment="Explainable natural language description of calibration evidence",
        ),
        sa.Column(
            "latest_feedback_timestamp",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp of latest feedback event contributing to calibration",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "profile_id",
            "dimension",
            "signal_value",
            name="uq_personalization_calibrations_profile_dim_val",
        ),
    )
    op.create_index(
        "idx_calibrations_profile_dim",
        "personalization_calibrations",
        ["profile_id", "dimension"],
    )
    op.create_index(
        "idx_calibrations_profile_state",
        "personalization_calibrations",
        ["profile_id", "calibration_state"],
    )
    op.create_index(
        "idx_calibrations_updated_at",
        "personalization_calibrations",
        ["updated_at"],
    )

    # 2. Create recommendation_feedback_attributions table
    op.create_table(
        "recommendation_feedback_attributions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "profile_id",
            UUID(as_uuid=True),
            sa.ForeignKey("research_profiles.id", ondelete="CASCADE"),
            nullable=False,
            comment="Associated ResearchProfileModel ID",
        ),
        sa.Column(
            "opportunity_id",
            UUID(as_uuid=True),
            sa.ForeignKey("opportunities.id", ondelete="CASCADE"),
            nullable=False,
            comment="Associated OpportunityModel ID",
        ),
        sa.Column(
            "interaction_id",
            UUID(as_uuid=True),
            sa.ForeignKey("researcher_interactions.id", ondelete="SET NULL"),
            nullable=True,
            comment="Associated ResearcherInteractionModel ID if linked",
        ),
        sa.Column(
            "dimension",
            sa.String(50),
            nullable=False,
            comment="Signal dimension",
        ),
        sa.Column(
            "signal_value",
            sa.String(255),
            nullable=False,
            comment="Signal value for this attribution",
        ),
        sa.Column(
            "personalization_contribution",
            sa.Float(),
            nullable=False,
            server_default="0.0",
            comment="Personalization contribution of this signal at recommendation time",
        ),
        sa.Column(
            "interaction_type",
            sa.String(50),
            nullable=False,
            comment="Interaction type",
        ),
        sa.Column(
            "outcome_type",
            sa.String(50),
            nullable=False,
            comment="Outcome type",
        ),
        sa.Column(
            "attribution_confidence",
            sa.String(50),
            nullable=False,
            server_default="DIRECT",
            comment="Attribution tier: DIRECT, LIKELY, WEAK, UNATTRIBUTED",
        ),
        sa.Column(
            "attribution_weight",
            sa.Float(),
            nullable=False,
            server_default="1.0",
            comment="Attribution confidence multiplier in [0.0, 1.0]",
        ),
        sa.Column(
            "decay_adjusted_weight",
            sa.Float(),
            nullable=False,
            server_default="0.0",
            comment="Final weight combining outcome weight, attribution confidence, and temporal decay",
        ),
        sa.Column(
            "recommendation_timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="Timestamp when recommendation exposure occurred",
        ),
        sa.Column(
            "interaction_timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="Timestamp when subsequent interaction occurred",
        ),
        sa.Column(
            "algorithm_version",
            sa.String(50),
            nullable=False,
            server_default="5.6.1",
            comment="Attribution algorithm version",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_attributions_profile_opp",
        "recommendation_feedback_attributions",
        ["profile_id", "opportunity_id"],
    )
    op.create_index(
        "idx_attributions_profile_signal",
        "recommendation_feedback_attributions",
        ["profile_id", "dimension", "signal_value"],
    )
    op.create_index(
        "idx_attributions_interaction_time",
        "recommendation_feedback_attributions",
        ["interaction_timestamp"],
    )


def downgrade() -> None:
    op.drop_index("idx_attributions_interaction_time", table_name="recommendation_feedback_attributions")
    op.drop_index("idx_attributions_profile_signal", table_name="recommendation_feedback_attributions")
    op.drop_index("idx_attributions_profile_opp", table_name="recommendation_feedback_attributions")
    op.drop_table("recommendation_feedback_attributions")

    op.drop_index("idx_calibrations_updated_at", table_name="personalization_calibrations")
    op.drop_index("idx_calibrations_profile_state", table_name="personalization_calibrations")
    op.drop_index("idx_calibrations_profile_dim", table_name="personalization_calibrations")
    op.drop_table("personalization_calibrations")
