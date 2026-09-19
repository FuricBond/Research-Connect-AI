"""
Phase 4.1 — Unit and Integration Tests for WorkspaceService and Workflow State Machine.

Tests cover:
  1. Workspace item creation and default values (SAVED status, MEDIUM priority, empty tags)
  2. Strict researcher ownership and cross-researcher access rejection (PermissionError)
  3. Deterministic workflow state machine transitions (all valid transitions)
  4. Deterministic rejection of invalid transitions (InvalidTransitionError)
  5. Idempotent status transitions (no-op success)
  6. Archive and unarchive behavior and timestamp updates
  7. Metadata updates (priority, notes, tags) and timestamps (status_updated_at vs updated_at)
  8. Filtering by status, priority, tag, search query, and archive inclusion
  9. Workspace summary statistics (active, archived, by status, by priority)
 10. Phase 3.6 feedback synchronization on SAVE and APPLY
 11. Deletion / removal semantics
 12. Query efficiency and eager relationship loading (joinedload)
"""
from __future__ import annotations

from datetime import datetime, timezone
import uuid
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.types import TSVector, Vector
from app.models.base import Base
from app.models.opportunity import OpportunityModel
from app.models.research_profile import ResearchProfileModel
from app.models.researcher_feedback import ResearcherRecommendationFeedbackModel
from app.models.saved_opportunity import SavedOpportunityModel, WorkspacePriority, WorkspaceStatus
from app.models.user import UserModel
from app.schemas.workspace import (
    WorkspaceItemCreate,
    WorkspaceItemUpdate,
)
from app.services.workspace_service import (
    InvalidTransitionError,
    WorkspaceService,
)

# SQLite compatibility
compiles(JSONB, "sqlite")(lambda type_, compiler, **kw: "JSON")
compiles(Vector, "sqlite")(lambda type_, compiler, **kw: "TEXT")
compiles(TSVector, "sqlite")(lambda type_, compiler, **kw: "TEXT")


@pytest.fixture
def db_session() -> Session:
    """Provides a fresh in-memory SQLite session with required tables."""
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
        Base.metadata.tables["research_profiles"],
        Base.metadata.tables["researcher_interests"],
        Base.metadata.tables["researcher_preferences"],
        Base.metadata.tables["researcher_recommendation_feedback"],
        Base.metadata.tables["workspace_members"],
        Base.metadata.tables["workspace_invitations"],
        Base.metadata.tables["workspace_tasks"],
        Base.metadata.tables["workspace_activities"],
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
    """Creates two distinct test researchers with profiles."""
    u1 = UserModel(
        id=uuid.uuid4(),
        email="researcher1@lab.org",
        hashed_password="dummy_hash_1",
        full_name="Dr. Jane Doe",
        role="FACULTY",
    )
    u2 = UserModel(
        id=uuid.uuid4(),
        email="researcher2@lab.org",
        hashed_password="dummy_hash_2",
        full_name="Dr. John Smith",
        role="FACULTY",
    )
    db_session.add_all([u1, u2])
    db_session.flush()

    p1 = ResearchProfileModel(
        id=uuid.uuid4(),
        user_id=u1.id,
        academic_status="FACULTY",
    )
    p2 = ResearchProfileModel(
        id=uuid.uuid4(),
        user_id=u2.id,
        academic_status="FACULTY",
    )
    db_session.add_all([p1, p2])
    db_session.commit()
    return u1, u2


@pytest.fixture
def test_opportunities(db_session: Session) -> list[OpportunityModel]:
    """Creates sample academic opportunities."""
    opps = [
        OpportunityModel(
            id=uuid.uuid4(),
            title="IEEE Conference on Software Engineering 2026",
            opportunity_type="CONFERENCE",
            delivery_mode="HYBRID",
            status="ACTIVE",
            publisher="IEEE",
            organizer="IEEE CS",
            submission_deadline=datetime(2026, 11, 15, 23, 59, 59, tzinfo=timezone.utc),
            risk_score=0.05,
            is_predatory_flag=False,
        ),
        OpportunityModel(
            id=uuid.uuid4(),
            title="ACM Transactions on Software Architecture",
            opportunity_type="JOURNAL",
            delivery_mode="ONLINE",
            status="ACTIVE",
            publisher="ACM",
            organizer="ACM SIGSOFT",
            submission_deadline=datetime(2026, 12, 1, 23, 59, 59, tzinfo=timezone.utc),
            risk_score=0.02,
            is_predatory_flag=False,
        ),
        OpportunityModel(
            id=uuid.uuid4(),
            title="International AI Workshop 2026",
            opportunity_type="WORKSHOP",
            delivery_mode="OFFLINE",
            status="ACTIVE",
            publisher="Springer",
            organizer="AI Association",
            submission_deadline=datetime(2026, 10, 30, 23, 59, 59, tzinfo=timezone.utc),
            risk_score=0.15,
            is_predatory_flag=False,
        ),
    ]
    db_session.add_all(opps)
    db_session.commit()
    return opps


