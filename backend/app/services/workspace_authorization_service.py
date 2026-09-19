"""
Workspace Authorization & Server-Side RBAC Service (Phase 4.6).

Enforces strict role-based access control and tenant isolation:
  - OWNER: Full management, member invitations/removals, role changes, deletion/archive.
  - EDITOR: Manage submissions, documents, tasks, edit workspace metadata.
  - CONTRIBUTOR: Create/update assigned tasks, upload document versions, add comments.
  - VIEWER: Read-only access to permitted workspace resources.
  - Non-members: Explicitly blocked (403 Forbidden / 404 Not Found).
"""
from __future__ import annotations

import logging
from typing import Sequence
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.saved_opportunity import SavedOpportunityModel
from app.models.workspace_collaboration import (
    MemberStatus,
    WorkspaceMemberModel,
    WorkspaceRole,
)

logger = logging.getLogger(__name__)


# Role permissions mapping for hierarchical access
ROLE_HIERARCHY: dict[WorkspaceRole, set[WorkspaceRole]] = {
    WorkspaceRole.VIEWER: {WorkspaceRole.VIEWER, WorkspaceRole.CONTRIBUTOR, WorkspaceRole.EDITOR, WorkspaceRole.OWNER},
    WorkspaceRole.CONTRIBUTOR: {WorkspaceRole.CONTRIBUTOR, WorkspaceRole.EDITOR, WorkspaceRole.OWNER},
    WorkspaceRole.EDITOR: {WorkspaceRole.EDITOR, WorkspaceRole.OWNER},
    WorkspaceRole.OWNER: {WorkspaceRole.OWNER},
}


class WorkspaceAuthorizationService:
    """Service providing server-side authorization checks for collaborative workspaces."""

    @classmethod
    def get_member(
        cls,
        db: Session,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> WorkspaceMemberModel | None:
        """
        Retrieves active membership record for a given workspace and user.
        Fast O(1) indexed lookup on (workspace_id, user_id).
        """
        try:
            return db.execute(
                select(WorkspaceMemberModel).where(
                    WorkspaceMemberModel.workspace_id == workspace_id,
                    WorkspaceMemberModel.user_id == user_id,
                    WorkspaceMemberModel.status == MemberStatus.ACTIVE.value,
                )
            ).scalar_one_or_none()
        except Exception:
            return None

    @classmethod
    def verify_workspace_access(
        cls,
        db: Session,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        required_minimum_role: WorkspaceRole | None = None,
    ) -> WorkspaceMemberModel:
        """
        Verifies that a user has active membership in the workspace and satisfies
        the minimum required role.

        Raises:
            HTTPException(404): If the workspace does not exist.
            HTTPException(403): If the user is not an active member or lacks required role.
        """
        member = cls.get_member(db, workspace_id, user_id)
        if member is None:
            # Check if the workspace actually exists to provide accurate status code
            workspace_exists = db.execute(
                select(SavedOpportunityModel.id).where(SavedOpportunityModel.id == workspace_id)
            ).scalar_one_or_none()
            if workspace_exists is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Workspace '{workspace_id}' not found.",
                )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You are not an active member of this research workspace.",
            )

        if required_minimum_role is not None:
            allowed_roles = ROLE_HIERARCHY.get(required_minimum_role, {required_minimum_role})
            member_role = WorkspaceRole(member.role)
            if member_role not in allowed_roles:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=(
                        f"Permission denied: Operation requires minimum role '{required_minimum_role.value}', "
                        f"but your current role is '{member.role}'."
                    ),
                )

        return member

    @classmethod
    def can_view(cls, member: WorkspaceMemberModel) -> bool:
        """Any active member can view workspace details."""
        return member.status == MemberStatus.ACTIVE.value

    @classmethod
    def can_contribute(cls, member: WorkspaceMemberModel) -> bool:
        """CONTRIBUTOR, EDITOR, or OWNER can contribute."""
        return (
            member.status == MemberStatus.ACTIVE.value
            and member.role in {WorkspaceRole.CONTRIBUTOR.value, WorkspaceRole.EDITOR.value, WorkspaceRole.OWNER.value}
        )

    @classmethod
    def can_edit(cls, member: WorkspaceMemberModel) -> bool:
        """EDITOR or OWNER can edit workspace metadata, submissions, and documents."""
        return (
            member.status == MemberStatus.ACTIVE.value
            and member.role in {WorkspaceRole.EDITOR.value, WorkspaceRole.OWNER.value}
        )

    @classmethod
    def can_manage(cls, member: WorkspaceMemberModel) -> bool:
        """Only OWNER can manage members, change roles, or archive workspace."""
        return (
            member.status == MemberStatus.ACTIVE.value
            and member.role == WorkspaceRole.OWNER.value
        )

    can_manage_workspace = can_manage

