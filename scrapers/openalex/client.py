"""
OpenAlex HTTP API client.

Responsibilities:
  - Build correct request URLs for the OpenAlex REST API
  - Apply polite pool header (``?mailto=``) when ``OPENALEX_EMAIL`` is set
  - Handle HTTP 429 (rate-limit) with exponential back-off
  - Delegate transport-level retries (500/502/503) to the underlying HttpClient
  - Support cursor-based pagination transparently
  - Return raw response dicts (parsing/normalisation is NOT done here)

The client is intentionally thin: it knows about the OpenAlex URL structure
and rate-limiting behaviour, nothing else.

Configuration (via environment or Settings):
  OPENALEX_API_BASE_URL — default: https://api.openalex.org
  OPENALEX_EMAIL        — optional, for polite pool access
"""
from __future__ import annotations

import logging
import time
from typing import Generator
from urllib.parse import urlencode

import requests

from scrapers.http_client import HttpClient

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

DEFAULT_BASE_URL = "https://api.openalex.org"
DEFAULT_PER_PAGE = 25
MAX_PER_PAGE = 200          # OpenAlex hard limit

# 429 back-off: initial wait, multiplier, max wait (seconds)
_429_INITIAL_WAIT = 10.0
_429_BACKOFF_MULTIPLIER = 2.0
_429_MAX_WAIT = 120.0
_429_MAX_RETRIES = 4

# Polite delay between paginated requests (seconds)
_POLITE_DELAY = 1.0


