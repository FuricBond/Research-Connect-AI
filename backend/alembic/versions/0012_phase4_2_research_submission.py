"""Phase 4.2 — Research Submission Management & Tracking

Creates research_submissions table linked to saved_opportunities (workspace items):
  - id (UUID primary key)
  - workspace_item_id (UUID, foreign key to saved_opportunities.id ON DELETE CASCADE)
  - title (VARCHAR 500, not null)
  - abstract (TEXT, nullable)
  - submission_type (VARCHAR 50, not null, default 'FULL_PAPER')
  - status (VARCHAR 50, not null, default 'DRAFT')
  - external_submission_id (VARCHAR 255, nullable)
  - submission_url (VARCHAR 1000, nullable)
  - notes (TEXT, nullable)
  - submitted_at (TIMESTAMPTZ, nullable)
  - decision_at (TIMESTAMPTZ, nullable)
  - status_updated_at (TIMESTAMPTZ, not null, default now())
  - created_at (TIMESTAMPTZ, not null, default now())
  - updated_at (TIMESTAMPTZ, not null, default now())
  - check constraint chk_research_submissions_status
  - check constraint chk_research_submissions_type
  - indexes on workspace_item_id, status, updated_at

Revision ID: 0012_phase4_2_research_submission
Revises:     0011_phase4_1_opportunity_workspace
Create Date: 2026-09-18 22:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0012_phase4_2_research_submission"
down_revision: Union[str, None] = "0011_phase4_1_opportunity_workspace"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create research_submissions table
    op.create_table(
        "research_submissions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "workspace_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("saved_opportunities.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
            comment="Foreign key referencing parent workspace opportunity item",
        ),
        sa.Column(
            "title",
            sa.String(length=500),
            nullable=False,
            comment="Manuscript or application title",
        ),
        sa.Column(
            "abstract",
            sa.Text(),
            nullable=True,
            comment="Abstract text or proposal summary",
        ),
        sa.Column(
            "submission_type",
            sa.String(length=50),
            nullable=False,
            server_default="FULL_PAPER",
            comment="Submission type: FULL_PAPER, SHORT_PAPER, POSTER, etc.",
        ),
        sa.Column(
            "status",
            sa.String(length=50),
            nullable=False,
            server_default="DRAFT",
            comment="Status: DRAFT, READY, SUBMITTED, UNDER_REVIEW, ACCEPTED, REJECTED, WITHDRAWN",
        ),
        sa.Column(
            "external_submission_id",
            sa.String(length=255),
            nullable=True,
            comment="External tracking ID (e.g. OpenReview #142, EasyChair #56)",
        ),
        sa.Column(
            "venue",
            sa.String(length=255),
            nullable=True,
            comment="Target venue/conference/journal name if overriding opportunity title",
        ),
        sa.Column(
            "submission_url",
            sa.String(length=1000),
            nullable=True,
            comment="URL of the submission portal or submitted paper page",
        ),
        sa.Column(
            "notes",
            sa.Text(),
            nullable=True,
            comment="Researcher personal notes, co-author tasks, or reviewer comments",
        ),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp when officially submitted",
        ),
        sa.Column(
            "decision_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp when decision (ACCEPTED or REJECTED) was received",
        ),
        sa.Column(
            "status_updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="Timestamp of latest status transition",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'READY', 'SUBMITTED', 'UNDER_REVIEW', 'ACCEPTED', 'REJECTED', 'WITHDRAWN')",
            name="chk_research_submissions_status",
        ),
        sa.CheckConstraint(
            "submission_type IN ('FULL_PAPER', 'SHORT_PAPER', 'EXTENDED_ABSTRACT', 'POSTER', 'WORKSHOP_PAPER', 'GRANT_PROPOSAL', 'OTHER')",
            name="chk_research_submissions_type",
        ),
    )

    # 2. Create indexes
    op.create_index(
        "idx_research_submissions_workspace_item",
        "research_submissions",
        ["workspace_item_id"],
    )
    op.create_index(
        "idx_research_submissions_status",
        "research_submissions",
        ["status"],
    )
    op.create_index(
        "idx_research_submissions_updated",
        "research_submissions",
        ["updated_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_research_submissions_updated", table_name="research_submissions")
    op.drop_index("idx_research_submissions_status", table_name="research_submissions")
    op.drop_index("idx_research_submissions_workspace_item", table_name="research_submissions")
    op.drop_table("research_submissions")
