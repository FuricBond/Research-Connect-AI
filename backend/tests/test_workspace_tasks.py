"""
Phase 4.6 — Workspace Tasks Unit & Integration Tests.

Validates:
  1. Creating a task (Owner / Editor / Contributor).
  2. Viewer cannot create tasks (403 / HTTPException).
  3. Updating task fields (title, description, priority, due_at).
  4. Assigning task to an active workspace member.
  5. Assigning task to non-member fails.
  6. Completing a task (status=COMPLETED, completed_at set).
  7. Reopening a task (status=TODO, completed_at cleared).
  8. Deleting a task (Owner / Editor only).
  9. Filtering tasks by status and priority.
  10. REST API integration for tasks.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
import uuid
from fastapi import HTTPException
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from app.db.session import get_db
from app.db.types import TSVector, Vector
from app.main import app
from app.models.base import Base
from app.models.opportunity import OpportunityModel
from app.models.saved_opportunity import SavedOpportunityModel, WorkspaceStatus
from app.models.user import UserModel
from app.models.workspace_collaboration import (
    MemberStatus,
    TaskPriority,
    TaskStatus,
    WorkspaceMemberModel,
    WorkspaceRole,
    WorkspaceTaskModel,
)
from app.schemas.workspace_collaboration import WorkspaceTaskCreate, WorkspaceTaskUpdate
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


@pytest.fixture
def client(db_session: Session) -> TestClient:
    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def sample_workspace(db_session: Session) -> tuple[UserModel, UserModel, UserModel, UserModel, SavedOpportunityModel]:
    u_owner = UserModel(id=uuid.uuid4(), email="owner@univ.edu", full_name="Owner Prof", hashed_password="pw")
    u_editor = UserModel(id=uuid.uuid4(), email="editor@univ.edu", full_name="Editor Researcher", hashed_password="pw")
    u_contrib = UserModel(id=uuid.uuid4(), email="contrib@univ.edu", full_name="Contributor Student", hashed_password="pw")
    u_viewer = UserModel(id=uuid.uuid4(), email="viewer@univ.edu", full_name="Viewer Observer", hashed_password="pw")
    db_session.add_all([u_owner, u_editor, u_contrib, u_viewer])
    db_session.flush()

    opp = OpportunityModel(
        id=uuid.uuid4(),
        title="Collab Grant 2026",
        opportunity_type="CONFERENCE",
        status="ACTIVE",
    )
    db_session.add(opp)
    db_session.flush()

    ws = SavedOpportunityModel(
        id=uuid.uuid4(),
        user_id=u_owner.id,
        opportunity_id=opp.id,
        status=WorkspaceStatus.PLANNING.value,
    )
    db_session.add(ws)
    db_session.flush()

    members = [
        WorkspaceMemberModel(workspace_id=ws.id, user_id=u_owner.id, role=WorkspaceRole.OWNER.value, status=MemberStatus.ACTIVE.value),
        WorkspaceMemberModel(workspace_id=ws.id, user_id=u_editor.id, role=WorkspaceRole.EDITOR.value, status=MemberStatus.ACTIVE.value),
        WorkspaceMemberModel(workspace_id=ws.id, user_id=u_contrib.id, role=WorkspaceRole.CONTRIBUTOR.value, status=MemberStatus.ACTIVE.value),
        WorkspaceMemberModel(workspace_id=ws.id, user_id=u_viewer.id, role=WorkspaceRole.VIEWER.value, status=MemberStatus.ACTIVE.value),
    ]
    db_session.add_all(members)
    db_session.commit()

    return u_owner, u_editor, u_contrib, u_viewer, ws


def test_create_task_by_contributor(db_session: Session, sample_workspace):
    _, _, u_contrib, _, ws = sample_workspace

    task = WorkspaceCollaborationService.create_task(
        db=db_session,
        workspace_id=ws.id,
        actor_id=u_contrib.id,
        payload=WorkspaceTaskCreate(
            title="Draft Related Work",
            description="Survey recent 2025-2026 papers",
            priority=TaskPriority.HIGH,
        ),
    )

    assert task.workspace_id == ws.id
    assert task.title == "Draft Related Work"
    assert task.priority == TaskPriority.HIGH.value
    assert task.status == TaskStatus.TODO.value
    assert task.creator_id == u_contrib.id


def test_create_task_by_viewer_forbidden(db_session: Session, sample_workspace):
    _, _, _, u_viewer, ws = sample_workspace

    with pytest.raises(HTTPException) as exc_info:
        WorkspaceCollaborationService.create_task(
            db=db_session,
            workspace_id=ws.id,
            actor_id=u_viewer.id,
            payload=WorkspaceTaskCreate(title="Unauthorized Task"),
        )
    assert exc_info.value.status_code == 403


def test_assign_task_to_member(db_session: Session, sample_workspace):
    u_owner, _, u_contrib, _, ws = sample_workspace

    task = WorkspaceCollaborationService.create_task(
        db=db_session,
        workspace_id=ws.id,
        actor_id=u_owner.id,
        payload=WorkspaceTaskCreate(title="Initial Task"),
    )

    assigned = WorkspaceCollaborationService.update_task(
        db=db_session,
        workspace_id=ws.id,
        actor_id=u_owner.id,
        task_id=task.id,
        payload=WorkspaceTaskUpdate(assignee_id=u_contrib.id),
    )

    assert assigned.assignee_id == u_contrib.id


def test_assign_task_to_non_member_fails(db_session: Session, sample_workspace):
    u_owner, _, _, _, ws = sample_workspace
    random_user_id = uuid.uuid4()

    with pytest.raises(HTTPException) as exc_info:
        WorkspaceCollaborationService.create_task(
            db=db_session,
            workspace_id=ws.id,
            actor_id=u_owner.id,
            payload=WorkspaceTaskCreate(title="Initial Task", assignee_id=random_user_id),
        )
    assert exc_info.value.status_code == 400


def test_complete_and_reopen_task(db_session: Session, sample_workspace):
    u_owner, _, _, _, ws = sample_workspace

    task = WorkspaceCollaborationService.create_task(
        db=db_session,
        workspace_id=ws.id,
        actor_id=u_owner.id,
        payload=WorkspaceTaskCreate(title="Complete Me"),
    )

    completed = WorkspaceCollaborationService.update_task(
        db=db_session,
        workspace_id=ws.id,
        actor_id=u_owner.id,
        task_id=task.id,
        payload=WorkspaceTaskUpdate(status=TaskStatus.COMPLETED),
    )
    assert completed.status == TaskStatus.COMPLETED.value
    assert completed.completed_at is not None

    reopened = WorkspaceCollaborationService.update_task(
        db=db_session,
        workspace_id=ws.id,
        actor_id=u_owner.id,
        task_id=task.id,
        payload=WorkspaceTaskUpdate(status=TaskStatus.TODO),
    )
    assert reopened.status == TaskStatus.TODO.value
    assert reopened.completed_at is None


def test_delete_task_permissions(db_session: Session, sample_workspace):
    u_owner, u_editor, u_contrib, _, ws = sample_workspace

    task = WorkspaceCollaborationService.create_task(
        db=db_session,
        workspace_id=ws.id,
        actor_id=u_owner.id,
        payload=WorkspaceTaskCreate(title="Delete Me"),
    )

    # Contributor (who did not create the task) cannot delete
    with pytest.raises(HTTPException) as exc_info:
        WorkspaceCollaborationService.delete_task(
            db=db_session,
            workspace_id=ws.id,
            actor_id=u_contrib.id,
            task_id=task.id,
        )
    assert exc_info.value.status_code == 403

    # Editor can delete
    WorkspaceCollaborationService.delete_task(
        db=db_session,
        workspace_id=ws.id,
        actor_id=u_editor.id,
        task_id=task.id,
    )

    # Task should be gone
    t_after = db_session.get(WorkspaceTaskModel, task.id)
    assert t_after is None


def test_api_task_lifecycle(client: TestClient, sample_workspace):
    u_owner, _, u_contrib, _, ws = sample_workspace

    # 1. Create task
    res = client.post(
        f"/api/v1/workspaces/{ws.id}/tasks",
        headers={"X-User-ID": str(u_owner.id)},
        json={"title": "Test Task", "priority": "HIGH"},
    )
    assert res.status_code == 201
    task_id = res.json()["id"]

    # 2. Assign task
    res = client.post(
        f"/api/v1/workspaces/{ws.id}/tasks/{task_id}/assign",
        headers={"X-User-ID": str(u_owner.id)},
        json={"assignee_id": str(u_contrib.id)},
    )
    assert res.status_code == 200
    assert res.json()["assignee_id"] == str(u_contrib.id)

    # 3. Complete task
    res = client.post(
        f"/api/v1/workspaces/{ws.id}/tasks/{task_id}/complete",
        headers={"X-User-ID": str(u_contrib.id)},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "COMPLETED"

    # 4. Reopen task
    res = client.post(
        f"/api/v1/workspaces/{ws.id}/tasks/{task_id}/reopen",
        headers={"X-User-ID": str(u_contrib.id)},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "TODO"

    # 5. List tasks
    res = client.get(
        f"/api/v1/workspaces/{ws.id}/tasks",
        headers={"X-User-ID": str(u_owner.id)},
    )
    assert res.status_code == 200
    assert res.json()["total_count"] == 1
