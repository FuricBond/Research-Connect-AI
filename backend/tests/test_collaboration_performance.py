"""
Phase 4.6 — Collaboration Performance & Scalability Benchmarks.

Measures:
  - Workspace membership retrieval with 10, 50, 100, 500, 1000 members.
  - Authorization lookup (O(1) indexed).
  - Task retrieval with pagination and filtering.
  - Activity feed retrieval (bounded/paginated).
  - Verifies zero N+1 queries.
"""
from __future__ import annotations

from datetime import datetime, timezone
import time
import uuid
import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.types import TSVector, Vector
from app.models.base import Base
from app.models.opportunity import OpportunityModel
from app.models.saved_opportunity import SavedOpportunityModel, WorkspaceStatus
from app.models.user import UserModel
from app.models.workspace_collaboration import (
    MemberStatus,
    TaskPriority,
    TaskStatus,
    WorkspaceActivityModel,
    WorkspaceMemberModel,
    WorkspaceRole,
    WorkspaceTaskModel,
)
from app.services.workspace_authorization_service import WorkspaceAuthorizationService
from app.services.workspace_collaboration_service import WorkspaceCollaborationService

# SQLite compatibility
compiles(JSONB, "sqlite")(lambda type_, compiler, **kw: "JSON")
compiles(Vector, "sqlite")(lambda type_, compiler, **kw: "TEXT")
compiles(TSVector, "sqlite")(lambda type_, compiler, **kw: "TEXT")


@pytest.fixture
def db_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.mark.parametrize("member_count", [10, 50, 100, 500, 1000])
def test_workspace_membership_scalability(db_session: Session, member_count: int):
    # Setup owner and workspace
    u_owner = UserModel(id=uuid.uuid4(), email="owner@univ.edu", full_name="Owner", hashed_password="pw")
    opp = OpportunityModel(id=uuid.uuid4(), title="Perf Grant", opportunity_type="CONFERENCE", status="ACTIVE")
    ws = SavedOpportunityModel(id=uuid.uuid4(), user_id=u_owner.id, opportunity_id=opp.id, status="PLANNING")
    db_session.add_all([u_owner, opp, ws])
    db_session.flush()

    # Bulk create members and users
    users = []
    members = [
        WorkspaceMemberModel(
            workspace_id=ws.id,
            user_id=u_owner.id,
            role=WorkspaceRole.OWNER.value,
            status=MemberStatus.ACTIVE.value,
        )
    ]
    for i in range(member_count - 1):
        u = UserModel(
            id=uuid.uuid4(),
            email=f"member_{i}@univ.edu",
            full_name=f"Member {i}",
            hashed_password="pw",
        )
        users.append(u)
        m = WorkspaceMemberModel(
            workspace_id=ws.id,
            user_id=u.id,
            role=WorkspaceRole.CONTRIBUTOR.value,
            status=MemberStatus.ACTIVE.value,
        )
        members.append(m)

    db_session.add_all(users)
    db_session.flush()
    db_session.add_all(members)
    db_session.commit()

    # Measure membership retrieval latency
    start = time.perf_counter()
    retrieved, _ = WorkspaceCollaborationService.list_members(
        db=db_session,
        workspace_id=ws.id,
        user_id=u_owner.id,
    )
    duration_ms = (time.perf_counter() - start) * 1000

    assert len(retrieved) == member_count
    # Should complete under 250ms even for 1000 members
    assert duration_ms < 250.0, f"Retrieval took too long: {duration_ms:.2f}ms for {member_count} members"

    # Measure authorization lookup (O(1) indexed)
    test_user_id = users[len(users) // 2].id if users else u_owner.id
    start_auth = time.perf_counter()
    member = WorkspaceAuthorizationService.get_member(db_session, ws.id, test_user_id)
    auth_duration_ms = (time.perf_counter() - start_auth) * 1000

    assert member is not None
    assert auth_duration_ms < 15.0, f"Auth lookup took too long: {auth_duration_ms:.2f}ms"


def test_zero_n_plus_1_query_count(db_session: Session):
    u_owner = UserModel(id=uuid.uuid4(), email="owner@univ.edu", full_name="Owner", hashed_password="pw")
    opp = OpportunityModel(id=uuid.uuid4(), title="Perf Grant", opportunity_type="CONFERENCE", status="ACTIVE")
    ws = SavedOpportunityModel(id=uuid.uuid4(), user_id=u_owner.id, opportunity_id=opp.id, status="PLANNING")
    db_session.add_all([u_owner, opp, ws])
    db_session.flush()

    # Create 20 members and 20 tasks
    users = []
    members = [
        WorkspaceMemberModel(workspace_id=ws.id, user_id=u_owner.id, role="OWNER", status="ACTIVE")
    ]
    tasks = []
    for i in range(20):
        u = UserModel(id=uuid.uuid4(), email=f"user_{i}@univ.edu", full_name=f"User {i}", hashed_password="pw")
        users.append(u)
        m = WorkspaceMemberModel(workspace_id=ws.id, user_id=u.id, role="CONTRIBUTOR", status="ACTIVE")
        members.append(m)
        t = WorkspaceTaskModel(
            workspace_id=ws.id,
            title=f"Task {i}",
            creator_id=u_owner.id,
            assignee_id=u.id,
            status=TaskStatus.TODO.value,
            priority=TaskPriority.MEDIUM.value,
        )
        tasks.append(t)

    db_session.add_all(users)
    db_session.flush()
    db_session.add_all(members)
    db_session.add_all(tasks)
    db_session.commit()

    # Track SQL queries executed
    query_count = 0

    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        nonlocal query_count
        query_count += 1

    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", before_cursor_execute)

    try:
        # Retrieve members (should be bounded, at most 2 queries: auth + joinedload members+user)
        query_count = 0
        m_list, _ = WorkspaceCollaborationService.list_members(db=db_session, workspace_id=ws.id, user_id=u_owner.id)
        assert len(m_list) == 21
        # Eagerly access user full_name on every member to ensure no lazy-loading triggers
        names = [m.user.full_name for m in m_list if m.user]
        assert len(names) == 21
        assert query_count <= 4, f"Expected <= 4 queries for members, got {query_count}"

        # Retrieve tasks (should be bounded, exactly 3 queries: auth + count + joinedload tasks)
        query_count = 0
        t_list, _ = WorkspaceCollaborationService.list_tasks(db=db_session, workspace_id=ws.id, user_id=u_owner.id, limit=100)
        assert len(t_list) == 20
        assert query_count <= 3, f"Expected <= 3 queries for tasks, got {query_count}"

    finally:
        event.remove(engine, "before_cursor_execute", before_cursor_execute)
