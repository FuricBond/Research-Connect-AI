"""
The remaining API findings of the independent audit:

  SEC-01  stored links must be plain web addresses, on create and update, in every schema and
          through ingestion
  SEC-04  researcher routes do not confirm that an id exists
  SEC-06  password changes are bounded per client, whatever the client claims about itself
  API-01  first reads of notification preferences do not race into a 500
  API-02  a NUL byte in the admin user search is not a 500
  FUNC-05 the admin user list filters on active and verified
  FUNC-08 an applicant's notifications use the interface's words
"""
from __future__ import annotations

from datetime import datetime, timezone
import uuid

from fastapi.routing import APIRoute
from pydantic import ValidationError
import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from app.core.security import create_access_token, hash_password
from app.core.url_safety import is_safe_web_url, validate_web_url, web_url_or_none
from app.db.session import get_db
from app.db.types import TSVector, Vector
from app.main import app
from app.models.base import Base
from app.models.notification import NotificationModel, NotificationPreferenceModel
from app.models.opportunity import OpportunityModel
from app.models.research_profile import ResearchProfileModel
from app.models.saved_opportunity import SavedOpportunityModel, WorkspaceStatus
from app.models.user import UserModel
from app.schemas.research_posting import ResearchPostingCreate, ResearchPostingUpdate
from app.schemas.research_posting_application import ApplicationCreate
from app.schemas.research_submission import ResearchSubmissionCreate, ResearchSubmissionUpdate
from app.services.notification_service import NotificationService
from scrapers.crossref.normalizer import normalize_crossref_work
from scrapers.openalex.normalizer import normalize_institution
from scrapers.validators.opportunity_validator import _is_valid_url

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


def _account(db: Session, role: str = "STUDENT", *, verified: bool = True, active: bool = True, email: str | None = None) -> UserModel:
    user = UserModel(
        id=uuid.uuid4(),
        email=email or f"{role.lower()}.{uuid.uuid4().hex[:8]}@univ.edu",
        full_name=f"Test {role.title()}",
        hashed_password="pw",
        role=role,
        is_active=active,
        is_verified=verified,
    )
    db.add(user)
    db.flush()
    db.add(ResearchProfileModel(id=uuid.uuid4(), user_id=user.id, academic_status="POSTGRADUATE"))
    db.commit()
    return user


def _h(user: UserModel) -> dict[str, str]:
    return {"X-User-ID": str(user.id)}


UNSAFE = [
    "javascript:alert(1)",
    "JaVaScRiPt:alert(1)",
    " javascript:alert(1)",
    "java\tscript:alert(1)",
    "java\nscript:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "vbscript:msgbox(1)",
    "file:///etc/passwd",
    "ftp://example.org/x",
    "//evil.example/x",
    "\\\\evil.example\\x",
    "/relative/path",
    "example.org",
    "http://",
    "https://",
    "http:///path",
    "https://user:secret@example.org/",
    "https://example.org:99999/",
    "https://exa mple.org/",
    "https://example.org/a\x00b",
]
SAFE = ["http://example.org", "https://example.org/path?q=1#top", "HTTPS://Example.org/", "https://example.org:8443/x"]


@pytest.mark.parametrize("value", UNSAFE)
def test_an_unsafe_address_is_refused(value):
    assert is_safe_web_url(value.strip() if value == " javascript:alert(1)" else value) is False
    with pytest.raises(ValueError):
        validate_web_url(value)


@pytest.mark.parametrize("value", SAFE)
def test_a_web_address_is_kept(value):
    assert validate_web_url(value) == value
    assert validate_web_url(f"  {value} ") == value


@pytest.mark.parametrize("blank", [None, "", "   "])
def test_blank_means_no_link(blank):
    assert validate_web_url(blank) is None


URL_FIELDS = [
    (ResearchPostingCreate, "external_url", {"title": "A good posting title", "posting_type": "RESEARCH_ASSISTANTSHIP", "description": "A description that is long enough to pass."}),
    (ResearchPostingUpdate, "external_url", {}),
    (ApplicationCreate, "portfolio_url", {}),
    (ResearchSubmissionCreate, "submission_url", {"opportunity_id": str(uuid.uuid4()), "workspace_item_id": str(uuid.uuid4()), "title": "A title", "submission_type": "CONFERENCE_PAPER"}),
    (ResearchSubmissionUpdate, "submission_url", {}),
]


@pytest.mark.parametrize("schema, field, base", URL_FIELDS)
@pytest.mark.parametrize("value", UNSAFE)
def test_every_schema_refuses_an_unsafe_address(schema, field, base, value):
    with pytest.raises(ValidationError) as caught:
        schema(**base, **{field: value})
    assert field in str(caught.value)