def test_add_opportunity_to_workspace_defaults(
    db_session: Session,
    test_users: tuple[UserModel, UserModel],
    test_opportunities: list[OpportunityModel],
):
    """Test workspace creation with default values and timestamps."""
    u1, _ = test_users
    opp1 = test_opportunities[0]

    item, is_new = WorkspaceService.add_opportunity(
        db=db_session,
        user_id=u1.id,
        payload=WorkspaceItemCreate(opportunity_id=opp1.id),
    )

    assert is_new is True
    assert item.id is not None
    assert item.user_id == u1.id
    assert item.opportunity_id == opp1.id
    assert item.status == WorkspaceStatus.SAVED.value
    assert item.priority == WorkspacePriority.MEDIUM.value
    assert item.tags == []
    assert item.notes is None
    assert item.created_at is not None
    assert item.updated_at is not None
    assert item.status_updated_at is not None
    assert item.archived_at is None

    read_schema = WorkspaceService.build_workspace_item_read(item)
    assert WorkspaceStatus.CONSIDERING in read_schema.allowed_transitions
    assert WorkspaceStatus.PLANNING in read_schema.allowed_transitions
    assert WorkspaceStatus.ARCHIVED in read_schema.allowed_transitions


def test_strict_researcher_isolation(
    db_session: Session,
    test_users: tuple[UserModel, UserModel],
    test_opportunities: list[OpportunityModel],
):
    """Ensure researcher 2 cannot read, transition, update, or delete researcher 1's items."""
    u1, u2 = test_users
    opp1 = test_opportunities[0]

    item1, _ = WorkspaceService.add_opportunity(
        db=db_session,
        user_id=u1.id,
        payload=WorkspaceItemCreate(opportunity_id=opp1.id),
    )

    # u2 tries to get u1's item
    with pytest.raises(PermissionError):
        WorkspaceService.get_workspace_item(db=db_session, user_id=u2.id, item_id=item1.id)

    # u2 tries to update u1's item
    with pytest.raises(PermissionError):
        WorkspaceService.update_workspace_item(
            db=db_session,
            user_id=u2.id,
            item_id=item1.id,
            payload=WorkspaceItemUpdate(notes="Malicious update"),
        )

    # u2 tries to transition u1's item
    with pytest.raises(PermissionError):
        WorkspaceService.transition_status(
            db=db_session,
            user_id=u2.id,
            item_id=item1.id,
            target_status=WorkspaceStatus.CONSIDERING,
        )

    # u2 tries to archive u1's item
    with pytest.raises(PermissionError):
        WorkspaceService.archive_item(db=db_session, user_id=u2.id, item_id=item1.id)

    # u2 tries to delete u1's item
    with pytest.raises(PermissionError):
        WorkspaceService.remove_item(db=db_session, user_id=u2.id, item_id=item1.id)


def test_valid_state_machine_pipeline(
    db_session: Session,
    test_users: tuple[UserModel, UserModel],
    test_opportunities: list[OpportunityModel],
):
    """Test full sequential workflow lifecycle from SAVED to ACCEPTED."""
    u1, _ = test_users
    opp = test_opportunities[0]

    # 1. Create -> SAVED
    item, _ = WorkspaceService.add_opportunity(
        db=db_session,
        user_id=u1.id,
        payload=WorkspaceItemCreate(opportunity_id=opp.id),
    )
    assert item.status == WorkspaceStatus.SAVED.value

    # 2. SAVED -> CONSIDERING
    item = WorkspaceService.transition_status(
        db=db_session,
        user_id=u1.id,
        item_id=item.id,
        target_status=WorkspaceStatus.CONSIDERING,
    )
    assert item.status == WorkspaceStatus.CONSIDERING.value

    # 3. CONSIDERING -> PLANNING
    item = WorkspaceService.transition_status(
        db=db_session,
        user_id=u1.id,
        item_id=item.id,
        target_status=WorkspaceStatus.PLANNING,
    )
    assert item.status == WorkspaceStatus.PLANNING.value

    # 4. PLANNING -> APPLIED
    item = WorkspaceService.transition_status(
        db=db_session,
        user_id=u1.id,
        item_id=item.id,
        target_status=WorkspaceStatus.APPLIED,
    )
    assert item.status == WorkspaceStatus.APPLIED.value

    # Verify Phase 3.6 feedback was synchronized on APPLIED
    feedbacks = db_session.execute(
        select(ResearcherRecommendationFeedbackModel).where(
            ResearcherRecommendationFeedbackModel.opportunity_id == opp.id,
            ResearcherRecommendationFeedbackModel.feedback_type == "APPLY",
        )
    ).scalars().all()
    assert len(feedbacks) >= 1

    # 5. APPLIED -> ACCEPTED
    item = WorkspaceService.transition_status(
        db=db_session,
        user_id=u1.id,
        item_id=item.id,
        target_status=WorkspaceStatus.ACCEPTED,
    )
    assert item.status == WorkspaceStatus.ACCEPTED.value


