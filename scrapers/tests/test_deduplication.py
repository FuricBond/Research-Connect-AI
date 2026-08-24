"""
Tests for the DuplicateDetector.
"""
from datetime import datetime, timezone
from scrapers.deduplication.detector import DuplicateDetector, _fingerprint_url
from scrapers.models import DuplicateClassification, NormalizedOpportunity


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
    )
    defaults.update(kwargs)
    return NormalizedOpportunity(**defaults)


class TestFingerprintUrl:
    def test_same_url_same_fingerprint(self):
        fp1 = _fingerprint_url("https://example.com/conf")
        fp2 = _fingerprint_url("https://example.com/conf")
        assert fp1 == fp2

    def test_trailing_slash_stripped(self):
        fp1 = _fingerprint_url("https://example.com/conf")
        fp2 = _fingerprint_url("https://example.com/conf/")
        assert fp1 == fp2

    def test_case_insensitive(self):
        fp1 = _fingerprint_url("https://EXAMPLE.COM/conf")
        fp2 = _fingerprint_url("https://example.com/conf")
        assert fp1 == fp2

    def test_none_returns_none(self):
        assert _fingerprint_url(None) is None

    def test_different_urls_different_fingerprints(self):
        fp1 = _fingerprint_url("https://example.com/conf1")
        fp2 = _fingerprint_url("https://example.com/conf2")
        assert fp1 != fp2


class TestDuplicateDetector:
    def test_new_opportunity_is_unique(self):
        detector = DuplicateDetector()
        opp = make_opp()
        result = detector.check(opp)
        assert result.classification == DuplicateClassification.UNIQUE
        assert result.is_duplicate is False
        assert result.is_potential_duplicate is False

    def test_registered_opportunity_is_tier1_confirmed_duplicate(self):
        detector = DuplicateDetector()
        opp = make_opp()
        detector.register(opp)
        result = detector.check(opp)
        assert result.classification == DuplicateClassification.CONFIRMED_DUPLICATE
        assert result.is_duplicate is True
        assert result.tier == 1

    def test_same_url_different_source_id_is_tier2_confirmed_duplicate(self):
        detector = DuplicateDetector()
        opp1 = make_opp(raw_source_id="111", website_url="https://conf2026.example.com")
        opp2 = make_opp(raw_source_id="222", website_url="https://conf2026.example.com")
        detector.register(opp1)
        result = detector.check(opp2)
        assert result.classification == DuplicateClassification.CONFIRMED_DUPLICATE
        assert result.is_duplicate is True
        assert result.tier == 2

    def test_different_source_id_different_url_is_unique(self):
        detector = DuplicateDetector()
        opp1 = make_opp(raw_source_id="111", website_url="https://conf-a.example.com")
        opp2 = make_opp(raw_source_id="222", website_url="https://conf-b.example.com")
        detector.register(opp1)
        result = detector.check(opp2)
        assert result.classification == DuplicateClassification.UNIQUE
        assert result.is_duplicate is False

    def test_same_title_same_deadline_is_tier3_potential_duplicate(self):
        deadline = datetime(2026, 8, 22, tzinfo=timezone.utc)
        detector = DuplicateDetector()
        opp1 = make_opp(raw_source_id="111", title="AI Conference 2026", submission_deadline=deadline)
        opp2 = make_opp(raw_source_id="222", title="AI Conference 2026", submission_deadline=deadline)
        detector.register(opp1)
        result = detector.check(opp2)
        assert result.classification == DuplicateClassification.POTENTIAL_DUPLICATE
        assert result.is_potential_duplicate is True
        assert result.is_duplicate is False
        assert result.tier == 3

    def test_same_title_different_deadline_is_not_duplicate(self):
        from datetime import timedelta

        deadline1 = datetime(2026, 8, 22, tzinfo=timezone.utc)
        deadline2 = deadline1 + timedelta(days=30)
        detector = DuplicateDetector()
        opp1 = make_opp(raw_source_id="111", title="AI Conference", submission_deadline=deadline1)
        opp2 = make_opp(raw_source_id="222", title="AI Conference", submission_deadline=deadline2)
        detector.register(opp1)
        result = detector.check(opp2)
        assert result.classification == DuplicateClassification.UNIQUE

    def test_no_url_no_tier2_duplicate(self):
        detector = DuplicateDetector()
        opp1 = make_opp(raw_source_id="111", website_url=None)
        opp2 = make_opp(raw_source_id="222", website_url=None)
        detector.register(opp1)
        result = detector.check(opp2)
        assert result.classification == DuplicateClassification.UNIQUE

    def test_reset_clears_all_seen_records(self):
        detector = DuplicateDetector()
        opp = make_opp()
        detector.register(opp)
        assert detector.seen_count == 1
        detector.reset()
        assert detector.seen_count == 0
        result = detector.check(opp)
        assert result.classification == DuplicateClassification.UNIQUE

    def test_seen_count_increments(self):
        detector = DuplicateDetector()
        detector.register(make_opp(raw_source_id="1"))
        detector.register(make_opp(raw_source_id="2"))
        assert detector.seen_count == 2

    def test_multiple_registrations_same_id_dont_double_count(self):
        detector = DuplicateDetector()
        opp = make_opp()
        detector.register(opp)
        detector.register(opp)
        assert detector.seen_count == 1

    def test_url_trailing_slash_treated_as_same(self):
        detector = DuplicateDetector()
        opp1 = make_opp(raw_source_id="111", website_url="https://conf.example.com/")
        opp2 = make_opp(raw_source_id="222", website_url="https://conf.example.com")
        detector.register(opp1)
        result = detector.check(opp2)
        assert result.classification == DuplicateClassification.CONFIRMED_DUPLICATE
        assert result.tier == 2
