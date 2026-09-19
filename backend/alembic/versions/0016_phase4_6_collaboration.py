"""Phase 4.6 — Collaborative Research Management

Creates tables for collaborative workspaces:
  - workspace_members:
      - id (UUID primary key)
      - workspace_id (UUID FK to saved_opportunities.id ON DELETE CASCADE)
      - user_id (UUID FK to users.id ON DELETE CASCADE)
      - role (VARCHAR 50, not null, default 'CONTRIBUTOR')
      - status (VARCHAR 50, not null, default 'ACTIVE')
      - invited_at (TIMESTAMPTZ, nullable)
      - joined_at (TIMESTAMPTZ, nullable)
      - removed_at (TIMESTAMPTZ, nullable)
      - created_at (TIMESTAMPTZ, not null, default now())
      - updated_at (TIMESTAMPTZ, not null, default now())
  - workspace_invitations:
      - id (UUID primary key)
      - workspace_id (UUID FK to saved_opportunities.id ON DELETE CASCADE)
      - inviter_id (UUID FK to users.id ON DELETE CASCADE)
      - invitee_email (VARCHAR 255, not null)
      - invitee_user_id (UUID FK to users.id ON DELETE SET NULL, nullable)
      - role (VARCHAR 50, not null, default 'CONTRIBUTOR')
      - token (VARCHAR 255, not null, unique)
      - status (VARCHAR 50, not null, default 'PENDING')
      - created_at (TIMESTAMPTZ, not null, default now())
      - expires_at (TIMESTAMPTZ, not null)
      - accepted_at (TIMESTAMPTZ, nullable)
      - revoked_at (TIMESTAMPTZ, nullable)
  - workspace_tasks:
      - id (UUID primary key)
      - workspace_id (UUID FK to saved_opportunities.id ON DELETE CASCADE)
      - title (VARCHAR 255, not null)
      - description (TEXT, nullable)
      - creator_id (UUID FK to users.id ON DELETE CASCADE)
      - assignee_id (UUID FK to users.id ON DELETE SET NULL, nullable)
      - status (VARCHAR 50, not null, default 'TODO')
      - priority (VARCHAR 20, not null, default 'MEDIUM')
      - due_at (TIMESTAMPTZ, nullable)
      - submission_id (UUID FK to research_submissions.id ON DELETE SET NULL, nullable)
      - document_id (UUID FK to research_submission_documents.id ON DELETE SET NULL, nullable)
      - created_at (TIMESTAMPTZ, not null, default now())
      - updated_at (TIMESTAMPTZ, not null, default now())
      - completed_at (TIMESTAMPTZ, nullable)
  - workspace_activities:
      - id (UUID primary key)
      - workspace_id (UUID FK to saved_opportunities.id ON DELETE CASCADE)
      - actor_id (UUID FK to users.id ON DELETE CASCADE)
      - activity_type (VARCHAR 50, not null)
      - target_type (VARCHAR 50, nullable)
      - target_id (UUID, nullable)
      - description (TEXT, not null)
      - comment (TEXT, nullable)
      - old_state (JSONB, nullable)
      - new_state (JSONB, nullable)
      - created_at (TIMESTAMPTZ, not null, default now())

Backfills existing saved_opportunities so each owner has an OWNER row in workspace_members.
Updates chk_notifications_type constraint to include collaboration notification types.

Revision ID: 0016_phase4_6_collaboration
Revises:     0015_phase4_5_deadline_reminders_notifications
Create Date: 2026-09-19 14:40:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0016_phase4_6_collaboration"
down_revision: Union[str, None] = "0015_phase4_5_deadline_reminders_notifications"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. Create workspace_members ──
    op.create_table(
        "workspace_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("saved_opportunities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(50), nullable=False, server_default="CONTRIBUTOR"),
        sa.Column("status", sa.String(50), nullable=False, server_default="ACTIVE"),
        sa.Column("invited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("workspace_id", "user_id", name="uq_workspace_members_workspace_user"),
        sa.CheckConstraint("role IN ('OWNER', 'EDITOR', 'CONTRIBUTOR', 'VIEWER')", name="chk_workspace_members_role"),
        sa.CheckConstraint("status IN ('ACTIVE', 'INVITED', 'REMOVED')", name="chk_workspace_members_status"),
    )
    op.create_index("idx_workspace_members_ws_status", "workspace_members", ["workspace_id", "status"])
    op.create_index("idx_workspace_members_user_status", "workspace_members", ["user_id", "status"])
    op.create_index("idx_workspace_members_role", "workspace_members", ["role"])

    # ── 2. Create workspace_invitations ──
    op.create_table(
        "workspace_invitations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("saved_opportunities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("inviter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("invitee_email", sa.String(255), nullable=False),
        sa.Column("invitee_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("role", sa.String(50), nullable=False, server_default="CONTRIBUTOR"),
        sa.Column("token", sa.String(255), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="PENDING"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("token", name="uq_workspace_invitations_token"),
        sa.CheckConstraint("status IN ('PENDING', 'ACCEPTED', 'DECLINED', 'EXPIRED', 'REVOKED')", name="chk_workspace_invitations_status"),
        sa.CheckConstraint("role IN ('EDITOR', 'CONTRIBUTOR', 'VIEWER')", name="chk_workspace_invitations_role"),
    )
    op.create_index("idx_workspace_invitations_ws_status", "workspace_invitations", ["workspace_id", "status"])
    op.create_index("idx_workspace_invitations_email_status", "workspace_invitations", ["invitee_email", "status"])
    op.create_index("idx_workspace_invitations_token", "workspace_invitations", ["token"])

    # ── 3. Create workspace_tasks ──
    op.create_table(
        "workspace_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("saved_opportunities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("creator_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("assignee_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="TODO"),
        sa.Column("priority", sa.String(20), nullable=False, server_default="MEDIUM"),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submission_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("research_submissions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("research_submission_documents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('TODO', 'IN_PROGRESS', 'REVIEW', 'COMPLETED', 'CANCELLED')", name="chk_workspace_tasks_status"),
        sa.CheckConstraint("priority IN ('LOW', 'MEDIUM', 'HIGH', 'URGENT')", name="chk_workspace_tasks_priority"),
    )
    op.create_index("idx_workspace_tasks_ws_status", "workspace_tasks", ["workspace_id", "status"])
    op.create_index("idx_workspace_tasks_assignee_status", "workspace_tasks", ["assignee_id", "status"])
    op.create_index("idx_workspace_tasks_due", "workspace_tasks", ["due_at"])

    # ── 4. Create workspace_activities ──
    op.create_table(
        "workspace_activities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("saved_opportunities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("activity_type", sa.String(50), nullable=False),
        sa.Column("target_type", sa.String(50), nullable=True),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("old_state", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("new_state", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_workspace_activities_ws_created", "workspace_activities", ["workspace_id", "created_at"])
    op.create_index("idx_workspace_activities_actor", "workspace_activities", ["actor_id"])
    op.create_index("idx_workspace_activities_type", "workspace_activities", ["activity_type"])

    # ── 5. Backfill existing saved_opportunities as OWNER memberships ──
    op.execute(
        """
        INSERT INTO workspace_members (id, workspace_id, user_id, role, status, joined_at, created_at, updated_at)
        SELECT gen_random_uuid(), id, user_id, 'OWNER', 'ACTIVE', created_at, created_at, updated_at
        FROM saved_opportunities
        ON CONFLICT (workspace_id, user_id) DO NOTHING;
        """
    )

    # ── 6. Update chk_notifications_type constraint ──
    op.drop_constraint("chk_notifications_type", "notifications", type_="check")
    op.create_check_constraint(
        "chk_notifications_type",
        "notifications",
        "notification_type IN ('DEADLINE_UPCOMING', 'DEADLINE_TODAY', 'DEADLINE_EXTENDED', 'DEADLINE_MOVED_EARLIER', 'DEADLINE_CONFLICT', 'CALENDAR_EVENT_UPCOMING', 'SUBMISSION_STATUS_CHANGE', 'SYSTEM', 'WORKSPACE_INVITATION', 'INVITATION_ACCEPTED', 'MEMBER_ROLE_CHANGED', 'MEMBER_REMOVED', 'TASK_ASSIGNED', 'TASK_COMPLETED', 'DOCUMENT_UPDATED', 'COLLABORATION_ACTIVITY')",
    )


def downgrade() -> None:
    # ── 1. Revert chk_notifications_type constraint ──
    op.drop_constraint("chk_notifications_type", "notifications", type_="check")
    op.create_check_constraint(
        "chk_notifications_type",
        "notifications",
        "notification_type IN ('DEADLINE_UPCOMING', 'DEADLINE_TODAY', 'DEADLINE_EXTENDED', 'DEADLINE_MOVED_EARLIER', 'DEADLINE_CONFLICT', 'CALENDAR_EVENT_UPCOMING', 'SUBMISSION_STATUS_CHANGE', 'SYSTEM')",
    )

    # ── 2. Drop collaboration tables ──
    op.drop_table("workspace_activities")
    op.drop_table("workspace_tasks")
    op.drop_table("workspace_invitations")
    op.drop_table("workspace_members")
