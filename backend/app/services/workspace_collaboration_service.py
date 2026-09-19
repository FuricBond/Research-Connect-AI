"""
Workspace Collaboration Service (Phase 4.6).

Provides deterministic business logic for research workspace collaboration:
  - Member management (list, add, update role, remove)
  - Invitation lifecycle (create, accept, decline, revoke, token generation)
  - Collaborative task management (create, list, assign, complete, reopen, delete)
  - Structured activity stream & workflow comments
  - Notification triggers using Phase 4.5 infrastructure
  - Zero N+1 query patterns with eager loading
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import logging
import secrets
from typing import Any, Sequence
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models.notification import (
    DeliveryChannel,
    DeliveryStatus,
    NotificationModel,
    NotificationPreferenceModel,
    NotificationType,
)
from app.models.research_profile import ResearchProfileModel
from app.models.research_submission import ResearchSubmissionModel
from app.models.saved_opportunity import SavedOpportunityModel
from app.models.submission_document import ResearchSubmissionDocumentModel
from app.models.user import UserModel
from app.models.workspace_collaboration import (
    ActivityType,
    InvitationStatus,
    MemberStatus,
    TaskPriority,
    TaskStatus,
    WorkspaceActivityModel,
    WorkspaceInvitationModel,
    WorkspaceMemberModel,
    WorkspaceRole,
    WorkspaceTaskModel,
)
from app.schemas.workspace_collaboration import (
    WorkspaceCommentCreate,
    WorkspaceInvitationCreate,
    WorkspaceMemberAdd,
    WorkspaceMemberRoleUpdate,
    WorkspaceTaskCreate,
    WorkspaceTaskUpdate,
)
from app.services.notification_service import NotificationService
from app.services.workspace_authorization_service import (
    WorkspaceAuthorizationService,
)

logger = logging.getLogger(__name__)


class WorkspaceCollaborationService:
    """Service orchestrating collaborative workspace operations."""

    # ──────────────────────────────────────────────────────────────────────────
    # Members Management
    # ──────────────────────────────────────────────────────────────────────────

    @classmethod
    def list_members(
        cls,
        db: Session,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> tuple[list[WorkspaceMemberModel], int]:
        """
        Lists all active members in a workspace.
        Requires VIEWER role or higher.
        """
        WorkspaceAuthorizationService.verify_workspace_access(
            db, workspace_id, user_id, WorkspaceRole.VIEWER
        )

        query = (
            select(WorkspaceMemberModel)
            .where(
                WorkspaceMemberModel.workspace_id == workspace_id,
                WorkspaceMemberModel.status == MemberStatus.ACTIVE.value,
            )
            .options(
                joinedload(WorkspaceMemberModel.user).joinedload(UserModel.research_profile)
            )
            .order_by(
                WorkspaceMemberModel.role.asc(),
                WorkspaceMemberModel.created_at.asc(),
            )
        )
        members = list(db.execute(query).scalars().all())
        return members, len(members)

    @classmethod
    def add_member(
        cls,
        db: Session,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        payload: WorkspaceMemberAdd,
    ) -> WorkspaceMemberModel:
        """
        Directly adds a member to a workspace.
        Requires OWNER role.
        """
        WorkspaceAuthorizationService.verify_workspace_access(
            db, workspace_id, actor_id, WorkspaceRole.OWNER
        )

        target_user = db.get(UserModel, payload.user_id)
        if target_user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User '{payload.user_id}' not found.",
            )

        existing = db.execute(
            select(WorkspaceMemberModel).where(
                WorkspaceMemberModel.workspace_id == workspace_id,
                WorkspaceMemberModel.user_id == payload.user_id,
            )
        ).scalar_one_or_none()

        now = datetime.now(timezone.utc)

        if existing is not None:
            if existing.status == MemberStatus.ACTIVE.value:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="User is already an active member of this workspace.",
                )
            # Reactivate previously removed member
            old_role = existing.role
            existing.status = MemberStatus.ACTIVE.value
            existing.role = payload.role.value
            existing.joined_at = now
            existing.removed_at = None
            member = existing
            cls.record_activity(
                db,
                workspace_id=workspace_id,
                actor_id=actor_id,
                activity_type=ActivityType.MEMBER_JOINED,
                target_type="MEMBER",
                target_id=member.id,
                description=f"Re-added {target_user.full_name} to workspace as {payload.role.value}.",
                old_state={"role": old_role, "status": MemberStatus.REMOVED.value},
                new_state={"role": payload.role.value, "status": MemberStatus.ACTIVE.value},
            )
        else:
            member = WorkspaceMemberModel(
                workspace_id=workspace_id,
                user_id=payload.user_id,
                role=payload.role.value,
                status=MemberStatus.ACTIVE.value,
                joined_at=now,
            )
            db.add(member)
            db.flush()

            cls.record_activity(
                db,
                workspace_id=workspace_id,
                actor_id=actor_id,
                activity_type=ActivityType.MEMBER_JOINED,
                target_type="MEMBER",
                target_id=member.id,
                description=f"Added {target_user.full_name} to workspace as {payload.role.value}.",
                new_state={"role": payload.role.value, "status": MemberStatus.ACTIVE.value},
            )

        # Notify the added member
        cls.send_collaboration_notification(
            db,
            recipient_user_id=payload.user_id,
            notification_type=NotificationType.COLLABORATION_ACTIVITY,
            title="Added to Research Workspace",
            body=f"You were added to a research workspace as {payload.role.value}.",
            source_id=workspace_id,
        )

        db.commit()
        db.refresh(member)
        return member

    @classmethod
    def update_member_role(
        cls,
        db: Session,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        target_user_id: uuid.UUID,
        payload: WorkspaceMemberRoleUpdate,
    ) -> WorkspaceMemberModel:
        """
        Updates a member's role.
        Requires OWNER role. Prevents removing the last active OWNER.
        """
        WorkspaceAuthorizationService.verify_workspace_access(
            db, workspace_id, actor_id, WorkspaceRole.OWNER
        )

        member = db.execute(
            select(WorkspaceMemberModel).where(
                WorkspaceMemberModel.workspace_id == workspace_id,
                WorkspaceMemberModel.user_id == target_user_id,
                WorkspaceMemberModel.status == MemberStatus.ACTIVE.value,
            )
        ).scalar_one_or_none()

        if member is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Active member '{target_user_id}' not found in this workspace.",
            )

        # If demoting an OWNER, ensure at least one other active OWNER remains
        if member.role == WorkspaceRole.OWNER.value and payload.role != WorkspaceRole.OWNER:
            other_owners = db.execute(
                select(func.count(WorkspaceMemberModel.id)).where(
                    WorkspaceMemberModel.workspace_id == workspace_id,
                    WorkspaceMemberModel.role == WorkspaceRole.OWNER.value,
                    WorkspaceMemberModel.status == MemberStatus.ACTIVE.value,
                    WorkspaceMemberModel.user_id != target_user_id,
                )
            ).scalar() or 0
            if other_owners == 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot demote the only active owner of the workspace.",
                )

        old_role = member.role
        member.role = payload.role.value

        cls.record_activity(
            db,
            workspace_id=workspace_id,
            actor_id=actor_id,
            activity_type=ActivityType.ROLE_CHANGED,
            target_type="MEMBER",
            target_id=member.id,
            description=f"Changed role of member from {old_role} to {payload.role.value}.",
            old_state={"role": old_role},
            new_state={"role": payload.role.value},
        )

        # Notify the affected member
        cls.send_collaboration_notification(
            db,
            recipient_user_id=target_user_id,
            notification_type=NotificationType.MEMBER_ROLE_CHANGED,
            title="Workspace Role Updated",
            body=f"Your role in the research workspace was updated to {payload.role.value}.",
            source_id=workspace_id,
        )

        db.commit()
        db.refresh(member)
        return member

    @classmethod
    def remove_member(
        cls,
        db: Session,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        target_user_id: uuid.UUID,
    ) -> None:
        """
        Removes a member from a workspace.
        OWNER can remove any member. Any member can remove (leave) themselves.
        Cannot remove the only active OWNER.
        """
        if actor_id != target_user_id:
            WorkspaceAuthorizationService.verify_workspace_access(
                db, workspace_id, actor_id, WorkspaceRole.OWNER
            )
        else:
            WorkspaceAuthorizationService.verify_workspace_access(
                db, workspace_id, actor_id, WorkspaceRole.VIEWER
            )

        member = db.execute(
            select(WorkspaceMemberModel).where(
                WorkspaceMemberModel.workspace_id == workspace_id,
                WorkspaceMemberModel.user_id == target_user_id,
                WorkspaceMemberModel.status == MemberStatus.ACTIVE.value,
            )
        ).scalar_one_or_none()

        if member is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Active member '{target_user_id}' not found in this workspace.",
            )

        # Prevent removing the only OWNER
        if member.role == WorkspaceRole.OWNER.value:
            other_owners = db.execute(
                select(func.count(WorkspaceMemberModel.id)).where(
                    WorkspaceMemberModel.workspace_id == workspace_id,
                    WorkspaceMemberModel.role == WorkspaceRole.OWNER.value,
                    WorkspaceMemberModel.status == MemberStatus.ACTIVE.value,
                    WorkspaceMemberModel.user_id != target_user_id,
                )
            ).scalar() or 0
            if other_owners == 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot remove the only active owner of the workspace.",
                )

        now = datetime.now(timezone.utc)
        member.status = MemberStatus.REMOVED.value
        member.removed_at = now

        cls.record_activity(
            db,
            workspace_id=workspace_id,
            actor_id=actor_id,
            activity_type=ActivityType.MEMBER_REMOVED,
            target_type="MEMBER",
            target_id=member.id,
            description=f"Removed member from workspace.",
            old_state={"status": MemberStatus.ACTIVE.value},
            new_state={"status": MemberStatus.REMOVED.value},
        )

        if actor_id != target_user_id:
            cls.send_collaboration_notification(
                db,
                recipient_user_id=target_user_id,
                notification_type=NotificationType.MEMBER_REMOVED,
                title="Removed from Research Workspace",
                body="You were removed from the research workspace.",
                source_id=workspace_id,
            )

        db.commit()

    # ──────────────────────────────────────────────────────────────────────────
    # Invitations Workflow
    # ──────────────────────────────────────────────────────────────────────────

    @classmethod
    def list_invitations(
        cls,
        db: Session,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> tuple[list[WorkspaceInvitationModel], int]:
        """
        Lists pending invitations for a workspace.
        Requires VIEWER role or higher.
        """
        WorkspaceAuthorizationService.verify_workspace_access(
            db, workspace_id, user_id, WorkspaceRole.VIEWER
        )

        query = (
            select(WorkspaceInvitationModel)
            .where(
                WorkspaceInvitationModel.workspace_id == workspace_id,
                WorkspaceInvitationModel.status == InvitationStatus.PENDING.value,
            )
            .options(joinedload(WorkspaceInvitationModel.inviter))
            .order_by(WorkspaceInvitationModel.created_at.desc())
        )
        invitations = list(db.execute(query).scalars().all())
        return invitations, len(invitations)

    @classmethod
    def create_invitation(
        cls,
        db: Session,
        workspace_id: uuid.UUID,
        inviter_id: uuid.UUID,
        payload: WorkspaceInvitationCreate,
    ) -> tuple[WorkspaceInvitationModel, str]:
        """
        Creates a new workspace invitation with a secure token.
        Requires OWNER role.
        """
        WorkspaceAuthorizationService.verify_workspace_access(
            db, workspace_id, inviter_id, WorkspaceRole.OWNER
        )

        if payload.role == WorkspaceRole.OWNER:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot invite as OWNER. Allowed roles: EDITOR, CONTRIBUTOR, VIEWER.",
            )

        email = payload.invitee_email.strip().lower()

        # Check if user already exists
        target_user = db.execute(
            select(UserModel).where(func.lower(UserModel.email) == email)
        ).scalar_one_or_none()

        if target_user is not None:
            # Check if already an active member
            member = db.execute(
                select(WorkspaceMemberModel).where(
                    WorkspaceMemberModel.workspace_id == workspace_id,
                    WorkspaceMemberModel.user_id == target_user.id,
                    WorkspaceMemberModel.status == MemberStatus.ACTIVE.value,
                )
            ).scalar_one_or_none()
            if member is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"User '{email}' is already an active member of this workspace.",
                )

        # Check for existing active pending invitation
        now = datetime.now(timezone.utc)
        existing_inv = db.execute(
            select(WorkspaceInvitationModel).where(
                WorkspaceInvitationModel.workspace_id == workspace_id,
                func.lower(WorkspaceInvitationModel.invitee_email) == email,
                WorkspaceInvitationModel.status == InvitationStatus.PENDING.value,
            )
        ).scalar_one_or_none()

        if existing_inv is not None:
            existing_expires = existing_inv.expires_at
            if existing_expires.tzinfo is None:
                existing_expires = existing_expires.replace(tzinfo=timezone.utc)
            if existing_expires > now:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"A pending invitation already exists for '{email}'.",
                )
            else:
                existing_inv.status = InvitationStatus.EXPIRED.value

        raw_token = secrets.token_urlsafe(32)
        days = payload.expires_in_days if getattr(payload, "expires_in_days", None) is not None else 7
        expires_at = now + timedelta(days=days)

        invitation = WorkspaceInvitationModel(
            workspace_id=workspace_id,
            inviter_id=inviter_id,
            invitee_email=email,
            invitee_user_id=target_user.id if target_user else None,
            role=payload.role.value,
            token=raw_token,
            status=InvitationStatus.PENDING.value,
            expires_at=expires_at,
        )
        db.add(invitation)
        db.flush()

        cls.record_activity(
            db,
            workspace_id=workspace_id,
            actor_id=inviter_id,
            activity_type=ActivityType.INVITATION_SENT,
            target_type="INVITATION",
            target_id=invitation.id,
            description=f"Sent invitation to {email} as {payload.role.value}.",
            new_state={"role": payload.role.value, "expires_at": expires_at.isoformat()},
        )

        if target_user is not None:
            cls.send_collaboration_notification(
                db,
                recipient_user_id=target_user.id,
                notification_type=NotificationType.WORKSPACE_INVITATION,
                title="Invitation to Research Workspace",
                body=f"You have been invited to collaborate on a research workspace as {payload.role.value}.",
                source_id=workspace_id,
            )

        db.commit()
        db.refresh(invitation)
        return invitation, raw_token

    @classmethod
    def accept_invitation(
        cls,
        db: Session,
        token: str,
        user_id: uuid.UUID,
    ) -> WorkspaceMemberModel:
        """
        Accepts a workspace invitation.
        Guarantees idempotency and verifies recipient identity.
        """
        invitation = db.execute(
            select(WorkspaceInvitationModel).where(WorkspaceInvitationModel.token == token)
        ).scalar_one_or_none()

        if invitation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invalid invitation token.",
            )

        # Idempotent return if already accepted
        if invitation.status == InvitationStatus.ACCEPTED.value:
            existing_member = db.execute(
                select(WorkspaceMemberModel).where(
                    WorkspaceMemberModel.workspace_id == invitation.workspace_id,
                    WorkspaceMemberModel.user_id == user_id,
                    WorkspaceMemberModel.status == MemberStatus.ACTIVE.value,
                )
            ).scalar_one_or_none()
            if existing_member is not None:
                return existing_member

        if invitation.status == InvitationStatus.REVOKED.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This invitation has been revoked by the workspace owner.",
            )

        if invitation.status == InvitationStatus.DECLINED.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This invitation was previously declined.",
            )

        now = datetime.now(timezone.utc)
        inv_expires = invitation.expires_at
        if inv_expires.tzinfo is None:
            inv_expires = inv_expires.replace(tzinfo=timezone.utc)
        if now > inv_expires:
            invitation.status = InvitationStatus.EXPIRED.value
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This invitation has expired.",
            )

        user = db.get(UserModel, user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found.",
            )

        # Verify email match if invitee_user_id was not explicitly specified
        if invitation.invitee_user_id is not None and invitation.invitee_user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This invitation was intended for a different user account.",
            )
        elif invitation.invitee_user_id is None and user.email.lower() != invitation.invitee_email.lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This invitation was sent to '{invitation.invitee_email}', but your account email is '{user.email}'.",
            )

        # Create or activate membership
        member = db.execute(
            select(WorkspaceMemberModel).where(
                WorkspaceMemberModel.workspace_id == invitation.workspace_id,
                WorkspaceMemberModel.user_id == user_id,
            )
        ).scalar_one_or_none()

        if member is not None:
            member.status = MemberStatus.ACTIVE.value
            member.role = invitation.role
            member.joined_at = now
            member.removed_at = None
        else:
            member = WorkspaceMemberModel(
                workspace_id=invitation.workspace_id,
                user_id=user_id,
                role=invitation.role,
                status=MemberStatus.ACTIVE.value,
                joined_at=now,
            )
            db.add(member)

        invitation.status = InvitationStatus.ACCEPTED.value
        invitation.accepted_at = now
        invitation.invitee_user_id = user_id

        cls.record_activity(
            db,
            workspace_id=invitation.workspace_id,
            actor_id=user_id,
            activity_type=ActivityType.INVITATION_ACCEPTED,
            target_type="INVITATION",
            target_id=invitation.id,
            description=f"{user.full_name} accepted the invitation to join as {invitation.role}.",
        )
        cls.record_activity(
            db,
            workspace_id=invitation.workspace_id,
            actor_id=user_id,
            activity_type=ActivityType.MEMBER_JOINED,
            target_type="MEMBER",
            target_id=member.id,
            description=f"{user.full_name} joined the workspace.",
        )

        # Notify inviter
        cls.send_collaboration_notification(
            db,
            recipient_user_id=invitation.inviter_id,
            notification_type=NotificationType.INVITATION_ACCEPTED,
            title="Invitation Accepted",
            body=f"{user.full_name} accepted your invitation to join the workspace.",
            source_id=invitation.workspace_id,
        )

        db.commit()
        db.refresh(member)
        return member

    @classmethod
    def decline_invitation(
        cls,
        db: Session,
        token: str,
        user_id: uuid.UUID,
    ) -> None:
        """Declines an invitation."""
        invitation = db.execute(
            select(WorkspaceInvitationModel).where(WorkspaceInvitationModel.token == token)
        ).scalar_one_or_none()

        if invitation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invalid invitation token.",
            )

        invitation.status = InvitationStatus.DECLINED.value
        db.commit()

    @classmethod
    def revoke_invitation(
        cls,
        db: Session,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        invitation_id: uuid.UUID,
    ) -> None:
        """Revokes a pending invitation. Requires OWNER role."""
        WorkspaceAuthorizationService.verify_workspace_access(
            db, workspace_id, actor_id, WorkspaceRole.OWNER
        )

        invitation = db.execute(
            select(WorkspaceInvitationModel).where(
                WorkspaceInvitationModel.id == invitation_id,
                WorkspaceInvitationModel.workspace_id == workspace_id,
            )
        ).scalar_one_or_none()

        if invitation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Invitation '{invitation_id}' not found.",
            )

        now = datetime.now(timezone.utc)
        invitation.status = InvitationStatus.REVOKED.value
        invitation.revoked_at = now

        cls.record_activity(
            db,
            workspace_id=workspace_id,
            actor_id=actor_id,
            activity_type=ActivityType.INVITATION_REVOKED,
            target_type="INVITATION",
            target_id=invitation.id,
            description=f"Revoked invitation for {invitation.invitee_email}.",
        )

        db.commit()

    # ──────────────────────────────────────────────────────────────────────────
    # Collaborative Tasks Management
    # ──────────────────────────────────────────────────────────────────────────

    @classmethod
    def list_tasks(
        cls,
        db: Session,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        assignee_id: uuid.UUID | None = None,
        task_status: TaskStatus | None = None,
        priority: TaskPriority | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[WorkspaceTaskModel], int]:
        """Lists workspace tasks with filtering and pagination."""
        WorkspaceAuthorizationService.verify_workspace_access(
            db, workspace_id, user_id, WorkspaceRole.VIEWER
        )

        query = select(WorkspaceTaskModel).where(
            WorkspaceTaskModel.workspace_id == workspace_id
        )

        if assignee_id is not None:
            query = query.where(WorkspaceTaskModel.assignee_id == assignee_id)
        if task_status is not None:
            query = query.where(WorkspaceTaskModel.status == task_status.value)
        if priority is not None:
            query = query.where(WorkspaceTaskModel.priority == priority.value)

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_count = db.execute(count_query).scalar() or 0

        # Fetch page with eager-loaded user names
        paged_query = (
            query.options(
                joinedload(WorkspaceTaskModel.creator),
                joinedload(WorkspaceTaskModel.assignee),
            )
            .order_by(
                WorkspaceTaskModel.due_at.asc().nullslast(),
                WorkspaceTaskModel.created_at.desc(),
            )
            .offset(offset)
            .limit(limit)
        )
        tasks = list(db.execute(paged_query).scalars().all())
        return tasks, total_count

    @classmethod
    def create_task(
        cls,
        db: Session,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        payload: WorkspaceTaskCreate,
    ) -> WorkspaceTaskModel:
        """Creates a new collaborative task in the workspace. Requires CONTRIBUTOR role."""
        WorkspaceAuthorizationService.verify_workspace_access(
            db, workspace_id, actor_id, WorkspaceRole.CONTRIBUTOR
        )

        # Validate assignee if provided
        if payload.assignee_id is not None:
            assignee_member = db.execute(
                select(WorkspaceMemberModel).where(
                    WorkspaceMemberModel.workspace_id == workspace_id,
                    WorkspaceMemberModel.user_id == payload.assignee_id,
                    WorkspaceMemberModel.status == MemberStatus.ACTIVE.value,
                )
            ).scalar_one_or_none()
            if assignee_member is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Task assignee must be an active member of the workspace.",
                )

        # Validate submission if provided
        if payload.submission_id is not None:
            sub = db.get(ResearchSubmissionModel, payload.submission_id)
            if sub is None or sub.workspace_item_id != workspace_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Linked submission does not belong to this workspace.",
                )

        # Validate document if provided
        if payload.document_id is not None:
            doc = db.get(ResearchSubmissionDocumentModel, payload.document_id)
            if doc is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Linked document not found.",
                )

        task = WorkspaceTaskModel(
            workspace_id=workspace_id,
            title=payload.title,
            description=payload.description,
            creator_id=actor_id,
            assignee_id=payload.assignee_id,
            status=TaskStatus.TODO.value,
            priority=payload.priority.value,
            due_at=payload.due_at,
            submission_id=payload.submission_id,
            document_id=payload.document_id,
        )
        db.add(task)
        db.flush()

        cls.record_activity(
            db,
            workspace_id=workspace_id,
            actor_id=actor_id,
            activity_type=ActivityType.TASK_CREATED,
            target_type="TASK",
            target_id=task.id,
            description=f"Created task: '{task.title}'.",
            new_state={"title": task.title, "priority": task.priority, "status": task.status},
        )

        if payload.assignee_id is not None and payload.assignee_id != actor_id:
            cls.send_collaboration_notification(
                db,
                recipient_user_id=payload.assignee_id,
                notification_type=NotificationType.TASK_ASSIGNED,
                title="New Task Assigned",
                body=f"You were assigned to task: '{task.title}'.",
                source_id=workspace_id,
            )

        db.commit()
        db.refresh(task)
        return task

    @classmethod
    def update_task(
        cls,
        db: Session,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        task_id: uuid.UUID,
        payload: WorkspaceTaskUpdate,
    ) -> WorkspaceTaskModel:
        """Updates a workspace task. Requires CONTRIBUTOR role."""
        member = WorkspaceAuthorizationService.verify_workspace_access(
            db, workspace_id, actor_id, WorkspaceRole.CONTRIBUTOR
        )

        task = db.execute(
            select(WorkspaceTaskModel).where(
                WorkspaceTaskModel.id == task_id,
                WorkspaceTaskModel.workspace_id == workspace_id,
            )
        ).scalar_one_or_none()

        if task is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Task '{task_id}' not found in this workspace.",
            )

        old_state = {
            "title": task.title,
            "status": task.status,
            "priority": task.priority,
            "assignee_id": str(task.assignee_id) if task.assignee_id else None,
        }

        # Apply updates
        if payload.title is not None:
            task.title = payload.title
        if payload.description is not None:
            task.description = payload.description
        if payload.priority is not None:
            task.priority = payload.priority.value
        if payload.due_at is not None:
            task.due_at = payload.due_at
        if payload.submission_id is not None:
            task.submission_id = payload.submission_id
        if payload.document_id is not None:
            task.document_id = payload.document_id

        # Status changes
        if payload.status is not None:
            old_status = task.status
            task.status = payload.status.value
            if payload.status == TaskStatus.COMPLETED and old_status != TaskStatus.COMPLETED.value:
                task.completed_at = datetime.now(timezone.utc)
                cls.record_activity(
                    db,
                    workspace_id=workspace_id,
                    actor_id=actor_id,
                    activity_type=ActivityType.TASK_COMPLETED,
                    target_type="TASK",
                    target_id=task.id,
                    description=f"Completed task: '{task.title}'.",
                )
            elif payload.status != TaskStatus.COMPLETED and old_status == TaskStatus.COMPLETED.value:
                task.completed_at = None

        # Assignee changes
        if payload.assignee_id is not None and payload.assignee_id != task.assignee_id:
            task.assignee_id = payload.assignee_id
            cls.record_activity(
                db,
                workspace_id=workspace_id,
                actor_id=actor_id,
                activity_type=ActivityType.TASK_ASSIGNED,
                target_type="TASK",
                target_id=task.id,
                description=f"Reassigned task: '{task.title}'.",
            )
            if payload.assignee_id != actor_id:
                cls.send_collaboration_notification(
                    db,
                    recipient_user_id=payload.assignee_id,
                    notification_type=NotificationType.TASK_ASSIGNED,
                    title="Task Assigned",
                    body=f"You were assigned to task: '{task.title}'.",
                    source_id=workspace_id,
                )

        cls.record_activity(
            db,
            workspace_id=workspace_id,
            actor_id=actor_id,
            activity_type=ActivityType.TASK_UPDATED,
            target_type="TASK",
            target_id=task.id,
            description=f"Updated task: '{task.title}'.",
            old_state=old_state,
            new_state={
                "title": task.title,
                "status": task.status,
                "priority": task.priority,
                "assignee_id": str(task.assignee_id) if task.assignee_id else None,
            },
        )

        db.commit()
        db.refresh(task)
        return task

    @classmethod
    def delete_task(
        cls,
        db: Session,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        task_id: uuid.UUID,
    ) -> None:
        """Deletes a task. Requires task creator, EDITOR, or OWNER role."""
        member = WorkspaceAuthorizationService.verify_workspace_access(
            db, workspace_id, actor_id, WorkspaceRole.CONTRIBUTOR
        )

        task = db.execute(
            select(WorkspaceTaskModel).where(
                WorkspaceTaskModel.id == task_id,
                WorkspaceTaskModel.workspace_id == workspace_id,
            )
        ).scalar_one_or_none()

        if task is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Task '{task_id}' not found in this workspace.",
            )

        # Only creator or EDITOR/OWNER can delete
        if task.creator_id != actor_id and member.role not in {WorkspaceRole.EDITOR.value, WorkspaceRole.OWNER.value}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied: Only the task creator, an editor, or the workspace owner can delete tasks.",
            )

        task_title = task.title
        db.delete(task)

        cls.record_activity(
            db,
            workspace_id=workspace_id,
            actor_id=actor_id,
            activity_type=ActivityType.TASK_UPDATED,
            target_type="TASK",
            target_id=task_id,
            description=f"Deleted task: '{task_title}'.",
        )

        db.commit()

    # ──────────────────────────────────────────────────────────────────────────
    # Activity Stream & Structured Comments
    # ──────────────────────────────────────────────────────────────────────────

    @classmethod
    def list_activities(
        cls,
        db: Session,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[WorkspaceActivityModel], int]:
        """Lists chronological workspace activities with pagination."""
        WorkspaceAuthorizationService.verify_workspace_access(
            db, workspace_id, user_id, WorkspaceRole.VIEWER
        )

        query = (
            select(WorkspaceActivityModel)
            .where(WorkspaceActivityModel.workspace_id == workspace_id)
            .options(joinedload(WorkspaceActivityModel.actor))
            .order_by(WorkspaceActivityModel.created_at.desc())
        )

        count_query = select(func.count(WorkspaceActivityModel.id)).where(
            WorkspaceActivityModel.workspace_id == workspace_id
        )
        total_count = db.execute(count_query).scalar() or 0

        activities = list(db.execute(query.offset(offset).limit(limit)).scalars().all())
        return activities, total_count

    @classmethod
    def add_comment(
        cls,
        db: Session,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        payload: WorkspaceCommentCreate,
    ) -> WorkspaceActivityModel:
        """Adds a structured workflow comment or note to the workspace activity stream."""
        WorkspaceAuthorizationService.verify_workspace_access(
            db, workspace_id, actor_id, WorkspaceRole.CONTRIBUTOR
        )

        actor = db.get(UserModel, actor_id)
        actor_name = actor.full_name if actor else "A team member"

        activity = cls.record_activity(
            db,
            workspace_id=workspace_id,
            actor_id=actor_id,
            activity_type=ActivityType.COMMENT_ADDED,
            target_type=payload.target_type or "WORKSPACE",
            target_id=payload.target_id or workspace_id,
            description=f"{actor_name} posted a comment.",
            comment=payload.comment,
        )
        db.commit()
        db.refresh(activity)
        return activity

    @classmethod
    def record_activity(
        cls,
        db: Session,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        activity_type: ActivityType,
        description: str,
        target_type: str | None = None,
        target_id: uuid.UUID | None = None,
        comment: str | None = None,
        old_state: dict[str, Any] | None = None,
        new_state: dict[str, Any] | None = None,
    ) -> WorkspaceActivityModel:
        """Appends a new immutable activity entry."""
        activity = WorkspaceActivityModel(
            workspace_id=workspace_id,
            actor_id=actor_id,
            activity_type=activity_type.value,
            target_type=target_type,
            target_id=target_id,
            description=description,
            comment=comment,
            old_state=old_state,
            new_state=new_state,
        )
        db.add(activity)
        return activity

    # ──────────────────────────────────────────────────────────────────────────
    # Notification Integration (Phase 4.5 Reuse)
    # ──────────────────────────────────────────────────────────────────────────

    @classmethod
    def send_collaboration_notification(
        cls,
        db: Session,
        recipient_user_id: uuid.UUID,
        notification_type: NotificationType,
        title: str,
        body: str,
        source_id: uuid.UUID,
    ) -> NotificationModel | None:
        """
        Sends a deterministic, deduplicated collaboration notification to a user
        if they have an active research profile and preferences allow it.
        """
        profile = db.execute(
            select(ResearchProfileModel).where(ResearchProfileModel.user_id == recipient_user_id)
        ).scalar_one_or_none()

        if profile is None:
            # If the user has no research profile yet, skip notification
            return None

        # Check notification preferences
        pref = db.execute(
            select(NotificationPreferenceModel).where(
                NotificationPreferenceModel.profile_id == profile.id
            )
        ).scalar_one_or_none()

        if pref is not None and not pref.in_app_enabled:
            return None

        now = datetime.now(timezone.utc)
        # Deterministic deduplication key
        raw_key = f"collab:{notification_type.value}:{source_id}:{profile.id}:{now.strftime('%Y%m%d%H%M')}"
        dedup_key = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

        existing = db.execute(
            select(NotificationModel).where(NotificationModel.deduplication_key == dedup_key)
        ).scalar_one_or_none()
        if existing is not None:
            return existing

        notification = NotificationModel(
            profile_id=profile.id,
            notification_type=notification_type.value,
            title=title,
            body=body,
            source_type="WORKSPACE",
            source_id=source_id,
            scheduled_for=now,
            delivered_at=now,
            delivery_status=DeliveryStatus.DELIVERED.value,
            delivery_channel=DeliveryChannel.IN_APP.value,
            deduplication_key=dedup_key,
            metadata_json={"workspace_id": str(source_id)},
        )
        db.add(notification)
        db.flush()
        return notification

    # Method Aliases
    list_activity = list_activities
    log_activity = record_activity
