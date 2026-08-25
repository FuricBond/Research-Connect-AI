"""
Persistence and DOI matching unit tests for Crossref integration.

Uses an in-memory SQLite test database with a schema compatible with
PostgreSQL research knowledge models.
"""
import uuid
from datetime import datetime, timezone
from pathlib import Path
import pytest
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    Text,
    create_engine,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from scrapers.crossref.models import (
    NormalizedCrossrefAuthor,
    NormalizedCrossrefSource,
    NormalizedCrossrefWork,
)
from scrapers.models import LifecycleAction


# ── SQLite Test Models ────────────────────────────────────────────────────────


class SqBase(DeclarativeBase):
    pass


class SqSource(SqBase):
    __tablename__ = "sources"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), default="API", nullable=False)
    base_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    reliability_score: Mapped[float] = mapped_column(String(10), default="1.00", nullable=False)
    last_scraped_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_successful_scrape_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_failed_scrape_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    consecutive_failure_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_scrape_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(tz=timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(tz=timezone.utc))


class SqIngestionRun(SqBase):
    __tablename__ = "ingestion_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="RUNNING", nullable=False)
    topic: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    pages_fetched: Mapped[int] = mapped_column(Integer, default=0)
    records_parsed: Mapped[int] = mapped_column(Integer, default=0)
    records_valid: Mapped[int] = mapped_column(Integer, default=0)
    records_invalid: Mapped[int] = mapped_column(Integer, default=0)
    records_inserted: Mapped[int] = mapped_column(Integer, default=0)
    records_updated: Mapped[int] = mapped_column(Integer, default=0)
    records_unchanged: Mapped[int] = mapped_column(Integer, default=0)
    duplicates_detected: Mapped[int] = mapped_column(Integer, default=0)
    potential_duplicates_detected: Mapped[int] = mapped_column(Integer, default=0)
    records_expired: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metrics_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(tz=timezone.utc))


class SqResearcher(SqBase):
    __tablename__ = "researchers"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    openalex_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    orcid: Mapped[str | None] = mapped_column(String(50), nullable=True)
    works_count: Mapped[int] = mapped_column(Integer, default=0)
    cited_by_count: Mapped[int] = mapped_column(Integer, default=0)
    raw_metadata: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(tz=timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(tz=timezone.utc))


class SqResearchSource(SqBase):
    __tablename__ = "research_sources"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    openalex_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    issn_l: Mapped[str | None] = mapped_column(String(20), nullable=True)
    issn: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_oa: Mapped[bool] = mapped_column(Boolean, default=False)
    is_in_doaj: Mapped[bool] = mapped_column(Boolean, default=False)
    host_organization: Mapped[str | None] = mapped_column(Text, nullable=True)
    works_count: Mapped[int] = mapped_column(Integer, default=0)
    cited_by_count: Mapped[int] = mapped_column(Integer, default=0)
    homepage_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_metadata: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(tz=timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(tz=timezone.utc))


class SqResearchWork(SqBase):
    __tablename__ = "research_works"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    openalex_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    doi: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    publication_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    publication_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    work_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    cited_by_count: Mapped[int] = mapped_column(Integer, default=0)
    is_oa: Mapped[bool] = mapped_column(Boolean, default=False)
    oa_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    landing_page_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    volume: Mapped[str | None] = mapped_column(String(50), nullable=True)
    issue: Mapped[str | None] = mapped_column(String(50), nullable=True)
    page: Mapped[str | None] = mapped_column(String(50), nullable=True)
    article_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    license_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    primary_source_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    ingestion_source_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    raw_metadata: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(tz=timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(tz=timezone.utc))


class SqResearchWorkAuthor(SqBase):
    __tablename__ = "research_work_authors"
    work_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    researcher_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    author_position: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_corresponding: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(tz=timezone.utc))


# ── Stub Crossref Repository ──────────────────────────────────────────────────


