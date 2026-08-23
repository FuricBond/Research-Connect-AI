"""
Source protocol — structural interface that all concrete scrapers must satisfy.

Using typing.Protocol (structural subtyping) rather than ABC so sources can
be duck-typed without inheritance boilerplate.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from scrapers.models import RawOpportunity


@runtime_checkable
class SourceProtocol(Protocol):
    """
    Structural interface for all scraping sources.

    Each source is responsible for:
      1. Fetching raw HTML/content from the target website.
      2. Parsing that content into RawOpportunity objects.

    Separation of fetch and parse allows independent testing of each step.
    """

    @property
    def source_name(self) -> str:
        """Human-readable name of the source (stored in the sources table)."""
        ...

    @property
    def source_type(self) -> str:
        """One of: SCRAPER | RSS | API | MANUAL"""
        ...

    @property
    def base_url(self) -> str:
        """Base URL of the source website."""
        ...

    @property
    def crawl_delay_seconds(self) -> float:
        """Minimum delay between consecutive HTTP requests (respect robots.txt)."""
        ...

    def fetch_pages(self, **kwargs) -> list[str]:
        """
        Fetch raw content (HTML strings) from the source.

        Returns a list of page contents — one per paginated page or batch.
        Implementations should NOT parse here, only fetch.
        """
        ...

    def parse(self, html: str, page_url: str) -> list[RawOpportunity]:
        """
        Parse a single page of raw content into RawOpportunity objects.

        Args:
            html: Raw HTML string from one fetch.
            page_url: The URL this HTML was fetched from (for provenance).

        Returns:
            List of extracted raw opportunities (may be empty).
        """
        ...
