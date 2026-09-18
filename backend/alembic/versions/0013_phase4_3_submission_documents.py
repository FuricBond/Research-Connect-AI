"""Phase 4.3 — Research Submission Workflow & Document Management

Creates research_submission_documents, research_submission_document_versions,
and research_submission_events tables:
  - research_submission_documents:
      - id (UUID primary key)
      - submission_id (UUID FK to research_submissions.id ON DELETE CASCADE)
      - document_type (VARCHAR 50, not null)
      - title (VARCHAR 255, not null)
      - description (TEXT, nullable)
      - status (VARCHAR 50, not null, default 'DRAFT')
      - is_required (BOOLEAN, not null, default false)
      - current_version (INTEGER, not null, default 1)
      - file_metadata (JSONB, not null, default '{}')
      - storage_reference (VARCHAR 500, nullable)
      - completed_at (TIMESTAMPTZ, nullable)
      - created_at (TIMESTAMPTZ, not null, default now())
      - updated_at (TIMESTAMPTZ, not null, default now())
  - research_submission_document_versions:
      - id (UUID primary key)
      - document_id (UUID FK to research_submission_documents.id ON DELETE CASCADE)
      - version_number (INTEGER, not null)
      - title (VARCHAR 255, not null)
      - file_metadata (JSONB, not null, default '{}')
      - storage_reference (VARCHAR 500, nullable)
      - checksum (VARCHAR 128, nullable)
      - status (VARCHAR 50, not null)
      - created_at (TIMESTAMPTZ, not null, default now())
      - created_by_id (UUID, nullable)
  - research_submission_events:
      - id (UUID primary key)
      - submission_id (UUID FK to research_submissions.id ON DELETE CASCADE)
      - event_type (VARCHAR 50, not null)
      - document_id (UUID FK to research_submission_documents.id ON DELETE SET NULL, nullable)
      - old_state (JSONB, nullable)
      - new_state (JSONB, nullable)
      - description (TEXT, not null)
      - created_at (TIMESTAMPTZ, not null, default now())
      - created_by_id (UUID, nullable)

Revision ID: 0013_phase4_3_submission_documents
Revises:     0012_phase4_2_research_submission
Create Date: 2026-09-18 23:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0013_phase4_3_submission_documents"
down_revision: Union[str, None] = "0012_phase4_2_research_submission"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create research_submission_documents table
    op.create_table(
        "research_submission_documents",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "submission_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("research_submissions.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
            comment="Foreign key referencing parent research submission",
        ),
        sa.Column(
            "document_type",
            sa.String(length=50),
            nullable=False,
            server_default="OTHER",
            comment="Document category: FULL_PAPER, ABSTRACT, COVER_LETTER, etc.",
        ),
        sa.Column(
            "title",
            sa.String(length=255),
            nullable=False,
            comment="Document title or display name",
        ),
        sa.Column(
            "description",
            sa.Text(),
            nullable=True,
            comment="Instructions or description",
        ),
        sa.Column(
            "status",
            sa.String(length=50),
            nullable=False,
            server_default="DRAFT",
            comment="Status: REQUIRED, MISSING, DRAFT, READY, REJECTED, ARCHIVED",
        ),
        sa.Column(
            "is_required",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="Whether this document is mandatory for readiness",
        ),
        sa.Column(
            "current_version",
            sa.Integer(),
            nullable=False,
            server_default="1",
            comment="Active version number",
        ),
        sa.Column(
            "file_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
            comment="MIME type, size, hash, original filename",
        ),
        sa.Column(
            "storage_reference",
            sa.String(length=500),
            nullable=True,
            comment="Opaque reference identifier or storage key",
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp when document transitioned to READY",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('REQUIRED', 'MISSING', 'DRAFT', 'READY', 'REJECTED', 'ARCHIVED')",
            name="chk_submission_docs_status",
        ),
        sa.CheckConstraint(
            "document_type IN ('ABSTRACT', 'FULL_PAPER', 'COVER_LETTER', 'AUTHOR_BIO', 'CV', 'SUPPLEMENTARY', 'FIGURES', 'DATASET', 'CODE', 'DISCLOSURE', 'OTHER')",
            name="chk_submission_docs_type",
        ),
    )
    op.create_index(
        "idx_sub_docs_sub_status",
        "research_submission_documents",
        ["submission_id", "status"],
    )
    op.create_index(
        "idx_sub_docs_sub_type",
        "research_submission_documents",
        ["submission_id", "document_type"],
    )
    op.create_index(
        "idx_sub_docs_updated",
        "research_submission_documents",
        ["updated_at"],
    )

    # 2. Create research_submission_document_versions table
    op.create_table(
        "research_submission_document_versions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("research_submission_documents.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "version_number",
            sa.Integer(),
            nullable=False,
            comment="1-based version number",
        ),
        sa.Column(
            "title",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "file_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "storage_reference",
            sa.String(length=500),
            nullable=True,
        ),
        sa.Column(
            "checksum",
            sa.String(length=128),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.String(length=50),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_by_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.UniqueConstraint("document_id", "version_number", name="uq_doc_version"),
    )
    op.create_index(
        "idx_doc_versions_doc_id",
        "research_submission_document_versions",
        ["document_id"],
    )

    # 3. Create research_submission_events table
    op.create_table(
        "research_submission_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "submission_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("research_submissions.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "event_type",
            sa.String(length=50),
            nullable=False,
            comment="Event category: SUBMISSION_CREATED, DOCUMENT_ADDED, etc.",
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("research_submission_documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "old_state",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "new_state",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "description",
            sa.Text(),
            nullable=False,
            comment="Human-readable event summary",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_by_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_index(
        "idx_sub_events_sub_created",
        "research_submission_events",
        ["submission_id", "created_at"],
    )
    op.create_index(
        "idx_sub_events_event_type",
        "research_submission_events",
        ["event_type"],
    )


def downgrade() -> None:
    op.drop_index("idx_sub_events_event_type", table_name="research_submission_events")
    op.drop_index("idx_sub_events_sub_created", table_name="research_submission_events")
    op.drop_table("research_submission_events")

    op.drop_index("idx_doc_versions_doc_id", table_name="research_submission_document_versions")
    op.drop_table("research_submission_document_versions")

    op.drop_index("idx_sub_docs_updated", table_name="research_submission_documents")
    op.drop_index("idx_sub_docs_sub_type", table_name="research_submission_documents")
    op.drop_index("idx_sub_docs_sub_status", table_name="research_submission_documents")
    op.drop_table("research_submission_documents")
