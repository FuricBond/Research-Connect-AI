"""
Crossref source adapter.

This module is responsible ONLY for fetching raw Crossref JSON messages.
Normalization, validation, and persistence are handled by their respective modules.

Source metadata:
  name: "Crossref"
  type: "API"
  base_url: "https://api.crossref.org"
"""
from __future__ import annotations

import logging
import os
from typing import Any

from scrapers.crossref.client import CrossrefClient
from scrapers.http_client import HttpClient

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://api.crossref.org"


class CrossrefSource:
    """
    Fetches scholarly work metadata from Crossref REST API.

    Usage:
        source = CrossrefSource()
        work_dict = source.fetch_work_by_doi("10.7717/peerj.4375")
        pages = source.fetch_works_pages(query="machine learning", per_page=25, max_pages=2)
    """

    source_name: str = "Crossref"
    source_type: str = "API"

    def __init__(
        self,
        http_client: HttpClient | None = None,
        base_url: str | None = None,
        email: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        resolved_base_url = (
            base_url
            or os.environ.get("CROSSREF_API_BASE_URL", _DEFAULT_BASE_URL)
        )
        resolved_email = email or os.environ.get("CROSSREF_EMAIL") or None
        resolved_ua = user_agent or os.environ.get("CROSSREF_USER_AGENT") or None

        self._api_client = CrossrefClient(
            base_url=resolved_base_url,
            email=resolved_email,
            user_agent=resolved_ua,
            http_client=http_client,
        )

        logger.info(
            "CrossrefSource initialized: base_url=%r email=%s",
            resolved_base_url,
            "set" if resolved_email else "not set (anonymous)",
        )

    @property
    def base_url(self) -> str:
        return self._api_client._base_url

    def fetch_work_by_doi(self, doi: str) -> dict[str, Any] | None:
        """Fetch single work message dict by DOI from Crossref."""
        return self._api_client.get_work_by_doi(doi)

    def fetch_works_pages(
        self,
        query: str | None = None,
        per_page: int = 25,
        max_pages: int = 1,
        filter_type: str | None = None,
        year: int | None = None,
    ) -> list[list[dict[str, Any]]]:
        """Fetch up to max_pages pages of raw Crossref work item dicts."""
        pages: list[list[dict[str, Any]]] = []
        try:
            for page in self._api_client.iter_works_pages(
                query=query,
                rows=per_page,
                max_pages=max_pages,
                filter_type=filter_type,
                year=year,
            ):
                pages.append(page)
        except Exception as exc:
            logger.error("CrossrefSource.fetch_works_pages failed: %s", exc)
        return pages

    def close(self) -> None:
        """Release the underlying connection pool."""
        self._api_client.close()

    def __enter__(self) -> "CrossrefSource":
        return self

    def __exit__(self, *_) -> None:
        self.close()
