from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, TYPE_CHECKING
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
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


class DocumentType(str, Enum):
    """Categorization for research submission documents and artifacts (Phase 4.3)."""

    ABSTRACT = "ABSTRACT"
    FULL_PAPER = "FULL_PAPER"
    COVER_LETTER = "COVER_LETTER"
    AUTHOR_BIO = "AUTHOR_BIO"
    CV = "CV"
    SUPPLEMENTARY = "SUPPLEMENTARY"
    FIGURES = "FIGURES"
    DATASET = "DATASET"
    CODE = "CODE"
    DISCLOSURE = "DISCLOSURE"
    OTHER = "OTHER"


class DocumentStatus(str, Enum):
    """Preparation and readiness state of a submission document (Phase 4.3)."""

    REQUIRED = "REQUIRED"
    MISSING = "MISSING"
    DRAFT = "DRAFT"
    READY = "READY"
    REJECTED = "REJECTED"
    ARCHIVED = "ARCHIVED"


class SubmissionEventType(str, Enum):
    """Audit event types for submission lifecycle tracking (Phase 4.3)."""

    SUBMISSION_CREATED = "SUBMISSION_CREATED"
    METADATA_UPDATED = "METADATA_UPDATED"
    STATUS_TRANSITIONED = "STATUS_TRANSITIONED"
    DOCUMENT_ADDED = "DOCUMENT_ADDED"
    DOCUMENT_UPDATED = "DOCUMENT_UPDATED"
    DOCUMENT_VERSION_CREATED = "DOCUMENT_VERSION_CREATED"
    DOCUMENT_STATUS_CHANGED = "DOCUMENT_STATUS_CHANGED"
    DOCUMENT_ARCHIVED = "DOCUMENT_ARCHIVED"
    DOCUMENT_DELETED = "DOCUMENT_DELETED"
    READINESS_EVALUATED = "READINESS_EVALUATED"


class ResearchSubmissionDocumentModel(Base):
    """
    Research submission document / artifact entity (Phase 4.3).

    Tracks manuscripts, cover letters, disclosures, datasets, and supplemental files
    associated with a specific research submission, their preparation status, and versions.
    """

    __tablename__ = "research_submission_documents"
    __table_args__ = (
        CheckConstraint(
            "status IN ('REQUIRED', 'MISSING', 'DRAFT', 'READY', 'REJECTED', 'ARCHIVED')",
            name="chk_submission_docs_status",
        ),
        CheckConstraint(
            "document_type IN ('ABSTRACT', 'FULL_PAPER', 'COVER_LETTER', 'AUTHOR_BIO', 'CV', 'SUPPLEMENTARY', 'FIGURES', 'DATASET', 'CODE', 'DISCLOSURE', 'OTHER')",
            name="chk_submission_docs_type",
        ),
        Index("idx_sub_docs_sub_status", "submission_id", "status"),
        Index("idx_sub_docs_sub_type", "submission_id", "document_type"),
        Index("idx_sub_docs_updated", "updated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research_submissions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    document_type: Mapped[str] = mapped_column(
        String(50),
        default=DocumentType.OTHER.value,
        server_default=DocumentType.OTHER.value,
        nullable=False,
        comment="Document category: FULL_PAPER, ABSTRACT, COVER_LETTER, etc.",
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Document title or display name",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Instructions, requirements description, or user notes",
    )
    status: Mapped[str] = mapped_column(
        String(50),
        default=DocumentStatus.DRAFT.value,
        server_default=DocumentStatus.DRAFT.value,
        nullable=False,
        index=True,
        comment="Preparation status: REQUIRED, MISSING, DRAFT, READY, REJECTED, ARCHIVED",
    )
    is_required: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
        comment="Whether this document is mandatory for marking submission READY",
    )
    current_version: Mapped[int] = mapped_column(
        Integer,
        default=1,
        server_default="1",
        nullable=False,
        comment="Current active version number",
    )
    file_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        server_default="{}",
        nullable=False,
        comment="MIME type, size, hash, original filename, etc.",
    )
    storage_reference: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Opaque reference identifier or storage key; never fabricated",
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when document transitioned to READY",
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
    submission: Mapped["ResearchSubmissionModel"] = relationship(
        back_populates="documents",
    )
    versions: Mapped[list["ResearchSubmissionDocumentVersionModel"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="desc(ResearchSubmissionDocumentVersionModel.version_number)",
    )


class ResearchSubmissionDocumentVersionModel(Base):
    """
    Immutable version snapshot for research submission documents (Phase 4.3).

    Preserves historical document revisions, metadata, and checksums.
    """

    __tablename__ = "research_submission_document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version_number", name="uq_doc_version"),
        Index("idx_doc_versions_doc_id", "document_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research_submission_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="1-based version number",
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    file_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        server_default="{}",
        nullable=False,
    )
    storage_reference: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    checksum: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        comment="SHA-256 or MD5 checksum of artifact if computed",
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )

    # Relationships
    document: Mapped["ResearchSubmissionDocumentModel"] = relationship(
        back_populates="versions",
    )


class ResearchSubmissionEventModel(Base):
    """
    Immutable audit trail event for research submissions and document actions (Phase 4.3).
    """

    __tablename__ = "research_submission_events"
    __table_args__ = (
        Index("idx_sub_events_sub_created", "submission_id", "created_at"),
        Index("idx_sub_events_event_type", "event_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research_submissions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Event category: SUBMISSION_CREATED, DOCUMENT_ADDED, etc.",
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research_submission_documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    old_state: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    new_state: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Human-readable event summary",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )

    # Relationships
    submission: Mapped["ResearchSubmissionModel"] = relationship(
        back_populates="events",
    )
