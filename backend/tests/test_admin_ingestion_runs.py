"""
Research refresh (step 4/6) — GET /api/v1/admin/ingestion-runs.

ADMIN only. Lists recent ingestion runs (research refresh rows by default) and reports data
freshness: the newest refresh's start and status, works added in the last 24 hours and the
next run estimate. Stored errors are returned as fixed categories, never their text.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import uuid

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.db.types import TSVector, Vector
from app.main import app
from app.models import Base
from app.models.ingestion_run import IngestionRunModel
from app.models.source import SourceModel
from app.models.user import UserModel

compiles(JSONB, "sqlite")(lambda type_, compiler, **kw: "JSON")
compiles(Vector, "sqlite")(lambda type_, compiler, **kw: "TEXT")
compiles(TSVector, "sqlite")(lambda type_, compiler, **kw: "TEXT")

URL = "/api/v1/admin/ingestion-runs"
REDACTED_ERROR = (
    "stopped on an error: HTTPSConnectionPool(host='api.openalex.org', port=443): "
    "Max retries exceeded with url: /works?filter=x&api_key=***"
)


@pytest.fixture
def db_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
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


def _user(db: Session, role: str) -> UserModel:
    user = UserModel(
        id=uuid.uuid4(),
        email=f"{role.lower()}.{uuid.uuid4().hex[:8]}@institution.edu",
        hashed_password=hash_password("SecurePass123!"),
        full_name=f"{role.title()} User",
        role=role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    return user


def _bearer(user: UserModel) -> dict[str, str]:
    token, _ = create_access_token(user.id)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_headers(db_session: Session) -> dict[str, str]:
    return _bearer(_user(db_session, "ADMIN"))


def _run(db: Session, source: SourceModel, topic: str, status: str, started_at: datetime, **fields) -> None:
    db.add(
        IngestionRunModel(
            id=uuid.uuid4(),
            source_id=source.id,
            topic=topic,
            status=status,
            started_at=started_at,
            completed_at=started_at + timedelta(minutes=5) if status != "RUNNING" else None,
            **fields,
        )
    )


@pytest.fixture
def seeded(db_session: Session) -> SimpleNamespace:
    """Two research refreshes (older A, newer B) and one WikiCFP run."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    source = SourceModel(id=uuid.uuid4(), name="OpenAlex", source_type="API")
    db_session.add(source)
    db_session.flush()
    tag_a, tag_b = "aaaa-older", "bbbb-newer"
    _run(db_session, source, f"research_refresh:{tag_a}:newest:1702", "COMPLETED", now - timedelta(hours=30),
         records_inserted=10, records_updated=1)
    _run(db_session, source, f"research_refresh:{tag_a}:rising:1702", "FAILED", now - timedelta(hours=29),
         error_message="OpenAlex daily usage budget exhausted. It resets in about 3.0 h.")
    _run(db_session, source, f"research_refresh:{tag_b}:newest:1702", "FAILED", now - timedelta(hours=2),
         error_message=REDACTED_ERROR, metrics_detail={"total_errors": 1, "note": "text is dropped"})
    _run(db_session, source, f"research_refresh:{tag_b}:rising:1702", "COMPLETED", now - timedelta(hours=1),
         records_inserted=4, records_updated=6)
    _run(db_session, source, "artificial intelligence", "COMPLETED", now - timedelta(minutes=90),
         records_inserted=99)
    db_session.commit()
    return SimpleNamespace(now=now, tag_a=tag_a, tag_b=tag_b, b_started=now - timedelta(hours=2))


def _when(value: str) -> datetime:
    moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


# ── Access ────────────────────────────────────────────────────────────────────


def test_anonymous_requests_are_refused(client):
    assert client.get(URL).status_code == 401


@pytest.mark.parametrize("role", ["STUDENT", "FACULTY"])
def test_non_admins_are_forbidden(client, db_session, role):
    assert client.get(URL, headers=_bearer(_user(db_session, role))).status_code == 403


