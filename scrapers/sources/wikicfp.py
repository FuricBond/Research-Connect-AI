"""
WikiCFP source implementation.

Source: http://www.wikicfp.com
License: Creative Commons Attribution-Share Alike 3.0
robots.txt: User-agent: *, Disallow: (empty — no path restrictions)
Crawl-delay: 5 seconds (stated in robots.txt AND on /cfp/data.jsp)

This module is responsible ONLY for fetching pages.
Parsing is delegated to scrapers.parsers.wikicfp_parser.WikiCFPParser.

URL structure (verified by live inspection 2026-08-24):
  List page: http://www.wikicfp.com/cfp/call?conference=<topic>&page=<n>
  Columns: Event (abbrev+title) | When | Where | Deadline

Content type: static HTML — no JavaScript rendering required.
BeautifulSoup with html.parser is sufficient.
"""
from __future__ import annotations

import logging
from urllib.parse import urlencode

from scrapers.http_client import HttpClient, fetch_with_delay
from scrapers.models import RawOpportunity
from scrapers.parsers.wikicfp_parser import WikiCFPParser

logger = logging.getLogger(__name__)

BASE_URL = "http://www.wikicfp.com"
LIST_PATH = "/cfp/call"


class WikiCFPSource:
    """
    Fetches conference/CFP listings from WikiCFP.

    Usage:
        source = WikiCFPSource()
        pages_html = source.fetch_pages(topic="machine learning", max_pages=2)
        for html, url in pages_html:
            records = source.parse(html, url)
    """

    source_name: str = "WikiCFP"
    source_type: str = "SCRAPER"
    base_url: str = BASE_URL
    crawl_delay_seconds: float = 5.0  # Respect robots.txt + data.jsp guidance

    def __init__(self, http_client: HttpClient | None = None) -> None:
        self._client = http_client or HttpClient()
        self._parser = WikiCFPParser()

    def build_list_url(self, topic: str, page: int = 1) -> str:
        """Return the URL for a single list page given a topic and page number."""
        params = urlencode({"conference": topic, "page": page})
        return f"{BASE_URL}{LIST_PATH}?{params}"

    def fetch_pages(
        self,
        topic: str = "artificial intelligence",
        max_pages: int = 1,
    ) -> list[tuple[str, str]]:
        """
        Fetch up to `max_pages` list pages for the given topic.

        Returns:
            List of (html_content, page_url) tuples, one per page.

        Stops early if a page returns no entries (exhausted results).
        """
        results: list[tuple[str, str]] = []
        for page_num in range(1, max_pages + 1):
            url = self.build_list_url(topic, page_num)
            logger.info("Fetching WikiCFP page %d for topic=%r: %s", page_num, topic, url)
            try:
                html = fetch_with_delay(
                    self._client,
                    url,
                    crawl_delay=self.crawl_delay_seconds,
                )
            except Exception as exc:
                logger.error("Failed to fetch page %d: %s", page_num, exc)
                break

            results.append((html, url))

            # Early stop: if the page is empty, no need to fetch further
            if not self._parser.has_entries(html):
                logger.info("No entries found on page %d — stopping early.", page_num)
                break

        logger.info(
            "WikiCFP fetch complete: %d page(s) fetched for topic=%r", len(results), topic
        )
        return results

    def parse(self, html: str, page_url: str) -> list[RawOpportunity]:
        """Parse a single list page HTML into RawOpportunity records."""
        return self._parser.parse(html, page_url)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "WikiCFPSource":
        return self

    def __exit__(self, *_) -> None:
        self.close()
