"""Phase 2.3B — Semantic Embedding Generation + pgvector Integration

Adds embedding vector columns and embedding-metadata columns to:

  research_works   — new ``embedding`` (vector 384), ``content_hash``,
                     ``embedding_model``, ``embedded_at``
  opportunities    — new ``content_hash``, ``embedding_model``, ``embedded_at``
                     (``embedding`` column already exists from Phase 1)

Also creates an HNSW index on both tables for fast approximate nearest-
neighbour search via pgvector's ``<=>`` (cosine distance) operator.

Revision ID: 0006_phase2_3b_semantic_embeddings
Revises:     0005_phase2_3a_topic_intelligence
Create Date: 2026-08-26 22:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0006_phase2_3b_semantic_embeddings"
down_revision: Union[str, None] = "0005_phase2_3a_topic_intelligence"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. research_works — add embedding + metadata columns
    # ------------------------------------------------------------------
    op.add_column(
        "research_works",
        sa.Column(
            "embedding",
            sa.Text(),  # stored as opaque text; pgvector renders it as vector(384)
            nullable=True,
            comment="384-dim sentence embedding (all-MiniLM-L6-v2, L2-normalised)",
        ),
    )
    # Alter the column type to vector(384) using raw SQL because SQLAlchemy
    # does not have a built-in vector type dialect.
    op.execute("ALTER TABLE research_works ALTER COLUMN embedding TYPE vector(384) USING embedding::vector(384)")

    op.add_column(
        "research_works",
        sa.Column(
            "content_hash",
            sa.String(length=64),
            nullable=True,
            comment="SHA-256 of the semantic text used to generate this embedding",
        ),
    )
    op.add_column(
        "research_works",
        sa.Column(
            "embedding_model",
            sa.String(length=100),
            nullable=True,
            comment="Model name, e.g. 'all-MiniLM-L6-v2'",
        ),
    )
    op.add_column(
        "research_works",
        sa.Column(
            "embedded_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When this embedding was last generated or refreshed",
        ),
    )

    # Plain B-tree index on content_hash for hash-equality lookups
    op.create_index(
        "idx_research_works_content_hash",
        "research_works",
        ["content_hash"],
        unique=False,
    )

    # HNSW index for approximate cosine-distance search
    # (requires pgvector >= 0.5.0)
    op.execute(
        "CREATE INDEX idx_research_works_embedding_hnsw "
        "ON research_works USING hnsw (embedding vector_cosine_ops)"
    )

    # ------------------------------------------------------------------
    # 2. opportunities — embedding column already exists; add metadata only
    # ------------------------------------------------------------------
    op.add_column(
        "opportunities",
        sa.Column(
            "content_hash",
            sa.String(length=64),
            nullable=True,
            comment="SHA-256 of the semantic text used to generate this embedding",
        ),
    )
    op.add_column(
        "opportunities",
        sa.Column(
            "embedding_model",
            sa.String(length=100),
            nullable=True,
            comment="Model name, e.g. 'all-MiniLM-L6-v2'",
        ),
    )
    op.add_column(
        "opportunities",
        sa.Column(
            "embedded_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When this embedding was last generated or refreshed",
        ),
    )

    op.create_index(
        "idx_opportunities_content_hash",
        "opportunities",
        ["content_hash"],
        unique=False,
    )

    # HNSW index on the existing opportunities.embedding column
    op.execute(
        "CREATE INDEX idx_opportunities_embedding_hnsw "
        "ON opportunities USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    # ------------------------------------------------------------------
    # opportunities — remove embedding metadata columns
    # ------------------------------------------------------------------
    op.execute("DROP INDEX IF EXISTS idx_opportunities_embedding_hnsw")
    op.drop_index("idx_opportunities_content_hash", table_name="opportunities")
    op.drop_column("opportunities", "embedded_at")
    op.drop_column("opportunities", "embedding_model")
    op.drop_column("opportunities", "content_hash")

    # ------------------------------------------------------------------
    # research_works — remove all added columns
    # ------------------------------------------------------------------
    op.execute("DROP INDEX IF EXISTS idx_research_works_embedding_hnsw")
    op.drop_index("idx_research_works_content_hash", table_name="research_works")
    op.drop_column("research_works", "embedded_at")
    op.drop_column("research_works", "embedding_model")
    op.drop_column("research_works", "content_hash")
    op.drop_column("research_works", "embedding")
