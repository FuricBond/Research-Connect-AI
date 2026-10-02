"""
End-to-end pipeline tests for the OpenAlex ingestion pipeline.

Mocks both HTTP (no API calls) and the database (no PostgreSQL required).
Tests the entire flow: Fetch → Normalise → Validate → Persist.
"""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_FIXTURES = Path(__file__).parent / "fixtures" / "openalex"


def load_fixture(name: str) -> dict:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


def page(results: list[dict], cursor: str = "*", next_cursor: str | None = None):
    from scrapers.openalex.client import WorksPage

    return WorksPage(results=results, cursor=cursor, next_cursor=next_cursor, total_count=None)


def mock_source(pages: list, error: BaseException | None = None) -> MagicMock:
    """An OpenAlexSource double whose iter_work_pages yields *pages*, then raises *error*."""

    def iter_work_pages(**_kwargs):
        yield from pages
        if error is not None:
            raise error

    source = MagicMock()
    source.iter_work_pages.side_effect = iter_work_pages
    return source


class TestOpenAlexPipeline:
    """Test the collect_openalex pipeline in dry-run mode (no DB needed)."""

    def test_dry_run_with_valid_works(self):
        """Dry-run should parse and validate works without touching the DB."""
        from scrapers.pipelines.collect_openalex import run_pipeline

        page_data = load_fixture("search_results_page1.json")
        page_data["meta"]["next_cursor"] = None  # Single page

        with patch("scrapers.pipelines.collect_openalex.OpenAlexSource") as MockSource:
            MockSource.return_value = mock_source([page(page_data["results"])])

            stats = run_pipeline(
                search="open access",
                max_pages=1,
                per_page=25,
                dry_run=True,
            )

        assert stats["parsed"] == 2
        assert stats["valid"] >= 1
        # No DB writes in dry-run
        assert stats["inserted"] == 0
        assert stats["updated"] == 0

    def test_dry_run_empty_results(self):
        """Empty search results should produce all-zero stats cleanly."""
        from scrapers.pipelines.collect_openalex import run_pipeline

        with patch("scrapers.pipelines.collect_openalex.OpenAlexSource") as MockSource:
            MockSource.return_value = mock_source([])

            stats = run_pipeline(
                search="xyzzy_nothing_matches",
                max_pages=1,
                dry_run=True,
            )

        assert stats["parsed"] == 0
        assert stats["valid"] == 0
        assert stats["invalid"] == 0

    def test_dry_run_skips_invalid_works(self):
        """Works that fail normalisation should be counted as invalid."""
        from scrapers.pipelines.collect_openalex import run_pipeline

        malformed = load_fixture("work_malformed.json")

        with patch("scrapers.pipelines.collect_openalex.OpenAlexSource") as MockSource:
            MockSource.return_value = mock_source([page([malformed])])

            stats = run_pipeline(
                search="test",
                max_pages=1,
                dry_run=True,
            )

        assert stats["invalid"] == 1
        assert stats["valid"] == 0

    def test_normalizer_integrated_with_abstract_reconstruction(self):
        """Abstract should be reconstructed from inverted index during pipeline."""
        from scrapers.openalex.normalizer import normalize_work

        raw = load_fixture("work_inverted_index.json")
        work = normalize_work(raw)
        assert work.abstract == "Machine learning is transforming research."

    def test_pipeline_dry_run_returns_sample_stats(self):
        """Stats dict should contain all expected keys."""
        from scrapers.pipelines.collect_openalex import run_pipeline

        with patch("scrapers.pipelines.collect_openalex.OpenAlexSource") as MockSource:
            MockSource.return_value = mock_source([])

            stats = run_pipeline(search="AI", dry_run=True)

        expected_keys = {"source", "search", "pages_fetched", "parsed", "valid", "invalid", "inserted", "updated", "unchanged", "errors"}
        assert expected_keys.issubset(set(stats.keys()))


