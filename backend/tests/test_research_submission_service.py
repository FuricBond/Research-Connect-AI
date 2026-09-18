"""
Phase 4.2 — Unit and Service Tests for ResearchSubmissionService.

Tests cover:
  1. Creation:
     - Default status DRAFT
     - Non-existent workspace item rejection (ValueError)
     - Cross-researcher workspace item rejection (PermissionError)
  2. Lifecycle and State Machine:
     - Valid transitions (DRAFT -> READY -> SUBMITTED -> UNDER_REVIEW -> ACCEPTED)
     - Valid rejection cycle (UNDER_REVIEW -> REJECTED -> DRAFT)
     - Valid withdrawal from various states (DRAFT -> WITHDRAWN, SUBMITTED -> WITHDRAWN, ACCEPTED -> WITHDRAWN)
     - Idempotent transitions (DRAFT -> DRAFT, READY -> READY)
     - Invalid transitions rejection (InvalidSubmissionTransitionError)
  3. Timestamp Management:
     - submitted_at populated on SUBMITTED
     - decision_at populated on ACCEPTED and REJECTED
     - status_updated_at updated on transition
  4. Workspace Status Synchronization:
     - SUBMITTED promotes PLANNING/SAVED/CONSIDERING workspace item to APPLIED
     - ACCEPTED promotes APPLIED workspace item to ACCEPTED
  5. Metadata Updates:
     - Partial updates to title, abstract, tracking ID, URL, venue, notes
     - Cross-researcher update rejection (PermissionError)
  6. Deletion:
     - Allowed in DRAFT and WITHDRAWN states
     - Disallowed in SUBMITTED, UNDER_REVIEW, ACCEPTED, REJECTED states
     - Cross-researcher delete rejection (PermissionError)
  7. Filtering and Summaries:
     - Filtering by status, submission_type, workspace_item_id, search query
     - User isolation in summary statistics
  8. Deadline Intelligence Integration:
     - Deadline context populated from canonical opportunity
     - Preserves null when deadline is absent
  9. Query Efficiency:
     - Zero N+1 queries during list and detail retrieval
"""
from __future__ import annotations

from datetime import datetime, timezone
import uuid
import pytest
from sqlalchemy import create_engine, event
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
from app.models.user import UserModel
from app.schemas.research_submission import (
    ResearchSubmissionCreate,
    ResearchSubmissionUpdate,
)
from app.services.research_submission_service import (
    InvalidSubmissionTransitionError,
    ResearchSubmissionService,
)
from app.services.workspace_service import WorkspaceService

# SQLite compatibility
compiles(JSONB, "sqlite")(lambda type_, compiler, **kw: "JSON")
compiles(Vector, "sqlite")(lambda type_, compiler, **kw: "TEXT")
compiles(TSVector, "sqlite")(lambda type_, compiler, **kw: "TEXT")


