"""
Tests for deterministic opportunity expiration management.
"""
from datetime import date, datetime, timedelta, timezone

from scrapers.expiration.manager import (
    apply_expiration_status,
    is_opportunity_expired,
)
from scrapers.models import NormalizedOpportunity


def make_opp(**kwargs) -> NormalizedOpportunity:
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
        status="ACTIVE",
    )
    defaults.update(kwargs)
    return NormalizedOpportunity(**defaults)


class TestExpirationLogic:
    def test_future_deadline_is_not_expired(self):
        now = datetime(2026, 8, 24, 12, 0, 0, tzinfo=timezone.utc)
        opp = make_opp(submission_deadline=now + timedelta(days=10))
        assert is_opportunity_expired(opp, now=now) is False

    def test_past_deadline_is_expired(self):
        now = datetime(2026, 8, 24, 12, 0, 0, tzinfo=timezone.utc)
        opp = make_opp(submission_deadline=now - timedelta(days=2))
        assert is_opportunity_expired(opp, now=now) is True

    def test_past_event_end_date_without_deadline_is_expired(self):
        now = datetime(2026, 8, 24, 12, 0, 0, tzinfo=timezone.utc)
        opp = make_opp(
            submission_deadline=None,
            event_start_date=date(2026, 8, 10),
            event_end_date=date(2026, 8, 20),
        )
        assert is_opportunity_expired(opp, now=now) is True

    def test_future_event_date_without_deadline_is_not_expired(self):
        now = datetime(2026, 8, 24, 12, 0, 0, tzinfo=timezone.utc)
        opp = make_opp(
            submission_deadline=None,
            event_start_date=date(2026, 9, 1),
            event_end_date=date(2026, 9, 5),
        )
        assert is_opportunity_expired(opp, now=now) is False

    def test_apply_expiration_status_updates_active_record(self):
        now = datetime(2026, 8, 24, 12, 0, 0, tzinfo=timezone.utc)
        opp = make_opp(
            submission_deadline=now - timedelta(days=1),
            status="ACTIVE",
        )
        changed = apply_expiration_status(opp, now=now)
        assert changed is True
        assert opp.status == "EXPIRED"

    def test_apply_expiration_status_ignores_already_expired_or_archived(self):
        now = datetime(2026, 8, 24, 12, 0, 0, tzinfo=timezone.utc)
        opp = make_opp(
            submission_deadline=now - timedelta(days=1),
            status="ARCHIVED",
        )
        changed = apply_expiration_status(opp, now=now)
        assert changed is False
        assert opp.status == "ARCHIVED"
