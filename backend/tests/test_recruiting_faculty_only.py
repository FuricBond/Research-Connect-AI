"""
Decision B — recruiting is faculty-only, on the server.

An administrator manages accounts: being one grants nothing over postings or applicants, whoever
wrote them, whatever the request says. Every endpoint that manages recruiting is tried directly for
each role. Verified faculty keep the whole workflow, the verification gate stays in force, students
keep the applicant's side, and administrators keep platform administration.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from app.db.session import get_db
from app.db.types import TSVector, Vector
from app.main import app
from app.models.base import Base
from app.models.research_posting import PostingStatus, ResearchPostingModel
from app.models.research_profile import ResearchProfileModel
from app.models.user import UserModel
from app.services.research_posting_service import ResearchPostingService

compiles(JSONB, "sqlite")(lambda type_, compiler, **kw: "JSON")
compiles(Vector, "sqlite")(lambda type_, compiler, **kw: "TEXT")
compiles(TSVector, "sqlite")(lambda type_, compiler, **kw: "TEXT")


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
    db.add(ResearchProfileModel(id=uuid.uuid4(), user_id=user.id, academic_status="FACULTY" if role == "FACULTY" else "POSTGRADUATE"))
    db.commit()
    return user


def _h(user: UserModel) -> dict[str, str]:
    return {"X-User-ID": str(user.id)}


BODY = {
    "title": "Assistant for causal inference",
    "posting_type": "RESEARCH_ASSISTANTSHIP",
    "description": "Work on causal inference methods with the group for a semester.",
    "required_skills": ["python"],
    "opening_terms": {
        "compensation_type": "STIPEND",
        "compensation_amount": 1000,
        "compensation_currency": "USD",
        "compensation_period": "MONTH",
        "commitment_type": "PART_TIME",
        "hours_per_week": 10,
        "duration_months": 6,
        "accepts_applications": True,
    },
}


def _posting(client: TestClient, faculty: UserModel, *, publish: bool = True) -> str:
    created = client.post("/api/v1/postings", headers=_h(faculty), json=BODY)
    assert created.status_code == 201, created.text
    posting_id = created.json()["id"]
    if publish:
        assert client.post(f"/api/v1/postings/{posting_id}/transition", headers=_h(faculty), json={"target_status": "OPEN"}).status_code == 200
    return posting_id


def _application(client: TestClient, posting_id: str, student: UserModel) -> str:
    applied = client.post(f"/api/v1/postings/{posting_id}/applications", headers=_h(student), json={"cover_note": "Hello"})
    assert applied.status_code == 201, applied.text
    return applied.json()["id"]


def _management_requests(posting_id: str, application_id: str) -> list[tuple[str, str, dict | None]]:
    """Every request that manages recruiting. Each must be refused for a role that does not recruit."""
    return [
        ("POST", "/api/v1/postings", BODY),
        ("GET", "/api/v1/postings/mine", None),
        ("GET", "/api/v1/postings/mine/summary", None),
        ("PATCH", f"/api/v1/postings/{posting_id}", {"summary": "Changed"}),
        ("POST", f"/api/v1/postings/{posting_id}/transition", {"target_status": "CLOSED"}),
        ("DELETE", f"/api/v1/postings/{posting_id}", None),
        ("GET", f"/api/v1/postings/{posting_id}/applications", None),
        ("GET", f"/api/v1/postings/applications/{application_id}", None),
        ("POST", f"/api/v1/postings/applications/{application_id}/transition", {"target_status": "UNDER_REVIEW"}),
    ]


def _refused(client: TestClient, user: UserModel, method: str, path: str, body: dict | None) -> int:
    return client.request(method, path, headers=_h(user), json=body).status_code


@pytest.mark.parametrize("role", ["ADMIN", "STUDENT"])
def test_a_role_that_does_not_recruit_is_refused_by_every_management_endpoint(client: TestClient, db_session: Session, role: str):
    faculty = _account(db_session, "FACULTY", verified=True)
    applicant = _account(db_session, "STUDENT")
    actor = _account(db_session, role, verified=True)
    posting_id = _posting(client, faculty)
    application_id = _application(client, posting_id, applicant)

    for method, path, body in _management_requests(posting_id, application_id):
        # 403, or 404 where the object's existence is itself not this account's business.
        assert _refused(client, actor, method, path, body) in (403, 404), f"{method} {path}"

    db_session.expire_all()
    posting = db_session.get(ResearchPostingModel, uuid.UUID(posting_id))
    assert posting.status == PostingStatus.OPEN.value and posting.summary is None
    assert client.get(f"/api/v1/postings/applications/{application_id}", headers=_h(faculty)).json()["status"] == "SUBMITTED"


def test_an_administrator_gets_a_clear_refusal_when_creating_even_without_a_profile(client: TestClient, db_session: Session):
    admin = UserModel(id=uuid.uuid4(), email="noprofile@univ.edu", full_name="No Profile", hashed_password="pw", role="ADMIN", is_active=True)
    db_session.add(admin)
    db_session.commit()
    refused = client.post("/api/v1/postings", headers=_h(admin), json=BODY)
    assert refused.status_code == 403
    assert refused.json()["detail"] == "Only faculty accounts may create research postings."


def test_a_verified_flag_gives_an_administrator_nothing(db_session: Session):
    admin = _account(db_session, "ADMIN", verified=True)
    assert ResearchPostingService.can_recruit(admin) is False


def test_an_administrator_cannot_manage_a_posting_written_before_the_rule_or_as_faculty(client: TestClient, db_session: Session):
    """Promoted to administrator, or an administrator's old posting: authorship grants nothing either."""
    author = _account(db_session, "FACULTY", verified=True)
    applicant = _account(db_session, "STUDENT")
    posting_id = _posting(client, author)
    application_id = _application(client, posting_id, applicant)
    draft_id = _posting(client, author, publish=False)
    author.role = "ADMIN"
    db_session.commit()

    for method, path, body in _management_requests(posting_id, application_id):
        assert _refused(client, author, method, path, body) in (403, 404), f"{method} {path}"
    assert client.delete(f"/api/v1/postings/{draft_id}", headers=_h(author)).status_code == 403
    # It no longer counts as someone recruiting: not public, and it takes no applications.
    assert client.get(f"/api/v1/postings/{posting_id}").status_code == 404
    assert posting_id not in [p["id"] for p in client.get("/api/v1/postings").json()["postings"]]
    other = _account(db_session, "STUDENT")
    assert client.post(f"/api/v1/postings/{posting_id}/applications", headers=_h(other), json={"cover_note": "Hi"}).status_code == 400