class TestPipelineNormalizeValidateCycle:
    """Unit-level tests for the normalise→validate cycle used inside the pipeline."""

    def test_normal_work_passes_all_stages(self):
        from scrapers.openalex.normalizer import normalize_work
        from scrapers.openalex.validator import validate_work

        raw = load_fixture("work_normal.json")
        work = normalize_work(raw)
        is_valid, errors = validate_work(work)
        assert is_valid is True
        assert errors == []

    def test_no_abstract_work_passes_validation(self):
        from scrapers.openalex.normalizer import normalize_work
        from scrapers.openalex.validator import validate_work

        raw = load_fixture("work_no_abstract.json")
        work = normalize_work(raw)
        is_valid, errors = validate_work(work)
        assert is_valid is True

    def test_multi_author_work_full_cycle(self):
        from scrapers.openalex.normalizer import normalize_work
        from scrapers.openalex.validator import validate_work

        raw = load_fixture("work_multi_author.json")
        work = normalize_work(raw)
        is_valid, _ = validate_work(work)
        assert is_valid is True
        assert len(work.authorships) == 3


class FakeRepository:
    """Stands in for OpenAlexRepository and records what the pipeline persists."""

    def __init__(self, interrupt_on_page: int | None = None) -> None:
        self.interrupt_on_page = interrupt_on_page
        self.saved_pages: list[list[str]] = []
        self.finished: dict | None = None
        self.discarded = False

    def start_run(self, label):
        import uuid

        from scrapers.persistence.openalex_repo import OpenAlexPersistenceResult

        self.label = label
        result = OpenAlexPersistenceResult()
        result.run_id = uuid.uuid4()
        return result

    def save_page(self, works, result, now=None):
        if self.interrupt_on_page == len(self.saved_pages) + 1:
            raise KeyboardInterrupt
        self.saved_pages.append([w.openalex_id for w in works])
        result.works_inserted += len(works)

    def finish_run(self, result, **kwargs):
        self.finished = kwargs

    def discard_page(self):
        self.discarded = True


class TestStreamingBulkLoad:
    """A bulk load saves page by page and can always be resumed where it stopped."""

    def _run(self, source, repo, **kwargs):
        from scrapers.pipelines.collect_openalex import run_pipeline

        with (
            patch("scrapers.pipelines.collect_openalex.OpenAlexSource", return_value=source),
            patch(
                "scrapers.pipelines.collect_openalex._open_repository",
                return_value=(MagicMock(), repo),
            ),
        ):
            return run_pipeline(**kwargs)

    def test_each_page_is_saved_as_it_arrives(self):
        work = load_fixture("work_normal.json")
        source = mock_source([page([work], next_cursor="c2"), page([work], cursor="c2")])
        repo = FakeRepository()

        stats = self._run(source, repo, search="ir", max_pages=5, per_page=1)

        assert len(repo.saved_pages) == 2
        assert stats["inserted"] == 2
        assert stats["next_cursor"] is None  # every matching work was fetched
        assert stats["stopped_reason"] is None
        assert repo.finished["pages_fetched"] == 2
        assert repo.finished["error_message"] is None

    def test_budget_exhaustion_keeps_saved_pages_and_reports_the_resume_cursor(self):
        from scrapers.openalex.client import OpenAlexBudgetExhaustedError

        work = load_fixture("work_normal.json")
        source = mock_source(
            [page([work], next_cursor="c2")], error=OpenAlexBudgetExhaustedError(3600)
        )
        repo = FakeRepository()

        stats = self._run(source, repo, subfield="1702", max_pages=10, per_page=1)

        assert len(repo.saved_pages) == 1
        assert stats["inserted"] == 1
        assert "budget" in stats["stopped_reason"]
        assert stats["next_cursor"] == "c2"
        assert "budget" in repo.finished["error_message"]

    def test_interrupt_discards_only_the_page_in_flight(self):
        work = load_fixture("work_normal.json")
        source = mock_source([page([work], next_cursor="c2"), page([work], cursor="c2", next_cursor="c3")])
        repo = FakeRepository(interrupt_on_page=2)

        stats = self._run(source, repo, search="ir", max_pages=5, per_page=1)

        assert repo.saved_pages and len(repo.saved_pages) == 1
        assert repo.discarded is True
        assert stats["stopped_reason"] == "interrupted"
        assert stats["next_cursor"] == "c2"  # page 2 was not saved, so resume at it

    def test_resume_cursor_is_passed_to_openalex(self):
        source = mock_source([])
        self._run(source, FakeRepository(), subfield="1702", cursor="c42")

        assert source.iter_work_pages.call_args.kwargs["start_cursor"] == "c42"

    def test_subfield_load_selects_with_filters_instead_of_search(self):
        from scrapers.pipelines.collect_openalex import run_pipeline

        source = mock_source([])
        with patch("scrapers.pipelines.collect_openalex.OpenAlexSource", return_value=source):
            stats = run_pipeline(
                subfield="1702", has_abstract=True, from_year=2015,
                sort="cited_by_count:desc", dry_run=True,
            )

        kwargs = source.iter_work_pages.call_args.kwargs
        assert kwargs["search"] is None
        assert kwargs["sort"] == "cited_by_count:desc"
        assert "primary_topic.subfield.id:1702" in kwargs["filters"]
        assert "has_abstract:true" in kwargs["filters"]
        assert "from_publication_date:2015-01-01" in kwargs["filters"]
        assert stats["search"] is None

    def test_without_search_or_subfield_the_default_search_is_kept(self):
        from scrapers.pipelines.collect_openalex import DEFAULT_SEARCH, run_pipeline

        source = mock_source([])
        with patch("scrapers.pipelines.collect_openalex.OpenAlexSource", return_value=source):
            run_pipeline(dry_run=True)

        assert source.iter_work_pages.call_args.kwargs["search"] == DEFAULT_SEARCH

    def test_unreachable_database_fails_before_spending_any_budget(self):
        from scrapers.pipelines.collect_openalex import run_pipeline

        with (
            patch("scrapers.pipelines.collect_openalex.OpenAlexSource") as MockSource,
            patch(
                "scrapers.pipelines.collect_openalex._open_repository",
                side_effect=ConnectionError("database unreachable"),
            ),
        ):
            with pytest.raises(ConnectionError):
                run_pipeline(subfield="1702")

        MockSource.assert_not_called()


