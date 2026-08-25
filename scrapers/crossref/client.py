"""
Crossref HTTP REST API client.

Responsibilities:
  - Query single works by DOI (`/works/{doi}`)
  - Search works by text query with pagination (`/works?query=...`)
  - Construct polite User-Agent and mailto parameters for the Crossref Polite Pool
  - Handle rate limiting (HTTP 429) with exponential back-off
  - Gracefully handle HTTP 404 (DOI not found -> None)
  - Delegate transport-level retries (500/502/503/504) to the underlying HttpClient
  - Support deterministic cursor/offset pagination
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Generator
import urllib.parse

import requests

from scrapers.crossref.doi_utils import canonicalize_doi
from scrapers.http_client import HttpClient

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.crossref.org"
DEFAULT_ROWS_PER_PAGE = 25
MAX_ROWS_PER_PAGE = 100

_429_INITIAL_WAIT = 5.0
_429_BACKOFF_MULTIPLIER = 2.0
_429_MAX_WAIT = 60.0
_429_MAX_RETRIES = 4

_POLITE_DELAY = 0.5


class CrossrefClient:
    """
    Dedicated Crossref REST API client.

    Usage:
        client = CrossrefClient(email="researcher@university.edu")
        work = client.get_work_by_doi("10.7717/peerj.4375")
        for page in client.iter_works_pages(query="machine learning", max_pages=2):
            for item in page:
                ...
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        email: str | None = None,
        user_agent: str | None = None,
        http_client: HttpClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._email = email or os.environ.get("CROSSREF_EMAIL") or None
        self._client = http_client or HttpClient()

        # Build polite User-Agent header
        default_ua = "ResearchConnect-AI/1.0 (https://researchconnect.ai)"
        if self._email:
            self._user_agent = f"ResearchConnect-AI/1.0 (https://researchconnect.ai; mailto:{self._email})"
        else:
            self._user_agent = user_agent or default_ua

    def _build_params(self, extra: dict[str, Any]) -> dict[str, Any]:
        """Inject mailto parameter if email is configured."""
        params = dict(extra)
        if self._email and "mailto" not in params:
            params["mailto"] = self._email
        return params

    def _get_json_with_retries(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        Execute GET request with rate limit (429) backoff handling.

        Raises:
            requests.HTTPError: On non-recoverable HTTP errors.
            ValueError: On invalid JSON payload.
        """
        wait = _429_INITIAL_WAIT
        params = self._build_params(params or {})

        for attempt in range(_429_MAX_RETRIES + 1):
            try:
                return self._client.get_json(url, params=params)
            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code == 429:
                    if attempt >= _429_MAX_RETRIES:
                        logger.error("Crossref 429 rate-limit: exceeded %d retries", _429_MAX_RETRIES)
                        raise
                    logger.warning(
                        "Crossref 429 rate-limit (attempt %d/%d) — backing off %.1fs",
                        attempt + 1,
                        _429_MAX_RETRIES,
                        wait,
                    )
                    time.sleep(wait)
                    wait = min(wait * _429_BACKOFF_MULTIPLIER, _429_MAX_WAIT)
                else:
                    raise
        raise RuntimeError("Unexpected exit from Crossref retry loop")

    def get_work_by_doi(self, raw_doi: str) -> dict[str, Any] | None:
        """
        Fetch a single work from Crossref by DOI.

        Args:
            raw_doi: Clean or raw DOI string.

        Returns:
            The 'message' dict from Crossref response, or None if not found (404) or invalid.
        """
        canonical_doi = canonicalize_doi(raw_doi)
        if not canonical_doi:
            logger.warning("Invalid DOI format: %r", raw_doi)
            return None

        # Crossref works endpoint: /works/{doi}
        encoded_doi = urllib.parse.quote(canonical_doi, safe="")
        url = f"{self._base_url}/works/{encoded_doi}"

        try:
            data = self._get_json_with_retries(url)
            if isinstance(data, dict) and data.get("status") == "ok":
                return data.get("message")
            return None
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                logger.info("Crossref DOI not found (404): %s", canonical_doi)
                return None
            logger.error("Crossref request failed for DOI %s: %s", canonical_doi, exc)
            raise
        except Exception as exc:
            logger.error("Unexpected error querying Crossref for DOI %s: %s", canonical_doi, exc)
            return None

    def iter_works_pages(
        self,
        query: str | None = None,
        rows: int = DEFAULT_ROWS_PER_PAGE,
        max_pages: int = 1,
        filter_type: str | None = None,
        year: int | None = None,
    ) -> Generator[list[dict[str, Any]], None, None]:
        """
        Iterate over paginated work items from Crossref /works endpoint.

        Args:
            query: Free-text search query.
            rows: Number of results per page (1–100).
            max_pages: Maximum pages to fetch.
            filter_type: Filter by Crossref type (e.g. 'journal-article').
            year: Filter by publication year (e.g. 2024).

        Yields:
            list[dict] of raw work messages per page.
        """
        rows = min(max(1, rows), MAX_ROWS_PER_PAGE)
        url = f"{self._base_url}/works"

        cursor = "*"
        pages_fetched = 0

        filters = []
        if filter_type:
            filters.append(f"type:{filter_type}")
        if year is not None:
            filters.append(f"from-pub-date:{year}-01-01,until-pub-date:{year}-12-31")

        while pages_fetched < max_pages:
            params: dict[str, Any] = {
                "rows": rows,
                "cursor": cursor,
            }
            if query:
                params["query"] = query
            if filters:
                params["filter"] = ",".join(filters)

            logger.info(
                "Fetching Crossref works page %d (query=%r rows=%d cursor=%r)",
                pages_fetched + 1,
                query,
                rows,
                cursor[:15] if isinstance(cursor, str) else cursor,
            )

            try:
                data = self._get_json_with_retries(url, params)
            except Exception as exc:
                logger.error("Crossref works request failed on page %d: %s", pages_fetched + 1, exc)
                return

            if not isinstance(data, dict) or data.get("status") != "ok":
                logger.warning("Crossref returned non-ok status: %s", data.get("status") if isinstance(data, dict) else type(data))
                return

            message = data.get("message", {})
            items = message.get("items", [])
            if not items:
                logger.info("Crossref returned 0 items — stopping pagination.")
                return

            yield items
            pages_fetched += 1

            next_cursor = message.get("next-cursor")
            if not next_cursor or next_cursor == cursor:
                logger.info("No more next-cursor in Crossref response — exhausted after page %d.", pages_fetched)
                return
            cursor = next_cursor

            if pages_fetched < max_pages:
                time.sleep(_POLITE_DELAY)

    def fetch_works(
        self,
        query: str | None = None,
        rows: int = DEFAULT_ROWS_PER_PAGE,
        max_pages: int = 1,
        filter_type: str | None = None,
        year: int | None = None,
    ) -> list[dict[str, Any]]:
        """Convenience method to retrieve all works across requested pages into a single list."""
        all_items: list[dict[str, Any]] = []
        for page in self.iter_works_pages(
            query=query,
            rows=rows,
            max_pages=max_pages,
            filter_type=filter_type,
            year=year,
        ):
            all_items.extend(page)
        return all_items

    def close(self) -> None:
        """Release underlying HTTP connection pool."""
        self._client.close()

    def __enter__(self) -> "CrossrefClient":
        return self

    def __exit__(self, *_) -> None:
        self.close()
