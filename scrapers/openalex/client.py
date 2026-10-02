"""
OpenAlex HTTP API client.

Responsibilities:
  - Build correct request URLs for the OpenAlex REST API
  - Apply polite pool header (``?mailto=``) when ``OPENALEX_EMAIL`` is set
  - Send the account API key (``?api_key=``) when ``OPENALEX_API_KEY`` is set
  - Handle HTTP 429 (rate-limit) with exponential back-off
  - Stop at once when the daily usage budget is spent (retrying cannot help)
  - Delegate transport-level retries (500/502/503) to the underlying HttpClient
  - Support cursor-based pagination transparently
  - Return raw response dicts (parsing/normalisation is NOT done here)

The client is intentionally thin: it knows about the OpenAlex URL structure
and rate-limiting behaviour, nothing else.

Configuration (via environment or Settings):
  OPENALEX_API_BASE_URL — default: https://api.openalex.org
  OPENALEX_EMAIL        — optional, for polite pool access
  OPENALEX_API_KEY      — optional, free account key; raises the daily budget 10x

Usage budget: OpenAlex charges every call against a daily budget that resets at
midnight UTC. A keyword ``search`` page costs ten times a filter-only page, so
bulk loads should select works with filters (``works_filter``) where possible.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import date, datetime
from typing import Generator
from urllib.parse import urlencode

import requests

from scrapers.http_client import HttpClient, redact_secrets

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

_WORK_FIELDS = (
    "id,doi,title,display_name,publication_year,publication_date,"
    "type,language,cited_by_count,primary_location,open_access,"
    "authorships,abstract_inverted_index,topics,keywords,concepts,"
    "open_access,counts_by_year,updated_date,indexed_in,biblio,ids"
)


class OpenAlexBudgetExhaustedError(RuntimeError):
    """
    The daily OpenAlex usage budget is spent.

    Raised instead of retrying: the budget only resets at midnight UTC, so backing off
    for minutes would just stall the caller. ``reset_seconds`` is how long until then,
    when OpenAlex reports it.
    """

    def __init__(self, reset_seconds: int | None = None) -> None:
        self.reset_seconds = reset_seconds
        when = f" It resets in about {reset_seconds / 3600:.1f} h." if reset_seconds else ""
        super().__init__(f"OpenAlex daily usage budget exhausted.{when}")


@dataclass(frozen=True)
class WorksPage:
    """One page of /works results and the cursors around it."""

    results: list[dict]
    cursor: str                 # the cursor that fetched this page
    next_cursor: str | None     # the cursor for the following page; None when exhausted
    total_count: int | None     # works matching the query, as reported by OpenAlex


def works_filter(
    year: int | None = None,
    work_type: str | None = None,
    from_year: int | None = None,
    to_year: int | None = None,
    subfield_id: str | None = None,
    has_abstract: bool = False,
    *,
    from_date: date | str | None = None,
    to_date: date | str | None = None,
) -> list[str]:
    """
    Build OpenAlex /works filter clauses.

    ``subfield_id`` selects works whose primary topic falls in an OpenAlex subfield,
    e.g. ``"1702"`` (Artificial Intelligence). A filter-only query costs a tenth of a
    keyword search, which is what makes loads of tens of thousands of works affordable.

    ``from_date`` and ``to_date`` bound the publication date to the day, for loads that
    look back a number of days rather than whole years. Each accepts a ``date``, a
    ``datetime`` (its date is used) or an ISO ``YYYY-MM-DD`` string; anything else, or a
    string carrying extra text, raises ``ValueError``. A year bound and a date bound on the
    same side conflict, as does a ``from_date`` after ``to_date``.
    """
    start = _filter_date(from_date, "from_date")
    end = _filter_date(to_date, "to_date")
    if from_year is not None and start is not None:
        raise ValueError("Give from_year or from_date, not both")
    if to_year is not None and end is not None:
        raise ValueError("Give to_year or to_date, not both")
    if start is not None and end is not None and start > end:
        raise ValueError(f"from_date {start} is after to_date {end}")

    filters: list[str] = []
    if year is not None:
        filters.append(f"publication_year:{year}")
    if from_year is not None:
        filters.append(f"from_publication_date:{from_year}-01-01")
    elif start is not None:
        filters.append(f"from_publication_date:{start.isoformat()}")
    if to_year is not None:
        filters.append(f"to_publication_date:{to_year}-12-31")
    elif end is not None:
        filters.append(f"to_publication_date:{end.isoformat()}")
    if work_type is not None:
        filters.append(f"type:{work_type}")
    if subfield_id is not None:
        filters.append(f"primary_topic.subfield.id:{subfield_id}")
    if has_abstract:
        filters.append("has_abstract:true")
    return filters


def _filter_date(value: date | str | None, name: str) -> date | None:
    """Normalize a ``works_filter`` date bound to a ``date``, or refuse it."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"{name} must be an ISO date (YYYY-MM-DD), got {value!r}") from exc
    raise ValueError(f"{name} must be a date, datetime or ISO date string, got {type(value).__name__}")


