"""Phase 5.10 — Faculty research opportunities and project postings

Creates:
  1. research_postings — platform-authored research openings (projects, thesis topics,
     collaborations, lab rotations) owned by a faculty member or administrator, with a
     deterministic DRAFT / OPEN / CLOSED / FILLED / CANCELLED / ARCHIVED lifecycle.
  2. research_posting_topics — canonical taxonomy links, mirroring opportunity_topics so
     postings participate in the same topic-aware filtering as ingested opportunities.

Non-destructive: creates new tables only and does not alter existing ones.

Revision ID: 0026_phase5_10_research_postings
Revises:     0025_phase6_personalization_reset_cutoff
Create Date: 2026-09-25 15:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


# revision identifiers, used by Alembic.
revision: str = "0026_phase5_10_research_postings"
down_revision: Union[str, None] = "0025_phase6_personalization_reset_cutoff"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "research_postings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "author_profile_id",
            UUID(as_uuid=True),
            sa.ForeignKey("research_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "author_user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("posting_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="DRAFT"),
        sa.Column("summary", sa.String(500), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("required_skills", JSONB, nullable=True),
        sa.Column("preferred_qualifications", sa.Text(), nullable=True),
        sa.Column("institution", sa.String(255), nullable=True),
        sa.Column("department", sa.String(255), nullable=True),
        sa.Column("location", sa.String(255), nullable=True),
        sa.Column("country", sa.String(2), nullable=True),
        sa.Column("work_mode", sa.String(50), nullable=False, server_default="ONSITE"),
        sa.Column("positions_available", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("application_deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expected_start_date", sa.Date(), nullable=True),
        sa.Column("expected_end_date", sa.Date(), nullable=True),
        sa.Column("contact_email", sa.String(255), nullable=True),
        sa.Column("external_url", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status_note", sa.Text(), nullable=True),
        sa.Column("application_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "posting_type IN ('PROJECT', 'THESIS_TOPIC', 'COLLABORATION', 'LAB_ROTATION')",
            name="chk_research_postings_type",
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'OPEN', 'CLOSED', 'FILLED', 'CANCELLED', 'ARCHIVED')",
            name="chk_research_postings_status",
        ),
        sa.CheckConstraint(
            "work_mode IN ('ONSITE', 'REMOTE', 'HYBRID')",
            name="chk_research_postings_work_mode",
        ),
        sa.CheckConstraint("positions_available >= 1", name="chk_research_postings_positions_positive"),
    )

    for name, columns in (
        ("idx_research_postings_author", ["author_profile_id"]),
        ("idx_research_postings_created", ["created_at"]),
        ("idx_research_postings_deadline", ["application_deadline"]),
        ("idx_research_postings_status_deadline", ["status", "application_deadline"]),
        ("idx_research_postings_status_type", ["status", "posting_type"]),
        ("ix_research_postings_application_deadline", ["application_deadline"]),
        ("ix_research_postings_author_profile_id", ["author_profile_id"]),
        ("ix_research_postings_author_user_id", ["author_user_id"]),
        ("ix_research_postings_posting_type", ["posting_type"]),
        ("ix_research_postings_status", ["status"]),
    ):
        op.create_index(name, "research_postings", columns)

    op.create_table(
        "research_posting_topics",
        sa.Column(
            "posting_id",
            UUID(as_uuid=True),
            sa.ForeignKey("research_postings.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "topic_id",
            UUID(as_uuid=True),
            sa.ForeignKey("topics.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("confidence_score", sa.Numeric(3, 2), nullable=False, server_default="1.00"),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("posting_id", "topic_id", name="uq_research_posting_topics"),
    )
    op.create_index("idx_research_posting_topics_topic", "research_posting_topics", ["topic_id"])
    op.create_index("ix_research_posting_topics_topic_id", "research_posting_topics", ["topic_id"])


def downgrade() -> None:
    op.drop_table("research_posting_topics")
    op.drop_table("research_postings")
