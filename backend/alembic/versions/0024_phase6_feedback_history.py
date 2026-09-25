"""Phase 6 — Backfill Phase 3.6 / 3.7 tables that shipped without a migration

The Phase 3.6 feedback model and Phase 3.7 recommendation history models were added to
the ORM but never migrated, so the live recommendation endpoints failed on PostgreSQL
with ``UndefinedTable``. This revision creates them exactly as the models define them.

Creates (each skipped if it already exists, e.g. on a hand-patched database):
  1. researcher_recommendation_feedback
  2. researcher_recommendation_snapshots
  3. researcher_recommendation_items

Revision ID: 0024_phase6_feedback_history
Revises:     0023_phase5_9_personalization_transparency
Create Date: 2026-09-25 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


# revision identifiers, used by Alembic.
revision: str = "0024_phase6_feedback_history"
down_revision: Union[str, None] = "0023_phase5_9_personalization_transparency"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    ]


def upgrade() -> None:
    if not _table_exists("researcher_recommendation_feedback"):
        op.create_table(
            "researcher_recommendation_feedback",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "researcher_id",
                UUID(as_uuid=True),
                sa.ForeignKey("research_profiles.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "opportunity_id",
                UUID(as_uuid=True),
                sa.ForeignKey("opportunities.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("feedback_type", sa.String(50), nullable=False),
            sa.Column("source", sa.String(50), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("rank_position", sa.Integer(), nullable=True),
            sa.Column("recommendation_session_id", sa.String(100), nullable=True),
            sa.Column("metadata_snapshot", JSONB, nullable=True),
            *_timestamps(),
            sa.UniqueConstraint(
                "researcher_id", "opportunity_id", "feedback_type", name="uq_researcher_feedback_type"
            ),
        )
        for name, column in (
            ("idx_researcher_feedback_created_at", "created_at"),
            ("idx_researcher_feedback_opportunity_id", "opportunity_id"),
            ("idx_researcher_feedback_researcher_id", "researcher_id"),
            ("idx_researcher_feedback_type", "feedback_type"),
            ("ix_researcher_recommendation_feedback_feedback_type", "feedback_type"),
            ("ix_researcher_recommendation_feedback_opportunity_id", "opportunity_id"),
            ("ix_researcher_recommendation_feedback_researcher_id", "researcher_id"),
        ):
            op.create_index(name, "researcher_recommendation_feedback", [column])

    if not _table_exists("researcher_recommendation_snapshots"):
        op.create_table(
            "researcher_recommendation_snapshots",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "researcher_id",
                UUID(as_uuid=True),
                sa.ForeignKey("research_profiles.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("ranking_version", sa.String(50), nullable=False),
            sa.Column("candidate_count", sa.Integer(), nullable=False),
            sa.Column("returned_count", sa.Integer(), nullable=False),
            sa.Column("request_context", JSONB, nullable=True),
            sa.Column("request_hash", sa.String(64), nullable=True),
            sa.Column("session_id", sa.String(100), nullable=True),
            *_timestamps(),
        )
        for name, column in (
            ("idx_rec_snapshots_created_at", "created_at"),
            ("idx_rec_snapshots_request_hash", "request_hash"),
            ("idx_rec_snapshots_researcher_id", "researcher_id"),
            ("idx_rec_snapshots_version", "ranking_version"),
            ("ix_researcher_recommendation_snapshots_request_hash", "request_hash"),
            ("ix_researcher_recommendation_snapshots_researcher_id", "researcher_id"),
            ("ix_researcher_recommendation_snapshots_session_id", "session_id"),
        ):
            op.create_index(name, "researcher_recommendation_snapshots", [column])

    if not _table_exists("researcher_recommendation_items"):
        op.create_table(
            "researcher_recommendation_items",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "snapshot_id",
                UUID(as_uuid=True),
                sa.ForeignKey("researcher_recommendation_snapshots.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "opportunity_id",
                UUID(as_uuid=True),
                sa.ForeignKey("opportunities.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("rank", sa.Integer(), nullable=False),
            sa.Column("base_relevance_score", sa.Float(), nullable=False),
            sa.Column("personalization_score", sa.Float(), nullable=False),
            sa.Column("behavioral_adjustment", sa.Float(), nullable=False),
            sa.Column("final_score", sa.Float(), nullable=False),
            sa.Column("risk_level", sa.String(50), nullable=True),
            sa.Column("deadline_status", sa.String(50), nullable=True),
            *_timestamps(),
            sa.UniqueConstraint("snapshot_id", "opportunity_id", name="uq_snapshot_opportunity"),
            sa.UniqueConstraint("snapshot_id", "rank", name="uq_snapshot_rank"),
        )
        for name, columns in (
            ("idx_rec_items_opportunity_id", ["opportunity_id"]),
            ("idx_rec_items_snapshot_id", ["snapshot_id"]),
            ("idx_rec_items_snapshot_rank", ["snapshot_id", "rank"]),
            ("ix_researcher_recommendation_items_opportunity_id", ["opportunity_id"]),
            ("ix_researcher_recommendation_items_snapshot_id", ["snapshot_id"]),
        ):
            op.create_index(name, "researcher_recommendation_items", columns)


def downgrade() -> None:
    op.drop_table("researcher_recommendation_items")
    op.drop_table("researcher_recommendation_snapshots")
    op.drop_table("researcher_recommendation_feedback")
