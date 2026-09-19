"""Phase 5.4 — Researcher Feedback & Interaction Signal Foundation

Creates researcher_interactions table:
  - id (UUID, primary key)
  - profile_id (UUID, foreign key to research_profiles.id, ondelete CASCADE)
  - opportunity_id (UUID, foreign key to opportunities.id, ondelete CASCADE)
  - interaction_type (VARCHAR 50, not null)
  - is_explicit_feedback (BOOLEAN, not null, default false)
  - source (VARCHAR 50, not null, default 'RECOMMENDATION')
  - client_event_id (VARCHAR 100, nullable, for idempotency)
  - metadata_payload (JSONB, not null, default '{}')
  - created_at (TIMESTAMP WITH TIME ZONE, not null, default now())
  - Check constraint on interaction_type
  - Composite indexes for efficient profile, opportunity, and chronological queries

Revision ID: 0018_phase5_4_researcher_interactions
Revises:     0017_phase5_1_researcher_preferences_foundation
Create Date: 2026-09-19 23:10:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


# revision identifiers, used by Alembic.
revision: str = "0018_phase5_4_researcher_interactions"
down_revision: Union[str, None] = "0017_phase5_1_researcher_preferences_foundation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create researcher_interactions table
    op.create_table(
        "researcher_interactions",
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
            "interaction_type",
            sa.String(50),
            nullable=False,
            comment="Interaction type (VIEWED, OPENED, SAVED, DISMISSED, HIDDEN, INTERESTED, NOT_INTERESTED, APPLIED, SHARED)",
        ),
        sa.Column(
            "is_explicit_feedback",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="True if explicit feedback, False if passive observation",
        ),
        sa.Column(
            "source",
            sa.String(50),
            nullable=False,
            server_default="RECOMMENDATION",
            comment="Context source (RECOMMENDATION, DISCOVERY, SEARCH, DIRECT, WORKSPACE)",
        ),
        sa.Column(
            "client_event_id",
            sa.String(100),
            nullable=True,
            comment="Client-supplied idempotency key / event identifier",
        ),
        sa.Column(
            "metadata_payload",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
            comment="Sanitized contextual metadata snapshot (rank position, session ID; no PII/credentials)",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment="Timestamp when interaction was recorded in UTC",
        ),
        sa.CheckConstraint(
            "interaction_type IN ('VIEWED', 'OPENED', 'SAVED', 'DISMISSED', 'HIDDEN', "
            "'INTERESTED', 'NOT_INTERESTED', 'APPLIED', 'SHARED')",
            name="chk_researcher_interaction_type",
        ),
    )

    # 2. Create composite indexes for high query performance
    op.create_index(
        "idx_researcher_interactions_profile_created",
        "researcher_interactions",
        ["profile_id", "created_at"],
    )
    op.create_index(
        "idx_researcher_interactions_profile_opp_type",
        "researcher_interactions",
        ["profile_id", "opportunity_id", "interaction_type"],
    )
    op.create_index(
        "idx_researcher_interactions_opp_type",
        "researcher_interactions",
        ["opportunity_id", "interaction_type"],
    )
    op.create_index(
        "idx_researcher_interactions_client_event",
        "researcher_interactions",
        ["profile_id", "client_event_id"],
    )


def downgrade() -> None:
    # 1. Drop indexes
    op.drop_index("idx_researcher_interactions_client_event", table_name="researcher_interactions")
    op.drop_index("idx_researcher_interactions_opp_type", table_name="researcher_interactions")
    op.drop_index("idx_researcher_interactions_profile_opp_type", table_name="researcher_interactions")
    op.drop_index("idx_researcher_interactions_profile_created", table_name="researcher_interactions")

    # 2. Drop table
    op.drop_table("researcher_interactions")
