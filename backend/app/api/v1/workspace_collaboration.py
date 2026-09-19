"""
FastAPI Router for Phase 4.6 Collaborative Research Management.

Provides endpoints for:
  - Workspace members (list, direct add, role update, remove)
  - Workspace invitations (list, create, revoke, accept, decline)
  - Collaborative tasks (create, list, get, update, assign, complete, reopen, delete)
  - Workspace activity stream & structured workflow comments
"""
from __future__ import annotations

import logging
from typing import Annotated
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import UserModel
from app.models.workspace_collaboration import (
    ActivityType,
    InvitationStatus,
    MemberStatus,
    TaskPriority,
    TaskStatus,
    WorkspaceMemberModel,
    WorkspaceRole,
    WorkspaceTaskModel,
)
from app.schemas.workspace_collaboration import (
    WorkspaceActivityListResponse,
    WorkspaceActivityRead,
    WorkspaceCommentCreate,
    WorkspaceInvitationCreate,
    WorkspaceInvitationCreateResponse,
    WorkspaceInvitationListResponse,
    WorkspaceInvitationRead,
    WorkspaceMemberAdd,
    WorkspaceMemberListResponse,
    WorkspaceMemberRead,
    WorkspaceMemberRoleUpdate,
    WorkspaceMemberUserSummary,
    WorkspaceTaskAssign,
    WorkspaceTaskCreate,
    WorkspaceTaskListResponse,
    WorkspaceTaskRead,
    WorkspaceTaskUpdate,
)
from app.services.workspace_collaboration_service import (
    WorkspaceCollaborationService,
)
from app.services.workspace_service import WorkspaceService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["workspace_collaboration"])


def resolve_current_user(
    db: Session,
    x_user_id: uuid.UUID | None,
) -> uuid.UUID:
    """Resolves authenticated user ID from X-User-ID header or active dev user."""
    if x_user_id is not None:
        return WorkspaceService.resolve_user_id(db, x_user_id)

    fallback_user = db.execute(
        select(UserModel).order_by(UserModel.created_at.asc())
    ).scalars().first()
    if fallback_user is not None:
        return fallback_user.id

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required: Please provide an 'X-User-ID' header.",
    )


def build_member_read(member: WorkspaceMemberModel) -> WorkspaceMemberRead:
    """Helper to serialize WorkspaceMemberModel to WorkspaceMemberRead schema."""
    user_summary = None
    if member.user:
        user_summary = WorkspaceMemberUserSummary(
            id=member.user.id,
            email=member.user.email,
            full_name=member.user.full_name,
            role=member.user.role,
            academic_status=member.user.research_profile.academic_status if member.user.research_profile else None,
        )

    return WorkspaceMemberRead(
        id=member.id,
        workspace_id=member.workspace_id,
        user_id=member.user_id,
        role=WorkspaceRole(member.role),
        status=MemberStatus(member.status),
        invited_at=member.invited_at,
        joined_at=member.joined_at,
        removed_at=member.removed_at,
        created_at=member.created_at,
        updated_at=member.updated_at,
        user=user_summary,
    )