def test_an_administrator_reads_any_posting_but_is_never_told_it_is_theirs(client: TestClient, db_session: Session):
    faculty = _account(db_session, "FACULTY", verified=True)
    admin = _account(db_session, "ADMIN")
    draft_id = _posting(client, faculty, publish=False)
    read = client.get(f"/api/v1/postings/{draft_id}", headers=_h(admin))
    assert read.status_code == 200
    assert read.json()["is_owner"] is False


def test_verified_faculty_keep_the_whole_workflow(client: TestClient, db_session: Session):
    faculty = _account(db_session, "FACULTY", verified=True)
    student = _account(db_session, "STUDENT")
    h = _h(faculty)

    posting_id = _posting(client, faculty, publish=False)
    assert client.patch(f"/api/v1/postings/{posting_id}", headers=h, json={"summary": "Edited"}).json()["summary"] == "Edited"
    assert client.post(f"/api/v1/postings/{posting_id}/transition", headers=h, json={"target_status": "OPEN"}).status_code == 200
    application_id = _application(client, posting_id, student)

    assert client.get("/api/v1/postings/mine", headers=h).json()["total"] == 1
    assert client.get("/api/v1/postings/mine/summary", headers=h).json()["total"] == 1
    assert [a["id"] for a in client.get(f"/api/v1/postings/{posting_id}/applications", headers=h).json()["applications"]] == [application_id]
    decided = client.post(f"/api/v1/postings/applications/{application_id}/transition", headers=h, json={"target_status": "UNDER_REVIEW"})
    assert decided.status_code == 200 and decided.json()["status"] == "UNDER_REVIEW"
    assert client.post(f"/api/v1/postings/{posting_id}/transition", headers=h, json={"target_status": "CLOSED"}).status_code == 200

    draft_id = _posting(client, faculty, publish=False)
    assert client.delete(f"/api/v1/postings/{draft_id}", headers=h).status_code == 204


