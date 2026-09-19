from __future__ import annotations

from datetime import datetime
from typing import Any
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.workspace_collaboration import (
    ActivityType,
    InvitationStatus,
    MemberStatus,
    TaskPriority,
    TaskStatus,
    WorkspaceRole,
)


# ── Member Schemas ──

class WorkspaceMemberUserSummary(BaseModel):
    """User identity summary for workspace member display."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    role: str = "STUDENT"
    academic_status: str | None = None


class WorkspaceMemberRead(BaseModel):
    """Schema for a workspace member record."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    role: WorkspaceRole
    status: MemberStatus
    invited_at: datetime | None = None
    joined_at: datetime | None = None
    removed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    user: WorkspaceMemberUserSummary | None = None


class WorkspaceMemberAdd(BaseModel):
    """Payload to directly add a member (Owner/Admin)."""
    user_id: uuid.UUID
    role: WorkspaceRole = WorkspaceRole.CONTRIBUTOR


class WorkspaceMemberRoleUpdate(BaseModel):
    """Payload to update an existing member's role."""
    role: WorkspaceRole


class WorkspaceMemberListResponse(BaseModel):
    """Paginated or complete list of workspace members."""
    items: list[WorkspaceMemberRead]
    total_count: int


# ── Invitation Schemas ──

class WorkspaceInvitationRead(BaseModel):
    """Schema for viewing a workspace invitation."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    inviter_id: uuid.UUID
    inviter_name: str | None = None
    invitee_email: str
    invitee_user_id: uuid.UUID | None = None
    role: WorkspaceRole
    status: InvitationStatus
    created_at: datetime
    expires_at: datetime
    accepted_at: datetime | None = None
    revoked_at: datetime | None = None


class WorkspaceInvitationCreate(BaseModel):
    """Payload to invite a new collaborator to a workspace."""
    invitee_email: str = Field(..., min_length=3, max_length=255)
    role: WorkspaceRole = WorkspaceRole.CONTRIBUTOR
    expires_in_days: int | None = 7


class WorkspaceInvitationCreateResponse(BaseModel):
    """Response returned when an invitation is generated."""
    invitation: WorkspaceInvitationRead
    token: str


class WorkspaceInvitationListResponse(BaseModel):
    """List of pending or historical invitations for a workspace."""
    items: list[WorkspaceInvitationRead]
    total_count: int


# ── Task Schemas ──

class WorkspaceTaskRead(BaseModel):
    """Schema for viewing a workspace task."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    title: str
    description: str | None = None
    creator_id: uuid.UUID
    creator_name: str | None = None
    assignee_id: uuid.UUID | None = None
    assignee_name: str | None = None
    status: TaskStatus
    priority: TaskPriority
    due_at: datetime | None = None
    submission_id: uuid.UUID | None = None
    document_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


class WorkspaceTaskCreate(BaseModel):
    """Payload to create a new collaborative task in a workspace."""
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    assignee_id: uuid.UUID | None = None
    priority: TaskPriority = TaskPriority.MEDIUM
    due_at: datetime | None = None
    submission_id: uuid.UUID | None = None
    document_id: uuid.UUID | None = None


class WorkspaceTaskUpdate(BaseModel):
    """Payload to update an existing workspace task."""
    title: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    assignee_id: uuid.UUID | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    due_at: datetime | None = None
    submission_id: uuid.UUID | None = None
    document_id: uuid.UUID | None = None


class WorkspaceTaskAssign(BaseModel):
    """Payload to assign or unassign a task."""
    assignee_id: uuid.UUID | None = None


class WorkspaceTaskListResponse(BaseModel):
    """List of tasks with summary count."""
    items: list[WorkspaceTaskRead]
    total_count: int


# ── Activity & Comment Schemas ──

class WorkspaceActivityRead(BaseModel):
    """Schema for a workspace activity audit or comment record."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    actor_id: uuid.UUID
    actor_name: str | None = None
    activity_type: ActivityType
    target_type: str | None = None
    target_id: uuid.UUID | None = None
    description: str
    comment: str | None = None
    old_state: dict[str, Any] | None = None
    new_state: dict[str, Any] | None = None
    created_at: datetime


class WorkspaceCommentCreate(BaseModel):
    """Payload to post a structured comment/note to the workspace activity feed."""
    comment: str = Field(..., min_length=1)
    target_type: str | None = None
    target_id: uuid.UUID | None = None


class WorkspaceActivityListResponse(BaseModel):
    """List of activity events with total count."""
    items: list[WorkspaceActivityRead]
    total_count: int
