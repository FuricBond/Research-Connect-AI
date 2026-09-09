"""Phase 3.2 — Researcher Interest & Expertise Intelligence

Creates researcher_interests table:
  - id (UUID primary key)
  - profile_id (FK to research_profiles.id, ON DELETE CASCADE)
  - canonical_researcher_id (FK to researchers.id, ON DELETE SET NULL)
  - topic_id (FK to topics.id, ON DELETE SET NULL)
  - topic_name (varchar 150)
  - topic_slug (varchar 150)
  - topic_category (varchar 50)
  - strength (float)
  - confidence (float)
  - evidence_count (integer)
  - recency_score (float)
  - classification (varchar 50)
  - is_primary_expertise (boolean)
  - first_observed_year (integer)
  - last_observed_year (integer)
  - source (varchar 100)
  - provenance (jsonb)
  - supporting_work_ids (jsonb)
  - created_at, updated_at (timestamptz)

Revision ID: 0009_phase3_2_researcher_interest_expertise
Revises:     0008_phase3_1_researcher_profile_foundation
Create Date: 2026-09-09 14:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0009_phase3_2_researcher_interest_expertise"
down_revision: Union[str, None] = "0008_phase3_1_researcher_profile_foundation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "researcher_interests",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("research_profiles.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "canonical_researcher_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("researchers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "topic_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("topics.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("topic_name", sa.String(length=150), nullable=False),
        sa.Column("topic_slug", sa.String(length=150), nullable=False),
        sa.Column("topic_category", sa.String(length=50), nullable=True),
        sa.Column(
            "strength",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0.0"),
        ),
        sa.Column(
            "confidence",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0.0"),
        ),
        sa.Column(
            "evidence_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "recency_score",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0.0"),
        ),
        sa.Column(
            "classification",
            sa.String(length=50),
            nullable=False,
            server_default=sa.text("'WEAK_INTEREST'"),
        ),
        sa.Column(
            "is_primary_expertise",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("first_observed_year", sa.Integer(), nullable=True),
        sa.Column("last_observed_year", sa.Integer(), nullable=True),
        sa.Column(
            "source",
            sa.String(length=100),
            nullable=False,
            server_default=sa.text("'SCHOLARLY_WORKS'"),
        ),
        sa.Column(
            "provenance",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "supporting_work_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
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
            "topic_name",
            name="uq_researcher_interests_profile_topic_name",
        ),
    )

    op.create_index(
        "idx_researcher_interests_profile_id",
        "researcher_interests",
        ["profile_id"],
    )
    op.create_index(
        "idx_researcher_interests_researcher_id",
        "researcher_interests",
        ["canonical_researcher_id"],
    )
    op.create_index(
        "idx_researcher_interests_topic_id",
        "researcher_interests",
        ["topic_id"],
    )
    op.create_index(
        "idx_researcher_interests_topic_name",
        "researcher_interests",
        ["topic_name"],
    )
    op.create_index(
        "idx_researcher_interests_classification",
        "researcher_interests",
        ["classification"],
    )
    op.create_index(
        "idx_researcher_interests_strength",
        "researcher_interests",
        ["strength"],
    )


def downgrade() -> None:
    op.drop_index("idx_researcher_interests_strength", table_name="researcher_interests")
    op.drop_index("idx_researcher_interests_classification", table_name="researcher_interests")
    op.drop_index("idx_researcher_interests_topic_name", table_name="researcher_interests")
    op.drop_index("idx_researcher_interests_topic_id", table_name="researcher_interests")
    op.drop_index("idx_researcher_interests_researcher_id", table_name="researcher_interests")
    op.drop_index("idx_researcher_interests_profile_id", table_name="researcher_interests")
    op.drop_table("researcher_interests")
