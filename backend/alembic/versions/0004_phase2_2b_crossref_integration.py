"""Phase 2.2B — Crossref Research Knowledge Integration

Extends the Research Knowledge Layer for Crossref integration:
  - Makes openalex_id nullable on research_works, researchers, research_sources, institutions
    so that Crossref-originating scholarly entities can be inserted cleanly without dummy IDs.
  - Adds volume, issue, page, article_number, and license_url columns to research_works for
    authoritative bibliographic citation metadata provided by Crossref.

Revision ID: 0004_phase2_2b_crossref_integration
Revises:     0003_phase2_2a_openalex_research_knowledge
Create Date: 2026-08-25 22:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0004_phase2_2b_crossref_integration"
down_revision: Union[str, None] = "0003_phase2_2a_openalex_research_knowledge"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Make openalex_id nullable on research entities
    op.alter_column(
        "researchers",
        "openalex_id",
        existing_type=sa.String(length=50),
        nullable=True,
    )
    op.alter_column(
        "research_sources",
        "openalex_id",
        existing_type=sa.String(length=50),
        nullable=True,
    )
    op.alter_column(
        "institutions",
        "openalex_id",
        existing_type=sa.String(length=50),
        nullable=True,
    )
    op.alter_column(
        "research_works",
        "openalex_id",
        existing_type=sa.String(length=50),
        nullable=True,
    )

    # 2. Add bibliographic citation fields to research_works
    op.add_column("research_works", sa.Column("volume", sa.String(length=50), nullable=True))
    op.add_column("research_works", sa.Column("issue", sa.String(length=50), nullable=True))
    op.add_column("research_works", sa.Column("page", sa.String(length=50), nullable=True))
    op.add_column("research_works", sa.Column("article_number", sa.String(length=50), nullable=True))
    op.add_column("research_works", sa.Column("license_url", sa.Text(), nullable=True))


def downgrade() -> None:
    # 1. Drop added bibliographic citation columns
    op.drop_column("research_works", "license_url")
    op.drop_column("research_works", "article_number")
    op.drop_column("research_works", "page")
    op.drop_column("research_works", "issue")
    op.drop_column("research_works", "volume")

    # 2. Revert openalex_id back to NOT NULL
    op.alter_column(
        "research_works",
        "openalex_id",
        existing_type=sa.String(length=50),
        nullable=False,
    )
    op.alter_column(
        "institutions",
        "openalex_id",
        existing_type=sa.String(length=50),
        nullable=False,
    )
    op.alter_column(
        "research_sources",
        "openalex_id",
        existing_type=sa.String(length=50),
        nullable=False,
    )
    op.alter_column(
        "researchers",
        "openalex_id",
        existing_type=sa.String(length=50),
        nullable=False,
    )
