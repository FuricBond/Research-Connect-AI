"""Phase 2.4I — Full-Text GIN Indexing & Searchable TSVECTOR

Adds generated stored tsvector columns and GIN indexes to:
  1. research_works  — new ``fts_vector`` (tsvector) with GIN index ``idx_research_works_fts_gin``
  2. opportunities   — new ``fts_vector`` (tsvector) with GIN index ``idx_opportunities_fts_gin``

This eliminates per-query dynamic ``to_tsvector()`` evaluations in PostgreSQL,
enabling fast indexed lexical search and scalability for large corpora.

Revision ID: 0007_phase2_4i_fts_gin_indexes
Revises:     0006_phase2_3b_semantic_embeddings
Create Date: 2026-08-31 01:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0007_phase2_4i_fts_gin_indexes"
down_revision: Union[str, None] = "0006_phase2_3b_semantic_embeddings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. research_works — add fts_vector GENERATED STORED column + GIN index
    # ------------------------------------------------------------------
    # Weights:
    #   A: title (1.0)
    #   B: abstract (0.4)
    #   C: work_type || ' ' || language (0.2)
    op.execute(
        """
        ALTER TABLE research_works
        ADD COLUMN IF NOT EXISTS fts_vector tsvector
        GENERATED ALWAYS AS (
            setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
            setweight(to_tsvector('english', coalesce(abstract, '')), 'B') ||
            setweight(to_tsvector('english', coalesce(work_type, '') || ' ' || coalesce(language, '')), 'C')
        ) STORED;
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_research_works_fts_gin
        ON research_works USING gin (fts_vector);
        """
    )

    # ------------------------------------------------------------------
    # 2. opportunities — add fts_vector GENERATED STORED column + GIN index
    # ------------------------------------------------------------------
    # Weights:
    #   A: title (1.0)
    #   B: summary || ' ' || description (0.4)
    #   C: publisher || ' ' || organizer || ' ' || series_name || ' ' || location (0.2)
    op.execute(
        """
        ALTER TABLE opportunities
        ADD COLUMN IF NOT EXISTS fts_vector tsvector
        GENERATED ALWAYS AS (
            setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
            setweight(to_tsvector('english', coalesce(summary, '') || ' ' || coalesce(description, '')), 'B') ||
            setweight(to_tsvector('english', coalesce(publisher, '') || ' ' || coalesce(organizer, '') || ' ' || coalesce(series_name, '') || ' ' || coalesce(location, '')), 'C')
        ) STORED;
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_opportunities_fts_gin
        ON opportunities USING gin (fts_vector);
        """
    )


def downgrade() -> None:
    # ------------------------------------------------------------------
    # 2. opportunities — drop GIN index and fts_vector column
    # ------------------------------------------------------------------
    op.execute("DROP INDEX IF EXISTS idx_opportunities_fts_gin;")
    op.execute("ALTER TABLE opportunities DROP COLUMN IF EXISTS fts_vector;")

    # ------------------------------------------------------------------
    # 1. research_works — drop GIN index and fts_vector column
    # ------------------------------------------------------------------
    op.execute("DROP INDEX IF EXISTS idx_research_works_fts_gin;")
    op.execute("ALTER TABLE research_works DROP COLUMN IF EXISTS fts_vector;")
