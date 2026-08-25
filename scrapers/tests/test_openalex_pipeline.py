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


class TestOpenAlexPipeline:
    """Test the collect_openalex pipeline in dry-run mode (no DB needed)."""

    def test_dry_run_with_valid_works(self):
        """Dry-run should parse and validate works without touching the DB."""
        from scrapers.pipelines.collect_openalex import run_pipeline

        page_data = load_fixture("search_results_page1.json")
        page_data["meta"]["next_cursor"] = None  # Single page

        mock_http = MagicMock()
        mock_http.get_json.return_value = page_data

        with patch("scrapers.sources.openalex.OpenAlexClient") as MockClient:
            instance = MockClient.return_value
            instance.iter_works_pages.return_value = iter([page_data["results"]])
            instance.__enter__ = lambda s: s
            instance.__exit__ = MagicMock(return_value=False)

            # Patch at the OpenAlexSource level
            with patch("scrapers.pipelines.collect_openalex.OpenAlexSource") as MockSource:
                mock_source_instance = MagicMock()
                mock_source_instance.fetch_works_pages.return_value = [page_data["results"]]
                MockSource.return_value = mock_source_instance

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
            mock_source_instance = MagicMock()
            mock_source_instance.fetch_works_pages.return_value = []
            MockSource.return_value = mock_source_instance

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
            mock_source_instance = MagicMock()
            mock_source_instance.fetch_works_pages.return_value = [[malformed]]
            MockSource.return_value = mock_source_instance

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
            mock_source_instance = MagicMock()
            mock_source_instance.fetch_works_pages.return_value = []
            MockSource.return_value = mock_source_instance

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
