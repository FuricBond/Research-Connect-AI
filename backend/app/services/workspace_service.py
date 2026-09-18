"""
Workspace Service Layer (Phase 4.1).

Provides deterministic business logic for Opportunity Workspace management:
  - Adding opportunities to workspace
  - Strict researcher ownership validation
  - Deterministic state machine workflow transitions
  - Filtering, pagination, sorting with zero N+1 queries
  - Workspace statistical summaries
  - Canonical deadline & risk intelligence enrichment
  - Phase 3.6 feedback synchronization
"""
from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, Sequence
import uuid

from sqlalchemy import Select, and_, case, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models.opportunity import OpportunityModel
from app.models.research_profile import ResearchProfileModel
from app.models.researcher_feedback import ResearcherRecommendationFeedbackModel
from app.models.saved_opportunity import (
    ResearchOpportunityWorkspaceModel,
    SavedOpportunityModel,
)
from app.ranking.deadline import deadline_explainability_service
from app.ranking.risk import assess_opportunity_risk, risk_explainability_service
from app.schemas.deadline import OpportunityDeadlineSchema
from app.schemas.opportunity import RiskExplanationSchema
from app.schemas.workspace import (
    WorkspaceItemCreate,
    WorkspaceItemRead,
    WorkspaceItemUpdate,
    WorkspaceListResponse,
    WorkspaceOpportunitySummary,
    WorkspacePriority,
    WorkspaceStatus,
    WorkspaceSummaryResponse,
)

logger = logging.getLogger(__name__)


class InvalidTransitionError(ValueError):
    """Raised when an invalid workflow state transition is attempted."""

    def __init__(
        self,
        current_status: WorkspaceStatus,
        target_status: WorkspaceStatus,
        allowed_targets: set[WorkspaceStatus],
    ):
        self.current_status = current_status
        self.target_status = target_status
        self.allowed_targets = allowed_targets
        allowed_str = ", ".join(f"'{s.value}'" for s in sorted(allowed_targets, key=lambda s: s.value))
        super().__init__(
            f"Invalid workspace state transition from '{current_status.value}' to '{target_status.value}'. "
            f"Allowed target states from '{current_status.value}' are: [{allowed_str}]."
        )


# Explicit deterministic state machine transition policy
VALID_TRANSITIONS: dict[WorkspaceStatus, set[WorkspaceStatus]] = {
    WorkspaceStatus.SAVED: {
        WorkspaceStatus.CONSIDERING,
        WorkspaceStatus.PLANNING,
        WorkspaceStatus.ARCHIVED,
    },
    WorkspaceStatus.CONSIDERING: {
        WorkspaceStatus.PLANNING,
        WorkspaceStatus.SAVED,
        WorkspaceStatus.ARCHIVED,
    },
    WorkspaceStatus.PLANNING: {
        WorkspaceStatus.APPLIED,
        WorkspaceStatus.CONSIDERING,
        WorkspaceStatus.SAVED,
        WorkspaceStatus.ARCHIVED,
    },
    WorkspaceStatus.APPLIED: {
        WorkspaceStatus.ACCEPTED,
        WorkspaceStatus.REJECTED,
        WorkspaceStatus.PLANNING,
        WorkspaceStatus.ARCHIVED,
    },
    WorkspaceStatus.ACCEPTED: {
        WorkspaceStatus.ARCHIVED,
        WorkspaceStatus.APPLIED,  # Administrative correction
    },
    WorkspaceStatus.REJECTED: {
        WorkspaceStatus.ARCHIVED,
        WorkspaceStatus.PLANNING,  # Re-targeting with revisions
    },
    WorkspaceStatus.ARCHIVED: {
        WorkspaceStatus.SAVED,
        WorkspaceStatus.CONSIDERING,
        WorkspaceStatus.PLANNING,
        WorkspaceStatus.APPLIED,
    },
}


