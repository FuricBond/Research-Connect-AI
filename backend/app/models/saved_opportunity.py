from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING
import uuid

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.opportunity import OpportunityModel
    from app.models.research_submission import ResearchSubmissionModel
    from app.models.user import UserModel
    from app.models.workspace_collaboration import (
        WorkspaceActivityModel,
        WorkspaceInvitationModel,
        WorkspaceMemberModel,
        WorkspaceTaskModel,
    )


class WorkspaceStatus(str, Enum):
    """Supported deterministic workspace workflow states (Phase 4.1)."""

    SAVED = "SAVED"
    CONSIDERING = "CONSIDERING"
    PLANNING = "PLANNING"
    APPLIED = "APPLIED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    ARCHIVED = "ARCHIVED"


class WorkspacePriority(str, Enum):
    """Researcher workspace urgency / priority rating."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"


class SavedOpportunityModel(Base):
    """
    User bookmarked and managed opportunity in the researcher workspace (Phase 4.1).
    
    Serves as the unified Opportunity Workspace entity (`ResearchOpportunityWorkspaceModel`),
    tracking opportunities across explicit workflow stages with priority, custom tags,
    notes, and status transition timestamps.
    """

    __tablename__ = "saved_opportunities"
    __table_args__ = (
        UniqueConstraint("user_id", "opportunity_id", name="uq_saved_opportunities_user_opportunity"),
        CheckConstraint(
            "status IN ('SAVED', 'CONSIDERING', 'PLANNING', 'APPLIED', 'ACCEPTED', 'REJECTED', 'ARCHIVED')",
            name="chk_saved_opportunities_status",
        ),
        CheckConstraint(
            "priority IN ('LOW', 'MEDIUM', 'HIGH', 'URGENT')",
            name="chk_saved_opportunities_priority",
        ),
        Index("idx_saved_opp_user_status", "user_id", "status"),
        Index("idx_saved_opp_user_priority", "user_id", "priority"),
        Index("idx_saved_opp_user_updated", "user_id", "updated_at"),
        Index("idx_saved_opp_archived_at", "archived_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("opportunities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Workflow state machine (Phase 4.1)
    status: Mapped[str] = mapped_column(
        String(50),
        default="SAVED",
        server_default="SAVED",
        nullable=False,
        index=True,
        comment="Workflow stage: SAVED, CONSIDERING, PLANNING, APPLIED, ACCEPTED, REJECTED, ARCHIVED",
    )

    # Researcher priority rating
    priority: Mapped[str] = mapped_column(
        String(20),
        default="MEDIUM",
        server_default="MEDIUM",
        nullable=False,
        index=True,
        comment="Priority: LOW, MEDIUM, HIGH, URGENT",
    )

    # Categorization and labeling tags
    tags: Mapped[list[str]] = mapped_column(
        JSONB,
        default=list,
        server_default="[]",
        nullable=False,
        comment="User-defined categorization tags",
    )

    # Researcher personal notes / annotations
    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Lifecycle timestamps
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
    status_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    # Relationships
    user: Mapped["UserModel"] = relationship(
        back_populates="saved_opportunities",
    )
    opportunity: Mapped["OpportunityModel"] = relationship(
        back_populates="saved_by_users",
    )
    submissions: Mapped[list["ResearchSubmissionModel"]] = relationship(
        back_populates="workspace_item",
        cascade="all, delete-orphan",
    )
    members: Mapped[list["WorkspaceMemberModel"]] = relationship(
        back_populates="workspace",
        cascade="all, delete-orphan",
    )
    invitations: Mapped[list["WorkspaceInvitationModel"]] = relationship(
        back_populates="workspace",
        cascade="all, delete-orphan",
    )
    tasks: Mapped[list["WorkspaceTaskModel"]] = relationship(
        back_populates="workspace",
        cascade="all, delete-orphan",
    )
    activities: Mapped[list["WorkspaceActivityModel"]] = relationship(
        back_populates="workspace",
        cascade="all, delete-orphan",
        order_by="desc(WorkspaceActivityModel.created_at)",
    )


# Domain alias for explicit Phase 4 domain modeling
ResearchOpportunityWorkspaceModel = SavedOpportunityModel
