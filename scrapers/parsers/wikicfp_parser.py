"""
WikiCFP HTML parser.

Parses the list-page HTML from WikiCFP's /cfp/call endpoint into
RawOpportunity objects.

HTML structure (verified by live inspection 2026-08-24):
The main content table has alternating bgcolor="#f6f6f6" / "#e6e6e6" rows.
Each event occupies exactly 2 consecutive <tr> rows:

  Row 1 (even index within the data rows):
    <td rowspan="2"><a href="/cfp/servlet/event.showcfp?eventid=NNN&...">ABBREV</a></td>
    <td colspan="3">Full Title of the Event</td>
    <td rowspan="2"><input type="checkbox" ...></td>  ← skip

  Row 2 (odd index):
    <td>When: e.g. "Oct 24, 2026 - Oct 25, 2026" or "N/A"</td>
    <td>Where: e.g. "Vienna, Austria" or "Virtual Conference" or "N/A"</td>
    <td>Deadline: e.g. "Aug 22, 2026"</td>

The header row has bgcolor="#bbbbbb" and is skipped by looking for data-row
colors only.

Selectors rationale:
- We select rows by bgcolor attribute rather than CSS class because the
  page uses inline bgcolor attributes throughout (no semantic classes exist).
- We extract the eventid from the href query string rather than relying on
  link text, which is just a display abbreviation.
"""
from __future__ import annotations

import logging
import re
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from scrapers.models import RawOpportunity

logger = logging.getLogger(__name__)

BASE_URL = "http://www.wikicfp.com"
# Row colors used for data rows (alternating)
DATA_ROW_COLORS = {"#f6f6f6", "#e6e6e6"}
EVENTID_RE = re.compile(r"eventid=(\d+)", re.IGNORECASE)


class WikiCFPParser:
    """Parses WikiCFP list-page HTML into RawOpportunity records."""

    SOURCE_NAME = "WikiCFP"

    def has_entries(self, html: str) -> bool:
        """
        Return True if the page contains at least one data entry.
        Used for early-stop pagination.
        """
        soup = BeautifulSoup(html, "html.parser")
        return bool(soup.find("tr", bgcolor=lambda v: v and v.lower() in DATA_ROW_COLORS))

    def parse(self, html: str, page_url: str) -> list[RawOpportunity]:
        """
        Parse one WikiCFP list page and return RawOpportunity records.

        Args:
            html: Full HTML string of the list page.
            page_url: The URL the HTML was fetched from (used for provenance).

        Returns:
            List of extracted RawOpportunity objects. May be empty.
        """
        soup = BeautifulSoup(html, "html.parser")

        # Collect all data rows (excluding header rows)
        data_rows = [
            tr
            for tr in soup.find_all("tr", bgcolor=True)
            if isinstance(tr, Tag) and tr.get("bgcolor", "").lower() in DATA_ROW_COLORS
        ]

        if not data_rows:
            logger.warning("No data rows found in page: %s", page_url)
            return []

        results: list[RawOpportunity] = []
        # Rows come in pairs: (row1: abbrev+title, row2: when+where+deadline)
        i = 0
        while i < len(data_rows) - 1:
            row1 = data_rows[i]
            row2 = data_rows[i + 1]
            i += 2

            try:
                raw = self._parse_row_pair(row1, row2, page_url)
                if raw is not None:
                    results.append(raw)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to parse row pair at index %d: %s", i - 2, exc)
                continue

        logger.debug("Parsed %d opportunities from %s", len(results), page_url)
        return results

    # ── Private helpers ───────────────────────────────────────────────────────

    def _parse_row_pair(
        self, row1: Tag, row2: Tag, page_url: str
    ) -> RawOpportunity | None:
        """Extract a single RawOpportunity from a (row1, row2) pair."""

        # --- Row 1: abbreviation link + full title ---
        link_tag = row1.find("a", href=True)
        if link_tag is None:
            return None

        href = str(link_tag["href"])
        raw_source_id = self._extract_event_id(href)
        if raw_source_id is None:
            logger.debug("Could not extract eventid from href=%r, skipping.", href)
            return None

        abbreviation = link_tag.get_text(strip=True) or None
        source_url = urljoin(BASE_URL, href)

        # The full title is in the <td colspan="3"> cell of row1
        title_td = row1.find("td", attrs={"colspan": "3"})
        if title_td is None:
            # Some rows use a different colspan — fall back to second TD
            tds = row1.find_all("td")
            title_td = tds[1] if len(tds) > 1 else None

        title = (
            title_td.get_text(strip=True)
            if title_td
            else (abbreviation or "")
        )
        if not title:
            return None

        # --- Row 2: When | Where | Deadline ---
        tds_row2 = row2.find_all("td")
        # Expected: [when, where, deadline]  (3 cells, but may vary)
        raw_event_dates = self._cell_text(tds_row2, 0)
        raw_location = self._cell_text(tds_row2, 1)
        raw_deadline = self._cell_text(tds_row2, 2)

        return RawOpportunity(
            source_name=self.SOURCE_NAME,
            raw_source_id=raw_source_id,
            source_url=source_url,
            title=title,
            abbreviation=abbreviation,
            website_url=None,         # Not available on list page — detail page only
            raw_submission_deadline=raw_deadline,
            raw_event_dates=raw_event_dates,
            raw_location=raw_location,
            raw_opportunity_type=None,  # Inferred by normalizer from title
        )

    @staticmethod
    def _extract_event_id(href: str) -> str | None:
        """Extract the numeric eventid from a WikiCFP href string."""
        match = EVENTID_RE.search(href)
        return match.group(1) if match else None

    @staticmethod
    def _cell_text(tds: list[Tag], index: int) -> str | None:
        """Safely extract and strip text from a list of <td> tags by index."""
        if index >= len(tds):
            return None
        text = tds[index].get_text(strip=True)
        # "N/A" means the field is unknown — treat as absent
        if text.upper() in {"N/A", "NA", ""}:
            return None
        return text or None