class WorkspaceService:
    """Service orchestrating researcher opportunity workspace operations."""

    @classmethod
    def resolve_user_id(cls, db: Session, user_or_profile_id: uuid.UUID) -> uuid.UUID:
        """
        Resolves a client-supplied identifier to canonical UserModel.id.
        Accepts either UserModel.id or ResearchProfileModel.id.
        """
        profile = db.execute(
            select(ResearchProfileModel).where(
                or_(
                    ResearchProfileModel.id == user_or_profile_id,
                    ResearchProfileModel.user_id == user_or_profile_id,
                )
            )
        ).scalar_one_or_none()
        if profile is not None:
            return profile.user_id
        return user_or_profile_id

    @classmethod
    def get_allowed_transitions(cls, status: WorkspaceStatus) -> list[WorkspaceStatus]:
        """Returns the sorted list of valid target transitions for a given status."""
        targets = VALID_TRANSITIONS.get(status, set())
        return sorted(list(targets), key=lambda s: s.value)

    @classmethod
    def build_opportunity_summary(cls, opp: OpportunityModel) -> WorkspaceOpportunitySummary:
        """Enriches an OpportunityModel with canonical deadline and risk intelligence."""
        deadline_intel: OpportunityDeadlineSchema | None = None
        risk_expl: RiskExplanationSchema | None = None

        try:
            deadline_intel = deadline_explainability_service.explain_opportunity_from_model(opp)
        except Exception as exc:
            logger.warning(f"Error computing deadline intelligence for opportunity {opp.id}: {exc}")

        try:
            assessment = assess_opportunity_risk(opp)
            explanation = risk_explainability_service.explain(assessment, opportunity=opp)
            risk_expl = RiskExplanationSchema.model_validate(explanation.to_dict())
        except Exception as exc:
            logger.warning(f"Error computing risk explanation for opportunity {opp.id}: {exc}")

        return WorkspaceOpportunitySummary(
            id=opp.id,
            title=opp.title,
            opportunity_type=opp.opportunity_type,
            delivery_mode=opp.delivery_mode,
            publisher=opp.publisher,
            organizer=opp.organizer,
            submission_deadline=opp.submission_deadline,
            notification_date=opp.notification_date,
            camera_ready_deadline=opp.camera_ready_deadline,
            event_start_date=opp.event_start_date,
            location=opp.location,
            website_url=opp.website_url,
            status=opp.status,
            risk_score=float(opp.risk_score) if opp.risk_score is not None else None,
            is_predatory_flag=opp.is_predatory_flag,
            deadline_intelligence=deadline_intel,
            risk_explanation=risk_expl,
        )

    @classmethod
    def build_workspace_item_read(cls, item: SavedOpportunityModel) -> WorkspaceItemRead:
        """Converts an ORM model to a typed WorkspaceItemRead schema."""
        current_status = WorkspaceStatus(item.status)
        current_priority = WorkspacePriority(item.priority)
        allowed = cls.get_allowed_transitions(current_status)

        opp_summary = cls.build_opportunity_summary(item.opportunity)

        return WorkspaceItemRead(
            id=item.id,
            user_id=item.user_id,
            opportunity_id=item.opportunity_id,
            status=current_status,
            priority=current_priority,
            tags=item.tags or [],
            notes=item.notes,
            created_at=item.created_at,
            updated_at=item.updated_at,
            status_updated_at=item.status_updated_at,
            archived_at=item.archived_at,
            allowed_transitions=allowed,
            opportunity=opp_summary,
        )

    @classmethod
    def add_opportunity(
        cls,
        db: Session,
        user_id: uuid.UUID,
        payload: WorkspaceItemCreate,
    ) -> tuple[SavedOpportunityModel, bool]:
        """
        Adds an opportunity to the researcher workspace or updates existing item.
        Returns tuple of (model, is_new).
        """
        resolved_user_id = cls.resolve_user_id(db, user_id)

        # 1. Verify opportunity exists
        opp = db.execute(
            select(OpportunityModel).where(OpportunityModel.id == payload.opportunity_id)
        ).scalar_one_or_none()
        if opp is None:
            raise ValueError(f"Opportunity with ID '{payload.opportunity_id}' not found.")

        # 2. Check for existing workspace record
        existing = db.execute(
            select(SavedOpportunityModel)
            .options(joinedload(SavedOpportunityModel.opportunity))
            .where(
                SavedOpportunityModel.user_id == resolved_user_id,
                SavedOpportunityModel.opportunity_id == payload.opportunity_id,
            )
        ).scalar_one_or_none()

        now = datetime.now(timezone.utc)

        if existing is not None:
            # Re-activating or updating metadata
            if existing.status == WorkspaceStatus.ARCHIVED.value and payload.status != WorkspaceStatus.ARCHIVED:
                existing.status = payload.status.value
                existing.status_updated_at = now
                existing.archived_at = None
            elif payload.status != WorkspaceStatus(existing.status):
                # Apply explicit state transition validation
                curr_status = WorkspaceStatus(existing.status)
                if payload.status in VALID_TRANSITIONS.get(curr_status, set()):
                    existing.status = payload.status.value
                    existing.status_updated_at = now

            if payload.priority:
                existing.priority = payload.priority.value
            if payload.tags:
                existing.tags = list(dict.fromkeys(payload.tags))
            if payload.notes is not None:
                existing.notes = payload.notes

            existing.updated_at = now
            db.flush()
            db.commit()
            return existing, False

        # 3. Create fresh workspace record
        tags_clean = list(dict.fromkeys(payload.tags)) if payload.tags else []
        new_item = SavedOpportunityModel(
            user_id=resolved_user_id,
            opportunity_id=payload.opportunity_id,
            status=payload.status.value,
            priority=payload.priority.value,
            tags=tags_clean,
            notes=payload.notes,
            created_at=now,
            updated_at=now,
            status_updated_at=now,
            archived_at=now if payload.status == WorkspaceStatus.ARCHIVED else None,
        )
        db.add(new_item)
        db.flush()

        # 4. Synchronize Phase 3.6 feedback loop if profile exists
        try:
            profile = db.execute(
                select(ResearchProfileModel).where(ResearchProfileModel.user_id == resolved_user_id)
            ).scalar_one_or_none()
            if profile:
                existing_fb = db.execute(
                    select(ResearcherRecommendationFeedbackModel).where(
                        ResearcherRecommendationFeedbackModel.researcher_id == profile.id,
                        ResearcherRecommendationFeedbackModel.opportunity_id == payload.opportunity_id,
                        ResearcherRecommendationFeedbackModel.feedback_type == "SAVE",
                    )
                ).scalar_one_or_none()
                if not existing_fb:
                    feedback = ResearcherRecommendationFeedbackModel(
                        researcher_id=profile.id,
                        opportunity_id=payload.opportunity_id,
                        feedback_type="SAVE",
                        source="WORKSPACE",
                        notes=payload.notes,
                    )
                    db.add(feedback)
        except Exception as exc:
            logger.warning(f"Failed to synchronize Phase 3.6 feedback on workspace add: {exc}")

        db.commit()
        # Eagerly load opportunity
        db.refresh(new_item, ["opportunity"])
        return new_item, True

    @classmethod
    def get_workspace_item(
        cls,
        db: Session,
        user_id: uuid.UUID,
        item_id: uuid.UUID,
    ) -> SavedOpportunityModel | None:
        """
        Retrieves a single workspace item with strict researcher ownership validation.
        Raises PermissionError if item exists but is owned by another user.
        """
        resolved_user_id = cls.resolve_user_id(db, user_id)

        item = db.execute(
            select(SavedOpportunityModel)
            .options(joinedload(SavedOpportunityModel.opportunity))
            .where(SavedOpportunityModel.id == item_id)
        ).scalar_one_or_none()

        if item is None:
            return None

        if item.user_id != resolved_user_id:
            raise PermissionError("Forbidden: You do not have permission to access this workspace item.")

        return item

    @classmethod
    def list_workspace_items(
        cls,
        db: Session,
        user_id: uuid.UUID,
        status: WorkspaceStatus | None = None,
        priority: WorkspacePriority | None = None,
        tag: str | None = None,
        search: str | None = None,
        include_archived: bool = False,
        sort_by: str = "updated_at",
        sort_order: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> WorkspaceListResponse:
        """
        Lists workspace items for the authenticated researcher with filtering and aggregates.
        Guarantees zero N+1 queries via eager loading.
        """
        resolved_user_id = cls.resolve_user_id(db, user_id)

        # Base query joined with OpportunityModel for search and sorting
        base_query = (
            select(SavedOpportunityModel)
            .options(joinedload(SavedOpportunityModel.opportunity))
            .join(OpportunityModel, SavedOpportunityModel.opportunity_id == OpportunityModel.id)
            .where(SavedOpportunityModel.user_id == resolved_user_id)
        )

        # Archive filter
        if status == WorkspaceStatus.ARCHIVED:
            base_query = base_query.where(SavedOpportunityModel.status == WorkspaceStatus.ARCHIVED.value)
        elif not include_archived and status is None:
            base_query = base_query.where(SavedOpportunityModel.status != WorkspaceStatus.ARCHIVED.value)

        # Status filter
        if status is not None:
            base_query = base_query.where(SavedOpportunityModel.status == status.value)

        # Priority filter
        if priority is not None:
            base_query = base_query.where(SavedOpportunityModel.priority == priority.value)

        # Search filter (title or notes)
        if search and search.strip():
            search_pat = f"%{search.strip()}%"
            base_query = base_query.where(
                or_(
                    OpportunityModel.title.ilike(search_pat),
                    SavedOpportunityModel.notes.ilike(search_pat),
                )
            )

        # Sorting
        order_col = SavedOpportunityModel.updated_at
        if sort_by == "created_at":
            order_col = SavedOpportunityModel.created_at
        elif sort_by == "deadline":
            order_col = OpportunityModel.submission_deadline
        elif sort_by == "priority":
            order_col = SavedOpportunityModel.priority
        elif sort_by == "status":
            order_col = SavedOpportunityModel.status

        if sort_order.lower() == "asc":
            base_query = base_query.order_by(order_col.asc().nullslast(), SavedOpportunityModel.id.asc())
        else:
            base_query = base_query.order_by(order_col.desc().nullslast(), SavedOpportunityModel.id.asc())

        # Execute query
        all_matched = db.execute(base_query).scalars().all()

        # Tag filter in python memory to maintain full SQLite/PostgreSQL cross-compatibility
        if tag and tag.strip():
            tag_clean = tag.strip().lower()
            filtered_items = [
                it for it in all_matched
                if any(t.lower() == tag_clean for t in (it.tags or []))
            ]
        else:
            filtered_items = list(all_matched)

        total_count = len(filtered_items)
        paged_items = filtered_items[offset : offset + limit]

        # Compute summary counts for this researcher across all their items (active & archived)
        all_user_items = db.execute(
            select(SavedOpportunityModel.status, SavedOpportunityModel.priority)
            .where(SavedOpportunityModel.user_id == resolved_user_id)
        ).all()

        counts_by_status: dict[str, int] = {s.value: 0 for s in WorkspaceStatus}
        counts_by_priority: dict[str, int] = {p.value: 0 for p in WorkspacePriority}
        active_count = 0
        archived_count = 0

        for it_status, it_priority in all_user_items:
            if it_status in counts_by_status:
                counts_by_status[it_status] += 1
            if it_priority in counts_by_priority:
                counts_by_priority[it_priority] += 1
            if it_status == WorkspaceStatus.ARCHIVED.value:
                archived_count += 1
            else:
                active_count += 1

        serialized = [cls.build_workspace_item_read(item) for item in paged_items]

        return WorkspaceListResponse(
            items=serialized,
            total_count=total_count,
            active_count=active_count,
            archived_count=archived_count,
            counts_by_status=counts_by_status,
            counts_by_priority=counts_by_priority,
        )

    @classmethod
    def get_summary(cls, db: Session, user_id: uuid.UUID) -> WorkspaceSummaryResponse:
        """Computes statistical breakdown for a researcher's workspace."""
        resolved_user_id = cls.resolve_user_id(db, user_id)

        rows = db.execute(
            select(SavedOpportunityModel.status, SavedOpportunityModel.priority)
            .where(SavedOpportunityModel.user_id == resolved_user_id)
        ).all()

        counts_by_status: dict[str, int] = {s.value: 0 for s in WorkspaceStatus}
        counts_by_priority: dict[str, int] = {p.value: 0 for p in WorkspacePriority}
        active_count = 0
        archived_count = 0

        for it_status, it_priority in rows:
            if it_status in counts_by_status:
                counts_by_status[it_status] += 1
            if it_priority in counts_by_priority:
                counts_by_priority[it_priority] += 1
            if it_status == WorkspaceStatus.ARCHIVED.value:
                archived_count += 1
            else:
                active_count += 1

        return WorkspaceSummaryResponse(
            total_count=len(rows),
            active_count=active_count,
            archived_count=archived_count,
            counts_by_status=counts_by_status,
            counts_by_priority=counts_by_priority,
        )

    @classmethod
    def update_workspace_item(
        cls,
        db: Session,
        user_id: uuid.UUID,
        item_id: uuid.UUID,
        payload: WorkspaceItemUpdate,
    ) -> SavedOpportunityModel:
        """Partially updates metadata (priority, tags, notes) with ownership validation."""
        item = cls.get_workspace_item(db, user_id, item_id)
        if item is None:
            raise ValueError(f"Workspace item with ID '{item_id}' not found.")

        now = datetime.now(timezone.utc)
        if payload.priority is not None:
            item.priority = payload.priority.value
        if payload.tags is not None:
            item.tags = list(dict.fromkeys(payload.tags))
        if payload.notes is not None:
            item.notes = payload.notes

        item.updated_at = now
        db.flush()
        db.commit()
        db.refresh(item, ["opportunity"])
        return item

    @classmethod
    def transition_status(
        cls,
        db: Session,
        user_id: uuid.UUID,
        item_id: uuid.UUID,
        target_status: WorkspaceStatus,
        notes: str | None = None,
    ) -> SavedOpportunityModel:
        """
        Executes a deterministic state machine transition.
        Enforces ownership and validation rules.
        """
        item = cls.get_workspace_item(db, user_id, item_id)
        if item is None:
            raise ValueError(f"Workspace item with ID '{item_id}' not found.")

        current_status = WorkspaceStatus(item.status)

        # Idempotent check
        if current_status == target_status:
            if notes:
                item.notes = notes
                item.updated_at = datetime.now(timezone.utc)
                db.commit()
                db.refresh(item, ["opportunity"])
            return item

        # Validate transition against policy
        allowed_targets = VALID_TRANSITIONS.get(current_status, set())
        if target_status not in allowed_targets:
            raise InvalidTransitionError(current_status, target_status, allowed_targets)

        now = datetime.now(timezone.utc)
        item.status = target_status.value
        item.status_updated_at = now
        item.updated_at = now

        # Timestamp tracking for ARCHIVED
        if target_status == WorkspaceStatus.ARCHIVED:
            item.archived_at = now
        elif current_status == WorkspaceStatus.ARCHIVED:
            item.archived_at = None

        if notes:
            item.notes = notes

        # Synchronize Phase 3.6 feedback on APPLIED
        if target_status == WorkspaceStatus.APPLIED:
            try:
                profile = db.execute(
                    select(ResearchProfileModel).where(ResearchProfileModel.user_id == item.user_id)
                ).scalar_one_or_none()
                if profile:
                    feedback = ResearcherRecommendationFeedbackModel(
                        researcher_id=profile.id,
                        opportunity_id=item.opportunity_id,
                        feedback_type="APPLY",
                        source="WORKSPACE",
                        notes=notes,
                    )
                    db.add(feedback)
            except Exception as exc:
                logger.warning(f"Failed to synchronize Phase 3.6 feedback on APPLY transition: {exc}")

        db.flush()
        db.commit()
        db.refresh(item, ["opportunity"])
        return item

    @classmethod
    def archive_item(cls, db: Session, user_id: uuid.UUID, item_id: uuid.UUID) -> SavedOpportunityModel:
        """Convenience method to archive an item."""
        return cls.transition_status(db, user_id, item_id, WorkspaceStatus.ARCHIVED)

    @classmethod
    def unarchive_item(
        cls,
        db: Session,
        user_id: uuid.UUID,
        item_id: uuid.UUID,
        target_status: WorkspaceStatus = WorkspaceStatus.SAVED,
    ) -> SavedOpportunityModel:
        """Convenience method to unarchive an item into an active state."""
        return cls.transition_status(db, user_id, item_id, target_status)

    @classmethod
    def remove_item(cls, db: Session, user_id: uuid.UUID, item_id: uuid.UUID) -> bool:
        """
        Removes an opportunity from the researcher workspace with ownership check.
        Synchronizes Phase 3.6 feedback if applicable.
        """
        item = cls.get_workspace_item(db, user_id, item_id)
        if item is None:
            raise ValueError(f"Workspace item with ID '{item_id}' not found.")

        # If it was in SAVED status, clean up SAVE feedback in Phase 3.6
        resolved_user_id = item.user_id
        opp_id = item.opportunity_id
        if item.status == WorkspaceStatus.SAVED.value:
            try:
                profile = db.execute(
                    select(ResearchProfileModel).where(ResearchProfileModel.user_id == resolved_user_id)
                ).scalar_one_or_none()
                if profile:
                    fb = db.execute(
                        select(ResearcherRecommendationFeedbackModel).where(
                            ResearcherRecommendationFeedbackModel.researcher_id == profile.id,
                            ResearcherRecommendationFeedbackModel.opportunity_id == opp_id,
                            ResearcherRecommendationFeedbackModel.feedback_type == "SAVE",
                        )
                    ).scalar_one_or_none()
                    if fb:
                        db.delete(fb)
            except Exception as exc:
                logger.warning(f"Failed to delete Phase 3.6 feedback on workspace remove: {exc}")

        db.delete(item)
        db.commit()
        return True