def _posting_body(**extra) -> dict:
    return {
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
        **extra,
    }


@pytest.mark.parametrize("value", ["javascript:alert(1)", "data:text/html,x", "vbscript:x", "ftp://x.org/y", "//evil.example"])
def test_the_posting_api_refuses_unsafe_links_on_create_and_update(client: TestClient, db_session: Session, value):
    faculty = _account(db_session, "FACULTY")
    assert client.post("/api/v1/postings", headers=_h(faculty), json=_posting_body(external_url=value)).status_code == 422
    created = client.post("/api/v1/postings", headers=_h(faculty), json=_posting_body(external_url="https://lab.example.org/a"))
    assert created.status_code == 201
    assert created.json()["external_url"] == "https://lab.example.org/a"
    posting_id = created.json()["id"]
    assert client.patch(f"/api/v1/postings/{posting_id}", headers=_h(faculty), json={"external_url": value}).status_code == 422
    assert client.get(f"/api/v1/postings/{posting_id}", headers=_h(faculty)).json()["external_url"] == "https://lab.example.org/a"
    assert client.patch(f"/api/v1/postings/{posting_id}", headers=_h(faculty), json={"external_url": "http://lab.example.org/b"}).json()["external_url"] == "http://lab.example.org/b"


def test_a_legacy_unsafe_value_does_not_block_other_edits(client: TestClient, db_session: Session):
    from app.models.research_posting import ResearchPostingModel

    faculty = _account(db_session, "FACULTY")
    created = client.post("/api/v1/postings", headers=_h(faculty), json=_posting_body()).json()
    row = db_session.get(ResearchPostingModel, uuid.UUID(created["id"]))
    row.external_url = "javascript:alert(1)"
    db_session.commit()
    res = client.patch(f"/api/v1/postings/{created['id']}", headers=_h(faculty), json={"title": "A corrected posting title"})
    assert res.status_code == 200
    assert res.json()["external_url"] == "javascript:alert(1)"  # kept, never silently deleted
    assert client.patch(f"/api/v1/postings/{created['id']}", headers=_h(faculty), json={"external_url": None}).json()["external_url"] is None


def test_the_application_api_refuses_an_unsafe_portfolio_link(client: TestClient, db_session: Session):
    faculty, student = _account(db_session, "FACULTY"), _account(db_session)
    posting_id = client.post("/api/v1/postings", headers=_h(faculty), json=_posting_body()).json()["id"]
    assert client.post(f"/api/v1/postings/{posting_id}/transition", headers=_h(faculty), json={"target_status": "OPEN"}).status_code == 200
    url = f"/api/v1/postings/{posting_id}/applications"
    assert client.post(url, headers=_h(student), json={"portfolio_url": "javascript:alert(1)"}).status_code == 422
    accepted = client.post(url, headers=_h(student), json={"portfolio_url": "https://me.example.org"})
    assert accepted.status_code == 201
    assert accepted.json()["portfolio_url"] == "https://me.example.org"


def test_ingestion_cannot_bring_an_unsafe_link_in():
    assert web_url_or_none("javascript:alert(1)") is None
    assert web_url_or_none(" https://example.org/x ") == "https://example.org/x"
    institution = normalize_institution({"id": "https://openalex.org/I1", "display_name": "U", "homepage_url": "javascript:alert(1)"})
    assert institution.homepage_url is None
    work = normalize_crossref_work(
        {
            "DOI": "10.1000/xyz",
            "title": ["A work"],
            "type": "journal-article",
            "URL": "javascript:alert(1)",
            "license": [{"URL": "javascript:alert(1)"}, {"URL": "https://creativecommons.org/licenses/by/4.0/"}],
        }
    )
    assert work.url is None
    assert work.license_url == "https://creativecommons.org/licenses/by/4.0/"
    assert _is_valid_url("javascript:alert(1)") is False
    assert _is_valid_url("https://example.org") is True


# ── SEC-04 ───────────────────────────────────────────────────────────────────


def _researcher_get_routes() -> list[str]:
    paths = set()
    for route in app.routes:
        if isinstance(route, APIRoute) and "GET" in route.methods and route.path.startswith("/api/v1/researchers/{researcher_id}"):
            if route.path.count("{") == 1:
                paths.add(route.path)
    return sorted(paths)


def test_the_route_list_is_not_empty():
    assert len(_researcher_get_routes()) >= 20


