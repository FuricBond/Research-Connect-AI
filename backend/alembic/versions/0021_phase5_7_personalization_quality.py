"""Phase 5.7 — Personalization Evaluation, Contextual Adaptation & Recommendation Quality Loop

Creates:
  1. personalization_quality_evaluations table:
     - id (UUID, primary key)
     - profile_id (UUID, foreign key to research_profiles.id, ondelete CASCADE)
     - evaluation_window_days (FLOAT, not null, default 30.0)
     - evaluation_timestamp (TIMESTAMP WITH TIME ZONE, not null)
     - total_recommendations_evaluated (INTEGER, not null, default 0)
     - total_attributed_interactions (INTEGER, not null, default 0)
     - positive_outcome_count (INTEGER, not null, default 0)
     - negative_outcome_count (INTEGER, not null, default 0)
     - neutral_outcome_count (INTEGER, not null, default 0)
     - engagement_rate (FLOAT, nullable)
     - positive_feedback_rate (FLOAT, nullable)
     - negative_feedback_rate (FLOAT, nullable)
     - observed_personalization_lift (FLOAT, nullable)
     - calibration_agreement_rate (FLOAT, nullable)
     - recommendation_diversity_score (FLOAT, nullable)
     - novelty_rate (FLOAT, nullable)
     - repeated_exposure_ratio (FLOAT, nullable)
     - confidence (FLOAT, not null, default 0.0)
     - evaluation_state (VARCHAR 50, not null, default 'INSUFFICIENT_DATA')
     - algorithm_version (VARCHAR 50, not null, default '5.7.1')
     - deterministic_explanation (TEXT, not null)
     - quality_metrics_breakdown (JSONB, nullable)
     - created_at (TIMESTAMP WITH TIME ZONE, not null, default now())
     - updated_at (TIMESTAMP WITH TIME ZONE, not null, default now())
     - Unique constraint on (profile_id, algorithm_version)
     - Indexes on profile_id + evaluation_state, updated_at

  2. personalization_contextual_adaptations table:
     - id (UUID, primary key)
     - profile_id (UUID, foreign key to research_profiles.id, ondelete CASCADE)
     - signal_id (UUID, foreign key to adaptive_preference_signals.id, ondelete SET NULL, nullable)
     - signal_dimension (VARCHAR 50, not null)
     - signal_value (VARCHAR 255, not null)
     - context_type (VARCHAR 50, not null)
     - context_value (VARCHAR 255, not null)
     - recommendations_count (INTEGER, not null, default 0)
     - positive_outcome_count (INTEGER, not null, default 0)
     - negative_outcome_count (INTEGER, not null, default 0)
     - context_engagement_rate (FLOAT, nullable)
     - contextual_lift (FLOAT, nullable)
     - contextual_modifier (FLOAT, not null, default 0.0)
     - confidence (FLOAT, not null, default 0.0)
     - adaptation_state (VARCHAR 50, not null, default 'INSUFFICIENT_DATA')
     - fallback_level (VARCHAR 50, not null, default 'EXACT_CONTEXT')
     - deterministic_explanation (TEXT, not null)
     - algorithm_version (VARCHAR 50, not null, default '5.7.1')
     - created_at (TIMESTAMP WITH TIME ZONE, not null, default now())
     - updated_at (TIMESTAMP WITH TIME ZONE, not null, default now())
     - Unique constraint on (profile_id, signal_dimension, signal_value, context_type, context_value)
     - Indexes on profile_id + signal_dimension + signal_value, profile_id + context_type + context_value, updated_at

Revision ID: 0021_phase5_7_personalization_quality
Revises:     0020_phase5_6_personalization_calibration
Create Date: 2026-09-20 20:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


# revision identifiers, used by Alembic.
revision: str = "0021_phase5_7_personalization_quality"
down_revision: Union[str, None] = "0020_phase5_6_personalization_calibration"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create personalization_quality_evaluations table
    op.create_table(
        "personalization_quality_evaluations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "profile_id",
            UUID(as_uuid=True),
            sa.ForeignKey("research_profiles.id", ondelete="CASCADE"),
            nullable=False,
            comment="Associated ResearchProfileModel ID",
        ),
        sa.Column(
            "evaluation_window_days",
            sa.Float(),
            nullable=False,
            server_default="30.0",
            comment="Evaluation window horizon in days",
        ),
        sa.Column(
            "evaluation_timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="Reference timestamp when quality evaluation was performed",
        ),
        sa.Column(
            "total_recommendations_evaluated",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Count of distinct recommended opportunities evaluated in the window",
        ),
        sa.Column(
            "total_attributed_interactions",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Count of interactions attributed to recommendations in the window",
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
            "engagement_rate",
            sa.Float(),
            nullable=True,
            comment="Engaged recommendations / eligible exposed recommendations",
        ),
        sa.Column(
            "positive_feedback_rate",
            sa.Float(),
            nullable=True,
            comment="Positive outcomes / total attributed interactions",
        ),
        sa.Column(
            "negative_feedback_rate",
            sa.Float(),
            nullable=True,
            comment="Negative outcomes / total attributed interactions",
        ),
        sa.Column(
            "observed_personalization_lift",
            sa.Float(),
            nullable=True,
            comment="Observed difference in positive engagement between personalized and baseline recommendations",
        ),
        sa.Column(
            "calibration_agreement_rate",
            sa.Float(),
            nullable=True,
            comment="Proportion of cases where calibration direction matched subsequent feedback",
        ),
        sa.Column(
            "recommendation_diversity_score",
            sa.Float(),
            nullable=True,
            comment="Normalized recommendation diversity across opportunity types and domains",
        ),
        sa.Column(
            "novelty_rate",
            sa.Float(),
            nullable=True,
            comment="Proportion of newly surfaced opportunities vs previously seen/interacted ones",
        ),
        sa.Column(
            "repeated_exposure_ratio",
            sa.Float(),
            nullable=True,
            comment="Ratio of opportunities presented multiple times in the evaluation window",
        ),
        sa.Column(
            "confidence",
            sa.Float(),
            nullable=False,
            server_default="0.0",
            comment="Evaluation confidence in [0.0, 1.0]",
        ),
        sa.Column(
            "evaluation_state",
            sa.String(50),
            nullable=False,
            server_default="INSUFFICIENT_DATA",
            comment="Evaluation state: INSUFFICIENT_DATA, EARLY_SIGNAL, EVALUATING, STABLE, POSITIVE, NEGATIVE, MIXED",
        ),
        sa.Column(
            "algorithm_version",
            sa.String(50),
            nullable=False,
            server_default="5.7.1",
            comment="Evaluation algorithm and configuration version",
        ),
        sa.Column(
            "deterministic_explanation",
            sa.Text(),
            nullable=False,
            comment="Explainable natural language description of personalization quality",
        ),
        sa.Column(
            "quality_metrics_breakdown",
            JSONB,
            nullable=True,
            comment="Detailed JSON metrics breakdown by context, dimension, and signal",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
            comment="Evaluation creation timestamp",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
            comment="Evaluation last update timestamp",
        ),
        sa.UniqueConstraint(
            "profile_id",
            "algorithm_version",
            name="uq_personalization_quality_profile_version",
        ),
    )

    op.create_index(
        "idx_quality_eval_profile_state",
        "personalization_quality_evaluations",
        ["profile_id", "evaluation_state"],
    )
    op.create_index(
        "idx_quality_eval_updated_at",
        "personalization_quality_evaluations",
        ["updated_at"],
    )

    # 2. Create personalization_contextual_adaptations table
    op.create_table(
        "personalization_contextual_adaptations",
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
            "signal_dimension",
            sa.String(50),
            nullable=False,
            comment="Signal dimension (e.g. OPPORTUNITY_TYPE, RESEARCH_TOPIC)",
        ),
        sa.Column(
            "signal_value",
            sa.String(255),
            nullable=False,
            comment="Signal value (e.g. 'CONFERENCE', 'Artificial Intelligence')",
        ),
        sa.Column(
            "context_type",
            sa.String(50),
            nullable=False,
            comment="Context dimension (e.g. DEADLINE_HORIZON, DELIVERY_MODE, RISK_TIER, OPPORTUNITY_TYPE)",
        ),
        sa.Column(
            "context_value",
            sa.String(255),
            nullable=False,
            comment="Context value (e.g. 'NEAR', 'HYBRID', 'LOW')",
        ),
        sa.Column(
            "recommendations_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Count of recommendations presented in this specific context",
        ),
        sa.Column(
            "positive_outcome_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Positive outcomes in this specific context",
        ),
        sa.Column(
            "negative_outcome_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Negative outcomes in this specific context",
        ),
        sa.Column(
            "context_engagement_rate",
            sa.Float(),
            nullable=True,
            comment="Engagement rate observed in this specific context",
        ),
        sa.Column(
            "contextual_lift",
            sa.Float(),
            nullable=True,
            comment="Observed personalization lift in this specific context vs baseline",
        ),
        sa.Column(
            "contextual_modifier",
            sa.Float(),
            nullable=False,
            server_default="0.0",
            comment="Bounded contextual adaptation modifier in [-0.03, +0.03]",
        ),
        sa.Column(
            "confidence",
            sa.Float(),
            nullable=False,
            server_default="0.0",
            comment="Confidence metric for this context slice",
        ),
        sa.Column(
            "adaptation_state",
            sa.String(50),
            nullable=False,
            server_default="INSUFFICIENT_DATA",
            comment="State: INSUFFICIENT_DATA, EARLY_SIGNAL, EVALUATING, STABLE, POSITIVE, NEGATIVE, MIXED",
        ),
        sa.Column(
            "fallback_level",
            sa.String(50),
            nullable=False,
            server_default="EXACT_CONTEXT",
            comment="Fallback level: EXACT_CONTEXT, BROAD_CONTEXT, GLOBAL_SIGNAL, NEUTRAL",
        ),
        sa.Column(
            "deterministic_explanation",
            sa.Text(),
            nullable=False,
            comment="Explainable natural language description of contextual adaptation",
        ),
        sa.Column(
            "algorithm_version",
            sa.String(50),
            nullable=False,
            server_default="5.7.1",
            comment="Contextual adaptation algorithm and version",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
            comment="Adaptation creation timestamp",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
            comment="Adaptation last update timestamp",
        ),
        sa.UniqueConstraint(
            "profile_id",
            "signal_dimension",
            "signal_value",
            "context_type",
            "context_value",
            name="uq_contextual_adaptations_profile_signal_context",
        ),
    )

    op.create_index(
        "idx_context_adapt_profile_signal",
        "personalization_contextual_adaptations",
        ["profile_id", "signal_dimension", "signal_value"],
    )
    op.create_index(
        "idx_context_adapt_context",
        "personalization_contextual_adaptations",
        ["profile_id", "context_type", "context_value"],
    )
    op.create_index(
        "idx_context_adapt_updated_at",
        "personalization_contextual_adaptations",
        ["updated_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_context_adapt_updated_at", table_name="personalization_contextual_adaptations")
    op.drop_index("idx_context_adapt_context", table_name="personalization_contextual_adaptations")
    op.drop_index("idx_context_adapt_profile_signal", table_name="personalization_contextual_adaptations")
    op.drop_table("personalization_contextual_adaptations")

    op.drop_index("idx_quality_eval_updated_at", table_name="personalization_quality_evaluations")
    op.drop_index("idx_quality_eval_profile_state", table_name="personalization_quality_evaluations")
    op.drop_table("personalization_quality_evaluations")
