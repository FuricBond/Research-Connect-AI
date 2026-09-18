"""
Research Submission Service (Phase 4.2).

Provides deterministic business logic for research submission lifecycle:
  - Creating manuscript/proposal submissions linked to workspace opportunities
  - Strict researcher ownership validation via parent workspace item
  - Deterministic state machine transitions (DRAFT -> READY -> SUBMITTED -> UNDER_REVIEW -> ACCEPTED/REJECTED)
  - Controlled workspace promotion (SUBMITTED promotes workspace to APPLIED; triggers Phase 3.6 feedback)
  - Canonical Phase 2.7 deadline context enrichment with zero calculation duplication
  - Eager relationship loading guaranteeing zero N+1 queries
"""
from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, Sequence
import uuid

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models.opportunity import OpportunityModel
from app.models.research_profile import ResearchProfileModel
from app.models.research_submission import (
    ResearchSubmissionModel,
    SubmissionStatus,
    SubmissionType,
)
from app.models.submission_document import SubmissionEventType
from app.models.researcher_feedback import ResearcherRecommendationFeedbackModel
from app.models.saved_opportunity import SavedOpportunityModel, WorkspaceStatus
from app.ranking.deadline import deadline_explainability_service
from app.schemas.research_submission import (
    ResearchSubmissionCreate,
    ResearchSubmissionListResponse,
    ResearchSubmissionRead,
    ResearchSubmissionUpdate,
    SubmissionDeadlineContext,
    SubmissionSummaryResponse,
)
from app.services.workspace_service import WorkspaceService

logger = logging.getLogger(__name__)


class InvalidSubmissionTransitionError(ValueError):
    """Raised when an invalid submission state machine transition is attempted."""

    def __init__(
        self,
        current_status: SubmissionStatus | str,
        target_status: SubmissionStatus | str | None = None,
        allowed_targets: set[SubmissionStatus] | None = None,
        message: str | None = None,
    ):
        self.current_status = current_status
        self.target_status = target_status
        self.allowed_targets = allowed_targets or set()
        if message:
            super().__init__(message)
        else:
            allowed_str = ", ".join(f"'{s.value}'" for s in sorted(self.allowed_targets, key=lambda s: s.value))
            super().__init__(
                f"Invalid submission lifecycle transition from '{getattr(current_status, 'value', current_status)}' to '{getattr(target_status, 'value', target_status)}'. "
                f"Allowed target states from '{getattr(current_status, 'value', current_status)}' are: [{allowed_str}]."
            )


# Explicit deterministic submission state machine transition policy
VALID_SUBMISSION_TRANSITIONS: dict[SubmissionStatus, set[SubmissionStatus]] = {
    SubmissionStatus.DRAFT: {
        SubmissionStatus.READY,
        SubmissionStatus.WITHDRAWN,
    },
    SubmissionStatus.READY: {
        SubmissionStatus.DRAFT,
        SubmissionStatus.SUBMITTED,
        SubmissionStatus.WITHDRAWN,
    },
    SubmissionStatus.SUBMITTED: {
        SubmissionStatus.UNDER_REVIEW,
        SubmissionStatus.WITHDRAWN,
    },
    SubmissionStatus.UNDER_REVIEW: {
        SubmissionStatus.ACCEPTED,
        SubmissionStatus.REJECTED,
        SubmissionStatus.WITHDRAWN,
    },
    SubmissionStatus.ACCEPTED: {
        SubmissionStatus.WITHDRAWN,
    },
    SubmissionStatus.REJECTED: {
        SubmissionStatus.DRAFT,  # Re-target with revisions
    },
    SubmissionStatus.WITHDRAWN: {
        SubmissionStatus.DRAFT,  # Restore to active draft
    },
}


