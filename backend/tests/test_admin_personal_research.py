"""
An administrator runs the platform and has no personal research workflow, on the server.

Hiding the pages was not enough: the API answered an administrator's reading list, submissions and
applications, and accepted applications from one. Every route of those workflows is found from the
application itself and tried directly, so a route added later is covered without being listed here.
"""
from __future__ import annotations

import re
import uuid

import pytest
from fastapi.routing import APIRoute
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from app.core.config import settings
from app.db.session import get_db
from app.db.types import TSVector, Vector
from app.main import app
from app.models.base import Base
from app.models.research_posting_application import ResearchPostingApplicationModel
from app.models.research_profile import ResearchProfileModel
from app.models.user import UserModel

compiles(JSONB, "sqlite")(lambda type_, compiler, **kw: "JSON")
compiles(Vector, "sqlite")(lambda type_, compiler, **kw: "TEXT")
compiles(TSVector, "sqlite")(lambda type_, compiler, **kw: "TEXT")

# What belongs to a person doing research, under both API prefixes.
PERSONAL = re.compile(
    r"^/api(?:/v1)?/(?:reading-list|submissions|workspace|workspaces|workspace-invitations|calendar|researchers"
    r"|postings/applications)(?:/|$)"
    r"|^/api(?:/v1)?/postings/\{posting_id\}/applications$"
)
# Reviewing applications is the author's: refused for an administrator already (Decision B).
AUTHOR_ONLY = {("GET", "postings/{posting_id}/applications")}
DENIED = "This action requires one of the roles: FACULTY, STUDENT."

OPENING = {
    "title": "Research assistantship in retrieval evaluation",
    "posting_type": "RESEARCH_ASSISTANTSHIP",
    "description": "Help build reproducible retrieval benchmarks and run evaluation campaigns.",
    "work_mode": "REMOTE",
    "positions_available": 1,
    "opening_terms": {
        "accepts_applications": True,
        "compensation_type": "STIPEND",
        "compensation_amount": 1500,
        "compensation_currency": "USD",
        "compensation_period": "MONTH",
        "commitment_type": "PART_TIME",
        "hours_per_week": 15,
        "duration_months": 6,
    },
}


@pytest.fixture
def db_session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_session: Session) -> TestClient:
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _account(db: Session, role: str, *, verified: bool = False) -> UserModel:
    user = UserModel(
        id=uuid.uuid4(),
        email=f"{role.lower()}.{uuid.uuid4().hex[:8]}@univ.edu",
        full_name=f"Test {role.title()}",
        hashed_password="pw",
        role=role,
        is_active=True,
        is_verified=verified,
    )
    db.add(user)
    db.flush()
    db.add(ResearchProfileModel(id=uuid.uuid4(), user_id=user.id, academic_status="FACULTY" if role == "FACULTY" else "PHD_STUDENT"))
    db.commit()
    return user


def _h(user: UserModel) -> dict[str, str]:
    return {"X-User-ID": str(user.id)}


def _profile_id(db: Session, user: UserModel) -> uuid.UUID:
    return db.query(ResearchProfileModel).filter_by(user_id=user.id).one().id


def _personal_routes() -> list[tuple[str, str]]:
    found = []
    for route in app.routes:
        if isinstance(route, APIRoute) and PERSONAL.search(route.path):
            for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
                short = re.sub(r"^/api(?:/v1)?/", "", route.path)
                if (method, short) not in AUTHOR_ONLY:
                    found.append((method, route.path))
    return found


def _fill(path: str) -> str:
    return re.sub(r"\{[^}]+\}", lambda _: str(uuid.uuid4()), path)


def test_the_list_really_covers_these_workflows() -> None:
    routes = _personal_routes()
    assert len(routes) > 300
    paths = {path for _, path in routes}
    for expected in (
        "/api/v1/reading-list",
        "/api/reading-list",
        "/api/v1/submissions",
        "/api/v1/workspace",
        "/api/v1/calendar",
        "/api/v1/researchers/{researcher_id}/preferences",
        "/api/v1/workspace-invitations/mine",
        "/api/v1/postings/{posting_id}/applications",
        "/api/v1/postings/applications/mine",
        "/api/v1/postings/applications/{application_id}/transition",
    ):
        assert expected in paths, expected


@pytest.mark.parametrize(("method", "path"), _personal_routes())
def test_every_personal_route_refuses_an_administrator(client: TestClient, db_session: Session, method: str, path: str) -> None:
    admin = _account(db_session, "ADMIN", verified=True)
    response = client.request(method, _fill(path), headers=_h(admin))
    assert response.status_code == 403, (method, path, response.text[:200])
    assert response.json()["detail"] == DENIED