# ── Research refresh: stoppable, labelled, credentialed, update-only loads ────


def _openalex_id(raw: dict) -> str:
    from scrapers.openalex.normalizer import normalize_work

    return normalize_work(raw).openalex_id


class KnownWorksRepository(FakeRepository):
    """A FakeRepository whose research_works already holds ``known`` openalex ids."""

    def __init__(self, known: set[str]) -> None:
        super().__init__()
        self.known = known
        self.lookups: list[list[str]] = []

    def existing_work_ids(self, openalex_ids):
        self.lookups.append(list(openalex_ids))
        return {i for i in openalex_ids if i in self.known}


class TestResearchRefreshOptions:
    """The options the scheduled research refresh drives the loader with."""

    def _run(self, source, repo, **kwargs):
        return TestStreamingBulkLoad()._run(source, repo, **kwargs)

    def test_should_stop_ends_the_load_at_a_page_boundary(self):
        from scrapers.pipelines.collect_openalex import STOP_REQUESTED

        work = load_fixture("work_normal.json")
        source = mock_source(
            [page([work], next_cursor="c2"), page([work], cursor="c2", next_cursor="c3")]
        )
        repo = FakeRepository()
        calls: list[int] = []

        def should_stop() -> bool:
            calls.append(len(repo.saved_pages))
            return True

        stats = self._run(source, repo, subfield="1702", max_pages=5, per_page=1, should_stop=should_stop)

        assert calls == [1], "checked once, after the first page was saved"
        assert len(repo.saved_pages) == 1
        assert stats["stopped_reason"] == STOP_REQUESTED
        assert stats["next_cursor"] == "c2", "resume after the saved page"
        assert repo.finished is not None and repo.finished["error_message"] == STOP_REQUESTED
        source.close.assert_called_once()

    def test_should_stop_returning_false_lets_the_load_finish(self):
        work = load_fixture("work_normal.json")
        source = mock_source([page([work], next_cursor="c2"), page([work], cursor="c2")])
        repo = FakeRepository()

        stats = self._run(source, repo, subfield="1702", max_pages=5, per_page=1, should_stop=lambda: False)

        assert len(repo.saved_pages) == 2
        assert stats["stopped_reason"] is None

    def test_run_label_names_the_ingestion_run(self):
        repo = FakeRepository()
        self._run(mock_source([]), repo, subfield="1702", run_label="research_refresh:new " + "x" * 300)
        assert repo.label.startswith("research_refresh:new ")
        assert len(repo.label) == 255

    def test_without_run_label_the_search_or_filter_names_the_run(self):
        repo = FakeRepository()
        self._run(mock_source([]), repo, search="graph learning")
        assert repo.label == "graph learning"
        repo = FakeRepository()
        self._run(mock_source([]), repo, subfield="1702")
        assert repo.label == "filter:primary_topic.subfield.id:1702"

    def test_day_level_dates_reach_the_filters(self):
        from datetime import date

        source = mock_source([])
        self._run(source, FakeRepository(), subfield="1702", from_date="2026-09-25", to_date=date(2026, 10, 2))

        filters = source.iter_work_pages.call_args.kwargs["filters"]
        assert "from_publication_date:2026-09-25" in filters
        assert "to_publication_date:2026-10-02" in filters

    def test_api_key_and_email_reach_the_source(self):
        from scrapers.pipelines.collect_openalex import run_pipeline

        with patch("scrapers.pipelines.collect_openalex.OpenAlexSource") as MockSource:
            MockSource.return_value = mock_source([])
            run_pipeline(subfield="1702", dry_run=True, api_key="test-key-not-real", email="ops@example.org")

        assert MockSource.call_args.kwargs == {"api_key": "test-key-not-real", "email": "ops@example.org"}

    def test_without_credentials_the_source_falls_back_to_the_environment(self):
        from scrapers.pipelines.collect_openalex import run_pipeline

        with patch("scrapers.pipelines.collect_openalex.OpenAlexSource") as MockSource:
            MockSource.return_value = mock_source([])
            run_pipeline(subfield="1702", dry_run=True)

        assert MockSource.call_args.kwargs == {"api_key": None, "email": None}

    def test_a_budget_stop_is_flagged(self):
        from scrapers.openalex.client import OpenAlexBudgetExhaustedError

        work = load_fixture("work_normal.json")
        source = mock_source([page([work], next_cursor="c2")], error=OpenAlexBudgetExhaustedError(3600))

        stats = self._run(source, FakeRepository(), subfield="1702", max_pages=5, per_page=1)

        assert stats["budget_exhausted"] is True
        assert "budget" in stats["stopped_reason"]

    def test_other_stops_are_not_budget_stops(self):
        work = load_fixture("work_normal.json")
        stats = self._run(
            mock_source([page([work])], error=RuntimeError("boom")), FakeRepository(), subfield="1702"
        )
        assert stats["budget_exhausted"] is False
        stats = self._run(mock_source([]), FakeRepository(), subfield="1702")
        assert stats["budget_exhausted"] is False and stats["stopped_reason"] is None

    def test_an_error_carrying_the_api_key_is_redacted_everywhere(self, caplog):
        import requests

        secret = "secret-value"
        error = requests.ConnectionError(
            f"HTTPSConnectionPool(host='api.openalex.org', port=443): Max retries exceeded "
            f"with url: /works?filter=x&api_key={secret}&mailto=ops@example.org"
        )
        repo = FakeRepository()

        stats = self._run(mock_source([], error=error), repo, subfield="1702")

        assert stats["stopped_reason"].startswith("stopped on an error:")
        assert "api_key=***" in stats["stopped_reason"]
        assert secret not in stats["stopped_reason"]
        assert secret not in repo.finished["error_message"]
        assert secret not in caplog.text
        assert "ops@example.org" not in caplog.text

    def test_update_only_keeps_known_works_and_counts_the_rest(self):
        known_raw = load_fixture("work_normal.json")
        new_raw = load_fixture("work_multi_author.json")
        known_id, new_id = _openalex_id(known_raw), _openalex_id(new_raw)
        assert known_id != new_id
        repo = KnownWorksRepository({known_id})

        stats = self._run(
            mock_source([page([known_raw, new_raw])]), repo, subfield="1702", update_only=True
        )

        assert repo.saved_pages == [[known_id]]
        assert stats["skipped_new"] == 1
        assert repo.lookups == [[known_id, new_id]]

    def test_without_update_only_new_works_are_saved_and_nothing_is_looked_up(self):
        repo = KnownWorksRepository(set())
        stats = self._run(
            mock_source([page([load_fixture("work_normal.json")])]), repo, subfield="1702"
        )
        assert len(repo.saved_pages[0]) == 1
        assert stats["skipped_new"] == 0
        assert repo.lookups == []


