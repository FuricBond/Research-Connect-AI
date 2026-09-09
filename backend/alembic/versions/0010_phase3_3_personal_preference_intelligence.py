"""Phase 3.3 — Personal Preference Intelligence

Creates researcher_preferences table:
  - id (UUID primary key)
  - profile_id (FK to research_profiles.id, ON DELETE CASCADE)
  - category (varchar 50)
  - preference_key (varchar 100)
  - preference_value (varchar 255)
  - display_label (varchar 255)
  - canonical_id (FK to topics.id, ON DELETE SET NULL)
  - strength (float)
  - confidence (float)
  - source (varchar 50)
  - is_active (boolean)
  - recency_score (float)
  - provenance (jsonb)
  - last_observed_at (timestamptz)
  - created_at, updated_at (timestamptz)

Revision ID: 0010_phase3_3_personal_preference_intelligence
Revises:     0009_phase3_2_researcher_interest_expertise
Create Date: 2026-09-09 21:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0010_phase3_3_personal_preference_intelligence"
down_revision: Union[str, None] = "0009_phase3_2_researcher_interest_expertise"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "researcher_preferences",
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
            nullable=False,
        ),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("preference_key", sa.String(length=100), nullable=False),
        sa.Column("preference_value", sa.String(length=255), nullable=False),
        sa.Column("display_label", sa.String(length=255), nullable=False),
        sa.Column(
            "canonical_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("topics.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "strength",
            sa.Float(),
            nullable=False,
            server_default=sa.text("1.0"),
        ),
        sa.Column(
            "confidence",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0.95"),
        ),
        sa.Column(
            "source",
            sa.String(length=50),
            nullable=False,
            server_default=sa.text("'EXPLICIT'"),
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "recency_score",
            sa.Float(),
            nullable=False,
            server_default=sa.text("1.0"),
        ),
        sa.Column(
            "provenance",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "last_observed_at",
            sa.DateTime(timezone=True),
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
            "category",
            "preference_value",
            name="uq_researcher_preferences_profile_cat_val",
        ),
    )

    op.create_index(
        "idx_researcher_preferences_profile_id",
        "researcher_preferences",
        ["profile_id"],
    )
    op.create_index(
        "idx_researcher_preferences_category",
        "researcher_preferences",
        ["category"],
    )
    op.create_index(
        "idx_researcher_preferences_source",
        "researcher_preferences",
        ["source"],
    )
    op.create_index(
        "idx_researcher_preferences_active",
        "researcher_preferences",
        ["is_active"],
    )


def downgrade() -> None:
    op.drop_index("idx_researcher_preferences_active", table_name="researcher_preferences")
    op.drop_index("idx_researcher_preferences_source", table_name="researcher_preferences")
    op.drop_index("idx_researcher_preferences_category", table_name="researcher_preferences")
    op.drop_index("idx_researcher_preferences_profile_id", table_name="researcher_preferences")
    op.drop_table("researcher_preferences")
