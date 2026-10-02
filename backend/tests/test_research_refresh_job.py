"""
Research refresh (step 3/6) — scrapers.pipelines.refresh_research.

The unit tests replace the loader, topic processing, embedding and the corpus count, so they
make no request and need no database. The PostgreSQL test at the end runs the real job once
against a temporary database, with only the OpenAlex HTTP layer and the embedding model faked.
"""
from __future__ import annotations

import asyncio
from datetime import date
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

import numpy as np
import pytest

from app.core.config import settings
from app.scheduler.jobs import RESEARCH_REFRESH, build_default_jobs

TODAY = date(2026, 10, 2)
FIXTURES = Path(__file__).resolve().parents[2] / "scrapers" / "tests" / "fixtures" / "openalex"


def pass_stats(**overrides) -> dict:
    """What collect_openalex.run_pipeline returns for one pass."""
    stats = {
        "pages_fetched": 1,
        "parsed": 10,
        "valid": 9,
        "invalid": 1,
        "inserted": 5,
        "updated": 2,
        "unchanged": 2,
        "errors": 0,
        "skipped_new": 0,
        "run_id": str(uuid.uuid4()),
        "next_cursor": None,
        "stopped_reason": None,
        "budget_exhausted": False,
    }
    stats.update(overrides)
    return stats


class FakeService:
    model_name = "all-MiniLM-L6-v2"
    device = "cpu"


class Harness:
    """Replaces everything run_refresh calls and records what it was asked to do."""

    # The unpatched failure-alert hook, for the test that exercises it on a fake session.
    from scrapers.pipelines.refresh_research import _alert_on_repeated_failures as real_alert_hook
    real_alert_hook = staticmethod(real_alert_hook)

    def __init__(self, monkeypatch, *, corpus: int = 0, results=None) -> None:
        import ml.embeddings.generate_embeddings as embed_module
        import ml.embeddings.service as service_module
        import ml.topic_analysis.process_topics as topics_module
        import scrapers.pipelines.collect_openalex as collect_module
        import scrapers.pipelines.refresh_research as refresh_module

        self.module = refresh_module
        self.passes: list[dict] = []
        self.topic_calls = 0
        self.embed_calls: list[dict] = []
        self.results = list(results or [])
        self.corpus = corpus
        self.service = FakeService()

        def fake_pipeline(**kwargs):
            self.passes.append(kwargs)
            result = self.results.pop(0) if self.results else pass_stats()
            return result(kwargs) if callable(result) else result

        def fake_topics(**kwargs):
            self.topic_calls += 1
            return {"entities_processed": 7, "errors": 0}

        def fake_embed(**kwargs):
            from ml.embeddings.generate_embeddings import PipelineStats

            self.embed_calls.append(kwargs)
            return PipelineStats(total=6, embedded=6)

        monkeypatch.setattr(collect_module, "run_pipeline", fake_pipeline)
        monkeypatch.setattr(topics_module, "run_topic_processing", fake_topics)
        monkeypatch.setattr(embed_module, "run_pipeline", fake_embed)
        monkeypatch.setattr(service_module, "get_embedding_service", lambda: self.service)
        monkeypatch.setattr(refresh_module, "_corpus_size", lambda: self.corpus)
        # The failure alert opens its own session; unit tests never reach a real database.
        self.alerts: list[str] = []
        monkeypatch.setattr(refresh_module, "_alert_on_repeated_failures", self.alerts.append)

    def run(self, **overrides) -> dict:
        options = dict(
            subfields=("1702",),
            new_pages=2,
            rising_pages=3,
            new_window_days=14,
            rising_window_days=365,
            max_works=50_000,
            run_tag="tag1",
            today=TODAY,
        )
        options.update(overrides)
        return self.module.run_refresh(**options)

    @property
    def labels(self) -> list[str]:
        return [p["run_label"] for p in self.passes]


# ── Lanes ─────────────────────────────────────────────────────────────────────


