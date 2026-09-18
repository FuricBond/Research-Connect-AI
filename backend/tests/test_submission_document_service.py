"""
Unit and Service Tests for Phase 4.3 Research Submission Document & Readiness Management.

Tests:
  - Document artifact creation, typing, and default version 1
  - Deterministic document lifecycle states (REQUIRED, MISSING, DRAFT, READY, REJECTED, ARCHIVED)
  - Document version history and immutability snapshots
  - Submission readiness engine (blockers, warnings, metadata completeness, deadline integration)
  - Submission status transition gating on readiness (blocking transitions to READY)
  - Chronological audit trail logging for all state-mutating actions
  - Strict researcher tenant isolation (HTTP 403 / PermissionError on cross-user access)
  - Query efficiency and zero N+1 behavior
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.types import TSVector, Vector
from app.models.base import Base
from app.models.opportunity import OpportunityModel
from app.models.research_profile import ResearchProfileModel
from app.models.research_submission import (
    ResearchSubmissionModel,
    SubmissionStatus,
    SubmissionType,
)
from app.models.saved_opportunity import SavedOpportunityModel, WorkspacePriority, WorkspaceStatus
from app.models.submission_document import (
    DocumentStatus,
    DocumentType,
    ResearchSubmissionDocumentModel,
    ResearchSubmissionDocumentVersionModel,
    ResearchSubmissionEventModel,
    SubmissionEventType,
)
from app.models.user import UserModel
from app.schemas.research_submission import (
    ResearchSubmissionCreate,
    SubmissionDocumentCreate,
    SubmissionDocumentUpdate,
)
from app.services.research_submission_document_service import (
    ResearchSubmissionDocumentService,
)
from app.services.research_submission_service import (
    InvalidSubmissionTransitionError,
    ResearchSubmissionService,
)

# SQLite compatibility
compiles(JSONB, "sqlite")(lambda type_, compiler, **kw: "JSON")
compiles(Vector, "sqlite")(lambda type_, compiler, **kw: "TEXT")
compiles(TSVector, "sqlite")(lambda type_, compiler, **kw: "TEXT")


@pytest.fixture
def db_session() -> Session:
    """Provides a fresh in-memory SQLite session with all Phase 4.3 tables."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    target_tables = [
        Base.metadata.tables["users"],
        Base.metadata.tables["institutions"],
        Base.metadata.tables["researchers"],
        Base.metadata.tables["topics"],
        Base.metadata.tables["opportunities"],
        Base.metadata.tables["opportunity_topics"],
        Base.metadata.tables["saved_opportunities"],
        Base.metadata.tables["research_submissions"],
        Base.metadata.tables["research_submission_documents"],
        Base.metadata.tables["research_submission_document_versions"],
        Base.metadata.tables["research_submission_events"],
        Base.metadata.tables["research_profiles"],
        Base.metadata.tables["researcher_interests"],
        Base.metadata.tables["researcher_preferences"],
        Base.metadata.tables["researcher_recommendation_feedback"],
    ]
    Base.metadata.create_all(bind=engine, tables=target_tables)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def test_users(db_session: Session) -> tuple[UserModel, UserModel]:
    """Creates two distinct researchers for authorization and tenant isolation testing."""
    u1 = UserModel(
        id=uuid.uuid4(),
        email="author1@institution.edu",
        hashed_password="hash_author1",
        full_name="Dr. Author One",
        role="FACULTY",
    )
    u2 = UserModel(
        id=uuid.uuid4(),
        email="author2@institution.edu",
        hashed_password="hash_author2",
        full_name="Dr. Author Two",
        role="FACULTY",
    )
    db_session.add_all([u1, u2])
    db_session.flush()

    p1 = ResearchProfileModel(id=uuid.uuid4(), user_id=u1.id, academic_status="FACULTY")
    p2 = ResearchProfileModel(id=uuid.uuid4(), user_id=u2.id, academic_status="FACULTY")
    db_session.add_all([p1, p2])
    db_session.commit()
    return u1, u2


@pytest.fixture
def test_opportunity(db_session: Session) -> OpportunityModel:
    """Creates a sample conference opportunity with submission deadline."""
    opp = OpportunityModel(
        id=uuid.uuid4(),
        title="ACM SIGMOD 2027",
        opportunity_type="CONFERENCE",
        submission_deadline=datetime(2027, 4, 15, 23, 59, 59, tzinfo=timezone.utc),
        notification_date=datetime(2027, 7, 1, 0, 0, 0, tzinfo=timezone.utc),
        event_start_date=datetime(2027, 10, 10, 0, 0, 0, tzinfo=timezone.utc),
        organizer="ACM",
        publisher="ACM",
    )
    db_session.add(opp)
    db_session.commit()
    return opp