@pytest.mark.parametrize(("method", "path"), _personal_routes())
def test_every_personal_route_refuses_a_visitor(client: TestClient, monkeypatch: pytest.MonkeyPatch, method: str, path: str) -> None:
    monkeypatch.setattr(settings, "auth_dev_identity_enabled", False)
    # 422 is a request without its required body, turned away before the route's own sign-in check.
    assert client.request(method, _fill(path)).status_code in (401, 422), (method, path)


def test_an_administrator_cannot_apply_and_nothing_is_recorded(client: TestClient, db_session: Session) -> None:
    faculty = _account(db_session, "FACULTY", verified=True)
    admin = _account(db_session, "ADMIN", verified=True)
    posting_id = client.post("/api/v1/postings", headers=_h(faculty), json=OPENING).json()["id"]
    assert client.post(f"/api/v1/postings/{posting_id}/transition", headers=_h(faculty), json={"target_status": "OPEN"}).status_code == 200

    refused = client.post(f"/api/v1/postings/{posting_id}/applications", headers=_h(admin), json={"cover_note": "From an administrator"})
    assert refused.status_code == 403
    assert refused.json()["detail"] == DENIED
    assert db_session.query(ResearchPostingApplicationModel).count() == 0


def test_a_student_keeps_the_whole_personal_side(client: TestClient, db_session: Session) -> None:
    student = _account(db_session, "STUDENT")
    profile = _profile_id(db_session, student)
    faculty = _account(db_session, "FACULTY", verified=True)
    for path in (
        "/api/v1/reading-list",
        "/api/v1/submissions",
        "/api/v1/workspace",
        "/api/v1/calendar",
        "/api/v1/workspace-invitations/mine",
        "/api/v1/postings/applications/mine",
        f"/api/v1/researchers/{profile}",
        f"/api/v1/researchers/{profile}/preferences",
    ):
        assert client.get(path, headers=_h(student)).status_code == 200, path

    posting_id = client.post("/api/v1/postings", headers=_h(faculty), json=OPENING).json()["id"]
    client.post(f"/api/v1/postings/{posting_id}/transition", headers=_h(faculty), json={"target_status": "OPEN"})
    applied = client.post(f"/api/v1/postings/{posting_id}/applications", headers=_h(student), json={"cover_note": "Please consider me"})
    assert applied.status_code == 201


def test_faculty_keep_their_research_tools_and_recruiting(client: TestClient, db_session: Session) -> None:
    faculty = _account(db_session, "FACULTY", verified=True)
    profile = _profile_id(db_session, faculty)
    for path in ("/api/v1/reading-list", "/api/v1/submissions", "/api/v1/workspace", "/api/v1/calendar", "/api/v1/postings/mine", f"/api/v1/researchers/{profile}"):
        assert client.get(path, headers=_h(faculty)).status_code == 200, path


def test_an_administrator_keeps_platform_administration(client: TestClient, db_session: Session) -> None:
    admin = _account(db_session, "ADMIN", verified=True)
    student = _account(db_session, "STUDENT")
    assert client.get("/api/v1/admin/users", headers=_h(admin)).status_code == 200
    assert client.get("/api/v1/admin/ingestion-runs", headers=_h(admin)).status_code == 200
    assert client.get("/api/v1/auth/me", headers=_h(admin)).status_code == 200
    assert client.get("/api/v1/notifications", headers=_h(admin)).status_code == 200
    assert client.get("/api/v1/notifications/unread-count", headers=_h(admin)).status_code == 200
    assert client.get("/api/v1/postings", headers=_h(admin)).status_code == 200
    updated = client.patch(f"/api/v1/admin/users/{student.id}", headers=_h(admin), json={"is_active": False})
    assert updated.status_code == 200
    assert updated.json()["is_active"] is False


def test_another_persons_records_stay_private_and_reveal_nothing(client: TestClient, db_session: Session) -> None:
    owner = _account(db_session, "STUDENT")
    stranger = _account(db_session, "STUDENT")
    admin = _account(db_session, "ADMIN", verified=True)
    profile = _profile_id(db_session, owner)
    for path in ("", "/preferences", "/feedback", "/calendar", "/notifications"):
        real = client.get(f"/api/v1/researchers/{profile}{path}", headers=_h(stranger))
        missing = client.get(f"/api/v1/researchers/{uuid.uuid4()}{path}", headers=_h(stranger))
        assert real.status_code == missing.status_code == 403, path
        assert real.json() == missing.json(), path
        # For an administrator, too, a real record and a missing one are answered alike.
        real_admin = client.get(f"/api/v1/researchers/{profile}{path}", headers=_h(admin))
        missing_admin = client.get(f"/api/v1/researchers/{uuid.uuid4()}{path}", headers=_h(admin))
        assert real_admin.status_code == missing_admin.status_code == 403, path
        assert real_admin.json() == missing_admin.json(), path
