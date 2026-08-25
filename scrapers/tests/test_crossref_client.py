"""
Tests for scrapers.crossref.client.CrossrefClient.

All HTTP operations are mocked. No live network calls.
"""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
import requests

from scrapers.crossref.client import CrossrefClient

_FIXTURES = Path(__file__).parent / "fixtures" / "crossref"


def load_fixture(name: str) -> dict:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


def make_mock_http_client(responses: list[dict]) -> MagicMock:
    mock = MagicMock()
    mock.get_json.side_effect = list(responses)
    return mock


class TestCrossrefClientLookups:
    def test_get_work_by_doi_success(self):
        work_fixture = load_fixture("work_normal.json")
        mock_http = make_mock_http_client([work_fixture])
        client = CrossrefClient(http_client=mock_http)

        message = client.get_work_by_doi("10.7717/peerj.4375")
        assert message is not None
        assert message["DOI"] == "10.7717/peerj.4375"
        assert mock_http.get_json.call_count == 1

    def test_get_work_by_doi_404_returns_none(self):
        err = requests.HTTPError(response=MagicMock(status_code=404))
        mock_http = MagicMock()
        mock_http.get_json.side_effect = err
        client = CrossrefClient(http_client=mock_http)

        message = client.get_work_by_doi("10.1234/nonexistent")
        assert message is None

    def test_get_work_by_invalid_doi_returns_none(self):
        mock_http = MagicMock()
        client = CrossrefClient(http_client=mock_http)
        assert client.get_work_by_doi("not-a-doi") is None
        assert mock_http.get_json.call_count == 0


class TestCrossrefClientPagination:
    def test_iter_works_pages(self):
        results_fixture = load_fixture("query_results.json")
        mock_http = make_mock_http_client([results_fixture])
        client = CrossrefClient(http_client=mock_http)

        pages = list(client.iter_works_pages(query="machine learning", max_pages=1))
        assert len(pages) == 1
        assert len(pages[0]) == 2
        assert pages[0][0]["DOI"] == "10.7717/peerj.4375"

    def test_empty_results_stops_pagination(self):
        empty_fixture = load_fixture("query_empty.json")
        mock_http = make_mock_http_client([empty_fixture])
        client = CrossrefClient(http_client=mock_http)

        pages = list(client.iter_works_pages(query="nothing matches", max_pages=5))
        assert pages == []
        assert mock_http.get_json.call_count == 1


class TestCrossrefClient429Handling:
    def test_429_rate_limit_backoff_and_retry(self):
        rate_limit_err = requests.HTTPError(response=MagicMock(status_code=429))
        work_fixture = load_fixture("work_normal.json")

        mock_http = MagicMock()
        mock_http.get_json.side_effect = [rate_limit_err, work_fixture]
        client = CrossrefClient(http_client=mock_http)

        with patch("scrapers.crossref.client.time.sleep") as mock_sleep:
            message = client.get_work_by_doi("10.7717/peerj.4375")

        assert message is not None
        assert mock_http.get_json.call_count == 2
        assert mock_sleep.call_count == 1


class TestCrossrefClientContextManager:
    def test_context_manager_closes_client(self):
        mock_http = MagicMock()
        with CrossrefClient(http_client=mock_http) as client:
            pass
        mock_http.close.assert_called_once()