def test_an_admin_gets_an_empty_list_on_an_empty_database(client, admin_headers):
    response = client.get(URL, headers=admin_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    status = body["research_refresh"]
    assert status["enabled"] is False
    assert status["interval_seconds"] == settings.scheduler_research_refresh_interval_seconds
    assert status["last_run_started_at"] is None and status["last_run_status"] is None
    assert status["works_added_last_24h"] == 0
    assert status["next_run_estimate"] is None


# ── Listing ───────────────────────────────────────────────────────────────────


def test_research_runs_are_listed_newest_first(client, admin_headers, seeded):
    items = client.get(URL, headers=admin_headers).json()["items"]

    assert [item["topic"] for item in items] == [
        f"research_refresh:{seeded.tag_b}:rising:1702",
        f"research_refresh:{seeded.tag_b}:newest:1702",
        f"research_refresh:{seeded.tag_a}:rising:1702",
        f"research_refresh:{seeded.tag_a}:newest:1702",
    ]
    assert [item["status"] for item in items] == ["COMPLETED", "FAILED", "FAILED", "COMPLETED"]


def test_the_limit_is_respected_and_bounded(client, admin_headers, seeded):
    assert len(client.get(URL, params={"limit": 2}, headers=admin_headers).json()["items"]) == 2
    assert client.get(URL, params={"limit": 0}, headers=admin_headers).status_code == 422
    assert client.get(URL, params={"limit": 101}, headers=admin_headers).status_code == 422


def test_research_only_can_be_turned_off(client, admin_headers, seeded):
    every = client.get(URL, params={"research_only": "false"}, headers=admin_headers).json()["items"]
    assert len(every) == 5
    assert "artificial intelligence" in [item["topic"] for item in every]


def test_errors_are_categories_and_no_url_or_key_is_returned(client, admin_headers, seeded):
    response = client.get(URL, headers=admin_headers)
    by_topic = {item["topic"]: item for item in response.json()["items"]}

    assert by_topic[f"research_refresh:{seeded.tag_b}:newest:1702"]["error_message"] == "error"
    assert by_topic[f"research_refresh:{seeded.tag_a}:rising:1702"]["error_message"] == "budget exhausted"
    assert by_topic[f"research_refresh:{seeded.tag_b}:rising:1702"]["error_message"] is None
    assert by_topic[f"research_refresh:{seeded.tag_b}:newest:1702"]["metrics_detail"] == {"total_errors": 1}
    text = response.text
    for leaked in ("api_key", "http", "HTTPSConnectionPool", "Max retries", "/works"):
        assert leaked not in text


# ── Freshness ─────────────────────────────────────────────────────────────────


def test_freshness_reports_the_newest_refresh(client, admin_headers, seeded):
    status = client.get(URL, headers=admin_headers).json()["research_refresh"]

    assert _when(status["last_run_started_at"]) == seeded.b_started
    # One pass failed and one completed: the run as a whole completed.
    assert status["last_run_status"] == "COMPLETED"
    # Only refresh B started in the last 24 hours; the WikiCFP run does not count.
    assert status["works_added_last_24h"] == 4


def test_next_run_is_unknown_while_the_job_is_disabled(client, admin_headers, seeded):
    status = client.get(URL, headers=admin_headers).json()["research_refresh"]
    assert status["enabled"] is False
    assert status["next_run_estimate"] is None


def test_next_run_is_the_last_start_plus_the_interval_when_enabled(client, admin_headers, seeded, monkeypatch):
    monkeypatch.setattr(settings, "scheduler_enabled", True)
    monkeypatch.setattr(settings, "scheduler_research_refresh_enabled", True)
    monkeypatch.setattr(settings, "scheduler_research_refresh_interval_seconds", 28_800)

    status = client.get(URL, headers=admin_headers).json()["research_refresh"]

    assert status["enabled"] is True
    assert _when(status["next_run_estimate"]) == seeded.b_started + timedelta(seconds=28_800)


def test_the_running_scheduler_is_preferred_when_it_has_the_job(client, admin_headers, seeded):
    started = seeded.now - timedelta(minutes=10)
    fake = SimpleNamespace(
        job_names=("deadline_expiry", "research_refresh"),
        job=lambda name: SimpleNamespace(interval_seconds=3_600),
        metrics=SimpleNamespace(get=lambda name: SimpleNamespace(last_started_at=started)),
    )
    client.app.state.scheduler = fake
    try:
        status = client.get(URL, headers=admin_headers).json()["research_refresh"]
    finally:
        client.app.state.scheduler = None

    assert status["enabled"] is True
    assert status["interval_seconds"] == 3_600
    assert _when(status["next_run_estimate"]) == started + timedelta(seconds=3_600)


def test_a_refresh_still_running_or_wholly_failed_is_reported_as_such(db_session, seeded):
    from app.services.ingestion_run_service import research_refresh_status

    source = db_session.query(SourceModel).first()
    started = seeded.now - timedelta(minutes=5)
    _run(db_session, source, "research_refresh:cccc-latest:newest:1702", "COMPLETED", started)
    _run(db_session, source, "research_refresh:cccc-latest:rising:1702", "RUNNING", started + timedelta(minutes=1))
    db_session.commit()
    assert research_refresh_status(db_session, settings).last_run_status == "RUNNING"

    started = seeded.now - timedelta(minutes=1)
    _run(db_session, source, "research_refresh:dddd-latest:newest:1702", "FAILED", started)
    _run(db_session, source, "research_refresh:dddd-latest:rising:1702", "FAILED", started)
    db_session.commit()
    assert research_refresh_status(db_session, settings).last_run_status == "FAILED"