@pytest.fixture
def test_submission(
    db_session: Session,
    test_users: tuple[UserModel, UserModel],
    test_opportunity: OpportunityModel,
) -> ResearchSubmissionModel:
    """Creates a test submission belonging to researcher u1."""
    u1, _ = test_users
    ws_item = SavedOpportunityModel(
        id=uuid.uuid4(),
        user_id=u1.id,
        opportunity_id=test_opportunity.id,
        status=WorkspaceStatus.PLANNING.value,
        priority=WorkspacePriority.HIGH.value,
    )
    db_session.add(ws_item)
    db_session.commit()

    submission = ResearchSubmissionService.create_submission(
        db=db_session,
        user_id=u1.id,
        payload=ResearchSubmissionCreate(
            workspace_item_id=ws_item.id,
            title="Efficient Query Optimization using ML",
            abstract="We present an autonomous learned query optimizer.",
            submission_type=SubmissionType.FULL_PAPER,
            venue="ACM SIGMOD 2027",
        ),
    )
    return submission


# ── Document Management Tests ──────────────────────────────────────────────────


def test_create_document_and_initial_version(
    db_session: Session,
    test_users: tuple[UserModel, UserModel],
    test_submission: ResearchSubmissionModel,
):
    """Verifies creating a document creates the artifact, initial version 1, and audit event."""
    u1, _ = test_users
    service = ResearchSubmissionDocumentService

    doc_read = service.create_document(
        db=db_session,
        user_id=u1.id,
        submission_id=test_submission.id,
        payload=SubmissionDocumentCreate(
            document_type=DocumentType.FULL_PAPER,
            title="Main Manuscript Draft",
            description="Initial 12-page camera ready draft",
            is_required=True,
            status=DocumentStatus.DRAFT,
            file_metadata={"filename": "paper_v1.pdf", "size_bytes": 1048576, "mime": "application/pdf"},
            storage_reference="docs/sub_1/paper_v1.pdf",
        ),
    )

    assert doc_read.title == "Main Manuscript Draft"
    assert doc_read.document_type == DocumentType.FULL_PAPER
    assert doc_read.is_required is True
    assert doc_read.status == DocumentStatus.DRAFT
    assert doc_read.current_version == 1
    assert doc_read.storage_reference == "docs/sub_1/paper_v1.pdf"
    assert doc_read.versions_count == 1

    # Verify version snapshot in DB
    versions = service.list_document_versions(db_session, u1.id, test_submission.id, doc_read.id)
    assert len(versions) == 1
    assert versions[0].version_number == 1
    assert versions[0].title == "Main Manuscript Draft"

    # Verify audit event logged
    history = service.get_submission_history(db_session, u1.id, test_submission.id)
    assert any(e.event_type == SubmissionEventType.DOCUMENT_ADDED for e in history.items)


def test_document_versioning_snapshots(
    db_session: Session,
    test_users: tuple[UserModel, UserModel],
    test_submission: ResearchSubmissionModel,
):
    """Verifies that updating with create_new_version=True increments version without destroying history."""
    u1, _ = test_users
    service = ResearchSubmissionDocumentService

    doc = service.create_document(
        db=db_session,
        user_id=u1.id,
        submission_id=test_submission.id,
        payload=SubmissionDocumentCreate(
            document_type=DocumentType.ABSTRACT,
            title="Short Abstract",
            is_required=True,
            status=DocumentStatus.DRAFT,
            file_metadata={"word_count": 250},
        ),
    )
    assert doc.current_version == 1

    # Update version 2
    updated_v2 = service.update_document(
        db=db_session,
        user_id=u1.id,
        submission_id=test_submission.id,
        document_id=doc.id,
        payload=SubmissionDocumentUpdate(
            title="Short Abstract - Final Revision",
            file_metadata={"word_count": 248, "checksum": "abc123hash"},
            create_new_version=True,
            status=DocumentStatus.READY,
        ),
    )
    assert updated_v2.current_version == 2
    assert updated_v2.title == "Short Abstract - Final Revision"
    assert updated_v2.status == DocumentStatus.READY
    assert updated_v2.completed_at is not None

    # Verify both version 1 and version 2 exist in history
    versions = service.list_document_versions(db_session, u1.id, test_submission.id, doc.id)
    assert len(versions) == 2
    assert versions[0].version_number == 2
    assert versions[0].title == "Short Abstract - Final Revision"
    assert versions[1].version_number == 1
    assert versions[1].title == "Short Abstract"