class FakeLock:
    def __init__(self) -> None:
        self.released = 0

    def release(self) -> None:
        self.released += 1


class TestResearchLoadLockCli:
    """The CLI holds the research load lock for a live load and never for a dry run."""

    STATS = {"source": "OpenAlex", "inserted": 0}

    def test_a_busy_lock_exits_3_without_loading(self, monkeypatch):
        from scrapers.pipelines import collect_openalex, load_lock

        monkeypatch.setattr(load_lock, "acquire_research_lock", lambda: None)
        run = MagicMock(return_value=self.STATS)
        monkeypatch.setattr(collect_openalex, "run_pipeline", run)

        with pytest.raises(SystemExit) as exit_info:
            collect_openalex.main(["--subfield", "1702", "--pages", "1"])

        assert exit_info.value.code == 3
        run.assert_not_called()

    def test_the_lock_is_released_after_a_run(self, monkeypatch):
        from scrapers.pipelines import collect_openalex, load_lock

        lock = FakeLock()
        monkeypatch.setattr(load_lock, "acquire_research_lock", lambda: lock)
        run = MagicMock(return_value=self.STATS)
        monkeypatch.setattr(collect_openalex, "run_pipeline", run)

        collect_openalex.main(["--subfield", "1702", "--from-date", "2026-09-25", "--to-date", "2026-10-02"])

        run.assert_called_once()
        assert str(run.call_args.kwargs["from_date"]) == "2026-09-25"
        assert str(run.call_args.kwargs["to_date"]) == "2026-10-02"
        assert lock.released == 1

    def test_the_lock_is_released_when_the_load_fails(self, monkeypatch):
        from scrapers.pipelines import collect_openalex, load_lock

        lock = FakeLock()
        monkeypatch.setattr(load_lock, "acquire_research_lock", lambda: lock)
        monkeypatch.setattr(collect_openalex, "run_pipeline", MagicMock(side_effect=RuntimeError("db down")))

        with pytest.raises(SystemExit) as exit_info:
            collect_openalex.main(["--subfield", "1702"])

        assert exit_info.value.code == 1
        assert lock.released == 1

    def test_a_dry_run_takes_no_lock(self, monkeypatch):
        from scrapers.pipelines import collect_openalex, load_lock

        def no_lock_expected():
            raise AssertionError("a dry run must not take the research lock")

        monkeypatch.setattr(load_lock, "acquire_research_lock", no_lock_expected)
        run = MagicMock(return_value=self.STATS)
        monkeypatch.setattr(collect_openalex, "run_pipeline", run)

        collect_openalex.main(["--subfield", "1702", "--dry-run"])

        assert run.call_args.kwargs["dry_run"] is True

    @pytest.mark.parametrize(
        "argv",
        [
            ["--from-year", "2025", "--from-date", "2026-01-01"],
            ["--to-year", "2026", "--to-date", "2026-10-02"],
            ["--from-date", "2026-01-01,type:x"],
        ],
    )
    def test_conflicting_or_malformed_date_options_are_refused(self, argv, monkeypatch):
        from scrapers.pipelines import collect_openalex

        run = MagicMock(return_value=self.STATS)
        monkeypatch.setattr(collect_openalex, "run_pipeline", run)

        with pytest.raises(SystemExit) as exit_info:
            collect_openalex.main(["--subfield", "1702", "--dry-run", *argv])

        assert exit_info.value.code == 2
        run.assert_not_called()

    def test_acquire_research_lock_uses_the_research_refresh_job_lock(self, monkeypatch):
        from app.scheduler import locks
        from app.scheduler.jobs import RESEARCH_REFRESH
        from scrapers.pipelines.load_lock import acquire_research_lock

        backend = locks.LocalLockBackend()
        monkeypatch.setattr(locks, "lock_backend_for", lambda engine: backend)

        first = acquire_research_lock()
        assert first is not None
        assert acquire_research_lock() is None, "a second load must find the lock busy"
        assert backend.try_acquire(RESEARCH_REFRESH) is None, "it is the research_refresh job's lock"
        first.release()
        again = acquire_research_lock()
        assert again is not None
        again.release()