def test_each_lane_selects_with_filters_dates_sort_and_pages(monkeypatch):
    harness = Harness(monkeypatch)
    stats = harness.run(api_key="test-key-not-real", email="ops@example.org")

    newest, rising = harness.passes
    assert newest == {
        "subfield": "1702",
        "has_abstract": True,
        "per_page": 200,
        "max_pages": 2,
        "sort": "publication_date:desc",
        "from_date": date(2026, 9, 18),
        "to_date": TODAY,
        "api_key": "test-key-not-real",
        "email": "ops@example.org",
        "should_stop": newest["should_stop"],
        "run_label": "research_refresh:tag1:newest:1702",
        "update_only": False,
    }
    assert rising["sort"] == "cited_by_count:desc"
    assert rising["max_pages"] == 3
    assert rising["from_date"] == date(2025, 10, 2) and rising["to_date"] == TODAY
    assert rising["run_label"] == "research_refresh:tag1:rising:1702"
    assert rising["update_only"] is False
    # Never a keyword search: it costs ten times a filter-only page.
    assert all("search" not in p for p in harness.passes)
    assert stats["passes_completed"] == 2 and stats["passes_failed"] == 0
    assert stats["stopped_reason"] is None


def test_new_pages_zero_skips_the_newest_lane(monkeypatch):
    harness = Harness(monkeypatch)
    harness.run(new_pages=0)
    assert harness.labels == ["research_refresh:tag1:rising:1702"]


def test_rising_pages_zero_skips_the_rising_lane(monkeypatch):
    harness = Harness(monkeypatch)
    harness.run(rising_pages=0)
    assert harness.labels == ["research_refresh:tag1:newest:1702"]


def test_subfields_run_in_order_newest_then_rising(monkeypatch):
    harness = Harness(monkeypatch)
    stats = harness.run(subfields=("1702", "1709"))
    assert harness.labels == [
        "research_refresh:tag1:newest:1702",
        "research_refresh:tag1:rising:1702",
        "research_refresh:tag1:newest:1709",
        "research_refresh:tag1:rising:1709",
    ]
    assert stats["subfields"] == ["1702", "1709"]
    assert stats["inserted"] == 20 and stats["updated"] == 8 and stats["pages_fetched"] == 4
    assert len(stats["run_ids"]) == 4


def test_a_run_tag_and_today_are_generated_when_not_given(monkeypatch):
    harness = Harness(monkeypatch)
    stats = harness.module.run_refresh(
        subfields=("1702",), new_pages=1, rising_pages=0, new_window_days=14,
        rising_window_days=365, max_works=50_000,
    )
    assert len(stats["run_tag"]) == 32
    assert harness.labels == [f"research_refresh:{stats['run_tag']}:newest:1702"]


# ── Outcomes ──────────────────────────────────────────────────────────────────


def test_a_spent_budget_ends_the_run_and_fails_every_remaining_pass(monkeypatch):
    budget = pass_stats(stopped_reason="OpenAlex daily usage budget exhausted.", budget_exhausted=True)
    harness = Harness(monkeypatch, results=[pass_stats(), budget])

    stats = harness.run(subfields=("1702", "1709"))

    assert len(harness.passes) == 2, "nothing runs after the budget is spent"
    assert stats["passes_completed"] == 1
    assert stats["passes_failed"] == 3  # this pass and the two for 1709
    assert stats["budget_exhausted"] is True
    assert stats["stopped_reason"] == "budget exhausted"
    # Local work still runs: the works already saved get topics and embeddings.
    assert harness.topic_calls == 1 and len(harness.embed_calls) == 1


def test_a_request_error_fails_only_that_pass(monkeypatch):
    failed = pass_stats(stopped_reason="stopped on an error: ConnectionError for /works?api_key=***")
    harness = Harness(monkeypatch, results=[pass_stats(), failed, pass_stats(), pass_stats()])

    stats = harness.run(subfields=("1702", "1709"))

    assert len(harness.passes) == 4
    assert stats["passes_completed"] == 3 and stats["passes_failed"] == 1
    assert stats["stopped_reason"] == "request failed"
    assert stats["budget_exhausted"] is False