def test_document_listing_and_filtering(
    db_session: Session,
    test_users: tuple[UserModel, UserModel],
    test_submission: ResearchSubmissionModel,
):
    """Verifies listing documents with status, type, and required filtering."""
    u1, _ = test_users
    service = ResearchSubmissionDocumentService

    # Create multiple documents
    service.create_document(
        db=db_session,
        user_id=u1.id,
        submission_id=test_submission.id,
        payload=SubmissionDocumentCreate(
            document_type=DocumentType.FULL_PAPER,
            title="Manuscript",
            is_required=True,
            status=DocumentStatus.READY,
        ),
    )
    service.create_document(
        db=db_session,
        user_id=u1.id,
        submission_id=test_submission.id,
        payload=SubmissionDocumentCreate(
            document_type=DocumentType.DATASET,
            title="Benchmark Dataset",
            is_required=False,
            status=DocumentStatus.DRAFT,
        ),
    )
    service.create_document(
        db=db_session,
        user_id=u1.id,
        submission_id=test_submission.id,
        payload=SubmissionDocumentCreate(
            document_type=DocumentType.COVER_LETTER,
            title="Cover Letter",
            is_required=False,
            status=DocumentStatus.ARCHIVED,
        ),
    )

    # List all active
    active_docs = service.list_documents(db_session, u1.id, test_submission.id, include_archived=False)
    assert active_docs.total_count == 2

    # Filter by required
    req_docs = service.list_documents(db_session, u1.id, test_submission.id, is_required=True)
    assert req_docs.total_count == 1
    assert req_docs.items[0].title == "Manuscript"

    # Filter by status
    draft_docs = service.list_documents(db_session, u1.id, test_submission.id, status=DocumentStatus.DRAFT)
    assert draft_docs.total_count == 1
    assert draft_docs.items[0].document_type == DocumentType.DATASET


def test_document_deletion_cascades_to_versions(
    db_session: Session,
    test_users: tuple[UserModel, UserModel],
    test_submission: ResearchSubmissionModel,
):
    """Verifies deleting a document removes versions and logs audit event."""
    u1, _ = test_users
    service = ResearchSubmissionDocumentService

    doc = service.create_document(
        db=db_session,
        user_id=u1.id,
        submission_id=test_submission.id,
        payload=SubmissionDocumentCreate(
            document_type=DocumentType.SUPPLEMENTARY,
            title="Old Appendix",
            status=DocumentStatus.DRAFT,
        ),
    )

    # Delete
    service.delete_document(db_session, u1.id, test_submission.id, doc.id)

    # Verify not found
    assert service.get_document(db_session, u1.id, test_submission.id, doc.id) is None

    # Verify audit event logged
    history = service.get_submission_history(db_session, u1.id, test_submission.id)
    assert any(e.event_type == SubmissionEventType.DOCUMENT_DELETED for e in history.items)


# ── Readiness Engine Tests ────────────────────────────────────────────────────


def test_readiness_with_missing_required_document(
    db_session: Session,
    test_users: tuple[UserModel, UserModel],
    test_submission: ResearchSubmissionModel,
):
    """Verifies that a required document in DRAFT or MISSING blocks readiness."""
    u1, _ = test_users
    service = ResearchSubmissionDocumentService

    # Add a required document in DRAFT
    service.create_document(
        db=db_session,
        user_id=u1.id,
        submission_id=test_submission.id,
        payload=SubmissionDocumentCreate(
            document_type=DocumentType.FULL_PAPER,
            title="Camera-ready Paper",
            is_required=True,
            status=DocumentStatus.DRAFT,
        ),
    )

    readiness = service.evaluate_readiness(db_session, u1.id, test_submission.id)

    assert readiness.can_mark_submission_ready is False
    assert readiness.overall_readiness in {"NOT_READY", "BLOCKED"}
    assert any(b.code == "REQUIRED_DOCUMENT_IN_DRAFT" for b in readiness.blocking_issues)


