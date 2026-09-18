"""Phase 4.1 — Opportunity Workspace

Extends saved_opportunities table to serve as unified workspace:
  - status (varchar 50, not null, default 'SAVED')
  - priority (varchar 20, not null, default 'MEDIUM')
  - tags (jsonb, not null, default '[]')
  - updated_at (timestamptz, not null, default now())
  - status_updated_at (timestamptz, not null, default now())
  - archived_at (timestamptz, nullable)
  - check constraint chk_saved_opportunities_status
  - check constraint chk_saved_opportunities_priority
  - indexes on (user_id, status), (user_id, priority), (user_id, updated_at), archived_at

Revision ID: 0011_phase4_1_opportunity_workspace
Revises:     0010_phase3_3_personal_preference_intelligence
Create Date: 2026-09-18 22:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0011_phase4_1_opportunity_workspace"
down_revision: Union[str, None] = "0010_phase3_3_personal_preference_intelligence"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add workspace columns with safe server defaults
    op.add_column(
        "saved_opportunities",
        sa.Column(
            "status",
            sa.String(length=50),
            nullable=False,
            server_default="SAVED",
            comment="Workflow stage: SAVED, CONSIDERING, PLANNING, APPLIED, ACCEPTED, REJECTED, ARCHIVED",
        ),
    )
    op.add_column(
        "saved_opportunities",
        sa.Column(
            "priority",
            sa.String(length=20),
            nullable=False,
            server_default="MEDIUM",
            comment="Priority: LOW, MEDIUM, HIGH, URGENT",
        ),
    )
    op.add_column(
        "saved_opportunities",
        sa.Column(
            "tags",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
            comment="User-defined categorization tags",
        ),
    )
    op.add_column(
        "saved_opportunities",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.add_column(
        "saved_opportunities",
        sa.Column(
            "status_updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.add_column(
        "saved_opportunities",
        sa.Column(
            "archived_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # 2. Add check constraints
    op.create_check_constraint(
        "chk_saved_opportunities_status",
        "saved_opportunities",
        "status IN ('SAVED', 'CONSIDERING', 'PLANNING', 'APPLIED', 'ACCEPTED', 'REJECTED', 'ARCHIVED')",
    )
    op.create_check_constraint(
        "chk_saved_opportunities_priority",
        "saved_opportunities",
        "priority IN ('LOW', 'MEDIUM', 'HIGH', 'URGENT')",
    )

    # 3. Add compound indexes for researcher-scoped filtering
    op.create_index(
        "idx_saved_opp_user_status",
        "saved_opportunities",
        ["user_id", "status"],
    )
    op.create_index(
        "idx_saved_opp_user_priority",
        "saved_opportunities",
        ["user_id", "priority"],
    )
    op.create_index(
        "idx_saved_opp_user_updated",
        "saved_opportunities",
        ["user_id", "updated_at"],
    )
    op.create_index(
        "idx_saved_opp_archived_at",
        "saved_opportunities",
        ["archived_at"],
    )


def downgrade() -> None:
    # 1. Drop indexes
    op.drop_index("idx_saved_opp_archived_at", table_name="saved_opportunities")
    op.drop_index("idx_saved_opp_user_updated", table_name="saved_opportunities")
    op.drop_index("idx_saved_opp_user_priority", table_name="saved_opportunities")
    op.drop_index("idx_saved_opp_user_status", table_name="saved_opportunities")

    # 2. Drop check constraints
    op.drop_constraint("chk_saved_opportunities_priority", "saved_opportunities", type_="check")
    op.drop_constraint("chk_saved_opportunities_status", "saved_opportunities", type_="check")

    # 3. Drop columns
    op.drop_column("saved_opportunities", "archived_at")
    op.drop_column("saved_opportunities", "status_updated_at")
    op.drop_column("saved_opportunities", "updated_at")
    op.drop_column("saved_opportunities", "tags")
    op.drop_column("saved_opportunities", "priority")
    op.drop_column("saved_opportunities", "status")
