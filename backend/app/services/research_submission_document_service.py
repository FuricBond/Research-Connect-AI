"""
Research Submission Document & Readiness Service (Phase 4.3).

Provides deterministic business logic for:
  - Document artifact lifecycle (REQUIRED, MISSING, DRAFT, READY, REJECTED, ARCHIVED)
  - Immutable document versioning snapshots
  - Submission readiness evaluation (blockers, warnings, metadata completeness, deadline context)
  - Chronological audit trail logging for all state-mutating actions
  - Strict researcher tenant isolation through parent workspace item
  - Zero N+1 query performance guarantees
"""
from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, Sequence
import uuid

from sqlalchemy import Select, and_, desc, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models.opportunity import OpportunityModel
from app.models.research_submission import ResearchSubmissionModel, SubmissionStatus
from app.models.saved_opportunity import SavedOpportunityModel
from app.models.submission_document import (
    DocumentStatus,
    DocumentType,
    ResearchSubmissionDocumentModel,
    ResearchSubmissionDocumentVersionModel,
    ResearchSubmissionEventModel,
    SubmissionEventType,
)
from app.schemas.research_submission import (
    SubmissionDocumentCreate,
    SubmissionDocumentListResponse,
    SubmissionDocumentRead,
    SubmissionDocumentUpdate,
    SubmissionDocumentVersionRead,
    SubmissionHistoryEvent,
    SubmissionHistoryResponse,
    SubmissionReadinessIssue,
    SubmissionReadinessResponse,
)
from app.services.workspace_service import WorkspaceService

logger = logging.getLogger(__name__)


