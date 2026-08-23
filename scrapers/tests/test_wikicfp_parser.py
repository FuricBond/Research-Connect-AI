"""
Tests for WikiCFPParser.

All tests use local HTML fixtures — no live network requests.
"""
import sys
from pathlib import Path

import pytest

# Ensure project root is on path
_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scrapers.parsers.wikicfp_parser import WikiCFPParser

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_HTML = (FIXTURES / "wikicfp_list_page.html").read_text(encoding="utf-8")
EMPTY_HTML = (FIXTURES / "wikicfp_empty_page.html").read_text(encoding="utf-8")
PAGE_URL = "http://www.wikicfp.com/cfp/call?conference=artificial+intelligence&page=1"


@pytest.fixture()
def parser() -> WikiCFPParser:
    return WikiCFPParser()


class TestHasEntries:
    def test_returns_true_for_page_with_data(self, parser):
        assert parser.has_entries(SAMPLE_HTML) is True

    def test_returns_false_for_empty_page(self, parser):
        assert parser.has_entries(EMPTY_HTML) is False

    def test_returns_false_for_blank_html(self, parser):
        assert parser.has_entries("<html><body></body></html>") is False


class TestParse:
    def test_parses_correct_number_of_records(self, parser):
        records = parser.parse(SAMPLE_HTML, PAGE_URL)
        assert len(records) == 5

    def test_source_name_is_wikicfp(self, parser):
        records = parser.parse(SAMPLE_HTML, PAGE_URL)
        for rec in records:
            assert rec.source_name == "WikiCFP"

    def test_conference_entry_title(self, parser):
        records = parser.parse(SAMPLE_HTML, PAGE_URL)
        titles = [r.title for r in records]
        assert any(
            "International Conference on Advanced Computer Science" in t for t in titles
        )

    def test_conference_entry_abbreviation(self, parser):
        records = parser.parse(SAMPLE_HTML, PAGE_URL)
        abbrevs = [r.abbreviation for r in records]
        assert "ICAIT 2026" in abbrevs

    def test_raw_source_id_is_extracted(self, parser):
        records = parser.parse(SAMPLE_HTML, PAGE_URL)
        ids = {r.raw_source_id for r in records}
        assert "195331" in ids
        assert "192996" in ids
        assert "192129" in ids

    def test_source_url_contains_event_id(self, parser):
        records = parser.parse(SAMPLE_HTML, PAGE_URL)
        rec = next(r for r in records if r.raw_source_id == "195331")
        assert "195331" in rec.source_url
        assert rec.source_url.startswith("http://www.wikicfp.com")

    def test_submission_deadline_is_extracted(self, parser):
        records = parser.parse(SAMPLE_HTML, PAGE_URL)
        rec = next(r for r in records if r.raw_source_id == "195331")
        assert rec.raw_submission_deadline == "Aug 22, 2026"

    def test_event_dates_are_extracted(self, parser):
        records = parser.parse(SAMPLE_HTML, PAGE_URL)
        rec = next(r for r in records if r.raw_source_id == "195331")
        assert rec.raw_event_dates == "Oct 24, 2026 - Oct 25, 2026"

    def test_location_is_extracted(self, parser):
        records = parser.parse(SAMPLE_HTML, PAGE_URL)
        rec = next(r for r in records if r.raw_source_id == "195331")
        assert "Vienna" in rec.raw_location

    def test_na_location_becomes_none(self, parser):
        """Journal entries with N/A dates and location should have None."""
        records = parser.parse(SAMPLE_HTML, PAGE_URL)
        rec = next(r for r in records if r.raw_source_id == "192996")
        assert rec.raw_location is None

    def test_na_dates_become_none(self, parser):
        records = parser.parse(SAMPLE_HTML, PAGE_URL)
        rec = next(r for r in records if r.raw_source_id == "192996")
        assert rec.raw_event_dates is None

    def test_virtual_conference_location(self, parser):
        records = parser.parse(SAMPLE_HTML, PAGE_URL)
        rec = next(r for r in records if r.raw_source_id == "192129")
        assert rec.raw_location == "Virtual Conference"

    def test_empty_page_returns_empty_list(self, parser):
        records = parser.parse(EMPTY_HTML, PAGE_URL)
        assert records == []

    def test_blank_html_returns_empty_list(self, parser):
        records = parser.parse("<html><body></body></html>", PAGE_URL)
        assert records == []

    def test_malformed_row_is_skipped_gracefully(self, parser):
        """A table with a single row (no pair) should not crash."""
        html = """
        <html><body>
        <table>
            <tr bgcolor="#f6f6f6">
                <td rowspan="2"><a href="/cfp/servlet/event.showcfp?eventid=99999">XX 2026</a></td>
                <td colspan="3">Incomplete entry</td>
            </tr>
        </table>
        </body></html>
        """
        # Should not raise, may return 0 or 1 depending on row pairing
        records = parser.parse(html, PAGE_URL)
        assert isinstance(records, list)

    def test_missing_eventid_in_href_is_skipped(self, parser):
        """Rows with hrefs that have no eventid should be skipped."""
        html = """
        <html><body>
        <table>
            <tr bgcolor="#f6f6f6">
                <td rowspan="2"><a href="/cfp/servlet/event.showcfp?otherid=99">XX 2026</a></td>
                <td colspan="3">Some Conference</td>
            </tr>
            <tr bgcolor="#f6f6f6">
                <td>N/A</td><td>N/A</td><td>N/A</td>
            </tr>
        </table>
        </body></html>
        """
        records = parser.parse(html, PAGE_URL)
        assert records == []

    def test_all_records_have_required_provenance(self, parser):
        records = parser.parse(SAMPLE_HTML, PAGE_URL)
        for rec in records:
            assert rec.source_name
            assert rec.raw_source_id
            assert rec.source_url
            assert rec.title