class OpenAlexClient:
    """
    Dedicated OpenAlex API client.

    Usage::

        client = OpenAlexClient(email="me@example.com")
        for page in client.iter_works_pages(search="machine learning", per_page=25):
            for work_dict in page:
                ...  # raw dict from OpenAlex API

    Args:
        base_url: OpenAlex API base URL (default: https://api.openalex.org).
        email:    Contact email for polite pool access (optional but recommended).
        http_client: Provide a custom HttpClient for testing.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        email: str | None = None,
        http_client: HttpClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._email = email
        self._client = http_client or HttpClient()

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _build_params(self, extra: dict) -> dict:
        """Build query params, injecting mailto if configured."""
        params = dict(extra)
        if self._email:
            params["mailto"] = self._email
        return params

    def _get_with_429_handling(self, url: str, params: dict) -> dict:
        """
        Perform a GET request with exponential back-off on HTTP 429.

        All other error handling (500/502/503 retries, timeouts) is delegated
        to the underlying ``HttpClient``.

        Returns:
            Parsed JSON dict.

        Raises:
            requests.HTTPError: On persistent non-transient errors.
            ValueError: On invalid JSON response.
        """
        wait = _429_INITIAL_WAIT
        for attempt in range(_429_MAX_RETRIES + 1):
            try:
                return self._client.get_json(url, params=params)
            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code == 429:
                    if attempt >= _429_MAX_RETRIES:
                        logger.error(
                            "OpenAlex 429 rate-limit: giving up after %d retries",
                            _429_MAX_RETRIES,
                        )
                        raise
                    logger.warning(
                        "OpenAlex 429 rate-limit (attempt %d/%d) — backing off %.0fs",
                        attempt + 1,
                        _429_MAX_RETRIES,
                        wait,
                    )
                    time.sleep(wait)
                    wait = min(wait * _429_BACKOFF_MULTIPLIER, _429_MAX_WAIT)
                else:
                    raise
        # Should not be reached
        raise RuntimeError("Unexpected exit from retry loop")

    # ── Works ─────────────────────────────────────────────────────────────────

    def iter_works_pages(
        self,
        search: str,
        per_page: int = DEFAULT_PER_PAGE,
        max_pages: int = 1,
        year: int | None = None,
        work_type: str | None = None,
    ) -> Generator[list[dict], None, None]:
        """
        Iterate over paginated work results from the OpenAlex /works endpoint.

        Uses cursor-based pagination for reliability.  Yields one list of raw
        work dicts per page.  Stops early if OpenAlex returns no more results.

        Args:
            search:    Full-text search query.
            per_page:  Results per page (1–200).
            max_pages: Maximum number of pages to fetch.
            year:      Optional filter: only works from this publication year.
            work_type: Optional filter: e.g. ``"article"``, ``"preprint"``.

        Yields:
            list[dict] — raw work dicts from the OpenAlex API.
        """
        per_page = min(max(1, per_page), MAX_PER_PAGE)
        url = f"{self._base_url}/works"

        # Build filter string
        filters: list[str] = []
        if year is not None:
            filters.append(f"publication_year:{year}")
        if work_type is not None:
            filters.append(f"type:{work_type}")

        cursor = "*"
        pages_fetched = 0

        while pages_fetched < max_pages:
            params = self._build_params(
                {
                    "search": search,
                    "per_page": per_page,
                    "cursor": cursor,
                    "select": (
                        "id,doi,title,display_name,publication_year,publication_date,"
                        "type,language,cited_by_count,primary_location,open_access,"
                        "authorships,abstract_inverted_index,topics,keywords,concepts,"
                        "open_access,counts_by_year,updated_date,indexed_in,biblio,ids"
                    ),
                }
            )
            if filters:
                params["filter"] = ",".join(filters)

            logger.info(
                "Fetching OpenAlex works page %d (search=%r per_page=%d cursor=%r)",
                pages_fetched + 1,
                search,
                per_page,
                cursor,
            )

            try:
                data = self._get_with_429_handling(url, params)
            except Exception as exc:
                logger.error(
                    "OpenAlex works request failed on page %d: %s",
                    pages_fetched + 1,
                    exc,
                )
                return

            results: list[dict] = data.get("results", [])
            if not results:
                logger.info("OpenAlex returned 0 results — stopping pagination.")
                return

            yield results
            pages_fetched += 1

            # Advance cursor
            meta = data.get("meta", {})
            next_cursor = meta.get("next_cursor")
            if not next_cursor:
                logger.info(
                    "No next_cursor in OpenAlex response — all pages exhausted after page %d.",
                    pages_fetched,
                )
                return
            cursor = next_cursor

            # Polite delay between pages
            if pages_fetched < max_pages:
                time.sleep(_POLITE_DELAY)

    def fetch_works(
        self,
        search: str,
        per_page: int = DEFAULT_PER_PAGE,
        max_pages: int = 1,
        year: int | None = None,
        work_type: str | None = None,
    ) -> list[dict]:
        """
        Convenience wrapper: collect all pages into a flat list.

        Returns:
            All raw work dicts from up to ``max_pages`` pages.
        """
        all_works: list[dict] = []
        for page in self.iter_works_pages(
            search=search,
            per_page=per_page,
            max_pages=max_pages,
            year=year,
            work_type=work_type,
        ):
            all_works.extend(page)
        return all_works

    # ── Single entity lookups ─────────────────────────────────────────────────

    def get_author(self, openalex_id: str) -> dict:
        """
        Fetch a single author/researcher by compact OpenAlex ID.

        Args:
            openalex_id: Compact ID, e.g. ``"A5048491430"`` or full URL.
        """
        clean_id = openalex_id.split("/")[-1]  # accept full URL or compact
        url = f"{self._base_url}/authors/{clean_id}"
        return self._get_with_429_handling(url, self._build_params({}))

    def get_source(self, openalex_id: str) -> dict:
        """Fetch a single source/venue by compact OpenAlex ID."""
        clean_id = openalex_id.split("/")[-1]
        url = f"{self._base_url}/sources/{clean_id}"
        return self._get_with_429_handling(url, self._build_params({}))

    def get_institution(self, openalex_id: str) -> dict:
        """Fetch a single institution by compact OpenAlex ID."""
        clean_id = openalex_id.split("/")[-1]
        url = f"{self._base_url}/institutions/{clean_id}"
        return self._get_with_429_handling(url, self._build_params({}))

    # ── Context manager support ───────────────────────────────────────────────

    def close(self) -> None:
        """Release the underlying connection pool."""
        self._client.close()

    def __enter__(self) -> "OpenAlexClient":
        return self

    def __exit__(self, *_) -> None:
        self.close()
