"""Phase 5.15 — Posting fit and match alerts

Adds a student's opt-in for "notify me when a new posting matches my interests" to
researcher_notification_preferences: a switch (off by default) and the minimum fit score (60 by
default, 0-100). Adds POSTING_MATCH to the notification types.

Every existing preference row gets the switch off, so nobody is alerted as a side effect of this
migration. The downgrade removes POSTING_MATCH notifications first, because the restored type
check would reject them.

Revision ID: 0030_phase5_15_posting_fit_alerts
Revises:     0029_phase5_14_reading_list
Create Date: 2026-10-03 17:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0030_phase5_15_posting_fit_alerts"
down_revision: Union[str, None] = "0029_phase5_14_reading_list"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TYPES_BEFORE = (
    "'DEADLINE_UPCOMING', 'DEADLINE_TODAY', 'DEADLINE_EXTENDED', 'DEADLINE_MOVED_EARLIER', "
    "'DEADLINE_CONFLICT', 'CALENDAR_EVENT_UPCOMING', 'SUBMISSION_STATUS_CHANGE', 'SYSTEM', "
    "'WORKSPACE_INVITATION', 'INVITATION_ACCEPTED', 'MEMBER_ROLE_CHANGED', 'MEMBER_REMOVED', "
    "'TASK_ASSIGNED', 'TASK_COMPLETED', 'DOCUMENT_UPDATED', 'COLLABORATION_ACTIVITY'"
)


def upgrade() -> None:
    op.add_column(
        "researcher_notification_preferences",
        sa.Column("posting_match_alerts_enabled", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "researcher_notification_preferences",
        sa.Column("posting_match_min_score", sa.Integer(), nullable=False, server_default="60"),
    )
    op.create_check_constraint(
        "chk_notification_prefs_posting_min_score",
        "researcher_notification_preferences",
        "posting_match_min_score BETWEEN 0 AND 100",
    )

    op.drop_constraint("chk_notifications_type", "notifications", type_="check")
    op.create_check_constraint(
        "chk_notifications_type",
        "notifications",
        f"notification_type IN ({_TYPES_BEFORE}, 'POSTING_MATCH')",
    )


def downgrade() -> None:
    # The restored check would reject these rows, so they go first.
    op.execute("DELETE FROM notifications WHERE notification_type = 'POSTING_MATCH'")
    op.drop_constraint("chk_notifications_type", "notifications", type_="check")
    op.create_check_constraint(
        "chk_notifications_type",
        "notifications",
        f"notification_type IN ({_TYPES_BEFORE})",
    )

    op.drop_constraint(
        "chk_notification_prefs_posting_min_score",
        "researcher_notification_preferences",
        type_="check",
    )
    op.drop_column("researcher_notification_preferences", "posting_match_min_score")
    op.drop_column("researcher_notification_preferences", "posting_match_alerts_enabled")
