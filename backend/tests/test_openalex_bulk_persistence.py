"""
OpenAlex bulk loading: the real OpenAlexRepository must keep every good work when one fails.

Loading tens of thousands of works means some records will not fit the schema (a value too
long for its column, a year outside the allowed range). Before, one such record rolled back
the whole batch, including every work saved before it, while the counters still reported
them as inserted. These tests run the real repository and ORM models on SQLite with
savepoints and foreign keys enforced, as PostgreSQL does.
"""
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (registers every table on Base.metadata)
from app.db.types import TSVector, Vector
from app.models.base import Base
from app.models.ingestion_run import IngestionRunModel
from app.models.research_knowledge import (
    ResearcherModel,
    ResearchWorkAuthorModel,
    ResearchWorkModel,
)
from scrapers.openalex.models import AuthorshipEntry, NormalizedResearcher, NormalizedWork
from scrapers.persistence.openalex_repo import OpenAlexRepository

compiles(JSONB, "sqlite")(lambda type_, compiler, **kw: "JSON")
compiles(Vector, "sqlite")(lambda type_, compiler, **kw: "TEXT")
compiles(TSVector, "sqlite")(lambda type_, compiler, **kw: "TEXT")

_TABLES = [
    "sources",
    "ingestion_runs",
    "research_sources",
    "researchers",
    "institutions",
    "research_works",
    "research_work_authors",
    "research_work_institutions",
]


@pytest.fixture
def session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # SQLAlchemy's documented recipe so pysqlite honours SAVEPOINT, plus foreign keys,
    # which SQLite leaves off unless asked.
    @event.listens_for(engine, "connect")
    def _connect(dbapi_connection, _record):
        dbapi_connection.isolation_level = None
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    @event.listens_for(engine, "begin")
    def _begin(connection):
        connection.exec_driver_sql("BEGIN")

    Base.metadata.create_all(engine, tables=[Base.metadata.tables[name] for name in _TABLES])
    db = sessionmaker(bind=engine)()
    yield db
    db.close()
    engine.dispose()


def work(openalex_id: str, *, year: int = 2020, authors: tuple[str, ...] = ()) -> NormalizedWork:
    return NormalizedWork(
        openalex_id=openalex_id,
        title=f"Paper {openalex_id}",
        publication_year=year,
        authorships=[
            AuthorshipEntry(
                researcher=NormalizedResearcher(openalex_id=author, display_name=f"Author {author}"),
                author_position="first",
            )
            for author in authors
        ],
    )


def unstorable(openalex_id: str, **kwargs) -> NormalizedWork:
    """A work the database refuses: its year breaks chk_research_works_year."""
    return work(openalex_id, year=5000, **kwargs)


def stored_ids(db: Session) -> set[str]:
    return set(db.execute(select(ResearchWorkModel.openalex_id)).scalars())


class TestOneBadWorkLosesOnlyItself:
    def test_batch_keeps_the_works_saved_before_and_after_a_failure(self, session):
        repo = OpenAlexRepository(session)

        result = repo.save_batch([work("W1"), unstorable("W2"), work("W3")], search_query="ir")

        assert stored_ids(session) == {"W1", "W3"}
        assert result.works_inserted == 2
        assert result.errors == 1

    def test_new_author_of_a_failed_work_is_inserted_again_for_the_next_work(self, session):
        repo = OpenAlexRepository(session)

        result = repo.save_batch(
            [unstorable("W1", authors=("A1",)), work("W2", authors=("A1",))],
            search_query="ir",
        )

        assert stored_ids(session) == {"W2"}
        assert result.errors == 1
        authors = session.execute(select(ResearcherModel.id, ResearcherModel.openalex_id)).all()
        assert [row.openalex_id for row in authors] == ["A1"]
        link = session.execute(select(ResearchWorkAuthorModel)).scalar_one()
        assert link.researcher_id == authors[0].id

    def test_the_run_record_survives_a_failed_work(self, session):
        repo = OpenAlexRepository(session)

        repo.save_batch([work("W1"), unstorable("W2")], search_query="ir")

        run = session.execute(select(IngestionRunModel)).scalar_one()
        assert run.status == "FAILED"  # a run with errors is never reported as clean
        assert run.records_inserted == 1