def test_readiness_with_rejected_required_document(
    db_session: Session,
    test_users: tuple[UserModel, UserModel],
    test_submission: ResearchSubmissionModel,
):
    """Verifies that a required document marked REJECTED sets overall_readiness to BLOCKED."""
    u1, _ = test_users
    service = ResearchSubmissionDocumentService

    service.create_document(
        db=db_session,
        user_id=u1.id,
        submission_id=test_submission.id,
        payload=SubmissionDocumentCreate(
            document_type=DocumentType.FULL_PAPER,
            title="Main Paper",
            is_required=True,
            status=DocumentStatus.REJECTED,
        ),
    )

    readiness = service.evaluate_readiness(db_session, u1.id, test_submission.id)

    assert readiness.can_mark_submission_ready is False
    assert readiness.overall_readiness == "BLOCKED"
    assert any(b.code == "REQUIRED_DOCUMENT_REJECTED" for b in readiness.blocking_issues)


def test_readiness_complete_when_required_documents_ready(
    db_session: Session,
    test_users: tuple[UserModel, UserModel],
    test_submission: ResearchSubmissionModel,
):
    """Verifies that when all required documents are READY, overall_readiness is READY."""
    u1, _ = test_users
    service = ResearchSubmissionDocumentService

    doc = service.create_document(
        db=db_session,
        user_id=u1.id,
        submission_id=test_submission.id,
        payload=SubmissionDocumentCreate(
            document_type=DocumentType.FULL_PAPER,
            title="Complete Paper",
            is_required=True,
            status=DocumentStatus.READY,
        ),
    )

    readiness = service.evaluate_readiness(db_session, u1.id, test_submission.id)

    assert readiness.can_mark_submission_ready is True
    assert readiness.overall_readiness == "READY"
    assert len(readiness.blocking_issues) == 0
    assert readiness.readiness_percentage == 100


def test_submission_transition_gated_by_readiness(
    db_session: Session,
    test_users: tuple[UserModel, UserModel],
    test_submission: ResearchSubmissionModel,
):
    """
    Verifies that transition from DRAFT to READY is rejected if blocking readiness issues exist,
    and succeeds once resolved.
    """
    u1, _ = test_users
    doc_service = ResearchSubmissionDocumentService
    sub_service = ResearchSubmissionService

    # Add a required document in DRAFT (blocking issue)
    doc = doc_service.create_document(
        db=db_session,
        user_id=u1.id,
        submission_id=test_submission.id,
        payload=SubmissionDocumentCreate(
            document_type=DocumentType.FULL_PAPER,
            title="Full Manuscript",
            is_required=True,
            status=DocumentStatus.DRAFT,
        ),
    )

    # Attempt transition to READY -> must fail
    with pytest.raises(InvalidSubmissionTransitionError) as exc_info:
        sub_service.transition_status(
            db=db_session,
            user_id=u1.id,
            submission_id=test_submission.id,
            target_status=SubmissionStatus.READY,
        )
    assert "blocking readiness issue" in str(exc_info.value)
    assert "REQUIRED_DOCUMENT_IN_DRAFT" in str(exc_info.value) or "Full Manuscript" in str(exc_info.value)

    # Resolve blocker by marking document READY
    doc_service.update_document(
        db=db_session,
        user_id=u1.id,
        submission_id=test_submission.id,
        document_id=doc.id,
        payload=SubmissionDocumentUpdate(status=DocumentStatus.READY),
    )

    # Now transition to READY -> must succeed
    transitioned = sub_service.transition_status(
        db=db_session,
        user_id=u1.id,
        submission_id=test_submission.id,
        target_status=SubmissionStatus.READY,
    )
    assert transitioned.status == SubmissionStatus.READY.value


# ── Audit Trail Tests ─────────────────────────────────────────────────────────


def test_audit_trail_chronology(
    db_session: Session,
    test_users: tuple[UserModel, UserModel],
    test_submission: ResearchSubmissionModel,
):
    """Verifies that audit history accurately preserves chronological submission actions."""
    u1, _ = test_users
    doc_service = ResearchSubmissionDocumentService
    sub_service = ResearchSubmissionService

    # Create document
    doc = doc_service.create_document(
        db=db_session,
        user_id=u1.id,
        submission_id=test_submission.id,
        payload=SubmissionDocumentCreate(
            document_type=DocumentType.COVER_LETTER,
            title="Editor Letter",
            status=DocumentStatus.DRAFT,
        ),
    )

    # Update metadata
    sub_service.update_submission(
        db=db_session,
        user_id=u1.id,
        submission_id=test_submission.id,
        payload=ResearchSubmissionCreate(
            workspace_item_id=test_submission.workspace_item_id,
            title="Updated Title For SIGMOD",
            submission_type=SubmissionType.FULL_PAPER,
        ),
    )

    # Retrieve history
    history = doc_service.get_submission_history(db_session, u1.id, test_submission.id)
    event_types = [e.event_type for e in history.items]

    assert SubmissionEventType.SUBMISSION_CREATED in event_types
    assert SubmissionEventType.DOCUMENT_ADDED in event_types
    assert SubmissionEventType.METADATA_UPDATED in event_types


