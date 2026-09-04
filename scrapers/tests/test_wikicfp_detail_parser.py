"""
Tests for WikiCFPDetailParser (Phase 2.7B).

Verifies milestone extraction from WikiCFP event detail pages.
"""
from pathlib import Path
import pytest

from scrapers.parsers.wikicfp_detail_parser import WikiCFPDetailParser

FIXTURES = Path(__file__).parent / "fixtures"
DETAIL_HTML = (FIXTURES / "wikicfp_detail_page.html").read_text(encoding="utf-8")
DETAIL_URL = "http://www.wikicfp.com/cfp/servlet/event.showcfp?eventid=195331"


@pytest.fixture()
def detail_parser() -> WikiCFPDetailParser:
    return WikiCFPDetailParser()


class TestWikiCFPDetailParser:
    def test_parse_metadata(self, detail_parser):
        record = detail_parser.parse(DETAIL_HTML, DETAIL_URL)
        assert record.event_id == "195331"
        assert record.title == "International Conference on Machine Learning and Neural Systems"
        assert record.abbreviation == "ICMLNS 2026"
        assert record.website_url == "https://icmlns2026.org/cfp"
        assert record.location == "Vienna, Austria"
        assert record.event_dates_raw == "Oct 24, 2026 - Oct 25, 2026"

    def test_parse_milestones(self, detail_parser):
        record = detail_parser.parse(DETAIL_HTML, DETAIL_URL)
        milestones = record.milestones
        assert len(milestones) >= 4
        assert "Abstract Registration Due" in milestones
        assert milestones["Abstract Registration Due"] == "Aug 10, 2026"
        assert "Submission Deadline" in milestones
        assert milestones["Submission Deadline"] == "Aug 22, 2026 23:59 AoE"
        assert "Notification Due" in milestones
        assert milestones["Notification Due"] == "Sep 15, 2026"
        assert "Final Version Due" in milestones
        assert milestones["Final Version Due"] == "Oct 1, 2026"

    def test_parse_description(self, detail_parser):
        record = detail_parser.parse(DETAIL_HTML, DETAIL_URL)
        assert record.description is not None
        assert "Call for Papers" in record.description

    def test_blank_html_handling(self, detail_parser):
        record = detail_parser.parse("<html><body></body></html>", "http://www.wikicfp.com/cfp/servlet/event.showcfp?eventid=999")
        assert record.event_id == "999"
        assert record.title is None
        assert len(record.milestones) == 0