class TestOpenAlexDataQuirks:
    def test_an_author_listed_twice_on_a_work_is_linked_once(self, session):
        """OpenAlex sometimes lists one merged author twice; the work must still be saved."""
        repo = OpenAlexRepository(session)
        twice = work("W1", authors=("A1", "A2", "A1"))

        result = repo.save_batch([twice], search_query="ir")

        assert result.errors == 0
        assert stored_ids(session) == {"W1"}
        links = session.execute(select(ResearchWorkAuthorModel)).scalars().all()
        assert len(links) == 2


class TestPageByPage:
    def test_a_saved_page_is_committed(self, session):
        repo = OpenAlexRepository(session)
        result = repo.start_run("ir")

        repo.save_page([work("W1"), work("W2")], result)
        session.rollback()  # nothing a later failure rolls back can reach a saved page

        assert stored_ids(session) == {"W1", "W2"}

    def test_run_totals_add_up_across_pages(self, session):
        repo = OpenAlexRepository(session)
        result = repo.start_run("filter:primary_topic.subfield.id:1702")

        repo.save_page([work("W1"), work("W2")], result)
        repo.save_page([work("W2"), work("W3")], result)  # W2 again: unchanged
        repo.finish_run(result, pages_fetched=2, records_parsed=4, records_valid=4)

        assert (result.works_inserted, result.works_unchanged, result.errors) == (3, 1, 0)
        run = session.execute(select(IngestionRunModel)).scalar_one()
        assert run.status == "COMPLETED"
        assert (run.records_inserted, run.records_unchanged, run.pages_fetched) == (3, 1, 2)

    def test_a_page_that_cannot_commit_is_neither_kept_nor_counted(self, session, monkeypatch):
        repo = OpenAlexRepository(session)
        result = repo.start_run("ir")

        def refuse():
            raise ConnectionError("connection lost")

        monkeypatch.setattr(session, "commit", refuse)
        with pytest.raises(ConnectionError):
            repo.save_page([work("W1", authors=("A1",))], result)
        monkeypatch.undo()

        assert stored_ids(session) == set()
        assert result.works_inserted == 0
        # The cached author id died with the page; the next page must insert it again.
        repo.save_page([work("W2", authors=("A1",))], result)
        assert session.execute(select(func.count()).select_from(ResearcherModel)).scalar_one() == 1
        assert stored_ids(session) == {"W2"}

    def test_losing_the_database_mid_page_reports_the_original_error(self, session, monkeypatch):
        """When even the savepoint rollback fails, the cause is the lost connection."""
        repo = OpenAlexRepository(session)
        result = repo.start_run("ir")

        class DeadSavepoint:
            def commit(self):
                raise AssertionError("never reached")

            def rollback(self):
                raise RuntimeError("Can't reconnect until invalid transaction is rolled back")

        def connection_lost(*_args, **_kwargs):
            raise ConnectionError("terminating connection due to administrator command")

        monkeypatch.setattr(session, "begin_nested", DeadSavepoint)
        monkeypatch.setattr(repo, "upsert_work", connection_lost)

        with pytest.raises(ConnectionError, match="administrator command"):
            repo.save_page([work("W1")], result)
        assert result.errors == 0  # an outage is not a bad record

    def test_an_interrupted_page_is_discarded_and_its_ids_forgotten(self, session):
        repo = OpenAlexRepository(session)
        result = repo.start_run("ir")
        repo.save_page([work("W1")], result)

        repo.upsert_work(work("W2", authors=("A9",)), result.source_id, datetime.now(tz=timezone.utc))
        repo.discard_page()  # what the loader does on Ctrl+C mid-page

        assert stored_ids(session) == {"W1"}
        repo.save_page([work("W3", authors=("A9",))], result)
        assert stored_ids(session) == {"W1", "W3"}
