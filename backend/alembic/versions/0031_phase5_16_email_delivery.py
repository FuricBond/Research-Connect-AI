"""Phase 5.16 — Email delivery of notifications

Adds the email copy of an in-app notification to notifications: its status (NULL until the
email_dispatch scheduler job decides, then SENT, RETRY, FAILED or SKIPPED), the number of send
attempts and when the mail server accepted it, plus an index for the job's queue.

Every notification that already exists is marked SKIPPED, so switching email on never mails the
backlog. The downgrade drops the three columns and nothing else.

Revision ID: 0031_phase5_16_email_delivery
Revises:     0030_phase5_15_posting_fit_alerts
Create Date: 2026-10-04 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0031_phase5_16_email_delivery"
down_revision: Union[str, None] = "0030_phase5_15_posting_fit_alerts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("notifications", sa.Column("email_status", sa.String(length=20), nullable=True))
    op.add_column(
        "notifications",
        sa.Column("email_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "notifications",
        sa.Column("email_sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "chk_notifications_email_status",
        "notifications",
        "email_status IS NULL OR email_status IN ('SENT', 'RETRY', 'FAILED', 'SKIPPED')",
    )
    op.create_index(
        "idx_notifications_email_queue",
        "notifications",
        ["email_status", "created_at"],
    )

    # Notifications created before email delivery existed are never emailed.
    op.execute("UPDATE notifications SET email_status = 'SKIPPED' WHERE email_status IS NULL")


def downgrade() -> None:
    op.drop_index("idx_notifications_email_queue", table_name="notifications")
    op.drop_constraint("chk_notifications_email_status", "notifications", type_="check")
    op.drop_column("notifications", "email_sent_at")
    op.drop_column("notifications", "email_attempts")
    op.drop_column("notifications", "email_status")