def test_a_stop_request_ends_the_run_and_skips_topics_and_embeddings(monkeypatch):
    harness = Harness(monkeypatch)
    stop = {"now": False}

    def after_first_pass(kwargs):
        stop["now"] = True
        return pass_stats()

    harness.results = [after_first_pass]
    stats = harness.run(subfields=("1702", "1709"), should_stop=lambda: stop["now"])

    assert len(harness.passes) == 1
    assert stats["stopped_reason"] == "stop requested"
    assert stats["passes_failed"] == 0
    assert harness.topic_calls == 0 and harness.embed_calls == []


def test_a_stop_inside_a_pass_ends_the_run_without_a_failure(monkeypatch):
    from scrapers.pipelines.collect_openalex import STOP_REQUESTED

    harness = Harness(monkeypatch, results=[pass_stats(stopped_reason=STOP_REQUESTED)])
    stats = harness.run(subfields=("1702", "1709"))

    assert len(harness.passes) == 1
    assert stats["stopped_reason"] == "stop requested"
    assert stats["passes_completed"] == 0 and stats["passes_failed"] == 0
    assert harness.topic_calls == 0 and harness.embed_calls == []


def test_should_stop_is_checked_before_every_pass(monkeypatch):
    harness = Harness(monkeypatch)
    checks: list[int] = []

    def should_stop() -> bool:
        checks.append(len(harness.passes))
        return False

    harness.run(subfields=("1702", "1709"), should_stop=should_stop)
    for done in range(4):
        assert done in checks, f"should_stop was not checked before pass {done + 1}"


def test_at_the_corpus_cap_inserts_stop_and_refreshes_continue(monkeypatch):
    harness = Harness(monkeypatch, corpus=50_000)
    stats = harness.run(max_works=50_000)

    assert harness.labels == ["research_refresh:tag1:rising:1702"]
    assert harness.passes[0]["update_only"] is True
    assert stats["inserts_allowed"] is False and stats["corpus_size"] == 50_000


def test_below_the_cap_both_lanes_may_insert(monkeypatch):
    harness = Harness(monkeypatch, corpus=49_999)
    stats = harness.run(max_works=50_000)
    assert [p["update_only"] for p in harness.passes] == [False, False]
    assert stats["inserts_allowed"] is True


def test_topics_then_pending_embeddings_through_the_shared_service(monkeypatch):
    harness = Harness(monkeypatch)
    stats = harness.run()

    assert harness.topic_calls == 1
    (embed,) = harness.embed_calls
    assert embed == {
        "entity": "research_work",
        "model_name": FakeService.model_name,
        "batch_size": 32,
        "limit": None,
        "dry_run": False,
        "force": False,
        "device": FakeService.device,
        "pending_only": True,
        "embedding_service": harness.service,
    }
    assert stats["topics_processed"] == 7 and stats["embedded"] == 6


def test_stopped_reason_and_summary_never_carry_exception_text(monkeypatch):
    import ml.topic_analysis.process_topics as topics_module

    secret = "secret-value"
    failed = pass_stats(stopped_reason=f"stopped on an error: boom api_key={secret}")
    harness = Harness(monkeypatch, results=[failed])

    def broken_topics(**kwargs):
        raise RuntimeError(f"topic store down {secret}")

    monkeypatch.setattr(topics_module, "run_topic_processing", broken_topics)
    stats = harness.run(rising_pages=0)

    assert stats["stopped_reason"] == "request failed"
    assert stats["errors"] == 1  # the topic step failed and was counted
    assert secret not in str(stats)
    assert stats["stopped_reason"] in (None, "stop requested", "budget exhausted", "request failed")


def test_a_database_that_cannot_be_reached_raises_before_any_request(monkeypatch):
    harness = Harness(monkeypatch)

    def unreachable():
        raise ConnectionError("database unreachable")

    monkeypatch.setattr(harness.module, "_corpus_size", unreachable)
    with pytest.raises(ConnectionError):
        harness.run()
    assert harness.passes == []


def test_a_pass_that_cannot_start_after_a_request_fails_only_that_pass(monkeypatch):
    harness = Harness(monkeypatch)

    def second_cannot_start(kwargs):
        raise ConnectionError("database went away")

    harness.results = [pass_stats(), second_cannot_start]
    stats = harness.run()

    assert stats["passes_completed"] == 1 and stats["passes_failed"] == 1
    assert stats["stopped_reason"] == "request failed"