def test_another_faculty_account_is_refused(client: TestClient, db_session: Session):
    author = _account(db_session, "FACULTY", verified=True)
    other = _account(db_session, "FACULTY", verified=True)
    applicant = _account(db_session, "STUDENT")
    posting_id = _posting(client, author)
    application_id = _application(client, posting_id, applicant)
    assert client.patch(f"/api/v1/postings/{posting_id}", headers=_h(other), json={"summary": "x"}).status_code == 403
    assert client.get(f"/api/v1/postings/{posting_id}/applications", headers=_h(other)).status_code == 403
    assert client.get(f"/api/v1/postings/applications/{application_id}", headers=_h(other)).status_code == 404


def test_the_verification_gate_stays_in_force_for_faculty(client: TestClient, db_session: Session):
    unverified = _account(db_session, "FACULTY")
    assert "has not been verified" in client.post("/api/v1/postings", headers=_h(unverified), json=BODY).json()["detail"]
    # Their own list still answers (empty), so the page can say what they are waiting for.
    assert client.get("/api/v1/postings/mine", headers=_h(unverified)).status_code == 200


def test_withdrawing_verification_is_how_an_administrator_takes_postings_down(client: TestClient, db_session: Session):
    faculty = _account(db_session, "FACULTY", verified=True)
    admin = _account(db_session, "ADMIN")
    posting_id = _posting(client, faculty)
    assert client.patch(f"/api/v1/admin/users/{faculty.id}", headers=_h(admin), json={"is_verified": False}).status_code == 200
    assert client.get(f"/api/v1/postings/{posting_id}").status_code == 404


def test_platform_administration_is_untouched(client: TestClient, db_session: Session):
    admin = _account(db_session, "ADMIN")
    target = _account(db_session, "FACULTY")
    h = _h(admin)
    assert client.get("/api/v1/admin/users", headers=h).status_code == 200
    assert client.patch(f"/api/v1/admin/users/{target.id}", headers=h, json={"is_verified": True}).json()["is_verified"] is True
    assert client.patch(f"/api/v1/admin/users/{target.id}", headers=h, json={"is_active": False}).json()["is_active"] is False
    assert client.patch(f"/api/v1/admin/users/{target.id}", headers=h, json={"role": "STUDENT"}).json()["role"] == "STUDENT"


def test_a_student_keeps_the_applicants_side(client: TestClient, db_session: Session):
    faculty = _account(db_session, "FACULTY", verified=True)
    student = _account(db_session, "STUDENT")
    h = _h(student)
    posting_id = _posting(client, faculty)

    assert [p["id"] for p in client.get("/api/v1/postings").json()["postings"]] == [posting_id]
    assert client.get(f"/api/v1/postings/{posting_id}", headers=h).status_code == 200
    application_id = _application(client, posting_id, student)
    assert client.get("/api/v1/postings/applications/mine", headers=h).json()["total"] == 1
    assert client.get(f"/api/v1/postings/applications/{application_id}", headers=h).status_code == 200
    withdrawn = client.post(f"/api/v1/postings/applications/{application_id}/transition", headers=h, json={"target_status": "WITHDRAWN"})
    assert withdrawn.status_code == 200 and withdrawn.json()["status"] == "WITHDRAWN"
