from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, TYPE_CHECKING
import uuid

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.research_submission import ResearchSubmissionModel
    from app.models.saved_opportunity import SavedOpportunityModel
    from app.models.submission_document import ResearchSubmissionDocumentModel
    from app.models.user import UserModel


class WorkspaceRole(str, Enum):
    """Supported deterministic workspace collaboration roles (Phase 4.6)."""

    OWNER = "OWNER"
    EDITOR = "EDITOR"
    CONTRIBUTOR = "CONTRIBUTOR"
    VIEWER = "VIEWER"


class MemberStatus(str, Enum):
    """Lifecycle status of a workspace membership (Phase 4.6)."""

    ACTIVE = "ACTIVE"
    INVITED = "INVITED"
    REMOVED = "REMOVED"


class InvitationStatus(str, Enum):
    """Status of an invitation to join a research workspace (Phase 4.6)."""

    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


class TaskStatus(str, Enum):
    """Execution status of a workspace collaborative task (Phase 4.6)."""

    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    REVIEW = "REVIEW"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class TaskPriority(str, Enum):
    """Priority level for workspace collaborative tasks (Phase 4.6)."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"


class ActivityType(str, Enum):
    """Categorization for structured workspace collaboration events (Phase 4.6)."""

    MEMBER_JOINED = "MEMBER_JOINED"
    MEMBER_REMOVED = "MEMBER_REMOVED"
    MEMBER_INVITED = "MEMBER_INVITED"
    ROLE_CHANGED = "ROLE_CHANGED"
    TASK_CREATED = "TASK_CREATED"
    TASK_ASSIGNED = "TASK_ASSIGNED"
    TASK_COMPLETED = "TASK_COMPLETED"
    TASK_UPDATED = "TASK_UPDATED"
    DOCUMENT_UPDATED = "DOCUMENT_UPDATED"
    SUBMISSION_UPDATED = "SUBMISSION_UPDATED"
    DEADLINE_CHANGED = "DEADLINE_CHANGED"
    COMMENT_ADDED = "COMMENT_ADDED"
    INVITATION_SENT = "INVITATION_SENT"
    INVITATION_ACCEPTED = "INVITATION_ACCEPTED"
    INVITATION_REVOKED = "INVITATION_REVOKED"


class WorkspaceMemberModel(Base):
    """
    Workspace Member entity (Phase 4.6).

    Links a user to a specific research workspace with an assigned role
    and lifecycle status.
    """

    __tablename__ = "workspace_members"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "user_id",
            name="uq_workspace_members_workspace_user",
        ),
        CheckConstraint(
            "role IN ('OWNER', 'EDITOR', 'CONTRIBUTOR', 'VIEWER')",
            name="chk_workspace_members_role",
        ),
        CheckConstraint(
            "status IN ('ACTIVE', 'INVITED', 'REMOVED')",
            name="chk_workspace_members_status",
        ),
        Index("idx_workspace_members_ws_status", "workspace_id", "status"),
        Index("idx_workspace_members_user_status", "user_id", "status"),
        Index("idx_workspace_members_role", "role"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("saved_opportunities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Associated workspace (saved opportunity) ID",
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Member user ID",
    )
    role: Mapped[str] = mapped_column(
        String(50),
        default=WorkspaceRole.CONTRIBUTOR.value,
        server_default=WorkspaceRole.CONTRIBUTOR.value,
        nullable=False,
        comment="Member role: OWNER, EDITOR, CONTRIBUTOR, VIEWER",
    )
    status: Mapped[str] = mapped_column(
        String(50),
        default=MemberStatus.ACTIVE.value,
        server_default=MemberStatus.ACTIVE.value,
        nullable=False,
        comment="Membership status: ACTIVE, INVITED, REMOVED",
    )
    invited_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when user was invited",
    )
    joined_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when user joined the workspace",
    )
    removed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when user was removed from workspace",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    workspace: Mapped["SavedOpportunityModel"] = relationship(
        back_populates="members",
    )
    user: Mapped["UserModel"] = relationship()


class WorkspaceInvitationModel(Base):
    """
    Workspace Invitation entity (Phase 4.6).

    Tracks an invitation to an external or existing researcher to join
    a research workspace with an assigned role.
    """

    __tablename__ = "workspace_invitations"
    __table_args__ = (
        UniqueConstraint("token", name="uq_workspace_invitations_token"),
        CheckConstraint(
            "status IN ('PENDING', 'ACCEPTED', 'DECLINED', 'EXPIRED', 'REVOKED')",
            name="chk_workspace_invitations_status",
        ),
        CheckConstraint(
            "role IN ('EDITOR', 'CONTRIBUTOR', 'VIEWER')",
            name="chk_workspace_invitations_role",
        ),
        Index("idx_workspace_invitations_ws_status", "workspace_id", "status"),
        Index("idx_workspace_invitations_email_status", "invitee_email", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("saved_opportunities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Associated workspace (saved opportunity) ID",
    )
    inviter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User ID of the inviter",
    )
    invitee_email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="Email address of invitee",
    )
    invitee_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="User ID if invitee already exists in system",
    )
    role: Mapped[str] = mapped_column(
        String(50),
        default=WorkspaceRole.CONTRIBUTOR.value,
        server_default=WorkspaceRole.CONTRIBUTOR.value,
        nullable=False,
        comment="Proposed role: EDITOR, CONTRIBUTOR, VIEWER",
    )
    token: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
        comment="Cryptographically secure invitation token",
    )
    status: Mapped[str] = mapped_column(
        String(50),
        default=InvitationStatus.PENDING.value,
        server_default=InvitationStatus.PENDING.value,
        nullable=False,
        index=True,
        comment="Status: PENDING, ACCEPTED, DECLINED, EXPIRED, REVOKED",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Timestamp when invitation expires",
    )
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    workspace: Mapped["SavedOpportunityModel"] = relationship(
        back_populates="invitations",
    )
    inviter: Mapped["UserModel"] = relationship(foreign_keys=[inviter_id])
    invitee_user: Mapped["UserModel | None"] = relationship(
        foreign_keys=[invitee_user_id]
    )


class WorkspaceTaskModel(Base):
    """
    Workspace Task entity (Phase 4.6).

    Represents an actionable research preparation task scoped to a workspace,
    with optional linkage to a submission or document.
    """

    __tablename__ = "workspace_tasks"
    __table_args__ = (
        CheckConstraint(
            "status IN ('TODO', 'IN_PROGRESS', 'REVIEW', 'COMPLETED', 'CANCELLED')",
            name="chk_workspace_tasks_status",
        ),
        CheckConstraint(
            "priority IN ('LOW', 'MEDIUM', 'HIGH', 'URGENT')",
            name="chk_workspace_tasks_priority",
        ),
        Index("idx_workspace_tasks_ws_status", "workspace_id", "status"),
        Index("idx_workspace_tasks_assignee_status", "assignee_id", "status"),
        Index("idx_workspace_tasks_due", "due_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("saved_opportunities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Associated workspace (saved opportunity) ID",
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Task headline / title",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Detailed task description",
    )
    creator_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Task creator user ID",
    )
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Assigned member user ID",
    )
    status: Mapped[str] = mapped_column(
        String(50),
        default=TaskStatus.TODO.value,
        server_default=TaskStatus.TODO.value,
        nullable=False,
        index=True,
        comment="Status: TODO, IN_PROGRESS, REVIEW, COMPLETED, CANCELLED",
    )
    priority: Mapped[str] = mapped_column(
        String(20),
        default=TaskPriority.MEDIUM.value,
        server_default=TaskPriority.MEDIUM.value,
        nullable=False,
        index=True,
        comment="Priority: LOW, MEDIUM, HIGH, URGENT",
    )
    due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="Task deadline / due date",
    )
    submission_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research_submissions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Optional linked research submission",
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research_submission_documents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Optional linked submission document",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when task was marked completed",
    )

    # Relationships
    workspace: Mapped["SavedOpportunityModel"] = relationship(
        back_populates="tasks",
    )
    creator: Mapped["UserModel"] = relationship(foreign_keys=[creator_id])
    assignee: Mapped["UserModel | None"] = relationship(
        foreign_keys=[assignee_id]
    )
    submission: Mapped["ResearchSubmissionModel | None"] = relationship(
        foreign_keys=[submission_id]
    )
    document: Mapped["ResearchSubmissionDocumentModel | None"] = relationship(
        foreign_keys=[document_id]
    )


class WorkspaceActivityModel(Base):
    """
    Workspace Activity entity (Phase 4.6).

    Append-only audit and collaboration stream capturing all workspace events,
    stage transitions, and structured comments.
    """

    __tablename__ = "workspace_activities"
    __table_args__ = (
        Index("idx_workspace_activities_ws_created", "workspace_id", "created_at"),
        Index("idx_workspace_activities_actor", "actor_id"),
        Index("idx_workspace_activities_type", "activity_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("saved_opportunities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Associated workspace (saved opportunity) ID",
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User who performed the activity",
    )
    activity_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Activity type: MEMBER_JOINED, TASK_CREATED, etc.",
    )
    target_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Target resource category: MEMBER, TASK, DOCUMENT, etc.",
    )
    target_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="ID of target resource",
    )
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Human-readable event summary",
    )
    comment: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Optional user comment or annotation",
    )
    old_state: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Previous state before mutation",
    )
    new_state: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="New state after mutation",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # Relationships
    workspace: Mapped["SavedOpportunityModel"] = relationship(
        back_populates="activities",
    )
    actor: Mapped["UserModel"] = relationship()
