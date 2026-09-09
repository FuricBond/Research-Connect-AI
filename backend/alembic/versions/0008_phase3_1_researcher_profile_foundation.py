"""Phase 3.1 — Researcher Profile Foundation

Adds columns, foreign keys, and indexes to research_profiles:
  - institution_id (FK to institutions.id, ON DELETE SET NULL)
  - canonical_researcher_id (FK to researchers.id, ON DELETE SET NULL)
  - orcid (varchar 50)
  - openalex_id (varchar 50)
  - academic_status (varchar 50, default 'UNKNOWN')
  - external_identifiers (jsonb)

Revision ID: 0008_phase3_1_researcher_profile_foundation
Revises:     0007_phase2_4i_fts_gin_indexes
Create Date: 2026-09-09 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0008_phase3_1_researcher_profile_foundation"
down_revision: Union[str, None] = "0007_phase2_4i_fts_gin_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add new columns to research_profiles
    op.add_column(
        "research_profiles",
        sa.Column(
            "institution_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("institutions.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "research_profiles",
        sa.Column(
            "canonical_researcher_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("researchers.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "research_profiles",
        sa.Column("orcid", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "research_profiles",
        sa.Column("openalex_id", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "research_profiles",
        sa.Column(
            "academic_status",
            sa.String(length=50),
            nullable=True,
            server_default="UNKNOWN",
        ),
    )
    op.add_column(
        "research_profiles",
        sa.Column(
            "external_identifiers",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )

    # 2. Add indexes for fast lookup and join operations
    op.create_index(
        "idx_research_profiles_institution_id",
        "research_profiles",
        ["institution_id"],
        unique=False,
    )
    op.create_index(
        "idx_research_profiles_canonical_researcher",
        "research_profiles",
        ["canonical_researcher_id"],
        unique=False,
    )
    op.create_index(
        "idx_research_profiles_orcid",
        "research_profiles",
        ["orcid"],
        unique=False,
    )
    op.create_index(
        "idx_research_profiles_openalex_id",
        "research_profiles",
        ["openalex_id"],
        unique=False,
    )


def downgrade() -> None:
    # Drop indexes
    op.drop_index("idx_research_profiles_openalex_id", table_name="research_profiles")
    op.drop_index("idx_research_profiles_orcid", table_name="research_profiles")
    op.drop_index("idx_research_profiles_canonical_researcher", table_name="research_profiles")
    op.drop_index("idx_research_profiles_institution_id", table_name="research_profiles")

    # Drop columns
    op.drop_column("research_profiles", "external_identifiers")
    op.drop_column("research_profiles", "academic_status")
    op.drop_column("research_profiles", "openalex_id")
    op.drop_column("research_profiles", "orcid")
    op.drop_column("research_profiles", "canonical_researcher_id")
    op.drop_column("research_profiles", "institution_id")