class ResearchSubmissionDocumentService:
    """Core service for submission document artifacts, versioning, audit trail, and readiness."""

    @classmethod
    def resolve_user_id(cls, db: Session, user_or_profile_id: uuid.UUID) -> uuid.UUID:
        """Resolves authenticated user ID from user or profile identifier."""
        return WorkspaceService.resolve_user_id(db, user_or_profile_id)

    @classmethod
    def validate_submission_ownership(
        cls,
        db: Session,
        user_id: uuid.UUID,
        submission_id: uuid.UUID,
    ) -> tuple[ResearchSubmissionModel, uuid.UUID]:
        """
        Validates researcher ownership of a submission.
        Raises ValueError if not found, PermissionError if owned by another researcher.
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
            raise ValueError(f"Research submission with ID '{submission_id}' not found.")

        if submission.workspace_item.user_id != resolved_user_id:
            raise PermissionError("Forbidden: You do not have permission to access this research submission.")

        return submission, resolved_user_id

    @classmethod
    def log_event(
        cls,
        db: Session,
        submission_id: uuid.UUID,
        event_type: SubmissionEventType,
        description: str,
        document_id: uuid.UUID | None = None,
        old_state: dict[str, Any] | None = None,
        new_state: dict[str, Any] | None = None,
        user_id: uuid.UUID | None = None,
    ) -> ResearchSubmissionEventModel:
        """Records an immutable audit trail event for a submission or document action."""
        now = datetime.now(timezone.utc)
        event = ResearchSubmissionEventModel(
            submission_id=submission_id,
            event_type=event_type.value if hasattr(event_type, "value") else str(event_type),
            document_id=document_id,
            old_state=old_state,
            new_state=new_state,
            description=description,
            created_at=now,
            created_by_id=user_id,
        )
        db.add(event)
        return event

    # ── Document CRUD & Version Management ──────────────────────────────────────

    @classmethod
    def create_document(
        cls,
        db: Session,
        user_id: uuid.UUID,
        submission_id: uuid.UUID,
        payload: SubmissionDocumentCreate,
    ) -> SubmissionDocumentRead:
        """
        Creates a new document artifact for a submission.
        Initializes version 1 and logs an audit event.
        """
        submission, resolved_user_id = cls.validate_submission_ownership(db, user_id, submission_id)

        now = datetime.now(timezone.utc)
        doc_status = payload.status.value if hasattr(payload.status, "value") else str(payload.status)
        doc_type = payload.document_type.value if hasattr(payload.document_type, "value") else str(payload.document_type)

        completed_at = now if doc_status == DocumentStatus.READY.value else None

        doc = ResearchSubmissionDocumentModel(
            submission_id=submission.id,
            document_type=doc_type,
            title=payload.title.strip(),
            description=payload.description.strip() if payload.description else None,
            status=doc_status,
            is_required=payload.is_required,
            current_version=1,
            file_metadata=payload.file_metadata or {},
            storage_reference=payload.storage_reference.strip() if payload.storage_reference else None,
            completed_at=completed_at,
            created_at=now,
            updated_at=now,
        )
        db.add(doc)
        db.flush()

        # Create initial version snapshot (v1)
        checksum_val = None
        if isinstance(doc.file_metadata, dict):
            checksum_val = doc.file_metadata.get("checksum") or doc.file_metadata.get("checksum_sha256")

        v1 = ResearchSubmissionDocumentVersionModel(
            document_id=doc.id,
            version_number=1,
            title=doc.title,
            file_metadata=doc.file_metadata,
            storage_reference=doc.storage_reference,
            checksum=checksum_val,
            status=doc.status,
            created_at=now,
            created_by_id=resolved_user_id,
        )
        db.add(v1)


        # Audit log event
        cls.log_event(
            db=db,
            submission_id=submission.id,
            event_type=SubmissionEventType.DOCUMENT_ADDED,
            document_id=doc.id,
            new_state={
                "title": doc.title,
                "document_type": doc.document_type,
                "status": doc.status,
                "is_required": doc.is_required,
                "version": doc.current_version,
            },
            description=f"Added document '{doc.title}' ({doc.document_type}) with status '{doc.status}'.",
            user_id=resolved_user_id,
        )

        db.commit()
        db.refresh(doc, ["versions"])
        return cls._to_document_read(doc)

    @classmethod
    def get_document(
        cls,
        db: Session,
        user_id: uuid.UUID,
        submission_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> SubmissionDocumentRead | None:
        """Retrieves a single document with versions and researcher authorization."""
        cls.validate_submission_ownership(db, user_id, submission_id)

        doc = db.execute(
            select(ResearchSubmissionDocumentModel)
            .options(joinedload(ResearchSubmissionDocumentModel.versions))
            .where(
                and_(
                    ResearchSubmissionDocumentModel.id == document_id,
                    ResearchSubmissionDocumentModel.submission_id == submission_id,
                )
            )
        ).unique().scalar_one_or_none()

        if doc is None:
            return None

        return cls._to_document_read(doc)

    @classmethod
    def list_documents(
        cls,
        db: Session,
        user_id: uuid.UUID,
        submission_id: uuid.UUID,
        status: DocumentStatus | str | None = None,
        document_type: DocumentType | str | None = None,
        is_required: bool | None = None,
        include_archived: bool = True,
    ) -> SubmissionDocumentListResponse:
        """
        Lists all document artifacts for a submission with counts and filtering.
        Single query guarantees zero N+1 queries.
        """
        cls.validate_submission_ownership(db, user_id, submission_id)

        stmt: Select = (
            select(ResearchSubmissionDocumentModel)
            .options(joinedload(ResearchSubmissionDocumentModel.versions))
            .where(ResearchSubmissionDocumentModel.submission_id == submission_id)
        )

        if not include_archived:
            stmt = stmt.where(ResearchSubmissionDocumentModel.status != DocumentStatus.ARCHIVED.value)

        if status is not None:
            status_val = status.value if hasattr(status, "value") else str(status)
            stmt = stmt.where(ResearchSubmissionDocumentModel.status == status_val)

        if document_type is not None:
            type_val = document_type.value if hasattr(document_type, "value") else str(document_type)
            stmt = stmt.where(ResearchSubmissionDocumentModel.document_type == type_val)

        if is_required is not None:
            stmt = stmt.where(ResearchSubmissionDocumentModel.is_required == is_required)

        stmt = stmt.order_by(
            ResearchSubmissionDocumentModel.is_required.desc(),
            ResearchSubmissionDocumentModel.created_at.asc(),
        )

        docs = db.execute(stmt).unique().scalars().all()

        counts_by_status: dict[str, int] = {s.value: 0 for s in DocumentStatus}
        counts_by_type: dict[str, int] = {t.value: 0 for t in DocumentType}

        items: list[SubmissionDocumentRead] = []
        for doc in docs:
            if doc.status in counts_by_status:
                counts_by_status[doc.status] += 1
            if doc.document_type in counts_by_type:
                counts_by_type[doc.document_type] += 1
            items.append(cls._to_document_read(doc))

        return SubmissionDocumentListResponse(
            items=items,
            total_count=len(items),
            submission_id=submission_id,
            counts_by_status=counts_by_status,
            counts_by_type=counts_by_type,
        )

    @classmethod
    def update_document(
        cls,
        db: Session,
        user_id: uuid.UUID,
        submission_id: uuid.UUID,
        document_id: uuid.UUID,
        payload: SubmissionDocumentUpdate,
    ) -> SubmissionDocumentRead:
        """
        Partially updates a document.
        If create_new_version is True, preserves history and creates an immutable snapshot.
        """
        submission, resolved_user_id = cls.validate_submission_ownership(db, user_id, submission_id)

        doc = db.execute(
            select(ResearchSubmissionDocumentModel)
            .options(joinedload(ResearchSubmissionDocumentModel.versions))
            .where(
                and_(
                    ResearchSubmissionDocumentModel.id == document_id,
                    ResearchSubmissionDocumentModel.submission_id == submission_id,
                )
            )
        ).unique().scalar_one_or_none()

        if doc is None:
            raise ValueError(f"Document with ID '{document_id}' not found for submission '{submission_id}'.")

        old_state = {
            "title": doc.title,
            "status": doc.status,
            "document_type": doc.document_type,
            "is_required": doc.is_required,
            "version": doc.current_version,
            "storage_reference": doc.storage_reference,
        }

        now = datetime.now(timezone.utc)
        status_changed = False
        old_status = doc.status

        if payload.title is not None:
            doc.title = payload.title.strip()
        if payload.description is not None:
            doc.description = payload.description.strip() if payload.description else None
        if payload.document_type is not None:
            doc.document_type = payload.document_type.value if hasattr(payload.document_type, "value") else str(payload.document_type)
        if payload.is_required is not None:
            doc.is_required = payload.is_required
        if payload.file_metadata is not None:
            doc.file_metadata = payload.file_metadata
        if payload.storage_reference is not None:
            doc.storage_reference = payload.storage_reference.strip() if payload.storage_reference else None

        if payload.status is not None:
            new_status = payload.status.value if hasattr(payload.status, "value") else str(payload.status)
            if new_status != doc.status:
                status_changed = True
                doc.status = new_status
                if new_status == DocumentStatus.READY.value:
                    doc.completed_at = now
                elif old_status == DocumentStatus.READY.value:
                    doc.completed_at = None

        # Versioning handling
        version_created = False
        if payload.create_new_version:
            doc.current_version += 1
            version_created = True
            v_checksum = None
            if isinstance(doc.file_metadata, dict):
                v_checksum = doc.file_metadata.get("checksum") or doc.file_metadata.get("checksum_sha256")

            new_version = ResearchSubmissionDocumentVersionModel(
                document_id=doc.id,
                version_number=doc.current_version,
                title=doc.title,
                file_metadata=doc.file_metadata or {},
                storage_reference=doc.storage_reference,
                checksum=v_checksum,
                status=doc.status,
                created_at=now,
                created_by_id=resolved_user_id,
            )
            db.add(new_version)


        doc.updated_at = now
        db.flush()

        # Audit event
        new_state = {
            "title": doc.title,
            "status": doc.status,
            "document_type": doc.document_type,
            "is_required": doc.is_required,
            "version": doc.current_version,
            "storage_reference": doc.storage_reference,
        }

        if version_created:
            cls.log_event(
                db=db,
                submission_id=submission.id,
                event_type=SubmissionEventType.DOCUMENT_VERSION_CREATED,
                document_id=doc.id,
                old_state=old_state,
                new_state=new_state,
                description=f"Created version {doc.current_version} for document '{doc.title}'.",
                user_id=resolved_user_id,
            )
        elif status_changed:
            cls.log_event(
                db=db,
                submission_id=submission.id,
                event_type=SubmissionEventType.DOCUMENT_STATUS_CHANGED,
                document_id=doc.id,
                old_state=old_state,
                new_state=new_state,
                description=f"Changed document '{doc.title}' status from '{old_status}' to '{doc.status}'.",
                user_id=resolved_user_id,
            )
        else:
            cls.log_event(
                db=db,
                submission_id=submission.id,
                event_type=SubmissionEventType.DOCUMENT_UPDATED,
                document_id=doc.id,
                old_state=old_state,
                new_state=new_state,
                description=f"Updated document '{doc.title}' metadata.",
                user_id=resolved_user_id,
            )

        db.commit()
        db.refresh(doc, ["versions"])
        return cls._to_document_read(doc)

    @classmethod
    def delete_document(
        cls,
        db: Session,
        user_id: uuid.UUID,
        submission_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> None:
        """
        Permanently removes a document and its version history.
        Logs an audit event.
        """
        submission, resolved_user_id = cls.validate_submission_ownership(db, user_id, submission_id)

        doc = db.execute(
            select(ResearchSubmissionDocumentModel).where(
                and_(
                    ResearchSubmissionDocumentModel.id == document_id,
                    ResearchSubmissionDocumentModel.submission_id == submission_id,
                )
            )
        ).scalar_one_or_none()

        if doc is None:
            raise ValueError(f"Document with ID '{document_id}' not found for submission '{submission_id}'.")

        doc_title = doc.title
        doc_type = doc.document_type

        db.delete(doc)

        cls.log_event(
            db=db,
            submission_id=submission.id,
            event_type=SubmissionEventType.DOCUMENT_DELETED,
            document_id=None,
            old_state={"title": doc_title, "document_type": doc_type},
            description=f"Deleted document '{doc_title}' ({doc_type}).",
            user_id=resolved_user_id,
        )

        db.commit()

    @classmethod
    def list_document_versions(
        cls,
        db: Session,
        user_id: uuid.UUID,
        submission_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> list[SubmissionDocumentVersionRead]:
        """Retrieves complete immutable version history for a specific document."""
        cls.validate_submission_ownership(db, user_id, submission_id)

        doc = db.execute(
            select(ResearchSubmissionDocumentModel).where(
                and_(
                    ResearchSubmissionDocumentModel.id == document_id,
                    ResearchSubmissionDocumentModel.submission_id == submission_id,
                )
            )
        ).scalar_one_or_none()

        if doc is None:
            raise ValueError(f"Document with ID '{document_id}' not found for submission '{submission_id}'.")

        versions = db.execute(
            select(ResearchSubmissionDocumentVersionModel)
            .where(ResearchSubmissionDocumentVersionModel.document_id == document_id)
            .order_by(desc(ResearchSubmissionDocumentVersionModel.version_number))
        ).scalars().all()

        return [
            SubmissionDocumentVersionRead(
                id=v.id,
                document_id=v.document_id,
                version_number=v.version_number,
                title=v.title,
                file_metadata=v.file_metadata or {},
                storage_reference=v.storage_reference,
                checksum=v.checksum,
                status=v.status,
                created_at=v.created_at,
                created_by_id=v.created_by_id,
            )
            for v in versions
        ]

    # ── Submission Readiness Assessment Engine ─────────────────────────────────

    @classmethod
    def evaluate_readiness(
        cls,
        db: Session,
        user_id: uuid.UUID,
        submission_id: uuid.UUID,
    ) -> SubmissionReadinessResponse:
        """
        Executes deterministic submission readiness evaluation.
        Computes document metrics, metadata completeness, blockers, warnings,
        and determines if the submission satisfies requirements to be marked READY.
        """
        from app.services.research_submission_service import ResearchSubmissionService

        submission, _ = cls.validate_submission_ownership(db, user_id, submission_id)

        ws_item = submission.workspace_item
        opp = ws_item.opportunity if ws_item else None
        deadline_ctx = ResearchSubmissionService.extract_deadline_context(opp) if opp else None

        # Load all documents for this submission
        docs = db.execute(
            select(ResearchSubmissionDocumentModel)
            .options(joinedload(ResearchSubmissionDocumentModel.versions))
            .where(ResearchSubmissionDocumentModel.submission_id == submission_id)
            .order_by(ResearchSubmissionDocumentModel.created_at.asc())
        ).unique().scalars().all()

        total_docs = len([d for d in docs if d.status != DocumentStatus.ARCHIVED.value])
        required_docs = [d for d in docs if d.is_required and d.status != DocumentStatus.ARCHIVED.value]
        completed_docs = [d for d in required_docs if d.status == DocumentStatus.READY.value]
        missing_docs = [d for d in docs if d.status in {DocumentStatus.MISSING.value, DocumentStatus.REQUIRED.value}]
        draft_docs = [d for d in docs if d.status == DocumentStatus.DRAFT.value]
        rejected_docs = [d for d in docs if d.status == DocumentStatus.REJECTED.value]
        archived_docs = [d for d in docs if d.status == DocumentStatus.ARCHIVED.value]

        # 1. Metadata completeness (0.0 to 1.0)
        completeness_score = 0.0
        if submission.title and len(submission.title.strip()) > 0:
            completeness_score += 0.4
        if submission.submission_type:
            completeness_score += 0.2
        if submission.abstract and len(submission.abstract.strip()) > 0:
            completeness_score += 0.2
        if submission.venue and len(submission.venue.strip()) > 0:
            completeness_score += 0.1
        if submission.external_submission_id or submission.submission_url:
            completeness_score += 0.1
        completeness_score = round(min(completeness_score, 1.0), 2)

        # 2. Blocking issues
        blocking_issues: list[SubmissionReadinessIssue] = []

        if not submission.title or len(submission.title.strip()) == 0:
            blocking_issues.append(
                SubmissionReadinessIssue(
                    code="EMPTY_TITLE",
                    message="Manuscript submission title cannot be empty.",
                    is_blocking=True,
                    field="title",
                )
            )

        for req_doc in required_docs:
            if req_doc.status == DocumentStatus.REJECTED.value:
                blocking_issues.append(
                    SubmissionReadinessIssue(
                        code="REQUIRED_DOCUMENT_REJECTED",
                        message=f"Required document '{req_doc.title}' ({req_doc.document_type}) was marked REJECTED and must be revised.",
                        is_blocking=True,
                        document_id=req_doc.id,
                        field="status",
                    )
                )
            elif req_doc.status in {DocumentStatus.MISSING.value, DocumentStatus.REQUIRED.value}:
                blocking_issues.append(
                    SubmissionReadinessIssue(
                        code="MISSING_REQUIRED_DOCUMENT",
                        message=f"Required document '{req_doc.title}' ({req_doc.document_type}) is missing and must be prepared.",
                        is_blocking=True,
                        document_id=req_doc.id,
                        field="status",
                    )
                )
            elif req_doc.status == DocumentStatus.DRAFT.value:
                blocking_issues.append(
                    SubmissionReadinessIssue(
                        code="REQUIRED_DOCUMENT_IN_DRAFT",
                        message=f"Required document '{req_doc.title}' ({req_doc.document_type}) is still in DRAFT status and must be marked READY.",
                        is_blocking=True,
                        document_id=req_doc.id,
                        field="status",
                    )
                )

        # 3. Informational warnings
        warnings: list[SubmissionReadinessIssue] = []

        if deadline_ctx:
            if deadline_ctx.urgency_tier in {"CRITICAL", "URGENT"}:
                warnings.append(
                    SubmissionReadinessIssue(
                        code="APPROACHING_DEADLINE",
                        message=f"Submission deadline is approaching ({deadline_ctx.days_remaining:.1f} days remaining, urgency: {deadline_ctx.urgency_tier}).",
                        is_blocking=False,
                        field="submission_deadline",
                    )
                )
            if deadline_ctx.days_remaining is not None and deadline_ctx.days_remaining < 0:
                warnings.append(
                    SubmissionReadinessIssue(
                        code="DEADLINE_PASSED",
                        message="The canonical submission deadline has already passed according to opportunity intelligence.",
                        is_blocking=False,
                        field="submission_deadline",
                    )
                )

        optional_drafts = [d for d in docs if not d.is_required and d.status == DocumentStatus.DRAFT.value]
        if optional_drafts:
            warnings.append(
                SubmissionReadinessIssue(
                    code="OPTIONAL_DOCUMENT_IN_DRAFT",
                    message=f"{len(optional_drafts)} optional document(s) are still in draft.",
                    is_blocking=False,
                )
            )

        if not submission.external_submission_id:
            warnings.append(
                SubmissionReadinessIssue(
                    code="MISSING_EXTERNAL_TRACKING_ID",
                    message="External portal submission/tracking ID (e.g. OpenReview #142) has not been entered.",
                    is_blocking=False,
                    field="external_submission_id",
                )
            )

        if total_docs == 0:
            warnings.append(
                SubmissionReadinessIssue(
                    code="NO_DOCUMENTS_ADDED",
                    message="No manuscript documents or files have been attached to this submission.",
                    is_blocking=False,
                )
            )

        # 4. Overall readiness state & percentage
        has_blockers = len(blocking_issues) > 0
        can_mark_ready = not has_blockers

        if len(required_docs) == 0:
            readiness_percentage = 100 if completeness_score >= 0.6 and not has_blockers else completeness_score * 100
        else:
            readiness_percentage = round((len(completed_docs) / len(required_docs)) * 100)

        if has_blockers:
            any_rejected = any(i.code == "REQUIRED_DOCUMENT_REJECTED" for i in blocking_issues)
            overall_readiness = "BLOCKED" if any_rejected else "NOT_READY"
        else:
            overall_readiness = "READY"

        explanation = (
            f"Readiness status: {overall_readiness}. "
            f"{len(completed_docs)}/{len(required_docs)} required documents ready. "
            f"Metadata completeness: {int(completeness_score * 100)}%. "
            f"Blocking issues: {len(blocking_issues)}, Warnings: {len(warnings)}."
        )

        return SubmissionReadinessResponse(
            submission_id=submission.id,
            overall_readiness=overall_readiness,
            can_mark_submission_ready=can_mark_ready,
            readiness_percentage=readiness_percentage,
            total_document_count=total_docs,
            required_document_count=len(required_docs),
            completed_document_count=len(completed_docs),
            missing_document_count=len(missing_docs),
            draft_document_count=len(draft_docs),
            rejected_document_count=len(rejected_docs),
            archived_document_count=len(archived_docs),
            metadata_completeness=completeness_score,
            blocking_issues=blocking_issues,
            warnings=warnings,
            readiness_explanation=explanation,
            deadline_context=deadline_ctx,
        )

    # ── Audit Trail History ───────────────────────────────────────────────────

    @classmethod
    def get_submission_history(
        cls,
        db: Session,
        user_id: uuid.UUID,
        submission_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> SubmissionHistoryResponse:
        """Retrieves chronological audit history events for a submission."""
        cls.validate_submission_ownership(db, user_id, submission_id)

        stmt = (
            select(ResearchSubmissionEventModel)
            .where(ResearchSubmissionEventModel.submission_id == submission_id)
            .order_by(desc(ResearchSubmissionEventModel.created_at))
            .limit(limit)
            .offset(offset)
        )
        events = db.execute(stmt).scalars().all()

        count_stmt = (
            select(func.count(ResearchSubmissionEventModel.id))
            .where(ResearchSubmissionEventModel.submission_id == submission_id)
        )
        total = db.execute(count_stmt).scalar() or 0

        items = [
            SubmissionHistoryEvent(
                id=ev.id,
                submission_id=ev.submission_id,
                event_type=SubmissionEventType(ev.event_type) if ev.event_type in [e.value for e in SubmissionEventType] else SubmissionEventType.STATUS_TRANSITIONED,
                document_id=ev.document_id,
                description=ev.description,
                old_state=ev.old_state,
                new_state=ev.new_state,
                created_at=ev.created_at,
                created_by_id=ev.created_by_id,
            )
            for ev in events
        ]

        return SubmissionHistoryResponse(
            items=items,
            total_count=total,
            submission_id=submission_id,
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    @classmethod
    def _to_document_read(cls, doc: ResearchSubmissionDocumentModel) -> SubmissionDocumentRead:
        """Converts ORM document model to typed Pydantic read schema."""
        versions = doc.versions or []
        versions_read = [
            SubmissionDocumentVersionRead(
                id=v.id,
                document_id=v.document_id,
                version_number=v.version_number,
                title=v.title,
                file_metadata=v.file_metadata or {},
                storage_reference=v.storage_reference,
                checksum=v.checksum,
                status=v.status,
                created_at=v.created_at,
                created_by_id=v.created_by_id,
            )
            for v in versions
        ]

        return SubmissionDocumentRead(
            id=doc.id,
            submission_id=doc.submission_id,
            document_type=DocumentType(doc.document_type) if doc.document_type in [t.value for t in DocumentType] else DocumentType.OTHER,
            title=doc.title,
            description=doc.description,
            status=DocumentStatus(doc.status) if doc.status in [s.value for s in DocumentStatus] else DocumentStatus.DRAFT,
            is_required=doc.is_required,
            current_version=doc.current_version,
            file_metadata=doc.file_metadata or {},
            storage_reference=doc.storage_reference,
            completed_at=doc.completed_at,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
            versions_count=len(versions_read) if versions_read else 1,
            latest_versions=versions_read[:5],
        )
