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
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scrapers.change_detection.detector import detect_changes
from scrapers.expiration.manager import is_opportunity_expired
from scrapers.models import LifecycleAction, NormalizedOpportunity


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
    last_successful_scrape_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_failed_scrape_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    consecutive_failure_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_scrape_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
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
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    slug: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(tz=timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(tz=timezone.utc), nullable=False
    )


class SqIngestionRun(SqBase):
    __tablename__ = "ingestion_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="RUNNING", nullable=False)
    topic: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pages_fetched: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_parsed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_valid: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_invalid: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_inserted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_updated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_unchanged: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicates_detected: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    potential_duplicates_detected: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_expired: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(tz=timezone.utc), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


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
    the SQLite SqSource / SqOpportunity / SqIngestionRun tables.
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
                consecutive_failure_count=0,
                total_scrape_count=0,
            )
            self._session.add(source)
            self._session.flush()
        return source.id

    def upsert_opportunity(
        self,
        opp: NormalizedOpportunity,
        source_id: str,
        now: datetime | None = None,
    ) -> LifecycleAction:
        ref_time = now or datetime.now(tz=timezone.utc)
        stmt = select(SqOpportunity).where(
            SqOpportunity.source_id == source_id,
            SqOpportunity.raw_source_id == opp.raw_source_id,
        )
        existing = self._session.execute(stmt).scalar_one_or_none()

        is_expired = is_opportunity_expired(opp, ref_time)
        target_status = "EXPIRED" if is_expired else opp.status

        if existing is None:
            new = SqOpportunity(
                id=str(uuid.uuid4()),
                title=opp.title,
                opportunity_type=opp.opportunity_type,
                delivery_mode=opp.delivery_mode,
                location=opp.location,
                website_url=opp.website_url,
                submission_deadline=opp.submission_deadline,
                status=target_status,
                source_id=source_id,
                raw_source_id=opp.raw_source_id,
                is_predatory_flag=opp.is_predatory_flag,
                last_verified_at=ref_time,
                last_seen_at=ref_time,
            )
            self._session.add(new)
            self._session.flush()
            return LifecycleAction.EXPIRED if is_expired else LifecycleAction.NEW
        else:
            change_result = detect_changes(existing, opp)
            existing.last_seen_at = ref_time

            if is_expired and existing.status in {"ACTIVE", "UNVERIFIED"}:
                existing.status = "EXPIRED"
                change_result.has_changed = True

            if change_result.has_changed:
                for c in change_result.changes:
                    setattr(existing, c.field_name, c.new_value)
                existing.updated_at = ref_time
                existing.last_verified_at = ref_time
                self._session.flush()
                return LifecycleAction.UPDATED
            else:
                self._session.flush()
                return LifecycleAction.UNCHANGED

    def finish_run(self, source_id: str, success: bool, now: datetime | None = None) -> None:
        ref_time = now or datetime.now(tz=timezone.utc)
        stmt = select(SqSource).where(SqSource.id == source_id)
        source = self._session.execute(stmt).scalar_one_or_none()
        if source:
            source.last_scraped_at = ref_time
            source.total_scrape_count += 1
            if success:
                source.last_successful_scrape_at = ref_time
                source.consecutive_failure_count = 0
            else:
                source.last_failed_scrape_at = ref_time
                source.consecutive_failure_count += 1
            self._session.flush()


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
        status="ACTIVE",
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


class TestUpsertOpportunityLifecycle:
    def test_inserts_new_opportunity(self, db_session):
        repo = StubOpportunityRepo(db_session)
        source_id = repo.get_or_create_source("WikiCFP")
        opp = make_norm()
        action = repo.upsert_opportunity(opp, source_id)
        assert action == LifecycleAction.NEW

        stmt = select(SqOpportunity).where(
            SqOpportunity.source_id == source_id,
            SqOpportunity.raw_source_id == "12345",
        )
        result = db_session.execute(stmt).scalar_one_or_none()
        assert result is not None
        assert result.title == "AI Conference 2026"
        assert result.last_seen_at is not None

    def test_unchanged_opportunity_returns_unchanged_and_refreshes_last_seen(self, db_session):
        repo = StubOpportunityRepo(db_session)
        source_id = repo.get_or_create_source("WikiCFP")
        t1 = datetime(2026, 8, 24, 10, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 8, 24, 12, 0, 0, tzinfo=timezone.utc)

        opp = make_norm(title="Static Title")
        repo.upsert_opportunity(opp, source_id, now=t1)

        # Ingest identical record at t2
        action = repo.upsert_opportunity(opp, source_id, now=t2)
        assert action == LifecycleAction.UNCHANGED

        stmt = select(SqOpportunity).where(SqOpportunity.raw_source_id == "12345")
        row = db_session.execute(stmt).scalar_one()
        assert row.last_seen_at.replace(tzinfo=timezone.utc) == t2

    def test_updates_existing_opportunity_when_fields_change(self, db_session):
        repo = StubOpportunityRepo(db_session)
        source_id = repo.get_or_create_source("WikiCFP")
        opp_v1 = make_norm(title="AI Conference 2026", location="Vienna")
        repo.upsert_opportunity(opp_v1, source_id)

        opp_v2 = make_norm(title="AI Conference 2026 (Extended)", location="Prague")
        action = repo.upsert_opportunity(opp_v2, source_id)
        assert action == LifecycleAction.UPDATED

        stmt = select(SqOpportunity).where(SqOpportunity.raw_source_id == "12345")
        result = db_session.execute(stmt).scalar_one()
        assert result.title == "AI Conference 2026 (Extended)"
        assert result.location == "Prague"

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

    def test_expired_opportunity_ingested_as_expired(self, db_session):
        repo = StubOpportunityRepo(db_session)
        source_id = repo.get_or_create_source("WikiCFP")
        now = datetime(2026, 8, 24, 12, 0, 0, tzinfo=timezone.utc)
        opp = make_norm(
            raw_source_id="EXPIRED1",
            submission_deadline=datetime(2026, 8, 20, tzinfo=timezone.utc),
        )
        action = repo.upsert_opportunity(opp, source_id, now=now)
        assert action == LifecycleAction.EXPIRED

        stmt = select(SqOpportunity).where(SqOpportunity.raw_source_id == "EXPIRED1")
        row = db_session.execute(stmt).scalar_one()
        assert row.status == "EXPIRED"


class TestSourceHealthTracking:
    def test_successful_run_updates_metrics(self, db_session):
        repo = StubOpportunityRepo(db_session)
        source_id = repo.get_or_create_source("HealthSource")
        now = datetime(2026, 8, 24, 12, 0, 0, tzinfo=timezone.utc)

        repo.finish_run(source_id, success=True, now=now)

        stmt = select(SqSource).where(SqSource.id == source_id)
        source = db_session.execute(stmt).scalar_one()
        assert source.total_scrape_count == 1
        assert source.consecutive_failure_count == 0
        assert source.last_successful_scrape_at.replace(tzinfo=timezone.utc) == now

    def test_failed_run_increments_consecutive_failures(self, db_session):
        repo = StubOpportunityRepo(db_session)
        source_id = repo.get_or_create_source("FailureSource")
        now = datetime(2026, 8, 24, 12, 0, 0, tzinfo=timezone.utc)

        repo.finish_run(source_id, success=False, now=now)
        repo.finish_run(source_id, success=False, now=now)

        stmt = select(SqSource).where(SqSource.id == source_id)
        source = db_session.execute(stmt).scalar_one()
        assert source.total_scrape_count == 2
        assert source.consecutive_failure_count == 2
        assert source.last_failed_scrape_at.replace(tzinfo=timezone.utc) == now
