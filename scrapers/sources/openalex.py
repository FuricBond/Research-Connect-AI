"""
OpenAlex source adapter.

Analogous to ``WikiCFPSource`` but for the OpenAlex REST API.

This module is responsible ONLY for fetching raw JSON pages.
Normalisation / validation / persistence are handled by their respective
modules.

Source metadata:
  name: "OpenAlex"
  type: API
  base_url: https://api.openalex.org
"""
from __future__ import annotations

import logging
import os

from scrapers.openalex.client import OpenAlexClient
from scrapers.http_client import HttpClient

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://api.openalex.org"


class OpenAlexSource:
    """
    Fetches research work listings from the OpenAlex API.

    Usage::

        source = OpenAlexSource()
        pages = source.fetch_works_pages(
            search="machine learning",
            per_page=25,
            max_pages=2,
        )
        for raw_works in pages:
            for work_dict in raw_works:
                ...

    Configuration is read from environment variables:
      ``OPENALEX_API_BASE_URL`` — API base URL (default: https://api.openalex.org)
      ``OPENALEX_EMAIL``         — contact email for polite pool (optional)
    """

    source_name: str = "OpenAlex"
    source_type: str = "API"

    def __init__(
        self,
        http_client: HttpClient | None = None,
        base_url: str | None = None,
        email: str | None = None,
    ) -> None:
        resolved_base_url = (
            base_url
            or os.environ.get("OPENALEX_API_BASE_URL", _DEFAULT_BASE_URL)
        )
        resolved_email = email or os.environ.get("OPENALEX_EMAIL") or None

        self._api_client = OpenAlexClient(
            base_url=resolved_base_url,
            email=resolved_email,
            http_client=http_client,
        )

        logger.info(
            "OpenAlexSource initialised: base_url=%r email=%s",
            resolved_base_url,
            "set" if resolved_email else "not set (anonymous)",
        )

    @property
    def base_url(self) -> str:
        return self._api_client._base_url

    def fetch_works_pages(
        self,
        search: str,
        per_page: int = 25,
        max_pages: int = 1,
        year: int | None = None,
        work_type: str | None = None,
    ) -> list[list[dict]]:
        """
        Fetch up to ``max_pages`` pages of raw work dicts.

        Returns a list of pages, where each page is a list of raw dicts
        (one per work).  If the API returns fewer results than requested,
        fewer pages are returned.

        Args:
            search:    Search query string.
            per_page:  Works per page (1–200).
            max_pages: Maximum pages to fetch.
            year:      Optional publication year filter.
            work_type: Optional work type filter (e.g. ``"article"``).

        Returns:
            list[list[dict]] — pages × works, or empty list on failure.
        """
        pages: list[list[dict]] = []
        try:
            for page in self._api_client.iter_works_pages(
                search=search,
                per_page=per_page,
                max_pages=max_pages,
                year=year,
                work_type=work_type,
            ):
                pages.append(page)
        except Exception as exc:
            logger.error("OpenAlexSource.fetch_works_pages failed: %s", exc)
        return pages

    def close(self) -> None:
        """Release the underlying connection pool."""
        self._api_client.close()

    def __enter__(self) -> "OpenAlexSource":
        return self

    def __exit__(self, *_) -> None:
        self.close()