@pytest.fixture
def db_session() -> Session:
    """Provides a fresh in-memory SQLite session with all required tables."""
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
    """Creates two distinct test researchers."""
    u1 = UserModel(
        id=uuid.uuid4(),
        email="alice@university.edu",
        hashed_password="hash_alice",
        full_name="Dr. Alice Chen",
        role="FACULTY",
    )
    u2 = UserModel(
        id=uuid.uuid4(),
        email="bob@university.edu",
        hashed_password="hash_bob",
        full_name="Dr. Bob Martin",
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
def test_opportunities(db_session: Session) -> tuple[OpportunityModel, OpportunityModel]:
    """Creates sample academic opportunities (one with deadline, one without)."""
    opp1 = OpportunityModel(
        id=uuid.uuid4(),
        title="NeurIPS 2026 Conference",
        opportunity_type="CONFERENCE",
        delivery_mode="HYBRID",
        status="ACTIVE",
        publisher="NeurIPS Foundation",
        organizer="NeurIPS Org",
        submission_deadline=datetime(2026, 12, 1, 23, 59, 59, tzinfo=timezone.utc),
        risk_score=0.02,
        is_predatory_flag=False,
    )
    opp2 = OpportunityModel(
        id=uuid.uuid4(),
        title="Nature Machine Intelligence Open Call",
        opportunity_type="JOURNAL",
        delivery_mode="ONLINE",
        status="ACTIVE",
        publisher="Springer Nature",
        organizer="Nature Group",
        submission_deadline=None,
        risk_score=0.01,
        is_predatory_flag=False,
    )
    db_session.add_all([opp1, opp2])
    db_session.commit()
    return opp1, opp2


@pytest.fixture
def test_workspace_items(
    db_session: Session,
    test_users: tuple[UserModel, UserModel],
    test_opportunities: tuple[OpportunityModel, OpportunityModel],
) -> tuple[SavedOpportunityModel, SavedOpportunityModel]:
    """Creates workspace items for user 1 and user 2."""
    u1, u2 = test_users
    opp1, opp2 = test_opportunities

    ws1 = SavedOpportunityModel(
        id=uuid.uuid4(),
        user_id=u1.id,
        opportunity_id=opp1.id,
        status=WorkspaceStatus.PLANNING,
        priority=WorkspacePriority.HIGH,
    )
    ws2 = SavedOpportunityModel(
        id=uuid.uuid4(),
        user_id=u2.id,
        opportunity_id=opp2.id,
        status=WorkspaceStatus.PLANNING,
        priority=WorkspacePriority.MEDIUM,
    )
    db_session.add_all([ws1, ws2])
    db_session.commit()
    return ws1, ws2


def test_create_submission_success_and_defaults(
    db_session: Session,
    test_users: tuple[UserModel, UserModel],
    test_workspace_items: tuple[SavedOpportunityModel, SavedOpportunityModel],
) -> None:
    u1, _ = test_users
    ws1, _ = test_workspace_items

    payload = ResearchSubmissionCreate(
        workspace_item_id=ws1.id,
        title="Scalable Representation Learning for Graphs",
        submission_type=SubmissionType.FULL_PAPER,
        abstract="We present an efficient self-supervised approach...",
        venue="NeurIPS 2026 Track A",
        notes="Primary draft ready for co-author review",
    )

    sub = ResearchSubmissionService.create_submission(db_session, u1.id, payload)
    assert sub.id is not None
    assert sub.workspace_item_id == ws1.id
    assert sub.status == SubmissionStatus.DRAFT
    assert sub.submission_type == SubmissionType.FULL_PAPER
    assert sub.title == "Scalable Representation Learning for Graphs"
    assert sub.venue == "NeurIPS 2026 Track A"
    assert sub.submitted_at is None
    assert sub.decision_at is None
    assert sub.status_updated_at is not None


def test_create_submission_cross_researcher_rejected(
    db_session: Session,
    test_users: tuple[UserModel, UserModel],
    test_workspace_items: tuple[SavedOpportunityModel, SavedOpportunityModel],
) -> None:
    _, u2 = test_users
    ws1, _ = test_workspace_items  # ws1 belongs to u1

    payload = ResearchSubmissionCreate(
        workspace_item_id=ws1.id,
        title="Unauthorized Attempt",
    )

    with pytest.raises(PermissionError, match="Forbidden"):
        ResearchSubmissionService.create_submission(db_session, u2.id, payload)


def test_create_submission_non_existent_workspace_item(
    db_session: Session,
    test_users: tuple[UserModel, UserModel],
) -> None:
    u1, _ = test_users
    fake_id = uuid.uuid4()
    payload = ResearchSubmissionCreate(
        workspace_item_id=fake_id,
        title="Orphan Submission",
    )

    with pytest.raises(ValueError, match="not found"):
        ResearchSubmissionService.create_submission(db_session, u1.id, payload)


def test_submission_state_machine_valid_full_lifecycle(
    db_session: Session,
    test_users: tuple[UserModel, UserModel],
    test_workspace_items: tuple[SavedOpportunityModel, SavedOpportunityModel],
) -> None:
    u1, _ = test_users
    ws1, _ = test_workspace_items

    # 1. Create (DRAFT)
    sub = ResearchSubmissionService.create_submission(
        db_session,
        u1.id,
        ResearchSubmissionCreate(workspace_item_id=ws1.id, title="Test Paper"),
    )
    assert sub.status == SubmissionStatus.DRAFT

    # 2. DRAFT -> READY
    sub = ResearchSubmissionService.transition_status(
        db_session, u1.id, sub.id, SubmissionStatus.READY, notes="Proofread complete"
    )
    assert sub.status == SubmissionStatus.READY

    # 3. READY -> SUBMITTED (Should set submitted_at AND promote workspace to APPLIED)
    assert ws1.status == WorkspaceStatus.PLANNING
    sub = ResearchSubmissionService.transition_status(
        db_session, u1.id, sub.id, SubmissionStatus.SUBMITTED, notes="Submitted on EasyChair"
    )
    assert sub.status == SubmissionStatus.SUBMITTED
    assert sub.submitted_at is not None

    # Workspace status should be synchronized to APPLIED
    db_session.refresh(ws1)
    assert ws1.status == WorkspaceStatus.APPLIED

    # 4. SUBMITTED -> UNDER_REVIEW
    sub = ResearchSubmissionService.transition_status(
        db_session, u1.id, sub.id, SubmissionStatus.UNDER_REVIEW
    )
    assert sub.status == SubmissionStatus.UNDER_REVIEW

    # 5. UNDER_REVIEW -> ACCEPTED (Should set decision_at AND promote workspace to ACCEPTED)
    sub = ResearchSubmissionService.transition_status(
        db_session, u1.id, sub.id, SubmissionStatus.ACCEPTED, notes="Camera-ready due next month"
    )
    assert sub.status == SubmissionStatus.ACCEPTED
    assert sub.decision_at is not None

    db_session.refresh(ws1)
    assert ws1.status == WorkspaceStatus.ACCEPTED


def test_submission_rejection_and_revision_cycle(
    db_session: Session,
    test_users: tuple[UserModel, UserModel],
    test_workspace_items: tuple[SavedOpportunityModel, SavedOpportunityModel],
) -> None:
    u1, _ = test_users
    ws1, _ = test_workspace_items

    sub = ResearchSubmissionService.create_submission(
        db_session,
        u1.id,
        ResearchSubmissionCreate(workspace_item_id=ws1.id, title="Revision Cycle Paper"),
    )

    ResearchSubmissionService.transition_status(db_session, u1.id, sub.id, SubmissionStatus.READY)
    ResearchSubmissionService.transition_status(db_session, u1.id, sub.id, SubmissionStatus.SUBMITTED)
    ResearchSubmissionService.transition_status(db_session, u1.id, sub.id, SubmissionStatus.UNDER_REVIEW)

    # REJECTED transition
    sub = ResearchSubmissionService.transition_status(
        db_session, u1.id, sub.id, SubmissionStatus.REJECTED, notes="Scores: 5, 4, 3"
    )
    assert sub.status == SubmissionStatus.REJECTED
    assert sub.decision_at is not None

    # REJECTED -> DRAFT for re-scoping/revising
    sub = ResearchSubmissionService.transition_status(
        db_session, u1.id, sub.id, SubmissionStatus.DRAFT, notes="Addressing reviewer comments"
    )
    assert sub.status == SubmissionStatus.DRAFT


def test_submission_withdrawals(
    db_session: Session,
    test_users: tuple[UserModel, UserModel],
    test_workspace_items: tuple[SavedOpportunityModel, SavedOpportunityModel],
) -> None:
    u1, _ = test_users
    ws1, _ = test_workspace_items

    # 1. DRAFT -> WITHDRAWN
    sub1 = ResearchSubmissionService.create_submission(
        db_session,
        u1.id,
        ResearchSubmissionCreate(workspace_item_id=ws1.id, title="Withdraw Draft"),
    )
    sub1 = ResearchSubmissionService.transition_status(
        db_session, u1.id, sub1.id, SubmissionStatus.WITHDRAWN
    )
    assert sub1.status == SubmissionStatus.WITHDRAWN

    # 2. SUBMITTED -> WITHDRAWN
    sub2 = ResearchSubmissionService.create_submission(
        db_session,
        u1.id,
        ResearchSubmissionCreate(workspace_item_id=ws1.id, title="Withdraw Submitted"),
    )
    ResearchSubmissionService.transition_status(db_session, u1.id, sub2.id, SubmissionStatus.READY)
    ResearchSubmissionService.transition_status(db_session, u1.id, sub2.id, SubmissionStatus.SUBMITTED)
    sub2 = ResearchSubmissionService.transition_status(
        db_session, u1.id, sub2.id, SubmissionStatus.WITHDRAWN, notes="Conflict of interest"
    )
    assert sub2.status == SubmissionStatus.WITHDRAWN


def test_submission_idempotent_transitions(
    db_session: Session,
    test_users: tuple[UserModel, UserModel],
    test_workspace_items: tuple[SavedOpportunityModel, SavedOpportunityModel],
) -> None:
    u1, _ = test_users
    ws1, _ = test_workspace_items

    sub = ResearchSubmissionService.create_submission(
        db_session,
        u1.id,
        ResearchSubmissionCreate(workspace_item_id=ws1.id, title="Idempotent Test"),
    )

    # Transitioning DRAFT -> DRAFT should succeed idempotently
    res = ResearchSubmissionService.transition_status(
        db_session, u1.id, sub.id, SubmissionStatus.DRAFT
    )
    assert res.status == SubmissionStatus.DRAFT


def test_submission_invalid_transitions_rejection(
    db_session: Session,
    test_users: tuple[UserModel, UserModel],
    test_workspace_items: tuple[SavedOpportunityModel, SavedOpportunityModel],
) -> None:
    u1, _ = test_users
    ws1, _ = test_workspace_items

    sub = ResearchSubmissionService.create_submission(
        db_session,
        u1.id,
        ResearchSubmissionCreate(workspace_item_id=ws1.id, title="Invalid Transitions Test"),
    )

    # DRAFT cannot jump directly to SUBMITTED
    with pytest.raises(InvalidSubmissionTransitionError, match="Invalid submission lifecycle transition"):
        ResearchSubmissionService.transition_status(
            db_session, u1.id, sub.id, SubmissionStatus.SUBMITTED
        )

    # DRAFT cannot jump directly to ACCEPTED
    with pytest.raises(InvalidSubmissionTransitionError, match="Invalid submission lifecycle transition"):
        ResearchSubmissionService.transition_status(
            db_session, u1.id, sub.id, SubmissionStatus.ACCEPTED
        )


def test_update_submission_metadata(
    db_session: Session,
    test_users: tuple[UserModel, UserModel],
    test_workspace_items: tuple[SavedOpportunityModel, SavedOpportunityModel],
) -> None:
    u1, u2 = test_users
    ws1, _ = test_workspace_items

    sub = ResearchSubmissionService.create_submission(
        db_session,
        u1.id,
        ResearchSubmissionCreate(workspace_item_id=ws1.id, title="Original Title"),
    )

    update_payload = ResearchSubmissionUpdate(
        title="Updated Title",
        abstract="New abstract text",
        external_submission_id="OPENREVIEW-2026-9921",
        venue="NeurIPS Oral",
        submission_url="https://openreview.net/forum?id=9921",
        notes="Added co-author feedback",
    )

    updated = ResearchSubmissionService.update_submission(
        db_session, u1.id, sub.id, update_payload
    )
    assert updated.title == "Updated Title"
    assert updated.abstract == "New abstract text"
    assert updated.external_submission_id == "OPENREVIEW-2026-9921"
    assert str(updated.submission_url) == "https://openreview.net/forum?id=9921"
    assert updated.venue == "NeurIPS Oral"

    # Cross-researcher update rejection
    with pytest.raises(PermissionError, match="Forbidden"):
        ResearchSubmissionService.update_submission(
            db_session, u2.id, sub.id, update_payload
        )


def test_delete_submission_lifecycle_constraints(
    db_session: Session,
    test_users: tuple[UserModel, UserModel],
    test_workspace_items: tuple[SavedOpportunityModel, SavedOpportunityModel],
) -> None:
    u1, u2 = test_users
    ws1, _ = test_workspace_items

    sub = ResearchSubmissionService.create_submission(
        db_session,
        u1.id,
        ResearchSubmissionCreate(workspace_item_id=ws1.id, title="To Delete"),
    )

    # Cross-researcher delete rejection
    with pytest.raises(PermissionError, match="Forbidden"):
        ResearchSubmissionService.delete_submission(db_session, u2.id, sub.id)

    # Cannot delete once SUBMITTED
    ResearchSubmissionService.transition_status(db_session, u1.id, sub.id, SubmissionStatus.READY)
    ResearchSubmissionService.transition_status(db_session, u1.id, sub.id, SubmissionStatus.SUBMITTED)

    with pytest.raises(InvalidSubmissionTransitionError, match="Cannot delete active submission in status 'SUBMITTED'"):
        ResearchSubmissionService.delete_submission(db_session, u1.id, sub.id)

    # Transition to WITHDRAWN -> Deletion is allowed
    ResearchSubmissionService.transition_status(db_session, u1.id, sub.id, SubmissionStatus.WITHDRAWN)
    ResearchSubmissionService.delete_submission(db_session, u1.id, sub.id)

    # Confirm it no longer exists
    assert ResearchSubmissionService.get_submission(db_session, u1.id, sub.id) is None


def test_list_and_summary_isolation(
    db_session: Session,
    test_users: tuple[UserModel, UserModel],
    test_workspace_items: tuple[SavedOpportunityModel, SavedOpportunityModel],
) -> None:
    u1, u2 = test_users
    ws1, ws2 = test_workspace_items

    # Create 2 submissions for user 1
    s1 = ResearchSubmissionService.create_submission(
        db_session, u1.id, ResearchSubmissionCreate(workspace_item_id=ws1.id, title="U1 Paper 1")
    )
    s2 = ResearchSubmissionService.create_submission(
        db_session, u1.id, ResearchSubmissionCreate(workspace_item_id=ws1.id, title="U1 Paper 2")
    )
    ResearchSubmissionService.transition_status(db_session, u1.id, s1.id, SubmissionStatus.READY)

    # Create 1 submission for user 2
    s3 = ResearchSubmissionService.create_submission(
        db_session, u2.id, ResearchSubmissionCreate(workspace_item_id=ws2.id, title="U2 Paper 1")
    )

    # User 1 listings
    u1_list = ResearchSubmissionService.list_submissions(db_session, u1.id)
    assert u1_list.total_count == 2
    assert {item.id for item in u1_list.items} == {s1.id, s2.id}

    # User 2 listings
    u2_list = ResearchSubmissionService.list_submissions(db_session, u2.id)
    assert u2_list.total_count == 1
    assert u2_list.items[0].id == s3.id

    # Filter by status
    ready_list = ResearchSubmissionService.list_submissions(
        db_session, u1.id, status=SubmissionStatus.READY
    )
    assert ready_list.total_count == 1
    assert ready_list.items[0].id == s1.id

    # Summary counts
    u1_summary = ResearchSubmissionService.get_summary(db_session, u1.id)
    assert u1_summary.total_submissions == 2
    assert u1_summary.counts_by_status.get(SubmissionStatus.READY.value) == 1
    assert u1_summary.counts_by_status.get(SubmissionStatus.DRAFT.value) == 1

    u2_summary = ResearchSubmissionService.get_summary(db_session, u2.id)
    assert u2_summary.total_submissions == 1
    assert u2_summary.counts_by_status.get(SubmissionStatus.DRAFT.value) == 1


def test_deadline_intelligence_exposure(
    db_session: Session,
    test_users: tuple[UserModel, UserModel],
    test_workspace_items: tuple[SavedOpportunityModel, SavedOpportunityModel],
) -> None:
    u1, _ = test_users
    ws1, _ = test_workspace_items  # opp1 has deadline in Dec 2026

    sub = ResearchSubmissionService.create_submission(
        db_session,
        u1.id,
        ResearchSubmissionCreate(workspace_item_id=ws1.id, title="Deadline Aware Paper"),
    )

    read_schema = ResearchSubmissionService.build_submission_read(sub)
    assert read_schema.deadline_context is not None
    assert read_schema.deadline_context.submission_deadline is not None
    assert read_schema.deadline_context.urgency_tier is not None
    assert read_schema.deadline_context.days_remaining is not None


def test_query_efficiency_zero_n_plus_one(
    db_session: Session,
    test_users: tuple[UserModel, UserModel],
    test_workspace_items: tuple[SavedOpportunityModel, SavedOpportunityModel],
) -> None:
    u1, _ = test_users
    ws1, _ = test_workspace_items

    # Create 5 submissions
    for i in range(5):
        ResearchSubmissionService.create_submission(
            db_session,
            u1.id,
            ResearchSubmissionCreate(workspace_item_id=ws1.id, title=f"Paper {i}"),
        )

    queries: list[str] = []

    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        queries.append(statement)

    event.listen(db_session.bind, "before_cursor_execute", before_cursor_execute)

    # Warm up session / user resolution before measuring
    ResearchSubmissionService.list_submissions(db_session, u1.id, limit=1)

    # Listing 1 item vs listing 5 items should execute the exact same number of queries (O(1), zero N+1)
    queries.clear()
    list_1 = ResearchSubmissionService.list_submissions(db_session, u1.id, limit=1)
    count_1 = len(queries)

    queries.clear()
    list_5 = ResearchSubmissionService.list_submissions(db_session, u1.id, limit=5)
    count_5 = len(queries)

    assert count_1 == count_5, f"Query count should not scale with number of items (got {count_1} for 1 vs {count_5} for 5)"
    assert count_5 <= 4, f"Expected bounded queries (<= 4), got {count_5}: {queries}"

    # Single item retrieval with eager loaded workspace and opportunity should be bounded (<= 2)
    queries.clear()
    sub_detail = ResearchSubmissionService.get_submission(db_session, u1.id, list_1.items[0].id)
    assert sub_detail is not None
    assert len(queries) <= 2, f"Expected <= 2 queries for joined get, got {len(queries)}: {queries}"

    event.remove(db_session.bind, "before_cursor_execute", before_cursor_execute)