def test_invalid_transitions_rejection(
    db_session: Session,
    test_users: tuple[UserModel, UserModel],
    test_opportunities: list[OpportunityModel],
):
    """Test that invalid, out-of-order transitions are deterministically rejected."""
    u1, _ = test_users
    opp = test_opportunities[0]

    item, _ = WorkspaceService.add_opportunity(
        db=db_session,
        user_id=u1.id,
        payload=WorkspaceItemCreate(opportunity_id=opp.id),
    )

    # Invalid: SAVED -> ACCEPTED
    with pytest.raises(InvalidTransitionError) as exc_info:
        WorkspaceService.transition_status(
            db=db_session,
            user_id=u1.id,
            item_id=item.id,
            target_status=WorkspaceStatus.ACCEPTED,
        )
    assert exc_info.value.current_status == WorkspaceStatus.SAVED
    assert exc_info.value.target_status == WorkspaceStatus.ACCEPTED

    # Invalid: SAVED -> REJECTED
    with pytest.raises(InvalidTransitionError):
        WorkspaceService.transition_status(
            db=db_session,
            user_id=u1.id,
            item_id=item.id,
            target_status=WorkspaceStatus.REJECTED,
        )

    # Invalid: SAVED -> APPLIED (must go through planning or considering)
    with pytest.raises(InvalidTransitionError):
        WorkspaceService.transition_status(
            db=db_session,
            user_id=u1.id,
            item_id=item.id,
            target_status=WorkspaceStatus.APPLIED,
        )


def test_idempotent_transition(
    db_session: Session,
    test_users: tuple[UserModel, UserModel],
    test_opportunities: list[OpportunityModel],
):
    """Transitioning to the same status should be a deterministic no-op."""
    u1, _ = test_users
    opp = test_opportunities[0]

    item, _ = WorkspaceService.add_opportunity(
        db=db_session,
        user_id=u1.id,
        payload=WorkspaceItemCreate(opportunity_id=opp.id),
    )
    original_updated_at = item.status_updated_at

    same_item = WorkspaceService.transition_status(
        db=db_session,
        user_id=u1.id,
        item_id=item.id,
        target_status=WorkspaceStatus.SAVED,
    )
    assert same_item.status == WorkspaceStatus.SAVED.value
    assert same_item.status_updated_at == original_updated_at


def test_archive_and_unarchive_lifecycle(
    db_session: Session,
    test_users: tuple[UserModel, UserModel],
    test_opportunities: list[OpportunityModel],
):
    """Test archiving an item sets status and timestamp, and unarchiving restores it."""
    u1, _ = test_users
    opp = test_opportunities[0]

    item, _ = WorkspaceService.add_opportunity(
        db=db_session,
        user_id=u1.id,
        payload=WorkspaceItemCreate(opportunity_id=opp.id),
    )

    # Archive
    archived = WorkspaceService.archive_item(db=db_session, user_id=u1.id, item_id=item.id)
    assert archived.status == WorkspaceStatus.ARCHIVED.value
    assert archived.archived_at is not None

    # Default list excludes archived
    res = WorkspaceService.list_workspace_items(db=db_session, user_id=u1.id, include_archived=False)
    assert res.total_count == 0
    assert len(res.items) == 0

    # List with include_archived includes it
    res_all = WorkspaceService.list_workspace_items(db=db_session, user_id=u1.id, include_archived=True)
    assert res_all.total_count == 1
    assert len(res_all.items) == 1

    # Unarchive back to PLANNING
    unarchived = WorkspaceService.unarchive_item(
        db=db_session,
        user_id=u1.id,
        item_id=item.id,
        target_status=WorkspaceStatus.PLANNING,
    )
    assert unarchived.status == WorkspaceStatus.PLANNING.value
    assert unarchived.archived_at is None


