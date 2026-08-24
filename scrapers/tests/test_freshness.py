"""
Tests for opportunity freshness tracking and staleness calculation.
"""
from datetime import datetime, timedelta, timezone

from scrapers.freshness.manager import get_freshness_summary, is_opportunity_stale


class TestFreshnessManager:
    def test_recent_opportunity_is_not_stale(self):
        now = datetime(2026, 8, 24, 12, 0, 0, tzinfo=timezone.utc)
        last_seen = now - timedelta(days=5)
        assert is_opportunity_stale(last_seen, stale_threshold_days=30, now=now) is False

    def test_opportunity_older_than_threshold_is_stale(self):
        now = datetime(2026, 8, 24, 12, 0, 0, tzinfo=timezone.utc)
        last_seen = now - timedelta(days=35)
        assert is_opportunity_stale(last_seen, stale_threshold_days=30, now=now) is True

    def test_never_seen_opportunity_is_stale(self):
        assert is_opportunity_stale(None) is True

    def test_get_freshness_summary(self):
        now = datetime(2026, 8, 24, 12, 0, 0, tzinfo=timezone.utc)
        record = {
            "created_at": now - timedelta(days=40),
            "last_seen_at": now - timedelta(days=2),
            "last_verified_at": now - timedelta(days=2),
        }
        summary = get_freshness_summary(record, stale_threshold_days=30, now=now)
        assert summary["is_stale"] is False
        assert summary["first_discovered_at"] == record["created_at"]
        assert summary["last_seen_at"] == record["last_seen_at"]
