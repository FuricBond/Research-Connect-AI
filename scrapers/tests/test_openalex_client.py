"""
Tests for scrapers.openalex.client.OpenAlexClient.

All HTTP calls are mocked.  No live network access.
"""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scrapers.openalex.client import OpenAlexClient

_FIXTURES = Path(__file__).parent / "fixtures" / "openalex"


def load_fixture(name: str) -> dict:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


def make_mock_http_client(responses: list[dict]) -> MagicMock:
    """
    Build a fake HttpClient whose get_json() returns responses in sequence.
    """
    mock = MagicMock()
    mock.get_json.side_effect = list(responses)
    return mock


class TestOpenAlexClientPagination:
    def test_single_page_returns_results(self):
        page_data = load_fixture("search_results_page1.json")
        mock_client = make_mock_http_client([page_data])
        client = OpenAlexClient(http_client=mock_client)

        pages = list(client.iter_works_pages(search="open access", per_page=25, max_pages=1))

        assert len(pages) == 1
        assert len(pages[0]) == 2
        assert pages[0][0]["id"] == "https://openalex.org/W2741809807"

    def test_empty_results_stops_pagination(self):
        empty_data = load_fixture("search_results_empty.json")
        mock_client = make_mock_http_client([empty_data])
        client = OpenAlexClient(http_client=mock_client)

        pages = list(client.iter_works_pages(search="nothing matches", max_pages=5))
        assert pages == []
        assert mock_client.get_json.call_count == 1

    def test_no_next_cursor_stops_early(self):
        page1 = load_fixture("search_results_page1.json")
        # Remove next_cursor to simulate last page
        page1_no_cursor = dict(page1)
        page1_no_cursor["meta"] = dict(page1["meta"])
        page1_no_cursor["meta"]["next_cursor"] = None

        mock_client = make_mock_http_client([page1_no_cursor])
        client = OpenAlexClient(http_client=mock_client)

        pages = list(client.iter_works_pages(search="test", max_pages=5))
        assert len(pages) == 1
        assert mock_client.get_json.call_count == 1

    def test_fetch_works_flattens_pages(self):
        page_data = load_fixture("search_results_page1.json")
        # Remove cursor so it stops after page 1
        page_data["meta"]["next_cursor"] = None
        mock_client = make_mock_http_client([page_data])
        client = OpenAlexClient(http_client=mock_client)

        works = client.fetch_works(search="open access", max_pages=2)
        assert len(works) == 2

    def test_email_added_to_params(self):
        page_data = load_fixture("search_results_empty.json")
        mock_client = make_mock_http_client([page_data])
        client = OpenAlexClient(email="test@example.com", http_client=mock_client)

        list(client.iter_works_pages(search="test"))
        call_kwargs = mock_client.get_json.call_args
        params = call_kwargs[1]["params"] if call_kwargs[1] else call_kwargs[0][1]
        assert params.get("mailto") == "test@example.com"


class TestOpenAlexClient429Handling:
    def test_429_retries_and_succeeds(self):
        """Client should back off and retry on 429, then succeed."""
        # Simulate 429 on first call, success on second
        rate_limit_error = requests.HTTPError(response=MagicMock(status_code=429))
        page_data = load_fixture("search_results_page1.json")
        page_data["meta"]["next_cursor"] = None

        mock_client = MagicMock()
        mock_client.get_json.side_effect = [rate_limit_error, page_data]

        client = OpenAlexClient(http_client=mock_client)

        with patch("scrapers.openalex.client.time.sleep"):
            pages = list(client.iter_works_pages(search="test", max_pages=1))

        assert len(pages) == 1
        assert mock_client.get_json.call_count == 2

    def test_persistent_429_gives_up_and_stops(self):
        """After max retries on 429, the generator should stop gracefully."""
        rate_limit_error = requests.HTTPError(response=MagicMock(status_code=429))
        mock_client = MagicMock()
        mock_client.get_json.side_effect = [rate_limit_error] * 10

        client = OpenAlexClient(http_client=mock_client)

        with patch("scrapers.openalex.client.time.sleep"):
            pages = list(client.iter_works_pages(search="test"))

        # Should return 0 pages (generator caught the exception)
        assert pages == []

    def test_500_propagates_as_http_error(self):
        """5xx errors are retried by HttpClient; if they persist, they stop pagination."""
        server_error = requests.HTTPError(response=MagicMock(status_code=500))
        mock_client = MagicMock()
        mock_client.get_json.side_effect = server_error

        client = OpenAlexClient(http_client=mock_client)
        pages = list(client.iter_works_pages(search="test"))
        assert pages == []


class TestOpenAlexClientSingleLookup:
    def test_get_author(self):
        author_data = load_fixture("author.json")
        mock_client = MagicMock()
        mock_client.get_json.return_value = author_data

        client = OpenAlexClient(http_client=mock_client)
        result = client.get_author("A5048491430")
        assert result["display_name"] == "Heather Piwowar"

    def test_get_author_accepts_full_url(self):
        author_data = load_fixture("author.json")
        mock_client = MagicMock()
        mock_client.get_json.return_value = author_data

        client = OpenAlexClient(http_client=mock_client)
        client.get_author("https://openalex.org/A5048491430")

        call_args = mock_client.get_json.call_args[0][0]
        assert call_args.endswith("/authors/A5048491430")

    def test_get_source(self):
        source_data = load_fixture("source.json")
        mock_client = MagicMock()
        mock_client.get_json.return_value = source_data

        client = OpenAlexClient(http_client=mock_client)
        result = client.get_source("S1983995261")
        assert result["display_name"] == "PeerJ"

    def test_get_institution(self):
        inst_data = load_fixture("institution.json")
        mock_client = MagicMock()
        mock_client.get_json.return_value = inst_data

        client = OpenAlexClient(http_client=mock_client)
        result = client.get_institution("I18014758")
        assert result["display_name"] == "Simon Fraser University"


class TestOpenAlexClientContextManager:
    def test_context_manager_calls_close(self):
        mock_client = MagicMock()
        mock_client.get_json.return_value = load_fixture("search_results_empty.json")
        with OpenAlexClient(http_client=mock_client):
            pass
        mock_client.close.assert_called_once()
