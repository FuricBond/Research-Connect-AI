"""Phase 2.1 Ingestion Hardening and Operational Metrics

Revision ID: 0002_phase2_1_ingestion_hardening
Revises: 0001_initial_phase1_schema
Create Date: 2026-08-24 23:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002_phase2_1_ingestion_hardening"
down_revision: Union[str, None] = "0001_initial_phase1_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Update opportunities table with last_seen_at
    op.add_column(
        "opportunities",
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_opportunities_last_seen",
        "opportunities",
        ["last_seen_at"],
        unique=False,
    )

    # 2. Update sources table with operational health metrics
    op.add_column(
        "sources",
        sa.Column("last_successful_scrape_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "sources",
        sa.Column("last_failed_scrape_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "sources",
        sa.Column("consecutive_failure_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "sources",
        sa.Column("total_scrape_count", sa.Integer(), nullable=False, server_default="0"),
    )

    # 3. Create ingestion_runs table
    op.create_table(
        "ingestion_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="RUNNING"),
        sa.Column("topic", sa.String(length=255), nullable=True),
        sa.Column("pages_fetched", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_parsed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_valid", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_invalid", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_inserted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_unchanged", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicates_detected", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("potential_duplicates_detected", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_expired", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metrics_detail", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('RUNNING', 'COMPLETED', 'FAILED')", name="chk_ingestion_runs_status"),
    )
    op.create_index("ix_ingestion_runs_source_id", "ingestion_runs", ["source_id"], unique=False)
    op.create_index("ix_ingestion_runs_status", "ingestion_runs", ["status"], unique=False)


def downgrade() -> None:
    op.drop_table("ingestion_runs")
    op.drop_column("sources", "total_scrape_count")
    op.drop_column("sources", "consecutive_failure_count")
    op.drop_column("sources", "last_failed_scrape_at")
    op.drop_column("sources", "last_successful_scrape_at")
    op.drop_index("ix_opportunities_last_seen", table_name="opportunities")
    op.drop_column("opportunities", "last_seen_at")