def _budget_reset_seconds(response: object) -> int | None:
    """
    Seconds until the budget resets when a 429 means the daily budget is spent, else None.

    OpenAlex answers 429 both for the daily budget and for bursts over 100 requests per
    second; only the budget case reports ``X-RateLimit-Remaining`` at or below zero.
    """
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    remaining = headers.get("X-RateLimit-Remaining")
    if not isinstance(remaining, str):
        return None
    try:
        if float(remaining) > 0:
            return None
    except ValueError:
        return None
    reset = headers.get("X-RateLimit-Reset")
    try:
        return int(float(reset)) if isinstance(reset, str) else 0
    except ValueError:
        return 0


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
        api_key:  OpenAlex account API key (optional). Never logged.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        email: str | None = None,
        http_client: HttpClient | None = None,
        api_key: str | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._email = email
        self._api_key = api_key
        self._client = http_client or HttpClient()

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _build_params(self, extra: dict) -> dict:
        """Build query params, injecting mailto and the API key if configured."""
        params = dict(extra)
        if self._email:
            params["mailto"] = self._email
        if self._api_key:
            params["api_key"] = self._api_key
        return params

    def _get_with_429_handling(self, url: str, params: dict) -> dict:
        """
        Perform a GET request with exponential back-off on HTTP 429.

        All other error handling (500/502/503 retries, timeouts) is delegated
        to the underlying ``HttpClient``.

        Returns:
            Parsed JSON dict.

        Raises:
            OpenAlexBudgetExhaustedError: When the daily usage budget is spent.
            requests.HTTPError: On persistent non-transient errors.
            ValueError: On invalid JSON response.
        """
        wait = _429_INITIAL_WAIT
        for attempt in range(_429_MAX_RETRIES + 1):
            try:
                return self._client.get_json(url, params=params)
            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code == 429:
                    reset_seconds = _budget_reset_seconds(exc.response)
                    if reset_seconds is not None:
                        raise OpenAlexBudgetExhaustedError(reset_seconds or None) from exc
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
        try:
            for page in self.iter_work_pages(
                search=search,
                filters=works_filter(year=year, work_type=work_type),
                per_page=per_page,
                max_pages=max_pages,
            ):
                yield page.results
        except Exception as exc:
            logger.error("OpenAlex works request failed: %s", redact_secrets(str(exc)))
            return

    def iter_work_pages(
        self,
        search: str | None = None,
        filters: list[str] | None = None,
        sort: str | None = None,
        per_page: int = DEFAULT_PER_PAGE,
        max_pages: int = 1,
        start_cursor: str = "*",
    ) -> Generator[WorksPage, None, None]:
        """
        Iterate over /works result pages with their cursors, for resumable bulk loads.

        Unlike ``iter_works_pages`` this raises when a request fails, so the caller
        knows the load stopped early; the last yielded page's ``next_cursor`` is where
        to resume.

        Args:
            search:       Optional full-text search query (costs 10x a filter-only page).
            filters:      Filter clauses, e.g. from ``works_filter``.
            sort:         Optional sort, e.g. ``"cited_by_count:desc"``.
            per_page:     Results per page (1–200).
            max_pages:    Maximum number of pages to fetch.
            start_cursor: Cursor to start from; ``"*"`` for the first page.

        Raises:
            OpenAlexBudgetExhaustedError: When the daily usage budget is spent.
            requests.RequestException: When a request fails after retries.
        """
        per_page = min(max(1, per_page), MAX_PER_PAGE)
        url = f"{self._base_url}/works"

        cursor = start_cursor
        pages_fetched = 0

        while pages_fetched < max_pages:
            query: dict = {"per_page": per_page, "cursor": cursor, "select": _WORK_FIELDS}
            if search:
                query["search"] = search
            if filters:
                query["filter"] = ",".join(filters)
            if sort:
                query["sort"] = sort
            params = self._build_params(query)

            logger.info(
                "Fetching OpenAlex works page %d (search=%r per_page=%d)",
                pages_fetched + 1,
                search,
                per_page,
            )

            data = self._get_with_429_handling(url, params)

            results: list[dict] = data.get("results", [])
            if not results:
                logger.info("OpenAlex returned 0 results — stopping pagination.")
                return

            meta = data.get("meta", {})
            next_cursor = meta.get("next_cursor") or None
            yield WorksPage(
                results=results,
                cursor=cursor,
                next_cursor=next_cursor,
                total_count=meta.get("count"),
            )
            pages_fetched += 1

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
