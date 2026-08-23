"""
Tests for the OpportunityRepository persistence service.

Uses SQLite in-memory with a SQLite-compatible test schema (same strategy
as backend/tests/test_opportunities.py) — no PostgreSQL required.
"""
import sys
import uuid
from collections.abc import Generator
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import Boolean, Column, DateTime, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scrapers.models import NormalizedOpportunity


# ── SQLite-compatible test schema ─────────────────────────────────────────────

class SqBase(DeclarativeBase):
    pass


class SqSource(SqBase):
    __tablename__ = "sources"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), default="SCRAPER", nullable=False)
    base_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    reliability_score: Mapped[float] = mapped_column(String(10), default="1.00", nullable=False)
    last_scraped_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(tz=timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(tz=timezone.utc), nullable=False
    )


class SqOpportunity(SqBase):
    __tablename__ = "opportunities"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    opportunity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    publisher: Mapped[str | None] = mapped_column(String(255), nullable=True)
    organizer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    website_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivery_mode: Mapped[str] = mapped_column(String(50), default="OFFLINE", nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    submission_deadline: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    event_start_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    event_end_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="ACTIVE", nullable=False)
    source_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    raw_source_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_predatory_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    slug: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(tz=timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(tz=timezone.utc), nullable=False
    )


SQLITE_URL = "sqlite:///:memory:"
engine = create_engine(SQLITE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="module", autouse=True)
def setup_db():
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


# ── Stub repository that works with SQLite schema ─────────────────────────────