@pytest.mark.parametrize("path", _researcher_get_routes())
def test_a_caller_cannot_tell_a_real_researcher_from_a_made_up_one(client: TestClient, db_session: Session, path):
    owner, other = _account(db_session), _account(db_session)
    profile = db_session.execute(select(ResearchProfileModel).where(ResearchProfileModel.user_id == owner.id)).scalar_one()
    real = path.replace("{researcher_id}", str(profile.id))
    fake = path.replace("{researcher_id}", str(uuid.uuid4()))

    signed_out_real, signed_out_fake = client.get(real), client.get(fake)
    assert signed_out_real.status_code == signed_out_fake.status_code, path
    assert signed_out_real.json() == signed_out_fake.json(), path

    signed_in_real, signed_in_fake = client.get(real, headers=_h(other)), client.get(fake, headers=_h(other))
    assert signed_in_real.status_code == signed_in_fake.status_code, path
    assert signed_in_real.json() == signed_in_fake.json(), path


def test_owners_still_reach_their_own_profile(client: TestClient, db_session: Session):
    owner = _account(db_session)
    profile = db_session.execute(select(ResearchProfileModel).where(ResearchProfileModel.user_id == owner.id)).scalar_one()
    assert client.get(f"/api/v1/researchers/{profile.id}", headers=_h(owner)).status_code == 200
    assert client.get(f"/api/v1/researchers/{owner.id}", headers=_h(owner)).status_code == 200


# ── SEC-06 ───────────────────────────────────────────────────────────────────


def test_password_changes_are_bounded_whatever_address_the_client_claims(client: TestClient, db_session: Session):
    user = _account(db_session)
    user.hashed_password = hash_password("The-current-passw0rd")
    db_session.commit()
    token, _ = create_access_token(user.id, token_version=user.token_version)
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"current_password": "Not-the-passw0rd", "new_password": "A-brand-new-passw0rd"}

    codes = [
        client.post("/api/v1/auth/change-password", headers={**headers, "X-Forwarded-For": f"10.0.0.{i}", "X-Real-IP": f"10.0.0.{i}"}, json=payload).status_code
        for i in range(12)
    ]
    assert codes[:10] == [400] * 10
    assert codes[10:] == [429, 429]
    limited = client.post("/api/v1/auth/change-password", headers=headers, json=payload)
    assert limited.status_code == 429
    assert int(limited.headers["Retry-After"]) > 0


# ── API-01 ───────────────────────────────────────────────────────────────────


def test_losing_the_race_to_create_preferences_returns_the_winners_row(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'race.db'}")
    Base.metadata.create_all(bind=engine)
    make = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    with make() as setup:
        user = _account(setup)
        profile_id = setup.execute(select(ResearchProfileModel.id).where(ResearchProfileModel.user_id == user.id)).scalar_one()

    winner_id = uuid.uuid4()

    raced = []

    def the_other_request_commits_first(session, *_):
        if raced:
            return
        raced.append(True)
        with make() as other:
            other.add(NotificationPreferenceModel(id=winner_id, profile_id=profile_id))
            other.commit()

    with make() as loser:
        event.listen(loser, "before_flush", the_other_request_commits_first)
        prefs = NotificationService.get_or_create_preferences(loser, profile_id)
        assert prefs.id == winner_id
    with make() as check:
        assert len(check.execute(select(NotificationPreferenceModel)).scalars().all()) == 1


# ── API-02, FUNC-05 ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("query", ["search=%00", "search=a%00b", "search=%00%00&role=STUDENT"])
def test_a_nul_in_the_user_search_finds_nothing(client: TestClient, db_session: Session, query):
    admin = _account(db_session, "ADMIN")
    res = client.get(f"/api/v1/admin/users?{query}", headers=_h(admin))
    assert res.status_code == 200
    assert res.json() == {"users": [], "total": 0}


def test_the_user_list_filters_on_active_and_verified(client: TestClient, db_session: Session):
    admin = _account(db_session, "ADMIN", email="admin@univ.edu")
    gone = _account(db_session, active=False, email="gone@univ.edu")
    waiting = _account(db_session, "FACULTY", verified=False, email="waiting@univ.edu")

    def emails(query: str) -> set[str]:
        res = client.get(f"/api/v1/admin/users?{query}", headers=_h(admin))
        assert res.status_code == 200
        body = res.json()
        assert body["total"] == len(body["users"])
        return {u["email"] for u in body["users"]}

    assert emails("is_active=false") == {gone.email}
    assert emails("is_active=true") == {admin.email, waiting.email}
    assert emails("is_verified=false") == {waiting.email}
    assert emails("is_verified=false&role=FACULTY") == {waiting.email}
    assert emails("is_verified=false&role=STUDENT") == set()
    assert emails("is_active=true&search=waiting") == {waiting.email}
    assert client.get("/api/v1/admin/users?is_active=false", headers=_h(gone)).status_code in (401, 403)
    assert client.get("/api/v1/admin/users?is_active=maybe", headers=_h(admin)).status_code == 422


