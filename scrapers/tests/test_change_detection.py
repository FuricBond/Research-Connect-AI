"""
Tests for opportunity change detection engine.
"""
from datetime import date, datetime, timezone
from scrapers.change_detection.detector import detect_changes
from scrapers.models import NormalizedOpportunity


def make_norm(**kwargs) -> NormalizedOpportunity:
    defaults = dict(
        source_name="WikiCFP",
        raw_source_id="12345",
        source_url="http://www.wikicfp.com/cfp/servlet/event.showcfp?eventid=12345",
        title="International Conference on AI",
        abbreviation="ICAI 2026",
        opportunity_type="CONFERENCE",
        website_url="https://icai2026.org",
        submission_deadline=datetime(2026, 8, 22, tzinfo=timezone.utc),
        event_start_date=date(2026, 10, 24),
        event_end_date=date(2026, 10, 25),
        location="Vienna, Austria",
        delivery_mode="OFFLINE",
    )
    defaults.update(kwargs)
    return NormalizedOpportunity(**defaults)


class TestDetectChanges:
    def test_identical_records_show_no_changes(self):
        norm = make_norm()
        existing = {
            "title": "International Conference on AI",
            "opportunity_type": "CONFERENCE",
            "publisher": None,
            "organizer": None,
            "summary": None,
            "description": None,
            "website_url": "https://icai2026.org",
            "delivery_mode": "OFFLINE",
            "location": "Vienna, Austria",
            "submission_deadline": datetime(2026, 8, 22, tzinfo=timezone.utc),
            "event_start_date": date(2026, 10, 24),
            "event_end_date": date(2026, 10, 25),
            "indexing": None,
            "apc_or_fee": None,
        }
        res = detect_changes(existing, norm)
        assert res.has_changed is False
        assert len(res.changes) == 0

    def test_deadline_change_detected(self):
        existing = {
            "title": "International Conference on AI",
            "submission_deadline": datetime(2026, 8, 22, tzinfo=timezone.utc),
        }
        new_deadline = datetime(2026, 9, 1, tzinfo=timezone.utc)
        norm = make_norm(submission_deadline=new_deadline)

        res = detect_changes(existing, norm)
        assert res.has_changed is True
        deadline_change = next(c for c in res.changes if c.field_name == "submission_deadline")
        assert deadline_change.old_value == datetime(2026, 8, 22, tzinfo=timezone.utc)
        assert deadline_change.new_value == new_deadline

    def test_title_change_detected(self):
        existing = {"title": "Old Conference Title"}
        norm = make_norm(title="New Extended Conference Title")

        res = detect_changes(existing, norm)
        assert res.has_changed is True
        title_change = next(c for c in res.changes if c.field_name == "title")
        assert title_change.old_value == "Old Conference Title"
        assert title_change.new_value == "New Extended Conference Title"

    def test_location_and_delivery_mode_change_detected(self):
        existing = {
            "location": "Vienna, Austria",
            "delivery_mode": "OFFLINE",
        }
        norm = make_norm(location="Online", delivery_mode="ONLINE")

        res = detect_changes(existing, norm)
        assert res.has_changed is True
        changed_fields = {c.field_name for c in res.changes}
        assert "location" in changed_fields
        assert "delivery_mode" in changed_fields

    def test_incoming_none_does_not_overwrite_existing_value(self):
        """If incoming list-page scraped record has None for description, existing description is preserved."""
        norm = make_norm(description=None)
        existing = {
            "title": norm.title,
            "opportunity_type": norm.opportunity_type,
            "publisher": norm.publisher,
            "organizer": norm.organizer,
            "summary": norm.summary,
            "description": "Full conference call for papers text.",
            "website_url": norm.website_url,
            "delivery_mode": norm.delivery_mode,
            "location": norm.location,
            "submission_deadline": norm.submission_deadline,
            "event_start_date": norm.event_start_date,
            "event_end_date": norm.event_end_date,
            "indexing": norm.indexing,
            "apc_or_fee": norm.apc_or_fee,
        }

        res = detect_changes(existing, norm)
        assert res.has_changed is False