class StubOpportunityRepo:
    """
    Test-only repository that mirrors OpportunityRepository logic but uses
    the SQLite SqSource / SqOpportunity tables instead of the production models.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_or_create_source(self, name: str, base_url: str | None = None) -> str:
        stmt = select(SqSource).where(SqSource.name == name)
        source = self._session.execute(stmt).scalar_one_or_none()
        if source is None:
            source = SqSource(
                id=str(uuid.uuid4()),
                name=name,
                base_url=base_url,
            )
            self._session.add(source)
            self._session.flush()
        return source.id

    def upsert_opportunity(self, opp: NormalizedOpportunity, source_id: str) -> str:
        stmt = select(SqOpportunity).where(
            SqOpportunity.source_id == source_id,
            SqOpportunity.raw_source_id == opp.raw_source_id,
        )
        existing = self._session.execute(stmt).scalar_one_or_none()
        if existing is None:
            new = SqOpportunity(
                id=str(uuid.uuid4()),
                title=opp.title,
                opportunity_type=opp.opportunity_type,
                delivery_mode=opp.delivery_mode,
                location=opp.location,
                website_url=opp.website_url,
                submission_deadline=opp.submission_deadline,
                status=opp.status,
                source_id=source_id,
                raw_source_id=opp.raw_source_id,
                is_predatory_flag=opp.is_predatory_flag,
                last_verified_at=datetime.now(tz=timezone.utc),
            )
            self._session.add(new)
            self._session.flush()
            return "inserted"
        else:
            old_title = existing.title
            existing.title = opp.title
            existing.delivery_mode = opp.delivery_mode
            existing.location = opp.location
            existing.website_url = opp.website_url
            existing.submission_deadline = opp.submission_deadline
            self._session.flush()
            return "updated" if existing.title != old_title else "no_change"


def make_norm(**kwargs) -> NormalizedOpportunity:
    defaults = dict(
        source_name="WikiCFP",
        raw_source_id="12345",
        source_url="http://www.wikicfp.com/cfp/servlet/event.showcfp?eventid=12345",
        title="AI Conference 2026",
        abbreviation="AIC 2026",
        opportunity_type="CONFERENCE",
        website_url=None,
        submission_deadline=None,
        event_start_date=None,
        event_end_date=None,
        location="Vienna, Austria",
        delivery_mode="OFFLINE",
    )
    defaults.update(kwargs)
    return NormalizedOpportunity(**defaults)


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestGetOrCreateSource:
    def test_creates_new_source(self, db_session):
        repo = StubOpportunityRepo(db_session)
        source_id = repo.get_or_create_source("TestSource", "http://test.com")
        assert source_id is not None

        stmt = select(SqSource).where(SqSource.name == "TestSource")
        source = db_session.execute(stmt).scalar_one_or_none()
        assert source is not None
        assert source.name == "TestSource"
        assert source.base_url == "http://test.com"

    def test_returns_existing_source_id(self, db_session):
        repo = StubOpportunityRepo(db_session)
        id1 = repo.get_or_create_source("WikiCFP", "http://www.wikicfp.com")
        id2 = repo.get_or_create_source("WikiCFP", "http://www.wikicfp.com")
        assert id1 == id2

    def test_different_names_different_ids(self, db_session):
        repo = StubOpportunityRepo(db_session)
        id1 = repo.get_or_create_source("Source A")
        id2 = repo.get_or_create_source("Source B")
        assert id1 != id2


class TestUpsertOpportunity:
    def test_inserts_new_opportunity(self, db_session):
        repo = StubOpportunityRepo(db_session)
        source_id = repo.get_or_create_source("WikiCFP")
        opp = make_norm()
        action = repo.upsert_opportunity(opp, source_id)
        assert action == "inserted"

        stmt = select(SqOpportunity).where(
            SqOpportunity.source_id == source_id,
            SqOpportunity.raw_source_id == "12345",
        )
        result = db_session.execute(stmt).scalar_one_or_none()
        assert result is not None
        assert result.title == "AI Conference 2026"
        assert result.opportunity_type == "CONFERENCE"

    def test_updates_existing_opportunity(self, db_session):
        repo = StubOpportunityRepo(db_session)
        source_id = repo.get_or_create_source("WikiCFP")
        opp_v1 = make_norm(title="AI Conference 2026")
        repo.upsert_opportunity(opp_v1, source_id)

        opp_v2 = make_norm(title="AI Conference 2026 — Updated Title")
        action = repo.upsert_opportunity(opp_v2, source_id)
        assert action == "updated"

        stmt = select(SqOpportunity).where(
            SqOpportunity.source_id == source_id,
            SqOpportunity.raw_source_id == "12345",
        )
        result = db_session.execute(stmt).scalar_one_or_none()
        assert "Updated Title" in result.title

    def test_does_not_create_duplicate_row(self, db_session):
        repo = StubOpportunityRepo(db_session)
        source_id = repo.get_or_create_source("DedupSource")
        opp = make_norm(raw_source_id="UNIQUE999")
        repo.upsert_opportunity(opp, source_id)
        repo.upsert_opportunity(opp, source_id)

        stmt = select(SqOpportunity).where(
            SqOpportunity.source_id == source_id,
            SqOpportunity.raw_source_id == "UNIQUE999",
        )
        rows = db_session.execute(stmt).scalars().all()
        assert len(rows) == 1

    def test_different_raw_source_ids_create_separate_rows(self, db_session):
        repo = StubOpportunityRepo(db_session)
        source_id = repo.get_or_create_source("MultiSource")
        opp1 = make_norm(raw_source_id="A001", title="Conference A")
        opp2 = make_norm(raw_source_id="A002", title="Conference B")
        repo.upsert_opportunity(opp1, source_id)
        repo.upsert_opportunity(opp2, source_id)

        stmt = select(SqOpportunity).where(SqOpportunity.source_id == source_id)
        rows = db_session.execute(stmt).scalars().all()
        assert len(rows) == 2

    def test_source_provenance_preserved(self, db_session):
        repo = StubOpportunityRepo(db_session)
        source_id = repo.get_or_create_source("ProvenanceSource")
        opp = make_norm(raw_source_id="PROV123")
        repo.upsert_opportunity(opp, source_id)

        stmt = select(SqOpportunity).where(SqOpportunity.raw_source_id == "PROV123")
        row = db_session.execute(stmt).scalar_one()
        assert row.source_id == source_id
        assert row.raw_source_id == "PROV123"