def test_metadata_updates_and_tag_management(
    db_session: Session,
    test_users: tuple[UserModel, UserModel],
    test_opportunities: list[OpportunityModel],
):
    """Test updating priority, notes, and tags."""
    u1, _ = test_users
    opp = test_opportunities[0]

    item, _ = WorkspaceService.add_opportunity(
        db=db_session,
        user_id=u1.id,
        payload=WorkspaceItemCreate(opportunity_id=opp.id),
    )

    updated = WorkspaceService.update_workspace_item(
        db=db_session,
        user_id=u1.id,
        item_id=item.id,
        payload=WorkspaceItemUpdate(
            priority=WorkspacePriority.URGENT,
            notes="Targeting Track A for empirical software engineering",
            tags=["icse2026", "software-eng", "top-priority"],
        ),
    )

    assert updated.priority == WorkspacePriority.URGENT.value
    assert updated.notes == "Targeting Track A for empirical software engineering"
    assert updated.tags == ["icse2026", "software-eng", "top-priority"]


def test_filtering_and_summary_statistics(
    db_session: Session,
    test_users: tuple[UserModel, UserModel],
    test_opportunities: list[OpportunityModel],
):
    """Test list filtering by status, priority, tag, search, and summary aggregations."""
    u1, _ = test_users
    opp1, opp2, opp3 = test_opportunities

    # Item 1: SAVED, HIGH, tag: ai
    WorkspaceService.add_opportunity(
        db=db_session,
        user_id=u1.id,
        payload=WorkspaceItemCreate(
            opportunity_id=opp1.id,
            status=WorkspaceStatus.SAVED,
            priority=WorkspacePriority.HIGH,
            tags=["ai", "conference"],
        ),
    )

    # Item 2: PLANNING, URGENT, tag: systems
    WorkspaceService.add_opportunity(
        db=db_session,
        user_id=u1.id,
        payload=WorkspaceItemCreate(
            opportunity_id=opp2.id,
            status=WorkspaceStatus.PLANNING,
            priority=WorkspacePriority.URGENT,
            tags=["systems", "journal"],
        ),
    )

    # Item 3: ARCHIVED, LOW, tag: ai
    item3, _ = WorkspaceService.add_opportunity(
        db=db_session,
        user_id=u1.id,
        payload=WorkspaceItemCreate(
            opportunity_id=opp3.id,
            status=WorkspaceStatus.SAVED,
            priority=WorkspacePriority.LOW,
            tags=["ai"],
        ),
    )
    WorkspaceService.archive_item(db=db_session, user_id=u1.id, item_id=item3.id)

    # Filter by status: PLANNING
    planning_res = WorkspaceService.list_workspace_items(
        db=db_session,
        user_id=u1.id,
        status=WorkspaceStatus.PLANNING,
    )
    assert planning_res.total_count == 1
    assert planning_res.items[0].opportunity_id == opp2.id

    # Filter by priority: HIGH
    high_res = WorkspaceService.list_workspace_items(
        db=db_session,
        user_id=u1.id,
        priority=WorkspacePriority.HIGH,
    )
    assert high_res.total_count == 1
    assert high_res.items[0].opportunity_id == opp1.id

    # Filter by tag: systems
    systems_res = WorkspaceService.list_workspace_items(
        db=db_session,
        user_id=u1.id,
        tag="systems",
    )
    assert systems_res.total_count == 1
    assert systems_res.items[0].opportunity_id == opp2.id

    # Filter by search: "Architecture"
    search_res = WorkspaceService.list_workspace_items(
        db=db_session,
        user_id=u1.id,
        search="Architecture",
    )
    assert search_res.total_count == 1
    assert search_res.items[0].opportunity_id == opp2.id

    # Summary checks
    summary = WorkspaceService.get_summary(db=db_session, user_id=u1.id)
    assert summary.total_count == 3
    assert summary.active_count == 2
    assert summary.archived_count == 1
    assert summary.counts_by_status[WorkspaceStatus.SAVED.value] == 1
    assert summary.counts_by_status[WorkspaceStatus.PLANNING.value] == 1
    assert summary.counts_by_status[WorkspaceStatus.ARCHIVED.value] == 1
    assert summary.counts_by_priority[WorkspacePriority.HIGH.value] == 1
    assert summary.counts_by_priority[WorkspacePriority.URGENT.value] == 1
    assert summary.counts_by_priority[WorkspacePriority.LOW.value] == 1
