"""
Tests for scrapers.pipelines.collect_crossref.

All tests use mocked Crossref source adapters and dry-run mode (no DB required).
"""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from scrapers.pipelines.collect_crossref import run_pipeline

_FIXTURES = Path(__file__).parent / "fixtures" / "crossref"


def load_fixture(name: str) -> dict:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


class TestCrossrefPipeline:
    def test_dry_run_single_doi(self):
        work_fixture = load_fixture("work_normal.json")["message"]

        with patch("scrapers.pipelines.collect_crossref.CrossrefSource") as MockSource:
            mock_inst = MagicMock()
            mock_inst.fetch_work_by_doi.return_value = work_fixture
            MockSource.return_value = mock_inst

            stats = run_pipeline(
                doi="10.7717/peerj.4375",
                dry_run=True,
            )

        assert stats["parsed"] == 1
        assert stats["valid"] == 1
        assert stats["invalid"] == 0
        assert stats["inserted"] == 0  # dry-run
        assert stats["enriched"] == 0

    def test_dry_run_query(self):
        items_fixture = load_fixture("query_results.json")["message"]["items"]

        with patch("scrapers.pipelines.collect_crossref.CrossrefSource") as MockSource:
            mock_inst = MagicMock()
            mock_inst.fetch_works_pages.return_value = [items_fixture]
            MockSource.return_value = mock_inst

            stats = run_pipeline(
                query="machine learning",
                max_pages=1,
                dry_run=True,
            )

        assert stats["parsed"] == 2
        assert stats["valid"] == 2
        assert stats["invalid"] == 0

    def test_dry_run_empty_query(self):
        with patch("scrapers.pipelines.collect_crossref.CrossrefSource") as MockSource:
            mock_inst = MagicMock()
            mock_inst.fetch_works_pages.return_value = []
            MockSource.return_value = mock_inst

            stats = run_pipeline(
                query="empty_query_result",
                dry_run=True,
            )

        assert stats["parsed"] == 0
        assert stats["valid"] == 0

    def test_dry_run_skips_malformed_item(self):
        malformed = load_fixture("work_malformed.json")

        with patch("scrapers.pipelines.collect_crossref.CrossrefSource") as MockSource:
            mock_inst = MagicMock()
            mock_inst.fetch_works_pages.return_value = [[malformed]]
            MockSource.return_value = mock_inst

            stats = run_pipeline(
                query="test",
                dry_run=True,
            )

        assert stats["parsed"] == 1
        assert stats["valid"] == 0
        assert stats["invalid"] == 1
