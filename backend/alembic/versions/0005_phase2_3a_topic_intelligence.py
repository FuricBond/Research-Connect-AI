"""Phase 2.3A — Topic & Taxonomy Intelligence

Introduces research topic intelligence layer schema:
  - topic_aliases: Maps acronyms, abbreviations, and source terms (NLP, LLM, CV) to canonical topics.
  - research_work_topics: Junction linking research_works to canonical topics with confidence,
    primary flag, assignment method, and provenance.

Revision ID: 0005_phase2_3a_topic_intelligence
Revises:     0004_phase2_2b_crossref_integration
Create Date: 2026-08-25 23:40:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0005_phase2_3a_topic_intelligence"
down_revision: Union[str, None] = "0004_phase2_2b_crossref_integration"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. topic_aliases table
    op.create_table(
        "topic_aliases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "topic_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("topics.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("alias", sa.String(length=150), nullable=False),
        sa.Column("normalized_alias", sa.String(length=150), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False, server_default="MANUAL"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("topic_id", "normalized_alias", name="uq_topic_aliases_topic_normalized"),
    )
    op.create_index("idx_topic_aliases_normalized", "topic_aliases", ["normalized_alias"], unique=False)
    op.create_index("idx_topic_aliases_topic_id", "topic_aliases", ["topic_id"], unique=False)

    # 2. research_work_topics table
    op.create_table(
        "research_work_topics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "work_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("research_works.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "topic_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("topics.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "confidence_score",
            sa.Numeric(precision=3, scale=2),
            nullable=False,
            server_default="1.00",
        ),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "assignment_method",
            sa.String(length=50),
            nullable=False,
            server_default="RULE_INFERRED",
        ),
        sa.Column(
            "source",
            sa.String(length=50),
            nullable=False,
            server_default="System",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("work_id", "topic_id", name="uq_research_work_topics_work_topic"),
        sa.CheckConstraint(
            "confidence_score >= 0.0 AND confidence_score <= 1.0",
            name="chk_research_work_topics_confidence",
        ),
        sa.CheckConstraint(
            "assignment_method IN ('SOURCE_EXPLICIT', 'ALIAS_MATCH', 'RULE_INFERRED', 'MANUAL')",
            name="chk_research_work_topics_method",
        ),
    )
    op.create_index("idx_rwt_work_id", "research_work_topics", ["work_id"], unique=False)
    op.create_index("idx_rwt_topic_id", "research_work_topics", ["topic_id"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_rwt_topic_id", table_name="research_work_topics")
    op.drop_index("idx_rwt_work_id", table_name="research_work_topics")
    op.drop_table("research_work_topics")

    op.drop_index("idx_topic_aliases_topic_id", table_name="topic_aliases")
    op.drop_index("idx_topic_aliases_normalized", table_name="topic_aliases")
    op.drop_table("topic_aliases")
