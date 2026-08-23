"""
Tests for the opportunity normalizer.

Covers: date parsing, type inference, delivery mode inference, URL normalization,
whitespace cleaning, virtual location handling.
"""
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scrapers.models import RawOpportunity
from scrapers.normalizers.opportunity_normalizer import (
    _infer_delivery_mode,
    _infer_opportunity_type,
    _parse_date,
    _parse_event_dates,
    normalize_opportunity,
)


def make_raw(**kwargs) -> RawOpportunity:
    defaults = dict(
        source_name="WikiCFP",
        raw_source_id="12345",
        source_url="http://www.wikicfp.com/cfp/servlet/event.showcfp?eventid=12345",
        title="International Conference on AI",
    )
    defaults.update(kwargs)
    return RawOpportunity(**defaults)


# ── Date parsing ──────────────────────────────────────────────────────────────

class TestParseDate:
    def test_parses_wikicfp_format(self):
        dt = _parse_date("Aug 22, 2026")
        assert dt is not None
        assert dt.month == 8
        assert dt.day == 22
        assert dt.year == 2026
        assert dt.tzinfo == timezone.utc

    def test_parses_full_month_name(self):
        dt = _parse_date("August 22, 2026")
        assert dt is not None
        assert dt.month == 8

    def test_returns_none_for_none(self):
        assert _parse_date(None) is None

    def test_returns_none_for_empty_string(self):
        assert _parse_date("") is None

    def test_returns_none_for_invalid_string(self):
        assert _parse_date("not a date") is None

    def test_returns_none_for_na(self):
        # "N/A" should have been converted to None by the parser already
        assert _parse_date("N/A") is None


class TestParseEventDates:
    def test_parses_date_range(self):
        start, end = _parse_event_dates("Oct 24, 2026 - Oct 25, 2026")
        assert start == date(2026, 10, 24)
        assert end == date(2026, 10, 25)

    def test_parses_single_date(self):
        start, end = _parse_event_dates("Oct 24, 2026")
        assert start == date(2026, 10, 24)
        assert end == date(2026, 10, 24)

    def test_returns_none_none_for_none(self):
        start, end = _parse_event_dates(None)
        assert start is None
        assert end is None


# ── Type inference ────────────────────────────────────────────────────────────

class TestInferOpportunityType:
    def test_conference_title(self):
        assert _infer_opportunity_type("International Conference on AI") == "CONFERENCE"

    def test_journal_title(self):
        assert _infer_opportunity_type("International Journal on Cybernetics") == "JOURNAL"

    def test_transactions_is_journal(self):
        assert _infer_opportunity_type("IEEE Transactions on Neural Networks") == "JOURNAL"

    def test_workshop_title(self):
        assert _infer_opportunity_type("Workshop on Machine Learning") == "WORKSHOP"

    def test_symposium_is_workshop(self):
        assert _infer_opportunity_type("Symposium on Distributed Systems") == "WORKSHOP"

    def test_special_issue_detected(self):
        assert _infer_opportunity_type("Special Issue on Advances in AI") == "SPECIAL_ISSUE"

    def test_special_issue_overrides_journal(self):
        # "Special Issue" should win over "Journal" keyword
        t = _infer_opportunity_type("Special Issue: IEEE Journal on AI")
        assert t == "SPECIAL_ISSUE"

    def test_unknown_defaults_to_conference(self):
        assert _infer_opportunity_type("Some Academic Event 2026") == "CONFERENCE"

    def test_cfp_in_abbreviation(self):
        assert _infer_opportunity_type("AI Event", abbreviation="CFP 2026") == "CALL_FOR_PAPERS"


# ── Delivery mode inference ───────────────────────────────────────────────────

class TestInferDeliveryMode:
    def test_virtual_is_online(self):
        assert _infer_delivery_mode("Virtual Conference") == "ONLINE"

    def test_online_keyword(self):
        assert _infer_delivery_mode("Online Only") == "ONLINE"

    def test_remote_is_online(self):
        assert _infer_delivery_mode("Remote Conference") == "ONLINE"

    def test_hybrid_detected(self):
        assert _infer_delivery_mode("Hybrid Event") == "HYBRID"

    def test_physical_city_is_offline(self):
        assert _infer_delivery_mode("Vienna, Austria") == "OFFLINE"

    def test_none_location_is_offline(self):
        assert _infer_delivery_mode(None) == "OFFLINE"

    def test_empty_location_is_offline(self):
        assert _infer_delivery_mode("") == "OFFLINE"


# ── Full normalizer ───────────────────────────────────────────────────────────

class TestNormalizeOpportunity:
    def test_normalizes_conference_correctly(self):
        raw = make_raw(
            title="  International Conference on AI Research  ",
            raw_submission_deadline="Aug 22, 2026",
            raw_event_dates="Oct 24, 2026 - Oct 25, 2026",
            raw_location="Vienna, Austria",
        )
        norm = normalize_opportunity(raw)

        assert norm.title == "International Conference on AI Research"
        assert norm.opportunity_type == "CONFERENCE"
        assert norm.delivery_mode == "OFFLINE"
        assert norm.location == "Vienna, Austria"
        assert norm.submission_deadline.month == 8
        assert norm.event_start_date == date(2026, 10, 24)
        assert norm.event_end_date == date(2026, 10, 25)
        assert norm.status == "ACTIVE"
        assert norm.is_predatory_flag is False

    def test_normalizes_journal_correctly(self):
        raw = make_raw(
            title="International Journal on Cybernetics & Informatics",
            raw_submission_deadline="Aug 22, 2026",
            raw_event_dates=None,
            raw_location=None,
        )
        norm = normalize_opportunity(raw)
        assert norm.opportunity_type == "JOURNAL"
        assert norm.delivery_mode == "OFFLINE"
        assert norm.location is None
        assert norm.event_start_date is None

    def test_virtual_conference_sets_online_mode_and_null_location(self):
        raw = make_raw(
            title="NLP Conference",
            raw_location="Virtual Conference",
        )
        norm = normalize_opportunity(raw)
        assert norm.delivery_mode == "ONLINE"
        assert norm.location is None  # "Virtual" locations cleared

    def test_provenance_preserved(self):
        raw = make_raw(raw_source_id="99999")
        norm = normalize_opportunity(raw)
        assert norm.raw_source_id == "99999"
        assert norm.source_name == "WikiCFP"

    def test_whitespace_collapsed_in_title(self):
        raw = make_raw(title="  Big   Data   Conference  ")
        norm = normalize_opportunity(raw)
        assert norm.title == "Big Data Conference"

    def test_none_deadline_produces_none(self):
        raw = make_raw(raw_submission_deadline=None)
        norm = normalize_opportunity(raw)
        assert norm.submission_deadline is None

    def test_unparseable_deadline_produces_none(self):
        raw = make_raw(raw_submission_deadline="TBD")
        norm = normalize_opportunity(raw)
        assert norm.submission_deadline is None

    def test_url_none_if_not_present(self):
        raw = make_raw(website_url=None)
        norm = normalize_opportunity(raw)
        assert norm.website_url is None

    def test_url_scheme_added_if_missing(self):
        raw = make_raw(website_url="example.com/conf")
        norm = normalize_opportunity(raw)
        assert norm.website_url is not None
        assert norm.website_url.startswith("http://")

    def test_special_issue_inferred(self):
        raw = make_raw(title="Special Issue on Advances in AI - IEEE Transactions")
        norm = normalize_opportunity(raw)
        assert norm.opportunity_type == "SPECIAL_ISSUE"