# ── FUNC-08 ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("target, title, phrase", [
    ("UNDER_REVIEW", "Application: Under review", "Under review."),
    ("SHORTLISTED", "Application: Shortlisted", "Shortlisted."),
    ("OFFERED", "Application: Offer made", "Offer made."),
    ("REJECTED", "Application: Not selected", "Not selected."),
])
def test_an_applicant_reads_the_interfaces_words(client: TestClient, db_session: Session, target, title, phrase):
    faculty, student = _account(db_session, "FACULTY"), _account(db_session)
    posting_id = client.post("/api/v1/postings", headers=_h(faculty), json=_posting_body()).json()["id"]
    client.post(f"/api/v1/postings/{posting_id}/transition", headers=_h(faculty), json={"target_status": "OPEN"})
    application_id = client.post(f"/api/v1/postings/{posting_id}/applications", headers=_h(student), json={"cover_note": "x"}).json()["id"]

    steps = {"UNDER_REVIEW": ["UNDER_REVIEW"], "SHORTLISTED": ["UNDER_REVIEW", "SHORTLISTED"], "OFFERED": ["UNDER_REVIEW", "SHORTLISTED", "OFFERED"], "REJECTED": ["REJECTED"]}
    for step in steps[target]:
        moved = client.post(f"/api/v1/postings/applications/{application_id}/transition", headers=_h(faculty), json={"target_status": step})
        assert moved.status_code == 200, moved.text

    profile = db_session.execute(select(ResearchProfileModel).where(ResearchProfileModel.user_id == student.id)).scalar_one()
    newest = db_session.execute(
        select(NotificationModel).where(NotificationModel.profile_id == profile.id).order_by(NotificationModel.created_at.desc())
    ).scalars().all()
    titles = [n.title for n in newest]
    assert title in titles
    body = next(n.body for n in newest if n.title == title)
    assert phrase in body
    for note in newest:
        assert "rejected" not in (note.title + note.body).lower()
        assert "is now offered" not in note.body


def test_an_author_reads_what_the_applicant_did(client: TestClient, db_session: Session):
    faculty, student = _account(db_session, "FACULTY"), _account(db_session)
    posting_id = client.post("/api/v1/postings", headers=_h(faculty), json=_posting_body()).json()["id"]
    client.post(f"/api/v1/postings/{posting_id}/transition", headers=_h(faculty), json={"target_status": "OPEN"})
    application_id = client.post(f"/api/v1/postings/{posting_id}/applications", headers=_h(student), json={"cover_note": "x"}).json()["id"]
    assert client.post(f"/api/v1/postings/applications/{application_id}/transition", headers=_h(student), json={"target_status": "WITHDRAWN"}).status_code == 200
    profile = db_session.execute(select(ResearchProfileModel).where(ResearchProfileModel.user_id == faculty.id)).scalar_one()
    titles = [n.title for n in db_session.execute(select(NotificationModel).where(NotificationModel.profile_id == profile.id)).scalars().all()]
    assert "An applicant withdrew their application" in titles


def test_the_report_lists_a_stored_unsafe_link_by_id_without_its_value_and_changes_nothing(tmp_path, monkeypatch, capsys):
    from app.models.research_posting import ResearchPostingModel
    from scripts import report_unsafe_urls

    engine = create_engine(f"sqlite:///{tmp_path / 'report.db'}")
    Base.metadata.create_all(bind=engine)
    make = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    with make() as db:
        user = _account(db, "FACULTY")
        profile_id = db.execute(select(ResearchProfileModel.id).where(ResearchProfileModel.user_id == user.id)).scalar_one()
        unsafe = uuid.uuid4()
        for row_id, url in ((unsafe, "javascript:alert(1)"), (uuid.uuid4(), "https://lab.example.org")):
            db.add(ResearchPostingModel(id=row_id, author_profile_id=profile_id, author_user_id=user.id, title="A posting", posting_type="PROJECT", status="DRAFT", description="A description", external_url=url))
        db.commit()

    monkeypatch.setattr(report_unsafe_urls, "SessionLocal", make)
    assert report_unsafe_urls.main() == 0
    out = capsys.readouterr().out
    assert f"research_postings.external_url\t{unsafe.hex}" in out or f"research_postings.external_url\t{unsafe}" in out
    assert "javascript" not in out
    assert "1 stored link(s)" in out
    with make() as db:
        assert db.get(ResearchPostingModel, unsafe).external_url == "javascript:alert(1)"
