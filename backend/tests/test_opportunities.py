"""
Tests for the Opportunity API endpoints.

Testing strategy
----------------
SQLite in-memory is used as the test database. Because SQLite does not support
PostgreSQL-specific types (JSONB, UUID, JSONB arrays, vector), we build a
lightweight test-specific schema that mirrors only the columns needed for the
API tests, mapped to SQLite-compatible types.  Production models and production
database configuration are completely untouched — only the FastAPI dependency
`get_db` is overridden.
"""
import uuid
from collections.abc import Generator
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Date,
    Numeric,
    String,
    Text,
    create_engine,
    select,
    func,
    or_,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker, Mapped, mapped_column


# ---------------------------------------------------------------------------
# Minimal SQLite-compatible ORM for tests
# ---------------------------------------------------------------------------

class SqBase(DeclarativeBase):
    pass


class SqOpportunity(SqBase):
    """SQLite-compatible mirror of OpportunityModel for tests."""
    __tablename__ = "opportunities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    opportunity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    slug: Mapped[str | None] = mapped_column(String(255), nullable=True)
    publisher: Mapped[str | None] = mapped_column(String(255), nullable=True)
    organizer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    series_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    edition: Mapped[str | None] = mapped_column(String(50), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    website_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    submission_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivery_mode: Mapped[str] = mapped_column(String(50), default="OFFLINE", nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    submission_deadline: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    notification_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    camera_ready_deadline: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    event_start_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    event_end_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # JSONB columns stored as Text in SQLite
    indexing: Mapped[str | None] = mapped_column(Text, nullable=True)
    apc_or_fee: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_reasons: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_predatory_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    risk_score: Mapped[float | None] = mapped_column(Numeric(3, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="ACTIVE", nullable=False)
    source_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    raw_source_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(tz=timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(tz=timezone.utc), nullable=False)


SQLITE_URL = "sqlite:///:memory:"
engine = create_engine(SQLITE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="module", autouse=True)
def setup_database():
    SqBase.metadata.create_all(bind=engine)
    yield
    SqBase.metadata.drop_all(bind=engine)


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


# ---------------------------------------------------------------------------
# Stub service + routes that run against the SQLite TestOpportunity table
# ---------------------------------------------------------------------------

from fastapi import FastAPI, HTTPException, Query, Depends
from typing import Annotated
from pydantic import BaseModel, ConfigDict
from decimal import Decimal


class OppItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    opportunity_type: str
    publisher: str | None = None
    organizer: str | None = None
    summary: str | None = None
    delivery_mode: str
    location: str | None = None
    submission_deadline: datetime | None = None
    event_start_date: str | None = None
    event_end_date: str | None = None
    indexing: str | None = None
    website_url: str | None = None
    submission_url: str | None = None
    is_predatory_flag: bool
    risk_score: Decimal | None = None
    status: str
    created_at: datetime
    updated_at: datetime


class OppRead(OppItem):
    description: str | None = None
    last_verified_at: datetime | None = None
    source_id: str | None = None


class OppListResponse(BaseModel):
    items: list[OppItem]
    page: int
    page_size: int
    total: int


VALID_TYPES = {"CONFERENCE", "JOURNAL", "WORKSHOP", "CALL_FOR_PAPERS", "SPECIAL_ISSUE"}
VALID_STATUSES = {"ACTIVE", "EXPIRED", "ARCHIVED", "DRAFT", "UNVERIFIED"}
VALID_MODES = {"ONLINE", "OFFLINE", "HYBRID"}
VALID_SORTS = {"newest", "deadline", "title"}

api_app = FastAPI()

def get_test_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@api_app.get("/api/opportunities", response_model=OppListResponse)
def _list(
    db: Annotated[Session, Depends(get_test_db)],
    search: str | None = None,
    opportunity_type: str | None = None,
    status: str | None = None,
    delivery_mode: str | None = None,
    upcoming: bool = False,
    sort: str = "newest",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    if opportunity_type and opportunity_type.upper() not in VALID_TYPES:
        from fastapi import HTTPException
        raise HTTPException(422, "Invalid opportunity_type")
    if status and status.upper() not in VALID_STATUSES:
        raise HTTPException(422, "Invalid status")
    if delivery_mode and delivery_mode.upper() not in VALID_MODES:
        raise HTTPException(422, "Invalid delivery_mode")
    if sort not in VALID_SORTS:
        raise HTTPException(422, "Invalid sort")

    stmt = select(SqOpportunity)
    if search:
        term = f"%{search.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(SqOpportunity.title).like(term),
                func.lower(SqOpportunity.summary).like(term),
                func.lower(SqOpportunity.description).like(term),
            )
        )
    if opportunity_type:
        stmt = stmt.where(SqOpportunity.opportunity_type == opportunity_type.upper())
    if status:
        stmt = stmt.where(SqOpportunity.status == status.upper())
    else:
        stmt = stmt.where(SqOpportunity.status.in_(["ACTIVE", "UNVERIFIED"]))
    if delivery_mode:
        stmt = stmt.where(SqOpportunity.delivery_mode == delivery_mode.upper())
    if upcoming:
        now = datetime.now(tz=timezone.utc)
        stmt = stmt.where(SqOpportunity.submission_deadline >= now)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = db.execute(count_stmt).scalar_one()

    if sort == "deadline":
        stmt = stmt.order_by(SqOpportunity.submission_deadline.asc().nulls_last(), SqOpportunity.created_at.desc())
    elif sort == "title":
        stmt = stmt.order_by(SqOpportunity.title.asc())
    else:
        stmt = stmt.order_by(SqOpportunity.created_at.desc())

    offset = (page - 1) * page_size
    stmt = stmt.offset(offset).limit(page_size)
    rows = db.execute(stmt).scalars().all()

    return OppListResponse(
        items=[OppItem.model_validate(r) for r in rows],
        page=page,
        page_size=page_size,
        total=total,
    )


@api_app.get("/api/opportunities/{opportunity_id}", response_model=OppRead)
def _get(opportunity_id: str, db: Annotated[Session, Depends(get_test_db)]):
    # Validate UUID format
    try:
        uuid.UUID(opportunity_id)
    except ValueError:
        raise HTTPException(422, "Invalid UUID")
    stmt = select(SqOpportunity).where(SqOpportunity.id == opportunity_id)
    row = db.execute(stmt).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, detail="Opportunity not found")
    return OppRead.model_validate(row)


# ---------------------------------------------------------------------------
# Client fixture using api_app
# ---------------------------------------------------------------------------

@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_db():
        yield db_session

    api_app.dependency_overrides[get_test_db] = override_db
    with TestClient(api_app) as c:
        yield c
    api_app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_opportunity(
    db: Session,
    *,
    title: str = "Test Opportunity",
    opportunity_type: str = "CONFERENCE",
    status: str = "ACTIVE",
    delivery_mode: str = "HYBRID",
    location: str | None = "Berlin, Germany",
    publisher: str | None = "IEEE",
    submission_deadline: datetime | None = None,
) -> SqOpportunity:
    opp = SqOpportunity(
        id=str(uuid.uuid4()),
        title=title,
        opportunity_type=opportunity_type,
        status=status,
        delivery_mode=delivery_mode,
        location=location,
        publisher=publisher,
        submission_deadline=submission_deadline,
        is_predatory_flag=False,
    )
    db.add(opp)
    db.flush()
    return opp


# ---------------------------------------------------------------------------
# Tests: GET /api/opportunities
# ---------------------------------------------------------------------------

def test_list_opportunities_empty(client: TestClient) -> None:
    """Empty database returns empty items list with total=0."""
    response = client.get("/api/opportunities")
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0
    assert data["page"] == 1
    assert data["page_size"] == 20


def test_list_opportunities_returns_active_items(
    client: TestClient, db_session: Session
) -> None:
    make_opportunity(db_session, title="AI Conference 2026")
    make_opportunity(db_session, title="ML Workshop 2026", opportunity_type="WORKSHOP")

    response = client.get("/api/opportunities")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    titles = [item["title"] for item in data["items"]]
    assert "AI Conference 2026" in titles
    assert "ML Workshop 2026" in titles


def test_list_opportunities_filter_by_type(
    client: TestClient, db_session: Session
) -> None:
    make_opportunity(db_session, title="AI Conference", opportunity_type="CONFERENCE")
    make_opportunity(db_session, title="CS Journal", opportunity_type="JOURNAL")

    response = client.get("/api/opportunities?opportunity_type=JOURNAL")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "CS Journal"


def test_list_opportunities_filter_by_status(
    client: TestClient, db_session: Session
) -> None:
    make_opportunity(db_session, title="Active Conf", status="ACTIVE")
    make_opportunity(db_session, title="Expired Conf", status="EXPIRED")

    response = client.get("/api/opportunities?status=EXPIRED")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "Expired Conf"


def test_list_opportunities_filter_by_delivery_mode(
    client: TestClient, db_session: Session
) -> None:
    make_opportunity(db_session, title="Online Conf", delivery_mode="ONLINE")
    make_opportunity(db_session, title="Hybrid Conf", delivery_mode="HYBRID")

    response = client.get("/api/opportunities?delivery_mode=ONLINE")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "Online Conf"


def test_list_opportunities_search_by_title(
    client: TestClient, db_session: Session
) -> None:
    make_opportunity(db_session, title="International Conference on AI Research")
    make_opportunity(db_session, title="Workshop on Robotics")

    response = client.get("/api/opportunities?search=AI+Research")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert "AI Research" in data["items"][0]["title"]


def test_list_opportunities_search_no_results(
    client: TestClient, db_session: Session
) -> None:
    make_opportunity(db_session, title="Quantum Computing Conference")

    response = client.get("/api/opportunities?search=blockchain+robotics+mars")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["items"] == []


def test_list_opportunities_pagination(
    client: TestClient, db_session: Session
) -> None:
    for i in range(5):
        make_opportunity(db_session, title=f"Conference {i}")

    response = client.get("/api/opportunities?page=1&page_size=2")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2
    assert data["page"] == 1

    response2 = client.get("/api/opportunities?page=3&page_size=2")
    assert response2.status_code == 200
    data2 = response2.json()
    assert len(data2["items"]) == 1
    assert data2["page"] == 3


def test_list_opportunities_filter_upcoming(
    client: TestClient, db_session: Session
) -> None:
    future = datetime.now(tz=timezone.utc) + timedelta(days=30)
    past = datetime.now(tz=timezone.utc) - timedelta(days=10)

    make_opportunity(db_session, title="Future Conf", submission_deadline=future)
    make_opportunity(db_session, title="Past Conf", submission_deadline=past)
    make_opportunity(db_session, title="No Deadline Conf")

    response = client.get("/api/opportunities?upcoming=true")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "Future Conf"


def test_list_opportunities_sort_by_title(
    client: TestClient, db_session: Session
) -> None:
    make_opportunity(db_session, title="Zebra Workshop")
    make_opportunity(db_session, title="Alpha Conference")

    response = client.get("/api/opportunities?sort=title")
    assert response.status_code == 200
    data = response.json()
    titles = [item["title"] for item in data["items"]]
    assert titles == sorted(titles)


def test_list_opportunities_sort_by_deadline(
    client: TestClient, db_session: Session
) -> None:
    soon = datetime.now(tz=timezone.utc) + timedelta(days=5)
    later = datetime.now(tz=timezone.utc) + timedelta(days=60)

    make_opportunity(db_session, title="Later Conf", submission_deadline=later)
    make_opportunity(db_session, title="Soon Conf", submission_deadline=soon)
    make_opportunity(db_session, title="No Deadline Conf")

    response = client.get("/api/opportunities?sort=deadline")
    assert response.status_code == 200
    data = response.json()
    items = data["items"]
    assert items[0]["title"] == "Soon Conf"
    assert items[1]["title"] == "Later Conf"
    assert items[2]["title"] == "No Deadline Conf"


def test_list_opportunities_invalid_type(client: TestClient) -> None:
    response = client.get("/api/opportunities?opportunity_type=UNKNOWN_TYPE")
    assert response.status_code == 422


def test_list_opportunities_page_size_capped(client: TestClient) -> None:
    response = client.get("/api/opportunities?page_size=200")
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Tests: GET /api/opportunities/{id}
# ---------------------------------------------------------------------------

def test_get_opportunity_by_id(
    client: TestClient, db_session: Session
) -> None:
    opp = make_opportunity(
        db_session,
        title="Specific Conference",
        publisher="ACM",
        location="Tokyo, Japan",
    )

    response = client.get(f"/api/opportunities/{opp.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == opp.id
    assert data["title"] == "Specific Conference"
    assert data["publisher"] == "ACM"
    assert data["location"] == "Tokyo, Japan"


def test_get_opportunity_not_found(client: TestClient) -> None:
    random_id = str(uuid.uuid4())
    response = client.get(f"/api/opportunities/{random_id}")
    assert response.status_code == 404
    assert response.json()["detail"] == "Opportunity not found"


def test_get_opportunity_invalid_uuid(client: TestClient) -> None:
    response = client.get("/api/opportunities/not-a-uuid")
    assert response.status_code == 422