def test_importing_the_module_configures_nothing():
    probe = (
        "import logging, sys; before = list(sys.path); "
        "import scrapers.pipelines.refresh_research; "
        "print(sys.path == before, logging.getLogger().handlers == [], "
        "'scrapers.pipelines.collect_openalex' in sys.modules, 'app.db.session' in sys.modules)"
    )
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, timeout=120, cwd=str(root)
    )
    assert result.returncode == 0, result.stderr[-2000:]
    assert result.stdout.strip().splitlines()[-1] == "True True False False"


# ── Failure alert (step 4/6) ──────────────────────────────────────────────────


def test_when_every_pass_fails_the_admins_are_alerted(monkeypatch):
    failed = pass_stats(stopped_reason="stopped on an error: ConnectionError")
    harness = Harness(monkeypatch, results=[failed, failed])

    stats = harness.run()

    assert stats["passes_completed"] == 0 and stats["passes_failed"] == 2
    assert harness.alerts == ["tag1"]


def test_a_budget_stop_before_any_completed_pass_also_alerts(monkeypatch):
    budget = pass_stats(stopped_reason="budget", budget_exhausted=True)
    harness = Harness(monkeypatch, results=[budget])
    harness.run()
    assert harness.alerts == ["tag1"]


@pytest.mark.parametrize(
    "results",
    [
        [pass_stats(), pass_stats(stopped_reason="stopped on an error: x")],  # one pass completed
        [pass_stats(), pass_stats()],  # nothing failed
    ],
)
def test_no_alert_unless_every_pass_failed(monkeypatch, results):
    harness = Harness(monkeypatch, results=results)
    harness.run()
    assert harness.alerts == []


def test_a_stop_request_does_not_alert(monkeypatch):
    from scrapers.pipelines.collect_openalex import STOP_REQUESTED

    harness = Harness(monkeypatch, results=[pass_stats(stopped_reason=STOP_REQUESTED)])
    harness.run()
    assert harness.alerts == []


def test_an_alert_failure_never_fails_the_run(monkeypatch, caplog):
    from unittest.mock import MagicMock

    import app.db.session as session_module
    import app.services.ingestion_alert_service as alert_module
    import scrapers.pipelines.refresh_research as refresh_module

    harness = Harness(monkeypatch, results=[pass_stats(stopped_reason="stopped on an error: x")])
    # Put the real hook back, on a fake session, with an alert that raises.
    monkeypatch.setattr(refresh_module, "_alert_on_repeated_failures", Harness.real_alert_hook)
    monkeypatch.setattr(session_module, "SessionLocal", MagicMock())
    calls: list[str] = []

    def broken_alert(db, *, run_tag, **kwargs):
        calls.append(run_tag)
        raise RuntimeError("notifications table missing api_key=secret-value")

    monkeypatch.setattr(alert_module, "notify_admins_after_repeated_failures", broken_alert)

    stats = harness.run(rising_pages=0)

    assert calls == ["tag1"]
    assert stats["passes_failed"] == 1
    assert "could not alert the administrators (RuntimeError)" in caplog.text
    assert "secret-value" not in caplog.text


# ── CLI ───────────────────────────────────────────────────────────────────────


class FakeLock:
    def __init__(self) -> None:
        self.released = 0

    def release(self) -> None:
        self.released += 1


def test_the_cli_exits_3_while_the_lock_is_held(monkeypatch):
    import scrapers.pipelines.load_lock as load_lock
    import scrapers.pipelines.refresh_research as refresh_module

    monkeypatch.setattr(load_lock, "acquire_research_lock", lambda: None)
    monkeypatch.setattr(refresh_module, "run_refresh", lambda **kw: pytest.fail("refreshed without the lock"))

    assert refresh_module.main([]) == 3