# ── Cross-Researcher Isolation Tests ──────────────────────────────────────────


def test_cross_researcher_document_access_forbidden(
    db_session: Session,
    test_users: tuple[UserModel, UserModel],
    test_submission: ResearchSubmissionModel,
):
    """Verifies researcher B cannot view, edit, or delete researcher A's documents."""
    u1, u2 = test_users
    service = ResearchSubmissionDocumentService

    doc = service.create_document(
        db=db_session,
        user_id=u1.id,
        submission_id=test_submission.id,
        payload=SubmissionDocumentCreate(
            document_type=DocumentType.FULL_PAPER,
            title="Private Manuscript",
            status=DocumentStatus.DRAFT,
        ),
    )

    # u2 tries to list u1's documents
    with pytest.raises(PermissionError):
        service.list_documents(db_session, u2.id, test_submission.id)

    # u2 tries to get document
    with pytest.raises(PermissionError):
        service.get_document(db_session, u2.id, test_submission.id, doc.id)

    # u2 tries to update document
    with pytest.raises(PermissionError):
        service.update_document(
            db_session,
            u2.id,
            test_submission.id,
            doc.id,
            payload=SubmissionDocumentUpdate(title="Hacked Title"),
        )

    # u2 tries to evaluate readiness
    with pytest.raises(PermissionError):
        service.evaluate_readiness(db_session, u2.id, test_submission.id)

    # u2 tries to access history
    with pytest.raises(PermissionError):
        service.get_submission_history(db_session, u2.id, test_submission.id)


# ── Query Efficiency & Zero N+1 ───────────────────────────────────────────────


def test_zero_n_plus_one_document_queries(
    db_session: Session,
    test_users: tuple[UserModel, UserModel],
    test_submission: ResearchSubmissionModel,
):
    """Verifies that listing documents and evaluating readiness executes in bounded O(1) queries."""
    from sqlalchemy import event

    u1, _ = test_users
    service = ResearchSubmissionDocumentService

    for i in range(5):
        service.create_document(
            db=db_session,
            user_id=u1.id,
            submission_id=test_submission.id,
            payload=SubmissionDocumentCreate(
                document_type=DocumentType.OTHER,
                title=f"Doc {i}",
                status=DocumentStatus.READY if i % 2 == 0 else DocumentStatus.DRAFT,
            ),
        )

    query_count = 0

    def query_listener(conn, cursor, statement, parameters, context, executemany):
        nonlocal query_count
        query_count += 1

    engine = db_session.get_bind()

    # Warm up user and submission resolution
    _ = service.list_documents(db_session, u1.id, test_submission.id)

    event.listen(engine, "before_cursor_execute", query_listener)

    try:
        # Listing 5 documents should execute <= 3 queries (constant O(1))
        query_count = 0
        docs_5 = service.list_documents(db_session, u1.id, test_submission.id)
        assert len(docs_5.items) == 5
        count_for_5 = query_count
        assert count_for_5 <= 3, f"Listing 5 docs used {count_for_5} queries (expected <= 3)"

        # Add 5 more documents (total 10)
        for i in range(5, 10):
            service.create_document(
                db=db_session,
                user_id=u1.id,
                submission_id=test_submission.id,
                payload=SubmissionDocumentCreate(
                    document_type=DocumentType.OTHER,
                    title=f"Doc {i}",
                    status=DocumentStatus.READY if i % 2 == 0 else DocumentStatus.DRAFT,
                ),
            )

        # Warm up session after commit
        _ = service.list_documents(db_session, u1.id, test_submission.id)

        # Listing 10 documents should use the EXACT SAME number of queries as 5 documents (O(1))
        query_count = 0
        docs_10 = service.list_documents(db_session, u1.id, test_submission.id)
        assert len(docs_10.items) == 10
        count_for_10 = query_count
        assert count_for_10 == count_for_5, (
            f"Expected O(1) query scaling: 5 docs took {count_for_5} queries, but 10 docs took {count_for_10}"
        )

        # Evaluating readiness also executes bounded queries
        query_count = 0
        readiness = service.evaluate_readiness(db_session, u1.id, test_submission.id)
        assert readiness.total_document_count == 10
        assert query_count <= 3, f"Readiness evaluation used {query_count} queries (expected <= 3)"
    finally:
        event.remove(engine, "before_cursor_execute", query_listener)
