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
