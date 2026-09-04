"""
WikiCFP detail-page HTML parser (Phase 2.7B).

Parses individual event detail pages (/cfp/servlet/event.showcfp?eventid=NNN)
from WikiCFP into structured milestone dictionaries and raw opportunity enrichments.

Extracts:
- Abstract Registration Due
- Submission Deadline
- Notification Due
- Final Version Due (Camera-Ready)
- When (Event Dates)
- Where (Location)
- Website URL
- CFP Description / Body
"""
from __future__ import annotations

from dataclasses import dataclass, field
import logging
import re
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)

EVENTID_RE = re.compile(r"eventid=(\d+)", re.IGNORECASE)


@dataclass
class WikiCFPDetailRecord:
    """Structured milestone and enrichment data extracted from a WikiCFP detail page."""

    event_id: str | None
    page_url: str
    title: str | None = None
    abbreviation: str | None = None
    website_url: str | None = None
    location: str | None = None
    event_dates_raw: str | None = None
    milestones: dict[str, str] = field(default_factory=dict)
    description: str | None = None


class WikiCFPDetailParser:
    """Parses WikiCFP detail page HTML into structured milestone records."""

    def parse(self, html: str, page_url: str = "") -> WikiCFPDetailRecord:
        """
        Parse a WikiCFP detail page HTML string.

        Args:
            html: HTML source of event.showcfp
            page_url: URL page was fetched from

        Returns:
            WikiCFPDetailRecord with extracted milestones.
        """
        soup = BeautifulSoup(html, "html.parser")
        event_id = self._extract_event_id(page_url) or self._extract_event_id_from_dom(soup)

        # 1. Title and Abbreviation
        title, abbreviation = self._extract_title_and_abbrev(soup)

        # 2. External Website URL
        website_url = self._extract_website_url(soup)

        # 3. Milestones table
        milestones, event_dates_raw, location = self._extract_milestones_table(soup)

        # 4. Description / CFP text
        description = self._extract_description(soup)

        return WikiCFPDetailRecord(
            event_id=event_id,
            page_url=page_url,
            title=title,
            abbreviation=abbreviation,
            website_url=website_url,
            location=location,
            event_dates_raw=event_dates_raw,
            milestones=milestones,
            description=description,
        )

    # ── Private extraction helpers ─────────────────────────────────────────────

    def _extract_title_and_abbrev(self, soup: BeautifulSoup) -> tuple[str | None, str | None]:
        """Extract title and acronym from header elements."""
        # Check standard WikiCFP span headers
        title_tag = soup.find("span", attrs={"property": "v:summary"}) or soup.find("h2")
        title_text = title_tag.get_text(strip=True) if title_tag else None

        # Check for abbreviation link or bold text
        abbrev = None
        abbrev_tag = soup.find("span", attrs={"property": "v:eventType"}) or soup.find("h3")
        if abbrev_tag:
            abbrev = abbrev_tag.get_text(strip=True)

        return title_text, abbrev

    def _extract_website_url(self, soup: BeautifulSoup) -> str | None:
        """Extract external homepage URL from link text or anchor."""
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            text = a.get_text(strip=True).lower()
            if any(k in text for k in ["link", "website", "homepage", "conference homepage"]) or "event.showcfp" not in href:
                if href.startswith("http://") or href.startswith("https://"):
                    if "wikicfp.com" not in href:
                        return href
        return None

    def _extract_milestones_table(
        self, soup: BeautifulSoup
    ) -> tuple[dict[str, str], str | None, str | None]:
        """
        Extract milestone key-value pairs from detail page tables.
        """
        milestones: dict[str, str] = {}
        event_dates_raw: str | None = None
        location: str | None = None

        # Iterate over all table rows containing th/td pairs
        for tr in soup.find_all("tr"):
            th = tr.find(["th", "td"])
            tds = tr.find_all("td")
            if not th or len(tds) == 0:
                continue

            label = th.get_text(strip=True).rstrip(":")
            # If th is the first td, the value is in the next td
            val_td = tds[1] if (th == tds[0] and len(tds) > 1) else (tds[0] if th != tds[0] else None)
            if not val_td:
                continue

            val = val_td.get_text(strip=True)
            if not label or not val:
                continue

            norm_label = label.lower()

            if "when" in norm_label:
                if val.upper() not in {"N/A", "NA"}:
                    event_dates_raw = val
            elif "where" in norm_label:
                if val.upper() not in {"N/A", "NA"}:
                    location = val
            else:
                # Milestone row (e.g. "Submission Deadline", "Notification Due", "Final Version Due", "Abstract Due")
                if any(m in norm_label for m in ["deadline", "due", "date", "submission", "notification", "final version", "camera"]):
                    milestones[label] = val

        return milestones, event_dates_raw, location

    def _extract_description(self, soup: BeautifulSoup) -> str | None:
        """Extract main CFP body text if present."""
        cfp_div = soup.find("div", attrs={"class": "cfp"})
        if cfp_div:
            return cfp_div.get_text(separator="\n", strip=True)
        return None

    def _extract_event_id(self, url: str) -> str | None:
        match = EVENTID_RE.search(url)
        return match.group(1) if match else None

    def _extract_event_id_from_dom(self, soup: BeautifulSoup) -> str | None:
        for a in soup.find_all("a", href=True):
            match = EVENTID_RE.search(a["href"])
            if match:
                return match.group(1)
        return None
