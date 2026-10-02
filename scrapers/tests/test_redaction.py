"""
Research refresh — the OpenAlex API key never reaches a log line.

requests and urllib3 put the full request URL, query string included, into their error
messages and DEBUG logs, so a key sent as ``?api_key=`` leaked wherever that text went.
"""
from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest
import requests

from scrapers.http_client import HttpClient, redact_secrets

SECRET = "secret-value"
URL = f"https://api.openalex.org/works?filter=has_abstract:true&api_key={SECRET}&mailto=me@example.org"


class TestRedactSecrets:
    def test_api_key_and_mailto_values_are_masked(self):
        assert redact_secrets(URL) == (
            "https://api.openalex.org/works?filter=has_abstract:true&api_key=***&mailto=***"
        )

    @pytest.mark.parametrize(
        "text",
        [
            f"HTTPSConnectionPool(host='api.openalex.org', port=443): Max retries exceeded "
            f"with url: /works?api_key={SECRET} (Caused by NewConnectionError)",
            f"404 Client Error: Not Found for url: https://api.openalex.org/works?API_KEY={SECRET}",
            f"'/works?api_key={SECRET}' failed",
            f'"GET /works?per-page=25&api_key={SECRET}&cursor=* HTTP/1.1" 200',
        ],
    )
    def test_the_secret_is_gone_from_error_messages(self, text):
        redacted = redact_secrets(text)
        assert SECRET not in redacted
        assert "=***" in redacted

    def test_text_without_secrets_is_unchanged(self):
        text = "https://api.openalex.org/works?filter=type:article&per-page=25"
        assert redact_secrets(text) == text


class TestNoSecretInLogs:
    def _client_failing_with(self, error: Exception) -> HttpClient:
        client = HttpClient()
        client._session = MagicMock()
        client._session.get.side_effect = error
        return client

    @pytest.mark.parametrize(
        "error",
        [
            requests.ConnectionError(f"Max retries exceeded with url: /works?api_key={SECRET}"),
            requests.Timeout(f"Read timed out for /works?api_key={SECRET}"),
            requests.RequestException(f"Invalid URL {URL}"),
        ],
    )
    def test_a_request_error_logs_no_secret(self, caplog, error):
        caplog.set_level(logging.DEBUG)
        client = self._client_failing_with(error)

        with pytest.raises(requests.RequestException):
            client.get(URL)

        assert caplog.records, "the failure should still be logged"
        assert SECRET not in caplog.text
        assert "me@example.org" not in caplog.text

    def test_a_successful_request_logs_no_secret(self, caplog):
        caplog.set_level(logging.DEBUG)
        client = HttpClient()
        client._session = MagicMock()
        response = client._session.get.return_value
        response.ok, response.status_code, response.content, response.text = True, 200, b"{}", "{}"

        assert client.get_json(URL) == {}
        assert SECRET not in caplog.text

    def test_urllib3_request_lines_are_redacted(self, caplog):
        """urllib3 logs every request line, query string included, at DEBUG."""
        import scrapers.http_client  # noqa: F401  (installs the filter)

        caplog.set_level(logging.DEBUG, logger="urllib3.connectionpool")
        logging.getLogger("urllib3.connectionpool").debug(
            '%s://%s:%s "%s %s %s" %s %s',
            "https", "api.openalex.org", 443, "GET", f"/works?api_key={SECRET}", "HTTP/1.1", 200, 2,
        )
        assert "api_key=***" in caplog.text
        assert SECRET not in caplog.text

    def test_the_source_logs_no_secret_when_a_fetch_fails(self, caplog):
        from scrapers.sources.openalex import OpenAlexSource

        source = OpenAlexSource(api_key="unused")
        source._api_client = MagicMock()
        source._api_client.iter_works_pages.side_effect = requests.HTTPError(
            f"500 Server Error for url: {URL}"
        )
        assert source.fetch_works_pages(search="x") == []
        assert "fetch_works_pages failed" in caplog.text
        assert SECRET not in caplog.text