class ResearchSubmissionService:
    """Service orchestrating research submission management and tracking."""

    @classmethod
    def resolve_user_id(cls, db: Session, user_or_profile_id: uuid.UUID) -> uuid.UUID:
        """Resolves authenticated user ID from user or profile identifier."""
        return WorkspaceService.resolve_user_id(db, user_or_profile_id)

    @classmethod
    def get_allowed_transitions(cls, status: SubmissionStatus) -> list[SubmissionStatus]:
        """Returns sorted list of permitted transitions from current state."""
        targets = VALID_SUBMISSION_TRANSITIONS.get(status, set())
        return sorted(list(targets), key=lambda s: s.value)

    @classmethod
    def extract_deadline_context(cls, opp: OpportunityModel) -> SubmissionDeadlineContext:
        """Enriches submission with canonical Phase 2.7 deadline intelligence."""
        try:
            intel = deadline_explainability_service.explain_opportunity_from_model(opp)
            primary_view = intel.primary_view if intel else None
            canon_deadline = primary_view.canonical_deadline if primary_view else None
            canon_assessment = primary_view.canonical_assessment if primary_view else None

            sub_dt = opp.submission_deadline
            if canon_deadline and canon_deadline.normalized_utc:
                sub_dt = canon_deadline.normalized_utc

            is_aoe = False
            if canon_deadline and canon_deadline.timezone_name in ("AoE", "Anywhere on Earth"):
                is_aoe = True

            urgency_tier = None
            if canon_assessment and canon_assessment.urgency_tier:
                urgency_tier = canon_assessment.urgency_tier

            return SubmissionDeadlineContext(
                submission_deadline=sub_dt,
                days_remaining=canon_assessment.days_remaining if canon_assessment else None,
                urgency_tier=urgency_tier,
                is_aoe=is_aoe,
                has_extension=intel.has_extension if intel else False,
                has_conflict=intel.has_conflict if intel else False,
                summary=intel.summary if intel else None,
            )
        except Exception as exc:
            logger.warning(f"Failed to extract deadline context for opportunity {opp.id}: {exc}")
            return SubmissionDeadlineContext(
                submission_deadline=opp.submission_deadline,
            )

    @classmethod
    def build_submission_read(cls, submission: ResearchSubmissionModel) -> ResearchSubmissionRead:
        """Converts an ORM submission model to typed ResearchSubmissionRead schema."""
        current_status = SubmissionStatus(submission.status)
        current_type = SubmissionType(submission.submission_type)
        allowed = cls.get_allowed_transitions(current_status)

        ws_item = submission.workspace_item
        opp = ws_item.opportunity if ws_item else None
        deadline_ctx = cls.extract_deadline_context(opp) if opp else None

        venue_name = submission.venue or (opp.publisher or opp.organizer if opp else None)
        opp_title = "Unknown Opportunity"
        opp_id = uuid.uuid4()
        ws_status = "SAVED"

        if ws_item:
            ws_status = ws_item.status
            if opp:
                opp_id = opp.id
                opp_title = opp.title
                if not submission.venue:
                    venue_name = opp.publisher or opp.organizer

        return ResearchSubmissionRead(
            id=submission.id,
            workspace_item_id=submission.workspace_item_id,
            title=submission.title,
            abstract=submission.abstract,
            submission_type=current_type,
            status=current_status,
            external_submission_id=submission.external_submission_id,
            venue=submission.venue,
            submission_url=submission.submission_url,
            notes=submission.notes,
            submitted_at=submission.submitted_at,
            decision_at=submission.decision_at,
            status_updated_at=submission.status_updated_at,
            created_at=submission.created_at,
            updated_at=submission.updated_at,
            allowed_transitions=allowed,
            workspace_status=ws_status,
            opportunity_id=opp_id,
            opportunity_title=opp_title,
            venue_name=venue_name,
            deadline_context=deadline_ctx,
        )

    @classmethod
    def create_submission(
        cls,
        db: Session,
        user_id: uuid.UUID,
        payload: ResearchSubmissionCreate,
    ) -> ResearchSubmissionModel:
        """
        Creates a new research submission draft linked to a workspace opportunity item.
        Validates researcher ownership of the parent workspace item.
        """
        resolved_user_id = cls.resolve_user_id(db, user_id)

        # Verify parent workspace item exists and is owned by this researcher
        ws_item = db.execute(
            select(SavedOpportunityModel)
            .options(joinedload(SavedOpportunityModel.opportunity))
            .where(SavedOpportunityModel.id == payload.workspace_item_id)
        ).scalar_one_or_none()

        if ws_item is None:
            raise ValueError(f"Workspace opportunity with ID '{payload.workspace_item_id}' not found.")

        if ws_item.user_id != resolved_user_id:
            raise PermissionError("Forbidden: You do not have permission to attach a submission to this workspace item.")

        now = datetime.now(timezone.utc)
        submission = ResearchSubmissionModel(
            workspace_item_id=payload.workspace_item_id,
            title=payload.title.strip(),
            abstract=payload.abstract.strip() if payload.abstract else None,
            submission_type=payload.submission_type.value,
            status=SubmissionStatus.DRAFT.value,
            external_submission_id=payload.external_submission_id.strip() if payload.external_submission_id else None,
            venue=payload.venue.strip() if payload.venue else None,
            submission_url=payload.submission_url.strip() if payload.submission_url else None,
            notes=payload.notes,
            status_updated_at=now,
            created_at=now,
            updated_at=now,
        )

        db.add(submission)
        db.flush()

        # Phase 4.3 Audit Event Logging
        from app.services.research_submission_document_service import ResearchSubmissionDocumentService
        ResearchSubmissionDocumentService.log_event(
            db=db,
            submission_id=submission.id,
            event_type=SubmissionEventType.SUBMISSION_CREATED,
            new_state={
                "title": submission.title,
                "submission_type": submission.submission_type,
                "status": submission.status,
            },
            description=f"Created submission '{submission.title}' ({submission.submission_type}).",
            user_id=resolved_user_id,
        )

        db.commit()

        # Eagerly refresh relationships
        db.refresh(submission, ["workspace_item"])
        return submission

    @classmethod
    def get_submission(
        cls,
        db: Session,
        user_id: uuid.UUID,
        submission_id: uuid.UUID,
    ) -> ResearchSubmissionModel | None:
        """
        Retrieves a single submission with researcher ownership verification.
        Raises PermissionError if owned by another researcher.
        """
        resolved_user_id = cls.resolve_user_id(db, user_id)

        submission = db.execute(
            select(ResearchSubmissionModel)
            .options(
                joinedload(ResearchSubmissionModel.workspace_item).joinedload(SavedOpportunityModel.opportunity)
            )
            .where(ResearchSubmissionModel.id == submission_id)
        ).scalar_one_or_none()

        if submission is None:
            return None

        if submission.workspace_item.user_id != resolved_user_id:
            raise PermissionError("Forbidden: You do not have permission to access this research submission.")

        return submission

    @classmethod
    def list_submissions(
        cls,
        db: Session,
        user_id: uuid.UUID,
        status: SubmissionStatus | None = None,
        submission_type: SubmissionType | None = None,
        workspace_item_id: uuid.UUID | None = None,
        search: str | None = None,
        sort_by: str = "updated_at",
        sort_order: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> ResearchSubmissionListResponse:
        """
        Lists submissions for the authenticated researcher with zero N+1 queries.
        Supports status, type, workspace_item_id, lexical search, and deterministic sorting.
        """
        resolved_user_id = cls.resolve_user_id(db, user_id)

        query = (
            select(ResearchSubmissionModel)
            .join(SavedOpportunityModel, ResearchSubmissionModel.workspace_item_id == SavedOpportunityModel.id)
            .options(
                joinedload(ResearchSubmissionModel.workspace_item).joinedload(SavedOpportunityModel.opportunity)
            )
            .where(SavedOpportunityModel.user_id == resolved_user_id)
        )

        if status is not None:
            query = query.where(ResearchSubmissionModel.status == status.value)

        if submission_type is not None:
            query = query.where(ResearchSubmissionModel.submission_type == submission_type.value)

        if workspace_item_id is not None:
            query = query.where(ResearchSubmissionModel.workspace_item_id == workspace_item_id)

        if search and search.strip():
            pat = f"%{search.strip()}%"
            query = query.where(
                or_(
                    ResearchSubmissionModel.title.ilike(pat),
                    ResearchSubmissionModel.abstract.ilike(pat),
                    ResearchSubmissionModel.external_submission_id.ilike(pat),
                    ResearchSubmissionModel.venue.ilike(pat),
                    ResearchSubmissionModel.notes.ilike(pat),
                )
            )

        sort_col = getattr(ResearchSubmissionModel, sort_by, ResearchSubmissionModel.updated_at)
        if sort_order.lower() == "asc":
            query = query.order_by(sort_col.asc(), ResearchSubmissionModel.id.asc())
        else:
            query = query.order_by(sort_col.desc(), ResearchSubmissionModel.id.asc())

        all_items = db.execute(query).scalars().all()
        total_count = len(all_items)
        paged_items = all_items[offset : offset + limit]

        # Compute summary counts for this researcher
        summary_rows = db.execute(
            select(ResearchSubmissionModel.status, ResearchSubmissionModel.submission_type)
            .join(SavedOpportunityModel, ResearchSubmissionModel.workspace_item_id == SavedOpportunityModel.id)
            .where(SavedOpportunityModel.user_id == resolved_user_id)
        ).all()

        counts_by_status: dict[str, int] = {s.value: 0 for s in SubmissionStatus}
        counts_by_type: dict[str, int] = {t.value: 0 for t in SubmissionType}

        for st, tp in summary_rows:
            if st in counts_by_status:
                counts_by_status[st] += 1
            if tp in counts_by_type:
                counts_by_type[tp] += 1

        serialized = [cls.build_submission_read(s) for s in paged_items]

        return ResearchSubmissionListResponse(
            items=serialized,
            total_count=total_count,
            counts_by_status=counts_by_status,
            counts_by_type=counts_by_type,
        )

    @classmethod
    def get_summary(cls, db: Session, user_id: uuid.UUID) -> SubmissionSummaryResponse:
        """Returns aggregated submission metrics for the authenticated researcher."""
        resolved_user_id = cls.resolve_user_id(db, user_id)

        rows = db.execute(
            select(ResearchSubmissionModel.status, ResearchSubmissionModel.submission_type)
            .join(SavedOpportunityModel, ResearchSubmissionModel.workspace_item_id == SavedOpportunityModel.id)
            .where(SavedOpportunityModel.user_id == resolved_user_id)
        ).all()

        counts_by_status: dict[str, int] = {s.value: 0 for s in SubmissionStatus}
        counts_by_type: dict[str, int] = {t.value: 0 for t in SubmissionType}
        active_count = 0
        accepted_count = 0
        rejected_count = 0
        withdrawn_count = 0

        for st, tp in rows:
            if st in counts_by_status:
                counts_by_status[st] += 1
            if tp in counts_by_type:
                counts_by_type[tp] += 1

            if st in {SubmissionStatus.DRAFT.value, SubmissionStatus.READY.value, SubmissionStatus.SUBMITTED.value, SubmissionStatus.UNDER_REVIEW.value}:
                active_count += 1
            elif st == SubmissionStatus.ACCEPTED.value:
                accepted_count += 1
            elif st == SubmissionStatus.REJECTED.value:
                rejected_count += 1
            elif st == SubmissionStatus.WITHDRAWN.value:
                withdrawn_count += 1

        return SubmissionSummaryResponse(
            total_submissions=len(rows),
            active_submissions=active_count,
            accepted_submissions=accepted_count,
            rejected_submissions=rejected_count,
            withdrawn_submissions=withdrawn_count,
            counts_by_status=counts_by_status,
            counts_by_type=counts_by_type,
        )

    @classmethod
    def update_submission(
        cls,
        db: Session,
        user_id: uuid.UUID,
        submission_id: uuid.UUID,
        payload: ResearchSubmissionUpdate,
    ) -> ResearchSubmissionModel:
        """Partially updates metadata of an existing submission draft."""
        submission = cls.get_submission(db, user_id, submission_id)
        if submission is None:
            raise ValueError(f"Research submission with ID '{submission_id}' not found.")

        now = datetime.now(timezone.utc)
        if payload.title is not None:
            submission.title = payload.title.strip()
        if payload.abstract is not None:
            submission.abstract = payload.abstract.strip() if payload.abstract else None
        if payload.submission_type is not None:
            submission.submission_type = payload.submission_type.value
        if payload.external_submission_id is not None:
            submission.external_submission_id = payload.external_submission_id.strip() if payload.external_submission_id else None
        if payload.venue is not None:
            submission.venue = payload.venue.strip() if payload.venue else None
        if payload.submission_url is not None:
            submission.submission_url = payload.submission_url.strip() if payload.submission_url else None
        if payload.notes is not None:
            submission.notes = payload.notes

        submission.updated_at = now
        db.flush()

        # Phase 4.3 Audit Event Logging
        from app.services.research_submission_document_service import ResearchSubmissionDocumentService
        ResearchSubmissionDocumentService.log_event(
            db=db,
            submission_id=submission.id,
            event_type=SubmissionEventType.METADATA_UPDATED,
            new_state={
                "title": submission.title,
                "submission_type": submission.submission_type,
                "venue": submission.venue,
                "external_submission_id": submission.external_submission_id,
            },
            description=f"Updated metadata for submission '{submission.title}'.",
            user_id=cls.resolve_user_id(db, user_id),
        )

        db.commit()
        db.refresh(submission, ["workspace_item"])
        return submission

    @classmethod
    def transition_status(
        cls,
        db: Session,
        user_id: uuid.UUID,
        submission_id: uuid.UUID,
        target_status: SubmissionStatus,
        notes: str | None = None,
    ) -> ResearchSubmissionModel:
        """
        Executes a deterministic submission status transition.
        Enforces lifecycle policy, timestamp triggers, and workspace promotion.
        """
        submission = cls.get_submission(db, user_id, submission_id)
        if submission is None:
            raise ValueError(f"Research submission with ID '{submission_id}' not found.")

        current_status = SubmissionStatus(submission.status)

        # Idempotent check
        if current_status == target_status:
            if notes:
                submission.notes = notes
                submission.updated_at = datetime.now(timezone.utc)
                db.commit()
                db.refresh(submission, ["workspace_item"])
            return submission

        # Validate transition against policy
        allowed_targets = VALID_SUBMISSION_TRANSITIONS.get(current_status, set())
        if target_status not in allowed_targets:
            raise InvalidSubmissionTransitionError(current_status, target_status, allowed_targets)

        # Readiness validation when transitioning to READY (Phase 4.3)
        if target_status == SubmissionStatus.READY:
            from app.services.research_submission_document_service import ResearchSubmissionDocumentService
            readiness = ResearchSubmissionDocumentService.evaluate_readiness(db, user_id, submission_id)
            if not readiness.can_mark_submission_ready:
                blocker_msgs = "; ".join(b.message for b in readiness.blocking_issues)
                raise InvalidSubmissionTransitionError(
                    current_status=current_status,
                    target_status=target_status,
                    allowed_targets=allowed_targets,
                    message=(
                        f"Cannot transition submission to 'READY': {len(readiness.blocking_issues)} blocking readiness issue(s) detected: [{blocker_msgs}]."
                    ),
                )

        now = datetime.now(timezone.utc)
        submission.status = target_status.value
        submission.status_updated_at = now
        submission.updated_at = now

        if notes:
            submission.notes = notes

        # Timestamp triggers
        if target_status == SubmissionStatus.SUBMITTED:
            submission.submitted_at = now
            # Workspace Promotion Rule:
            # When a submission is SUBMITTED, promote parent workspace opportunity to APPLIED if currently preparatory
            ws_item = submission.workspace_item
            if ws_item and ws_item.status in {WorkspaceStatus.SAVED.value, WorkspaceStatus.CONSIDERING.value, WorkspaceStatus.PLANNING.value}:
                ws_item.status = WorkspaceStatus.APPLIED.value
                ws_item.status_updated_at = now
                ws_item.updated_at = now

                # Trigger Phase 3.6 feedback synchronization
                try:
                    profile = db.execute(
                        select(ResearchProfileModel).where(ResearchProfileModel.user_id == ws_item.user_id)
                    ).scalar_one_or_none()
                    if profile:
                        fb = ResearcherRecommendationFeedbackModel(
                            researcher_id=profile.id,
                            opportunity_id=ws_item.opportunity_id,
                            feedback_type="APPLY",
                            source="SUBMISSION_WORKFLOW",
                            notes=notes,
                        )
                        db.add(fb)
                except Exception as exc:
                    logger.warning(f"Failed to sync Phase 3.6 feedback on submission promotion: {exc}")

        elif target_status in {SubmissionStatus.ACCEPTED, SubmissionStatus.REJECTED}:
            submission.decision_at = now
            # Workspace Promotion Rule on Acceptance:
            ws_item = submission.workspace_item
            if ws_item and target_status == SubmissionStatus.ACCEPTED and ws_item.status == WorkspaceStatus.APPLIED.value:
                ws_item.status = WorkspaceStatus.ACCEPTED.value
                ws_item.status_updated_at = now
                ws_item.updated_at = now
            elif ws_item and target_status == SubmissionStatus.REJECTED and ws_item.status == WorkspaceStatus.APPLIED.value:
                # Check if other submissions for this workspace item are active or accepted
                other_active = db.execute(
                    select(ResearchSubmissionModel).where(
                        ResearchSubmissionModel.workspace_item_id == ws_item.id,
                        ResearchSubmissionModel.id != submission.id,
                        ResearchSubmissionModel.status.in_([
                            SubmissionStatus.ACCEPTED.value,
                            SubmissionStatus.SUBMITTED.value,
                            SubmissionStatus.UNDER_REVIEW.value,
                        ]),
                    )
                ).scalars().all()
                if not other_active:
                    ws_item.status = WorkspaceStatus.REJECTED.value
                    ws_item.status_updated_at = now
                    ws_item.updated_at = now

        elif target_status == SubmissionStatus.DRAFT:
            # If reverting back to draft, reset submitted_at and decision_at
            submission.submitted_at = None
            submission.decision_at = None

        db.flush()

        # Phase 4.3 Audit Event Logging
        from app.services.research_submission_document_service import ResearchSubmissionDocumentService
        ResearchSubmissionDocumentService.log_event(
            db=db,
            submission_id=submission.id,
            event_type=SubmissionEventType.STATUS_TRANSITIONED,
            old_state={"status": current_status.value},
            new_state={"status": target_status.value},
            description=f"Transitioned submission status from '{current_status.value}' to '{target_status.value}'.",
            user_id=cls.resolve_user_id(db, user_id),
        )

        db.commit()
        db.refresh(submission, ["workspace_item"])
        return submission

    @classmethod
    def delete_submission(
        cls,
        db: Session,
        user_id: uuid.UUID,
        submission_id: uuid.UUID,
    ) -> bool:
        """
        Deletes a submission draft or withdrawn submission.
        Active/submitted submissions cannot be deleted directly (must be withdrawn first).
        """
        submission = cls.get_submission(db, user_id, submission_id)
        if submission is None:
            raise ValueError(f"Research submission with ID '{submission_id}' not found.")

        if submission.status not in {SubmissionStatus.DRAFT.value, SubmissionStatus.WITHDRAWN.value}:
            raise InvalidSubmissionTransitionError(
                current_status=submission.status,
                message=(
                    f"Cannot delete active submission in status '{submission.status}'. "
                    "Only 'DRAFT' or 'WITHDRAWN' submissions can be deleted."
                ),
            )

        db.delete(submission)
        db.commit()
        return True