def test_the_cli_runs_under_the_lock_and_releases_it(monkeypatch):
    import scrapers.pipelines.load_lock as load_lock
    import scrapers.pipelines.refresh_research as refresh_module

    lock = FakeLock()
    seen: list[dict] = []
    monkeypatch.setattr(load_lock, "acquire_research_lock", lambda: lock)
    monkeypatch.setattr(
        refresh_module, "run_refresh", lambda **kw: seen.append(kw) or {"passes_failed": 0, "inserted": 1}
    )

    code = refresh_module.main(["--subfields", " 1702, 1707,1702", "--new-pages", "0", "--max-works", "10"])

    assert code == 0 and lock.released == 1
    assert seen[0]["subfields"] == ("1702", "1707")
    assert seen[0]["new_pages"] == 0 and seen[0]["max_works"] == 10
    assert seen[0]["rising_pages"] == settings.research_refresh_rising_pages


def test_the_cli_exits_1_and_releases_the_lock_when_the_refresh_fails(monkeypatch):
    import scrapers.pipelines.load_lock as load_lock
    import scrapers.pipelines.refresh_research as refresh_module

    lock = FakeLock()
    monkeypatch.setattr(load_lock, "acquire_research_lock", lambda: lock)

    def broken(**kwargs):
        raise ConnectionError("database unreachable")

    monkeypatch.setattr(refresh_module, "run_refresh", broken)
    assert refresh_module.main([]) == 1
    assert lock.released == 1

    monkeypatch.setattr(refresh_module, "run_refresh", lambda **kw: {"passes_failed": 2})
    assert refresh_module.main([]) == 1
    assert lock.released == 2


def test_the_cli_refuses_malformed_subfields(monkeypatch):
    import scrapers.pipelines.load_lock as load_lock
    import scrapers.pipelines.refresh_research as refresh_module

    monkeypatch.setattr(load_lock, "acquire_research_lock", lambda: pytest.fail("locked before parsing"))
    with pytest.raises(SystemExit) as exit_info:
        refresh_module.main(["--subfields", "17.02"])
    assert exit_info.value.code == 2


# ── PostgreSQL: the real job against a temporary database ─────────────────────


def _postgres_available() -> bool:
    from sqlalchemy import create_engine, select

    try:
        probe = create_engine(settings.database_url, pool_pre_ping=True)
        with probe.connect() as connection:
            return connection.execute(select(1)).scalar_one() == 1
    except Exception:
        return False


class DeterministicEncoder:
    """A 384-dimension stand-in for the embedding model: same text, same unit vector."""

    model_name = "all-MiniLM-L6-v2"
    device = "cpu"

    def encode_batch(self, texts):
        vectors = []
        for text in texts:
            rng = np.random.default_rng(abs(hash(text)) % (2**32))
            vector = rng.standard_normal(384).astype(np.float32)
            vectors.append(vector / np.linalg.norm(vector))
        return np.vstack(vectors)


def _fixture_page() -> dict:
    works = [
        json.loads((FIXTURES / name).read_text(encoding="utf-8"))
        for name in ("work_normal.json", "work_multi_author.json", "work_inverted_index.json")
    ]
    return {"meta": {"count": len(works), "next_cursor": None}, "results": works}


