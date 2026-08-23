"""Initial Phase 1 database schema

Revision ID: 0001_initial_phase1_schema
Revises: 
Create Date: 2026-08-24 01:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.db.types import Vector

# revision identifiers, used by Alembic.
revision: str = "0001_initial_phase1_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 0. Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # 1. users table
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False, server_default="STUDENT"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("role IN ('STUDENT', 'FACULTY', 'ADMIN')", name="chk_users_role"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # 2. research_profiles table
    op.create_table(
        "research_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("institution", sa.String(length=255), nullable=True),
        sa.Column("department", sa.String(length=255), nullable=True),
        sa.Column("academic_level", sa.String(length=100), nullable=True),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("keywords", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("target_opportunity_types", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_research_profiles_user_id", "research_profiles", ["user_id"], unique=True)

    # 3. sources table
    op.create_table(
        "sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False, unique=True),
        sa.Column("source_type", sa.String(length=50), nullable=False, server_default="SCRAPER"),
        sa.Column("base_url", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("reliability_score", sa.Numeric(precision=3, scale=2), nullable=False, server_default="1.00"),
        sa.Column("last_scraped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("source_type IN ('SCRAPER', 'RSS', 'API', 'MANUAL')", name="chk_sources_source_type"),
    )

    # 4. topics table
    op.create_table(
        "topics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=150), nullable=False, unique=True),
        sa.Column("slug", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "parent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("topics.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_topics_slug", "topics", ["slug"], unique=True)
    op.create_index("ix_topics_parent_id", "topics", ["parent_id"], unique=False)

    # 5. opportunities table
    op.create_table(
        "opportunities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("opportunity_type", sa.String(length=50), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=True),
        sa.Column("publisher", sa.String(length=255), nullable=True),
        sa.Column("organizer", sa.String(length=255), nullable=True),
        sa.Column("series_name", sa.String(length=255), nullable=True),
        sa.Column("edition", sa.String(length=50), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("website_url", sa.Text(), nullable=True),
        sa.Column("submission_url", sa.Text(), nullable=True),
        sa.Column("delivery_mode", sa.String(length=50), nullable=False, server_default="OFFLINE"),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("submission_deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notification_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("camera_ready_deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("event_start_date", sa.Date(), nullable=True),
        sa.Column("event_end_date", sa.Date(), nullable=True),
        sa.Column("indexing", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("apc_or_fee", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_predatory_flag", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("risk_score", sa.Numeric(precision=3, scale=2), nullable=True, server_default="0.00"),
        sa.Column("risk_reasons", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="ACTIVE"),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sources.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("raw_source_id", sa.String(length=255), nullable=True),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("embedding", Vector(384), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("source_id", "raw_source_id", name="uq_opportunities_source_raw_id"),
        sa.CheckConstraint(
            "opportunity_type IN ('CONFERENCE', 'JOURNAL', 'WORKSHOP', 'CALL_FOR_PAPERS', 'SPECIAL_ISSUE')",
            name="chk_opportunities_type",
        ),
        sa.CheckConstraint(
            "delivery_mode IN ('ONLINE', 'OFFLINE', 'HYBRID')",
            name="chk_opportunities_delivery_mode",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'EXPIRED', 'ARCHIVED', 'DRAFT', 'UNVERIFIED')",
            name="chk_opportunities_status",
        ),
    )
    op.create_index("ix_opportunities_opportunity_type", "opportunities", ["opportunity_type"], unique=False)
    op.create_index("ix_opportunities_slug", "opportunities", ["slug"], unique=False)
    op.create_index("ix_opportunities_status", "opportunities", ["status"], unique=False)
    op.create_index("ix_opportunities_source_id", "opportunities", ["source_id"], unique=False)
    op.create_index("ix_opportunities_submission_deadline", "opportunities", ["submission_deadline"], unique=False)
    op.create_index("idx_opportunities_type_status", "opportunities", ["opportunity_type", "status"], unique=False)
    op.create_index("idx_opportunities_deadline", "opportunities", ["submission_deadline"], unique=False)

    # 6. opportunity_topics junction table
    op.create_table(
        "opportunity_topics",
        sa.Column(
            "opportunity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("opportunities.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "topic_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("topics.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("confidence_score", sa.Numeric(precision=3, scale=2), nullable=False, server_default="1.00"),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_opportunity_topics_topic_id", "opportunity_topics", ["topic_id"], unique=False)

    # 7. saved_opportunities table
    op.create_table(
        "saved_opportunities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "opportunity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("opportunities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "opportunity_id", name="uq_saved_opportunities_user_opportunity"),
    )
    op.create_index("ix_saved_opportunities_user_id", "saved_opportunities", ["user_id"], unique=False)
    op.create_index("ix_saved_opportunities_opportunity_id", "saved_opportunities", ["opportunity_id"], unique=False)


def downgrade() -> None:
    op.drop_table("saved_opportunities")
    op.drop_table("opportunity_topics")
    op.drop_table("opportunities")
    op.drop_table("topics")
    op.drop_table("sources")
    op.drop_table("research_profiles")
    op.drop_table("users")
    # We do not drop extension vector automatically in downgrade as other DB objects might use it
