"""
Decision 1 (audit SEC-03) — anyone can register as faculty, but recruiting waits for an
administrator's verification, and the API enforces it whatever the frontend shows.

Unverified faculty cannot create or publish a posting; a posting of theirs is not public and
receives no applications. Verified faculty, administrators and students keep what they had.
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


def _open_posting(client: TestClient, db: Session, author: UserModel) -> str:
    """A posting published while `author` was verified."""
    created = client.post("/api/v1/postings", headers=_h(author), json=BODY)
    assert created.status_code == 201, created.text
    posting_id = created.json()["id"]
    assert client.post(f"/api/v1/postings/{posting_id}/transition", headers=_h(author), json={"target_status": "OPEN"}).status_code == 200
    return posting_id


def test_unverified_faculty_cannot_create_a_posting_through_the_api(client: TestClient, db_session: Session):
    faculty = _account(db_session, "FACULTY")
    res = client.post("/api/v1/postings", headers=_h(faculty), json=BODY)
    assert res.status_code == 403
    assert "verif" in res.json()["detail"].lower()
    assert db_session.query(ResearchPostingModel).count() == 0


def test_registering_as_faculty_leaves_the_account_unverified_and_unable_to_recruit(client: TestClient):
    registered = client.post(
        "/api/v1/auth/register",
        json={"email": "self.declared@univ.edu", "password": "A-long-enough-passw0rd", "full_name": "Self Declared", "role": "FACULTY"},
    )
    assert registered.status_code == 201
    assert registered.json()["user"]["is_verified"] is False
    res = client.post("/api/v1/postings", headers={"Authorization": f"Bearer {registered.json()['access_token']}"}, json=BODY)
    assert res.status_code == 403


def test_verified_faculty_keep_working(client: TestClient, db_session: Session):
    faculty = _account(db_session, "FACULTY", verified=True)
    posting_id = _open_posting(client, db_session, faculty)
    assert client.get(f"/api/v1/postings/{posting_id}").status_code == 200
    assert [p["id"] for p in client.get("/api/v1/postings").json()["postings"]] == [posting_id]


def test_an_administrator_needs_no_verification(client: TestClient, db_session: Session):
    admin = _account(db_session, "ADMIN")
    posting_id = _open_posting(client, db_session, admin)
    assert client.get(f"/api/v1/postings/{posting_id}").status_code == 200


def test_verification_by_an_administrator_opens_recruiting(client: TestClient, db_session: Session):
    faculty = _account(db_session, "FACULTY")
    admin = _account(db_session, "ADMIN")
    assert client.post("/api/v1/postings", headers=_h(faculty), json=BODY).status_code == 403
    assert client.patch(f"/api/v1/admin/users/{faculty.id}", headers=_h(admin), json={"is_verified": True}).status_code == 200
    assert client.post("/api/v1/postings", headers=_h(faculty), json=BODY).status_code == 201


def test_a_faculty_member_cannot_verify_themselves(client: TestClient, db_session: Session):
    faculty = _account(db_session, "FACULTY")
    assert client.patch(f"/api/v1/admin/users/{faculty.id}", headers=_h(faculty), json={"is_verified": True}).status_code == 403
    db_session.refresh(faculty)
    assert faculty.is_verified is False


class TestWhenVerificationIsWithdrawn:
    """A posting published while verified, whose author then loses verification."""

    @pytest.fixture
    def setup(self, client: TestClient, db_session: Session):
        faculty = _account(db_session, "FACULTY", verified=True)
        posting_id = _open_posting(client, db_session, faculty)
        faculty.is_verified = False
        db_session.commit()
        return faculty, posting_id

    def test_it_leaves_the_public_listing_and_page(self, client: TestClient, db_session: Session, setup):
        _, posting_id = setup
        student = _account(db_session, "STUDENT")
        assert client.get("/api/v1/postings").json()["postings"] == []
        assert client.get("/api/v1/postings", params={"status": "OPEN"}).json()["postings"] == []
        assert client.get(f"/api/v1/postings/{posting_id}").status_code == 404
        assert client.get(f"/api/v1/postings/{posting_id}", headers=_h(student)).status_code == 404

    def test_it_receives_no_application_even_by_direct_request(self, client: TestClient, db_session: Session, setup):
        _, posting_id = setup
        student = _account(db_session, "STUDENT")
        res = client.post(f"/api/v1/postings/{posting_id}/applications", headers=_h(student), json={"cover_note": "Please"})
        assert res.status_code == 400
        assert "cannot receive applications" in res.json()["detail"]

    def test_its_fit_is_not_offered(self, client: TestClient, db_session: Session, setup):
        _, posting_id = setup
        student = _account(db_session, "STUDENT")
        assert client.post("/api/v1/postings/fit-scores", headers=_h(student), json={"posting_ids": [posting_id]}).json()["fits"] == []
        assert client.get(f"/api/v1/postings/{posting_id}/fit", headers=_h(student)).status_code == 404

    def test_the_author_still_sees_it_and_can_wind_it_down_but_not_reopen(self, client: TestClient, setup):
        faculty, posting_id = setup
        assert client.get(f"/api/v1/postings/{posting_id}", headers=_h(faculty)).status_code == 200
        assert [p["id"] for p in client.get("/api/v1/postings/mine", headers=_h(faculty)).json()["postings"]] == [posting_id]
        assert client.post(f"/api/v1/postings/{posting_id}/transition", headers=_h(faculty), json={"target_status": "CLOSED"}).status_code == 200
        reopened = client.post(f"/api/v1/postings/{posting_id}/transition", headers=_h(faculty), json={"target_status": "OPEN"})
        assert reopened.status_code == 403
        assert "verif" in reopened.json()["detail"].lower()


def test_a_draft_cannot_be_published_once_verification_is_withdrawn(client: TestClient, db_session: Session):
    faculty = _account(db_session, "FACULTY", verified=True)
    posting_id = client.post("/api/v1/postings", headers=_h(faculty), json=BODY).json()["id"]
    faculty.is_verified = False
    db_session.commit()
    res = client.post(f"/api/v1/postings/{posting_id}/transition", headers=_h(faculty), json={"target_status": "OPEN"})
    assert res.status_code == 403
    assert db_session.get(ResearchPostingModel, uuid.UUID(posting_id)).status == PostingStatus.DRAFT.value


def test_an_administrator_cannot_publish_for_an_unverified_author(client: TestClient, db_session: Session):
    faculty = _account(db_session, "FACULTY", verified=True)
    admin = _account(db_session, "ADMIN")
    posting_id = client.post("/api/v1/postings", headers=_h(faculty), json=BODY).json()["id"]
    faculty.is_verified = False
    db_session.commit()
    assert client.post(f"/api/v1/postings/{posting_id}/transition", headers=_h(admin), json={"target_status": "OPEN"}).status_code == 403


def test_students_are_refused_for_their_role_and_keep_what_they_had(client: TestClient, db_session: Session):
    faculty = _account(db_session, "FACULTY", verified=True)
    student = _account(db_session, "STUDENT")
    posting_id = _open_posting(client, db_session, faculty)
    assert "FACULTY and ADMIN" in client.post("/api/v1/postings", headers=_h(student), json=BODY).json()["detail"]
    assert client.get(f"/api/v1/postings/{posting_id}", headers=_h(student)).status_code == 200
    assert client.post(f"/api/v1/postings/{posting_id}/applications", headers=_h(student), json={"cover_note": "Hello"}).status_code == 201


def test_an_unverified_account_keeps_its_other_features(client: TestClient, db_session: Session):
    faculty = _account(db_session, "FACULTY")
    assert client.get("/api/v1/auth/me", headers=_h(faculty)).json()["is_verified"] is False
    assert client.get("/api/v1/postings/mine", headers=_h(faculty)).status_code == 200
    assert client.get("/api/v1/postings", headers=_h(faculty)).status_code == 200
    assert client.get("/api/v1/workspace", headers=_h(faculty)).status_code == 200