@pytest.mark.postgres_integration
@pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_MIGRATION_TESTS") != "1" or not _postgres_available(),
    reason="set RUN_POSTGRES_MIGRATION_TESTS=1 to run tests that create an isolated PostgreSQL database",
)
def test_the_scheduled_job_loads_tags_and_embeds_new_works_without_duplicates(monkeypatch):
    import requests
    from sqlalchemy import create_engine, func, select, text
    from sqlalchemy.engine import make_url
    from sqlalchemy.orm import sessionmaker

    import app.db.session as session_module
    import ml.embeddings.generate_embeddings as embed_module
    import ml.embeddings.service as service_module
    from app.models.ingestion_run import IngestionRunModel
    from app.models.research_knowledge import ResearchWorkModel
    from app.scheduler.locks import PostgresAdvisoryLockBackend
    from app.scheduler.metrics import JobRunStatus
    from app.scheduler.scheduler import Scheduler
    from scrapers.http_client import HttpClient

    base = make_url(settings.database_url)
    name = f"researchconnect_refresh_{uuid.uuid4().hex[:10]}"
    admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    engine = None
    try:
        url = base.set(database=name)
        migrated = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=str(Path(__file__).resolve().parents[1]),
            env={**os.environ, "DATABASE_URL": url.render_as_string(hide_password=False)},
            capture_output=True,
            text=True,
        )
        assert migrated.returncode == 0, migrated.stderr[-2000:]
        engine = create_engine(url, pool_pre_ping=True)
        factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

        # Every session the refresh opens goes to the temporary database, never the main one.
        monkeypatch.setattr(session_module, "SessionLocal", factory)
        monkeypatch.setattr(session_module, "engine", engine)
        monkeypatch.setattr(embed_module, "SessionLocal", factory)
        assert factory.kw["bind"].url.database == name

        # Only the OpenAlex HTTP layer and the model are faked; nothing reaches the network.
        requests_seen: list[dict] = []

        def fake_get_json(self, url, *, timeout=None, params=None):
            requests_seen.append(dict(params or {}))
            return _fixture_page()

        def no_network(*args, **kwargs):
            raise AssertionError("the refresh tried to reach the network")

        monkeypatch.setattr(HttpClient, "get_json", fake_get_json)
        monkeypatch.setattr(requests.Session, "request", no_network)
        encoder = DeterministicEncoder()
        monkeypatch.setattr(service_module, "get_embedding_service", lambda: encoder)

        cfg = settings.model_copy(
            update={
                "scheduler_research_refresh_enabled": True,
                "research_refresh_subfields": "1702",
                "research_refresh_new_pages": 1,
                "research_refresh_rising_pages": 1,
                "openalex_api_key": "",
                "openalex_email": "",
            }
        )
        (job,) = [j for j in build_default_jobs(cfg) if j.name == RESEARCH_REFRESH]
        scheduler = Scheduler(
            [job],
            session_factory=factory,
            lock_backend=PostgresAdvisoryLockBackend(engine),
            startup_delay_seconds=0.0,
            stagger_seconds=0.0,
            cancel_grace_seconds=5.0,
            shutdown_timeout_seconds=5.0,
        )

        first = asyncio.run(scheduler.run_job_now(RESEARCH_REFRESH))
        assert first.status is JobRunStatus.SUCCEEDED, (first.status, first.error_type, first.details)
        assert len(requests_seen) == 2  # one page per lane
        assert all("search" not in params for params in requests_seen)
        assert "primary_topic.subfield.id:1702" in requests_seen[0]["filter"]

        with factory() as db:
            works = db.execute(select(ResearchWorkModel)).scalars().all()
            assert len(works) == 3
            assert all(w.embedding is not None and w.embedding_model == encoder.model_name for w in works)
            labels = sorted(
                db.execute(
                    select(IngestionRunModel.topic).where(
                        IngestionRunModel.topic.like("research_refresh:%")
                    )
                ).scalars()
            )
        assert labels == [
            f"research_refresh:{first.run_id}:newest:1702",
            f"research_refresh:{first.run_id}:rising:1702",
        ]
        assert first.details["inserted"] == 3
        assert first.details["embedded"] == 3
        assert first.details["errors"] == 0
        assert first.details["topics_processed"] >= 0  # topic processing ran without error

        second = asyncio.run(scheduler.run_job_now(RESEARCH_REFRESH))
        assert second.status is JobRunStatus.SUCCEEDED, (second.status, second.error_type, second.details)
        with factory() as db:
            total = db.execute(select(func.count()).select_from(ResearchWorkModel)).scalar_one()
            distinct = db.execute(
                select(func.count(func.distinct(ResearchWorkModel.openalex_id)))
            ).scalar_one()
        assert total == distinct == 3, "a second run must not duplicate works"
        assert second.details["inserted"] == 0
        assert second.details["embedded"] == 0, "nothing is pending the second time"
    finally:
        if engine is not None:
            engine.dispose()
        with admin.connect() as connection:
            connection.execute(
                text("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = :n"), {"n": name}
            )
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
        admin.dispose()