class StubCrossrefRepository:
    """SQLite-compatible stub mirroring CrossrefRepository logic."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_or_create_source(self) -> str:
        stmt = select(SqSource).where(SqSource.name == "Crossref")
        existing = self._session.execute(stmt).scalar_one_or_none()
        if existing:
            return existing.id
        source = SqSource(
            id=str(uuid.uuid4()),
            name="Crossref",
            source_type="API",
            base_url="https://api.crossref.org",
            is_active=True,
            reliability_score=1.00,
        )
        self._session.add(source)
        self._session.flush()
        return source.id

    def upsert_or_match_source(self, src: NormalizedCrossrefSource, now: datetime) -> tuple[LifecycleAction, str]:
        existing = None
        if src.issn_l:
            stmt = select(SqResearchSource).where(SqResearchSource.issn_l == src.issn_l)
            existing = self._session.execute(stmt).scalar_one_or_none()

        if existing is None and src.title:
            stmt = select(SqResearchSource).where(SqResearchSource.display_name == src.title)
            existing = self._session.execute(stmt).scalar_one_or_none()

        if existing is None:
            new_source = SqResearchSource(
                id=str(uuid.uuid4()),
                openalex_id=None,
                display_name=src.title,
                source_type=src.source_type,
                issn_l=src.issn_l,
                host_organization=src.publisher,
                last_seen_at=now,
            )
            self._session.add(new_source)
            self._session.flush()
            return LifecycleAction.NEW, new_source.id

        existing.last_seen_at = now
        changed = False
        if not existing.host_organization and src.publisher:
            existing.host_organization = src.publisher
            changed = True
        self._session.flush()
        return (LifecycleAction.UPDATED if changed else LifecycleAction.UNCHANGED), existing.id

    def upsert_or_match_researcher(self, author: NormalizedCrossrefAuthor, now: datetime) -> tuple[LifecycleAction, str]:
        existing = None
        if author.orcid:
            stmt = select(SqResearcher).where(SqResearcher.orcid == author.orcid)
            existing = self._session.execute(stmt).scalar_one_or_none()

        if existing is None:
            new_r = SqResearcher(
                id=str(uuid.uuid4()),
                openalex_id=None,
                display_name=author.full_name,
                orcid=author.orcid,
                last_seen_at=now,
            )
            self._session.add(new_r)
            self._session.flush()
            return LifecycleAction.NEW, new_r.id

        existing.last_seen_at = now
        self._session.flush()
        return LifecycleAction.UNCHANGED, existing.id

    def upsert_or_enrich_work(self, work: NormalizedCrossrefWork, source_id: str, now: datetime) -> LifecycleAction:
        primary_source_id = None
        if work.source:
            _, primary_source_id = self.upsert_or_match_source(work.source, now)

        stmt = select(SqResearchWork).where(SqResearchWork.doi == work.doi)
        existing = self._session.execute(stmt).scalar_one_or_none()

        if existing is None:
            new_work = SqResearchWork(
                id=str(uuid.uuid4()),
                openalex_id=None,
                doi=work.doi,
                title=work.title,
                abstract=work.abstract,
                publication_year=work.publication_year,
                publication_date=work.publication_date,
                work_type=work.work_type,
                volume=work.volume,
                issue=work.issue,
                page=work.page,
                article_number=work.article_number,
                license_url=work.license_url,
                is_oa=work.is_oa,
                landing_page_url=work.url,
                primary_source_id=primary_source_id,
                ingestion_source_id=source_id,
                last_seen_at=now,
            )
            self._session.add(new_work)
            self._session.flush()
            return LifecycleAction.NEW

        # Existing record found: non-destructive enrichment
        existing.last_seen_at = now
        changed = False

        if not existing.abstract and work.abstract:
            existing.abstract = work.abstract
            changed = True
        if not existing.volume and work.volume:
            existing.volume = work.volume
            changed = True
        if not existing.issue and work.issue:
            existing.issue = work.issue
            changed = True
        if not existing.page and work.page:
            existing.page = work.page
            changed = True
        if not existing.license_url and work.license_url:
            existing.license_url = work.license_url
            changed = True
        if not existing.primary_source_id and primary_source_id:
            existing.primary_source_id = primary_source_id
            changed = True

        self._session.flush()
        return LifecycleAction.UPDATED if changed else LifecycleAction.UNCHANGED


# ── Pytest Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    SqBase.metadata.create_all(engine)
    SessionMaker = sessionmaker(bind=engine)
    sess = SessionMaker()
    yield sess
    sess.close()
    engine.dispose()


@pytest.fixture
def repo(session):
    return StubCrossrefRepository(session)


@pytest.fixture
def now():
    return datetime.now(tz=timezone.utc)


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestCrossrefMatchingAndEnrichment:
    def test_get_or_create_source(self, repo, session):
        source_id = repo.get_or_create_source()
        assert source_id is not None
        sources = session.execute(select(SqSource)).scalars().all()
        assert len(sources) == 1
        assert sources[0].name == "Crossref"

    def test_enrich_existing_openalex_work_by_doi(self, repo, session, now):
        source_id = repo.get_or_create_source()

        # 1. Pre-populate an OpenAlex work in DB with abstract and basic metadata
        openalex_work = SqResearchWork(
            id=str(uuid.uuid4()),
            openalex_id="W2741809807",
            doi="10.7717/peerj.4375",
            title="The state of OA: a large-scale analysis",
            abstract="Existing high quality OpenAlex abstract",
            publication_year=2018,
            volume=None,
            page=None,
            license_url=None,
            last_seen_at=now,
        )
        session.add(openalex_work)
        session.commit()

        # 2. Ingest matching work from Crossref with citation details
        crossref_work = NormalizedCrossrefWork(
            doi="10.7717/peerj.4375",
            title="The state of OA: a large-scale analysis",
            abstract="Short Crossref abstract snippet",
            volume="6",
            page="e4375",
            license_url="http://creativecommons.org/licenses/by/4.0/",
        )

        action = repo.upsert_or_enrich_work(crossref_work, source_id, now)
        assert action == LifecycleAction.UPDATED

        # 3. Verify enrichment behavior
        rows = session.execute(select(SqResearchWork)).scalars().all()
        assert len(rows) == 1  # No duplicate work created!
        work_row = rows[0]

        # Existing abstract preserved (not overwritten by shorter snippet)
        assert work_row.abstract == "Existing high quality OpenAlex abstract"
        # Enriched fields added
        assert work_row.volume == "6"
        assert work_row.page == "e4375"
        assert work_row.license_url == "http://creativecommons.org/licenses/by/4.0/"

    def test_insert_new_crossref_work_when_no_match(self, repo, session, now):
        source_id = repo.get_or_create_source()

        crossref_work = NormalizedCrossrefWork(
            doi="10.1093/oso/9780198828044.003.0003",
            title="Machine learning with sklearn",
            abstract="Chapter abstract.",
            publication_year=2019,
            publication_date="2019-11-28",
            volume=None,
            page="38-65",
            work_type="book-chapter",
        )

        action = repo.upsert_or_enrich_work(crossref_work, source_id, now)
        assert action == LifecycleAction.NEW

        rows = session.execute(select(SqResearchWork)).scalars().all()
        assert len(rows) == 1
        assert rows[0].doi == "10.1093/oso/9780198828044.003.0003"
        assert rows[0].openalex_id is None  # Born in Crossref!

    def test_idempotent_crossref_ingestion(self, repo, session, now):
        source_id = repo.get_or_create_source()
        work = NormalizedCrossrefWork(
            doi="10.1145/3318464.3389700",
            title="A Scalable Framework for Distributed Machine Learning",
            volume="1",
            page="10-20",
        )

        action1 = repo.upsert_or_enrich_work(work, source_id, now)
        assert action1 == LifecycleAction.NEW

        # Second run without changes -> UNCHANGED
        action2 = repo.upsert_or_enrich_work(work, source_id, now)
        assert action2 == LifecycleAction.UNCHANGED

        rows = session.execute(select(SqResearchWork)).scalars().all()
        assert len(rows) == 1

    def test_author_matching_by_orcid(self, repo, session, now):
        # 1. Existing researcher with ORCID
        existing_r = SqResearcher(
            id=str(uuid.uuid4()),
            openalex_id="A5048491430",
            display_name="Heather Piwowar",
            orcid="0000-0003-1613-5981",
            last_seen_at=now,
        )
        session.add(existing_r)
        session.commit()

        # 2. Crossref author with matching ORCID
        author = NormalizedCrossrefAuthor(
            full_name="H. Piwowar",
            orcid="0000-0003-1613-5981",
        )

        action, r_id = repo.upsert_or_match_researcher(author, now)
        assert action == LifecycleAction.UNCHANGED
        assert r_id == existing_r.id

        researchers = session.execute(select(SqResearcher)).scalars().all()
        assert len(researchers) == 1  # Reused existing researcher!

    def test_source_matching_by_issn(self, repo, session, now):
        existing_src = SqResearchSource(
            id=str(uuid.uuid4()),
            openalex_id="S1983995261",
            display_name="PeerJ",
            issn_l="2167-8359",
            host_organization=None,
            last_seen_at=now,
        )
        session.add(existing_src)
        session.commit()

        src = NormalizedCrossrefSource(
            title="PeerJ",
            issn_l="2167-8359",
            publisher="PeerJ, Inc.",
        )

        action, src_id = repo.upsert_or_match_source(src, now)
        assert action == LifecycleAction.UPDATED
        assert src_id == existing_src.id

        sources = session.execute(select(SqResearchSource)).scalars().all()
        assert len(sources) == 1
        assert sources[0].host_organization == "PeerJ, Inc."
