"""Phase 5.14 — Personal reading list

Creates reading_list_items: research works a user saved to read, with a TO_READ / READING / DONE
status, private notes and the times reading started and finished. One row per user and work.

Existing users get no rows; the list starts empty.

Revision ID: 0029_phase5_14_reading_list
Revises:     0028_phase5_12_peer_discovery
Create Date: 2026-10-03 15:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = "0029_phase5_14_reading_list"
down_revision: Union[str, None] = "0028_phase5_12_peer_discovery"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "reading_list_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "work_id",
            UUID(as_uuid=True),
            sa.ForeignKey("research_works.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="TO_READ"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "status_updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "work_id", name="uq_reading_list_items_user_work"),
        sa.CheckConstraint(
            "status IN ('TO_READ', 'READING', 'DONE')",
            name="chk_reading_list_items_status",
        ),
    )

    # The list is always read per user, filtered by status or ordered by last update.
    op.create_index("idx_reading_list_user_status", "reading_list_items", ["user_id", "status"])
    op.create_index("idx_reading_list_user_updated", "reading_list_items", ["user_id", "updated_at"])
    op.create_index("ix_reading_list_items_user_id", "reading_list_items", ["user_id"])
    op.create_index("ix_reading_list_items_work_id", "reading_list_items", ["work_id"])


def downgrade() -> None:
    op.drop_table("reading_list_items")