def build_task_read(task: WorkspaceTaskModel) -> WorkspaceTaskRead:
    """Helper to serialize WorkspaceTaskModel to WorkspaceTaskRead schema."""
    return WorkspaceTaskRead(
        id=task.id,
        workspace_id=task.workspace_id,
        title=task.title,
        description=task.description,
        creator_id=task.creator_id,
        creator_name=task.creator.full_name if task.creator else None,
        assignee_id=task.assignee_id,
        assignee_name=task.assignee.full_name if task.assignee else None,
        status=TaskStatus(task.status),
        priority=TaskPriority(task.priority),
        due_at=task.due_at,
        submission_id=task.submission_id,
        document_id=task.document_id,
        created_at=task.created_at,
        updated_at=task.updated_at,
        completed_at=task.completed_at,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Members Endpoints
# ──────────────────────────────────────────────────────────────────────────────

@router.get(
    "/workspaces/{workspace_id}/members",
    response_model=WorkspaceMemberListResponse,
    status_code=status.HTTP_200_OK,
    summary="List workspace members",
)
@router.get(
    "/workspace/{workspace_id}/members",
    response_model=WorkspaceMemberListResponse,
    include_in_schema=False,
)
def list_workspace_members(
    workspace_id: uuid.UUID,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> WorkspaceMemberListResponse:
    user_id = resolve_current_user(db, x_user_id)
    members, total = WorkspaceCollaborationService.list_members(db, workspace_id, user_id)
    return WorkspaceMemberListResponse(
        items=[build_member_read(m) for m in members],
        total_count=total,
    )


@router.post(
    "/workspaces/{workspace_id}/members",
    response_model=WorkspaceMemberRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add member to workspace directly",
)
@router.post(
    "/workspace/{workspace_id}/members",
    response_model=WorkspaceMemberRead,
    include_in_schema=False,
)
def add_workspace_member(
    workspace_id: uuid.UUID,
    payload: WorkspaceMemberAdd,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> WorkspaceMemberRead:
    user_id = resolve_current_user(db, x_user_id)
    member = WorkspaceCollaborationService.add_member(db, workspace_id, user_id, payload)
    return build_member_read(member)


@router.patch(
    "/workspaces/{workspace_id}/members/{target_user_id}",
    response_model=WorkspaceMemberRead,
    status_code=status.HTTP_200_OK,
    summary="Update member role",
)
@router.patch(
    "/workspace/{workspace_id}/members/{target_user_id}",
    response_model=WorkspaceMemberRead,
    include_in_schema=False,
)
@router.patch(
    "/workspaces/{workspace_id}/members/{target_user_id}/role",
    response_model=WorkspaceMemberRead,
    include_in_schema=False,
)
@router.patch(
    "/workspace/{workspace_id}/members/{target_user_id}/role",
    response_model=WorkspaceMemberRead,
    include_in_schema=False,
)
def update_workspace_member_role(
    workspace_id: uuid.UUID,
    target_user_id: uuid.UUID,
    payload: WorkspaceMemberRoleUpdate,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> WorkspaceMemberRead:
    user_id = resolve_current_user(db, x_user_id)
    member = WorkspaceCollaborationService.update_member_role(
        db, workspace_id, user_id, target_user_id, payload
    )
    return build_member_read(member)


@router.delete(
    "/workspaces/{workspace_id}/members/{target_user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove member from workspace",
)
@router.delete(
    "/workspace/{workspace_id}/members/{target_user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    include_in_schema=False,
)
def remove_workspace_member(
    workspace_id: uuid.UUID,
    target_user_id: uuid.UUID,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> Response:
    user_id = resolve_current_user(db, x_user_id)
    WorkspaceCollaborationService.remove_member(db, workspace_id, user_id, target_user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ──────────────────────────────────────────────────────────────────────────────
# Invitations Endpoints
# ──────────────────────────────────────────────────────────────────────────────

@router.get(
    "/workspaces/{workspace_id}/invitations",
    response_model=WorkspaceInvitationListResponse,
    status_code=status.HTTP_200_OK,
    summary="List workspace invitations",
)
@router.get(
    "/workspace/{workspace_id}/invitations",
    response_model=WorkspaceInvitationListResponse,
    include_in_schema=False,
)
def list_workspace_invitations(
    workspace_id: uuid.UUID,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> WorkspaceInvitationListResponse:
    user_id = resolve_current_user(db, x_user_id)
    invitations, total = WorkspaceCollaborationService.list_invitations(db, workspace_id, user_id)
    return WorkspaceInvitationListResponse(
        items=[
            WorkspaceInvitationRead(
                id=inv.id,
                workspace_id=inv.workspace_id,
                inviter_id=inv.inviter_id,
                inviter_name=inv.inviter.full_name if inv.inviter else None,
                invitee_email=inv.invitee_email,
                invitee_user_id=inv.invitee_user_id,
                role=WorkspaceRole(inv.role),
                status=InvitationStatus(inv.status),
                created_at=inv.created_at,
                expires_at=inv.expires_at,
                accepted_at=inv.accepted_at,
                revoked_at=inv.revoked_at,
            )
            for inv in invitations
        ],
        total_count=total,
    )


@router.post(
    "/workspaces/{workspace_id}/invitations",
    response_model=WorkspaceInvitationCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create workspace invitation",
)
@router.post(
    "/workspace/{workspace_id}/invitations",
    response_model=WorkspaceInvitationCreateResponse,
    include_in_schema=False,
)
def create_workspace_invitation(
    workspace_id: uuid.UUID,
    payload: WorkspaceInvitationCreate,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> WorkspaceInvitationCreateResponse:
    user_id = resolve_current_user(db, x_user_id)
    invitation, token = WorkspaceCollaborationService.create_invitation(
        db, workspace_id, user_id, payload
    )
    return WorkspaceInvitationCreateResponse(
        invitation=WorkspaceInvitationRead(
            id=invitation.id,
            workspace_id=invitation.workspace_id,
            inviter_id=invitation.inviter_id,
            inviter_name=invitation.inviter.full_name if invitation.inviter else None,
            invitee_email=invitation.invitee_email,
            invitee_user_id=invitation.invitee_user_id,
            role=WorkspaceRole(invitation.role),
            status=InvitationStatus(invitation.status),
            created_at=invitation.created_at,
            expires_at=invitation.expires_at,
            accepted_at=invitation.accepted_at,
            revoked_at=invitation.revoked_at,
        ),
        token=token,
    )


@router.delete(
    "/workspaces/{workspace_id}/invitations/{invitation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke invitation",
)
@router.delete(
    "/workspace/{workspace_id}/invitations/{invitation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    include_in_schema=False,
)
def revoke_workspace_invitation(
    workspace_id: uuid.UUID,
    invitation_id: uuid.UUID,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> Response:
    user_id = resolve_current_user(db, x_user_id)
    WorkspaceCollaborationService.revoke_invitation(db, workspace_id, user_id, invitation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/workspaces/invitations/{token}/accept",
    response_model=WorkspaceMemberRead,
    status_code=status.HTTP_200_OK,
    summary="Accept invitation",
)
@router.post(
    "/workspace/invitations/{token}/accept",
    response_model=WorkspaceMemberRead,
    include_in_schema=False,
)
def accept_workspace_invitation(
    token: str,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> WorkspaceMemberRead:
    user_id = resolve_current_user(db, x_user_id)
    member = WorkspaceCollaborationService.accept_invitation(db, token, user_id)
    return build_member_read(member)


@router.post(
    "/workspaces/invitations/{token}/decline",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Decline invitation",
)
@router.post(
    "/workspace/invitations/{token}/decline",
    status_code=status.HTTP_204_NO_CONTENT,
    include_in_schema=False,
)
def decline_workspace_invitation(
    token: str,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> Response:
    user_id = resolve_current_user(db, x_user_id)
    WorkspaceCollaborationService.decline_invitation(db, token, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ──────────────────────────────────────────────────────────────────────────────
# Tasks Endpoints
# ──────────────────────────────────────────────────────────────────────────────

@router.get(
    "/workspaces/{workspace_id}/tasks",
    response_model=WorkspaceTaskListResponse,
    status_code=status.HTTP_200_OK,
    summary="List workspace tasks",
)
@router.get(
    "/workspace/{workspace_id}/tasks",
    response_model=WorkspaceTaskListResponse,
    include_in_schema=False,
)
def list_workspace_tasks(
    workspace_id: uuid.UUID,
    assignee_id: Annotated[uuid.UUID | None, Query(description="Filter by assignee user ID")] = None,
    status_filter: Annotated[TaskStatus | None, Query(alias="status", description="Filter by status")] = None,
    priority: Annotated[TaskPriority | None, Query(description="Filter by priority")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> WorkspaceTaskListResponse:
    user_id = resolve_current_user(db, x_user_id)
    tasks, total = WorkspaceCollaborationService.list_tasks(
        db=db,
        workspace_id=workspace_id,
        user_id=user_id,
        assignee_id=assignee_id,
        task_status=status_filter,
        priority=priority,
        limit=limit,
        offset=offset,
    )
    return WorkspaceTaskListResponse(
        items=[build_task_read(t) for t in tasks],
        total_count=total,
    )


@router.post(
    "/workspaces/{workspace_id}/tasks",
    response_model=WorkspaceTaskRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create workspace task",
)
@router.post(
    "/workspace/{workspace_id}/tasks",
    response_model=WorkspaceTaskRead,
    include_in_schema=False,
)
def create_workspace_task(
    workspace_id: uuid.UUID,
    payload: WorkspaceTaskCreate,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> WorkspaceTaskRead:
    user_id = resolve_current_user(db, x_user_id)
    task = WorkspaceCollaborationService.create_task(db, workspace_id, user_id, payload)
    return build_task_read(task)


@router.patch(
    "/workspaces/{workspace_id}/tasks/{task_id}",
    response_model=WorkspaceTaskRead,
    status_code=status.HTTP_200_OK,
    summary="Update workspace task",
)
@router.patch(
    "/workspace/{workspace_id}/tasks/{task_id}",
    response_model=WorkspaceTaskRead,
    include_in_schema=False,
)
def update_workspace_task(
    workspace_id: uuid.UUID,
    task_id: uuid.UUID,
    payload: WorkspaceTaskUpdate,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> WorkspaceTaskRead:
    user_id = resolve_current_user(db, x_user_id)
    task = WorkspaceCollaborationService.update_task(db, workspace_id, user_id, task_id, payload)
    return build_task_read(task)


@router.post(
    "/workspaces/{workspace_id}/tasks/{task_id}/assign",
    response_model=WorkspaceTaskRead,
    status_code=status.HTTP_200_OK,
    summary="Assign task",
)
@router.post(
    "/workspace/{workspace_id}/tasks/{task_id}/assign",
    response_model=WorkspaceTaskRead,
    include_in_schema=False,
)
def assign_workspace_task(
    workspace_id: uuid.UUID,
    task_id: uuid.UUID,
    payload: WorkspaceTaskAssign,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> WorkspaceTaskRead:
    user_id = resolve_current_user(db, x_user_id)
    task = WorkspaceCollaborationService.update_task(
        db, workspace_id, user_id, task_id, WorkspaceTaskUpdate(assignee_id=payload.assignee_id)
    )
    return build_task_read(task)


@router.post(
    "/workspaces/{workspace_id}/tasks/{task_id}/complete",
    response_model=WorkspaceTaskRead,
    status_code=status.HTTP_200_OK,
    summary="Complete task",
)
@router.post(
    "/workspace/{workspace_id}/tasks/{task_id}/complete",
    response_model=WorkspaceTaskRead,
    include_in_schema=False,
)
def complete_workspace_task(
    workspace_id: uuid.UUID,
    task_id: uuid.UUID,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> WorkspaceTaskRead:
    user_id = resolve_current_user(db, x_user_id)
    task = WorkspaceCollaborationService.update_task(
        db, workspace_id, user_id, task_id, WorkspaceTaskUpdate(status=TaskStatus.COMPLETED)
    )
    return build_task_read(task)


@router.post(
    "/workspaces/{workspace_id}/tasks/{task_id}/reopen",
    response_model=WorkspaceTaskRead,
    status_code=status.HTTP_200_OK,
    summary="Reopen task",
)
@router.post(
    "/workspace/{workspace_id}/tasks/{task_id}/reopen",
    response_model=WorkspaceTaskRead,
    include_in_schema=False,
)
def reopen_workspace_task(
    workspace_id: uuid.UUID,
    task_id: uuid.UUID,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> WorkspaceTaskRead:
    user_id = resolve_current_user(db, x_user_id)
    task = WorkspaceCollaborationService.update_task(
        db, workspace_id, user_id, task_id, WorkspaceTaskUpdate(status=TaskStatus.TODO)
    )
    return build_task_read(task)


@router.delete(
    "/workspaces/{workspace_id}/tasks/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete task",
)
@router.delete(
    "/workspace/{workspace_id}/tasks/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    include_in_schema=False,
)
def delete_workspace_task(
    workspace_id: uuid.UUID,
    task_id: uuid.UUID,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> Response:
    user_id = resolve_current_user(db, x_user_id)
    WorkspaceCollaborationService.delete_task(db, workspace_id, user_id, task_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ──────────────────────────────────────────────────────────────────────────────
# Activity & Structured Comments Endpoints
# ──────────────────────────────────────────────────────────────────────────────

@router.get(
    "/workspaces/{workspace_id}/activity",
    response_model=WorkspaceActivityListResponse,
    status_code=status.HTTP_200_OK,
    summary="List workspace activity stream",
)
@router.get(
    "/workspace/{workspace_id}/activity",
    response_model=WorkspaceActivityListResponse,
    include_in_schema=False,
)
def list_workspace_activity(
    workspace_id: uuid.UUID,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> WorkspaceActivityListResponse:
    user_id = resolve_current_user(db, x_user_id)
    activities, total = WorkspaceCollaborationService.list_activities(
        db=db,
        workspace_id=workspace_id,
        user_id=user_id,
        limit=limit,
        offset=offset,
    )
    return WorkspaceActivityListResponse(
        items=[
            WorkspaceActivityRead(
                id=act.id,
                workspace_id=act.workspace_id,
                actor_id=act.actor_id,
                actor_name=act.actor.full_name if act.actor else None,
                activity_type=ActivityType(act.activity_type),
                target_type=act.target_type,
                target_id=act.target_id,
                description=act.description,
                comment=act.comment,
                old_state=act.old_state,
                new_state=act.new_state,
                created_at=act.created_at,
            )
            for act in activities
        ],
        total_count=total,
    )


@router.post(
    "/workspaces/{workspace_id}/activity/comments",
    response_model=WorkspaceActivityRead,
    status_code=status.HTTP_201_CREATED,
    summary="Post workflow comment to workspace activity feed",
)
@router.post(
    "/workspace/{workspace_id}/activity/comments",
    response_model=WorkspaceActivityRead,
    include_in_schema=False,
)
@router.post(
    "/workspaces/{workspace_id}/comments",
    response_model=WorkspaceActivityRead,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
@router.post(
    "/workspace/{workspace_id}/comments",
    response_model=WorkspaceActivityRead,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
def post_workspace_comment(
    workspace_id: uuid.UUID,
    payload: WorkspaceCommentCreate,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> WorkspaceActivityRead:
    user_id = resolve_current_user(db, x_user_id)
    activity = WorkspaceCollaborationService.add_comment(db, workspace_id, user_id, payload)
    return WorkspaceActivityRead(
        id=activity.id,
        workspace_id=activity.workspace_id,
        actor_id=activity.actor_id,
        actor_name=activity.actor.full_name if activity.actor else None,
        activity_type=ActivityType(activity.activity_type),
        target_type=activity.target_type,
        target_id=activity.target_id,
        description=activity.description,
        comment=activity.comment,
        old_state=activity.old_state,
        new_state=activity.new_state,
        created_at=activity.created_at,
    )
