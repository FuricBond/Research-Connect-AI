"""
Tests for the opportunity validator.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scrapers.models import NormalizedOpportunity
from scrapers.validators.opportunity_validator import validate_opportunity


def make_valid(**kwargs) -> NormalizedOpportunity:
    """Return a minimally valid NormalizedOpportunity."""
    defaults = dict(
        source_name="WikiCFP",
        raw_source_id="12345",
        source_url="http://www.wikicfp.com/cfp/servlet/event.showcfp?eventid=12345",
        title="International Conference on AI",
        abbreviation="ICAI 2026",
        opportunity_type="CONFERENCE",
        website_url=None,
        submission_deadline=None,
        event_start_date=None,
        event_end_date=None,
        location="Vienna, Austria",
        delivery_mode="OFFLINE",
    )
    defaults.update(kwargs)
    return NormalizedOpportunity(**defaults)


class TestValidOpportunity:
    def test_valid_minimal_record_passes(self):
        opp = make_valid()
        is_valid, errors = validate_opportunity(opp)
        assert is_valid is True
        assert errors == []

    def test_valid_with_all_optional_fields_passes(self):
        opp = make_valid(
            website_url="https://example.com/conf",
            submission_deadline=datetime.now(tz=timezone.utc) + timedelta(days=90),
        )
        is_valid, errors = validate_opportunity(opp)
        assert is_valid is True


class TestRequiredFields:
    def test_empty_title_fails(self):
        opp = make_valid(title="")
        is_valid, errors = validate_opportunity(opp)
        assert is_valid is False
        assert any("title" in e for e in errors)

    def test_whitespace_only_title_fails(self):
        opp = make_valid(title="   ")
        is_valid, errors = validate_opportunity(opp)
        assert is_valid is False

    def test_empty_source_name_fails(self):
        opp = make_valid(source_name="")
        is_valid, errors = validate_opportunity(opp)
        assert is_valid is False
        assert any("source_name" in e for e in errors)

    def test_empty_raw_source_id_fails(self):
        opp = make_valid(raw_source_id="")
        is_valid, errors = validate_opportunity(opp)
        assert is_valid is False
        assert any("raw_source_id" in e for e in errors)


class TestOpportunityType:
    def test_invalid_type_fails(self):
        opp = make_valid(opportunity_type="SEMINAR")
        is_valid, errors = validate_opportunity(opp)
        assert is_valid is False
        assert any("opportunity_type" in e for e in errors)

    def test_all_valid_types_pass(self):
        for t in ["CONFERENCE", "JOURNAL", "WORKSHOP", "CALL_FOR_PAPERS", "SPECIAL_ISSUE"]:
            opp = make_valid(opportunity_type=t)
            is_valid, _ = validate_opportunity(opp)
            assert is_valid is True, f"Expected {t} to be valid"


class TestDeliveryMode:
    def test_invalid_mode_fails(self):
        opp = make_valid(delivery_mode="IN_PERSON")
        is_valid, errors = validate_opportunity(opp)
        assert is_valid is False
        assert any("delivery_mode" in e for e in errors)

    def test_all_valid_modes_pass(self):
        for m in ["ONLINE", "OFFLINE", "HYBRID"]:
            opp = make_valid(delivery_mode=m)
            is_valid, _ = validate_opportunity(opp)
            assert is_valid is True


class TestURLValidation:
    def test_valid_https_url_passes(self):
        opp = make_valid(website_url="https://example.com/conference")
        is_valid, errors = validate_opportunity(opp)
        assert is_valid is True

    def test_valid_http_url_passes(self):
        opp = make_valid(website_url="http://conf.example.org")
        is_valid, errors = validate_opportunity(opp)
        assert is_valid is True

    def test_none_url_passes(self):
        opp = make_valid(website_url=None)
        is_valid, errors = validate_opportunity(opp)
        assert is_valid is True

    def test_ftp_url_fails(self):
        opp = make_valid(website_url="ftp://files.example.com")
        is_valid, errors = validate_opportunity(opp)
        assert is_valid is False
        assert any("website_url" in e for e in errors)

    def test_no_scheme_url_fails(self):
        opp = make_valid(website_url="example.com")
        is_valid, errors = validate_opportunity(opp)
        assert is_valid is False

    def test_junk_string_fails(self):
        opp = make_valid(website_url="not a url at all!!")
        is_valid, errors = validate_opportunity(opp)
        assert is_valid is False


class TestDateValidation:
    def test_future_deadline_passes(self):
        opp = make_valid(
            submission_deadline=datetime.now(tz=timezone.utc) + timedelta(days=30)
        )
        is_valid, _ = validate_opportunity(opp)
        assert is_valid is True

    def test_past_deadline_passes(self):
        # Past deadlines are still valid (expired events)
        opp = make_valid(
            submission_deadline=datetime(2024, 1, 15, tzinfo=timezone.utc)
        )
        is_valid, _ = validate_opportunity(opp)
        assert is_valid is True

    def test_deadline_before_2000_fails(self):
        opp = make_valid(
            submission_deadline=datetime(1999, 12, 31, tzinfo=timezone.utc)
        )
        is_valid, errors = validate_opportunity(opp)
        assert is_valid is False
        assert any("submission_deadline" in e and "2000" in e for e in errors)

    def test_deadline_more_than_6_years_future_fails(self):
        opp = make_valid(
            submission_deadline=datetime.now(tz=timezone.utc) + timedelta(days=365 * 7)
        )
        is_valid, errors = validate_opportunity(opp)
        assert is_valid is False

    def test_none_deadline_passes(self):
        opp = make_valid(submission_deadline=None)
        is_valid, _ = validate_opportunity(opp)
        assert is_valid is True


class TestEventDates:
    def test_start_after_end_fails(self):
        from datetime import date

        opp = make_valid(
            event_start_date=date(2026, 10, 25),
            event_end_date=date(2026, 10, 24),
        )
        is_valid, errors = validate_opportunity(opp)
        assert is_valid is False
        assert any("event_start_date" in e for e in errors)

    def test_start_equals_end_passes(self):
        from datetime import date

        opp = make_valid(
            event_start_date=date(2026, 10, 24),
            event_end_date=date(2026, 10, 24),
        )
        is_valid, _ = validate_opportunity(opp)
        assert is_valid is True


class TestMultipleErrors:
    def test_multiple_failures_reported_together(self):
        opp = make_valid(
            title="",
            source_name="",
            opportunity_type="UNKNOWN",
        )
        is_valid, errors = validate_opportunity(opp)
        assert is_valid is False
        assert len(errors) >= 3
