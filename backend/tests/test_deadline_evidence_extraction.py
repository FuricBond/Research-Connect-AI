"""
Unit and integration tests for Deadline Evidence Extraction (Phase 2.7B).

Verifies:
1. Extraction of distinct milestones: submission, abstract, notification, camera-ready, registration, event dates.
2. Exact raw value preservation without premature UTC midnight coercion.
3. Explicit AoE indicator preservation without premature timezone conversion.
4. Precision tracking: DATE_ONLY vs EXACT_TIME vs YEAR_MONTH.
5. Missing, TBA, TBD, and N/A conservative handling.
6. Ambiguous date formatting detection.
7. Extraction from OpportunityModel, RawOpportunity, milestone dicts, and free text.
8. Strict 100-run determinism.
"""
from datetime import date, datetime, timezone
import pytest

from app.ranking.deadline import (
    DeadlineEvidence,
    DeadlineEvidenceCollection,
    DeadlineEvidenceExtractor,
    DeadlinePrecision,
    DeadlineProvenance,
    DeadlineType,
    ExtractionMethod,
    TimezoneIndicator,
    parse_raw_date_components,
)
from scrapers.models import RawOpportunity


class TestRawDateParsing:
    """Verifies that date components and timezone indicators are extracted without premature coercion."""

    def test_date_only_preserves_date_only_precision(self):
        yr, mo, dy, tm, prec, tz_ind, is_pres, is_ambig = parse_raw_date_components("Aug 22, 2026")
        assert yr == 2026
        assert mo == 8
        assert dy == 22
        assert tm is None
        assert prec == DeadlinePrecision.DATE_ONLY
        assert tz_ind == TimezoneIndicator.UNSPECIFIED
        assert is_pres is True
        assert is_ambig is False

    def test_explicit_time_preserves_exact_time_precision(self):
        yr, mo, dy, tm, prec, tz_ind, is_pres, is_ambig = parse_raw_date_components("Aug 22, 2026 23:59")
        assert yr == 2026
        assert mo == 8
        assert dy == 22
        assert tm == "23:59"
        assert prec == DeadlinePrecision.EXACT_TIME
        assert tz_ind == TimezoneIndicator.UNSPECIFIED
        assert is_pres is True

    def test_explicit_aoe_indicator_preserved_without_conversion(self):
        yr, mo, dy, tm, prec, tz_ind, is_pres, is_ambig = parse_raw_date_components("Aug 22, 2026 23:59 AoE")
        assert yr == 2026
        assert mo == 8
        assert dy == 22
        assert tm == "23:59"
        assert prec == DeadlinePrecision.EXACT_TIME
        assert tz_ind == TimezoneIndicator.EXPLICIT_AOE
        # CRITICAL: Day is still 22, NOT converted to 23 or UTC!
        assert dy == 22

    def test_explicit_utc_and_offset_indicators(self):
        _, _, _, _, _, tz_utc, _, _ = parse_raw_date_components("Sep 15, 2026 18:00 UTC")
        assert tz_utc == TimezoneIndicator.EXPLICIT_UTC

        _, _, _, _, _, tz_off, _, _ = parse_raw_date_components("Sep 15, 2026 18:00 +05:30")
        assert tz_off == TimezoneIndicator.EXPLICIT_OFFSET

        _, _, _, _, _, tz_loc, _, _ = parse_raw_date_components("Sep 15, 2026 18:00 EST")
        assert tz_loc == TimezoneIndicator.LOCAL_NAMED

    def test_iso_date_format(self):
        yr, mo, dy, tm, prec, tz_ind, is_pres, is_ambig = parse_raw_date_components("2026-11-05")
        assert yr == 2026
        assert mo == 11
        assert dy == 5
        assert prec == DeadlinePrecision.DATE_ONLY
        assert is_ambig is False

    def test_ambiguous_slash_format(self):
        yr, mo, dy, tm, prec, tz_ind, is_pres, is_ambig = parse_raw_date_components("04/05/2026")
        assert yr == 2026
        assert is_pres is True
        # Both 4 and 5 are <= 12, so inherently ambiguous between MM/DD and DD/MM
        assert is_ambig is True

    def test_unambiguous_slash_format(self):
        yr, mo, dy, tm, prec, tz_ind, is_pres, is_ambig = parse_raw_date_components("25/08/2026")
        assert yr == 2026
        assert mo == 8
        assert dy == 25
        assert is_ambig is False

    def test_non_date_strings_marked_not_present(self):
        for raw in ["TBA", "TBD", "N/A", "NA", "None", "Rolling", "See website", "soon"]:
            yr, mo, dy, tm, prec, tz_ind, is_pres, is_ambig = parse_raw_date_components(raw)
            assert is_pres is False
            assert yr is None

    def test_none_and_empty_strings(self):
        yr, mo, dy, tm, prec, tz_ind, is_pres, is_ambig = parse_raw_date_components(None)
        assert is_pres is False
        assert yr is None

        yr, mo, dy, tm, prec, tz_ind, is_pres, is_ambig = parse_raw_date_components("   ")
        assert is_pres is False


class TestMilestoneExtraction:
    """Verifies multi-milestone extraction from WikiCFP detail dictionaries and unstructured text."""

    def test_extract_all_milestones_from_dict(self):
        milestones = {
            "Abstract Registration Due": "Aug 10, 2026",
            "Submission Deadline": "Aug 22, 2026 23:59 AoE",
            "Notification Due": "Sep 15, 2026",
            "Final Version Due": "Oct 1, 2026",
            "Author Registration": "Oct 10, 2026",
            "When": "Oct 24, 2026 - Oct 25, 2026",
        }

        coll = DeadlineEvidenceExtractor.extract_from_milestone_dict(milestones, source="wikicfp")
        assert len(coll.items) == 7  # Abstract, Submission, Notification, CameraReady, Registration, EventStart, EventEnd

        # Check Abstract
        abstracts = coll.get_by_type(DeadlineType.ABSTRACT)
        assert len(abstracts) == 1
        assert abstracts[0].raw_value == "Aug 10, 2026"
        assert abstracts[0].parsed_month == 8
        assert abstracts[0].parsed_day == 10

        # Check Submission
        sub = coll.get_primary_submission_deadline()
        assert sub is not None
        assert sub.deadline_type == DeadlineType.SUBMISSION
        assert sub.raw_value == "Aug 22, 2026 23:59 AoE"
        assert sub.timezone_indicator == TimezoneIndicator.EXPLICIT_AOE
        assert sub.precision == DeadlinePrecision.EXACT_TIME

        # Check Notification
        notifs = coll.get_by_type(DeadlineType.NOTIFICATION)
        assert len(notifs) == 1
        assert notifs[0].parsed_month == 9
        assert notifs[0].parsed_day == 15

        # Check Camera-Ready
        cams = coll.get_by_type(DeadlineType.CAMERA_READY)
        assert len(cams) == 1
        assert cams[0].parsed_month == 10
        assert cams[0].parsed_day == 1

        # Check Registration
        regs = coll.get_by_type(DeadlineType.REGISTRATION)
        assert len(regs) == 1
        assert regs[0].parsed_month == 10
        assert regs[0].parsed_day == 10

        # Check Event Dates
        assert coll.has_type(DeadlineType.EVENT_START)
        assert coll.has_type(DeadlineType.EVENT_END)

    def test_milestone_isolation_invariant(self):
        """Ensures that milestones are never substituted for one another."""
        milestones = {
            "Abstract Registration Due": "Aug 10, 2026",
            "Notification Due": "Sep 15, 2026",
        }
        coll = DeadlineEvidenceExtractor.extract_from_milestone_dict(milestones)
        assert coll.has_type(DeadlineType.ABSTRACT) is True
        assert coll.has_type(DeadlineType.NOTIFICATION) is True
        # Submission deadline must NOT be silently populated from abstract or notification!
        assert coll.has_type(DeadlineType.SUBMISSION) is False
        assert coll.get_primary_submission_deadline() is None

    def test_extract_from_unstructured_text(self):
        cfp_text = """
        Call for Papers:
        Please note the following important dates:
        Abstract Submission: July 15, 2026
        Paper Submission Deadline: August 1, 2026 23:59 AoE
        Acceptance Notification: September 20, 2026
        Camera-Ready Due: October 5, 2026
        Early Bird Registration: October 12, 2026
        """
        coll = DeadlineEvidenceExtractor.extract_from_text(cfp_text, source="cfp_text")
        assert coll.has_type(DeadlineType.ABSTRACT) is True
        assert coll.has_type(DeadlineType.SUBMISSION) is True
        assert coll.has_type(DeadlineType.NOTIFICATION) is True
        assert coll.has_type(DeadlineType.CAMERA_READY) is True
        assert coll.has_type(DeadlineType.REGISTRATION) is True

        sub = coll.get_primary_submission_deadline()
        assert sub is not None
        assert "August 1, 2026" in sub.raw_value
        assert sub.timezone_indicator == TimezoneIndicator.EXPLICIT_AOE


class TestModelAndScraperIntegration:
    """Verifies extraction from existing OpportunityModel and RawOpportunity data structures."""

    def test_extract_from_raw_opportunity(self):
        raw_opp = RawOpportunity(
            source_name="WikiCFP",
            raw_source_id="195331",
            source_url="http://www.wikicfp.com/cfp/servlet/event.showcfp?eventid=195331",
            title="International Conference on AI",
            raw_submission_deadline="Aug 22, 2026",
            raw_event_dates="Oct 24, 2026 - Oct 25, 2026",
        )
        coll = DeadlineEvidenceExtractor.extract_from_raw_opportunity(raw_opp)
        assert coll.has_type(DeadlineType.SUBMISSION) is True
        assert coll.has_type(DeadlineType.EVENT_START) is True
        assert coll.has_type(DeadlineType.EVENT_END) is True

        sub = coll.get_primary_submission_deadline()
        assert sub.raw_value == "Aug 22, 2026"
        assert sub.provenance == DeadlineProvenance.WIKICFP_LIST_PAGE
        assert sub.precision == DeadlinePrecision.DATE_ONLY
        assert sub.parsed_year == 2026
        assert sub.parsed_month == 8
        assert sub.parsed_day == 22

    def test_extract_from_opportunity_model_dict(self):
        opp_dict = {
            "id": "12345678-1234-5678-1234-567812345678",
            "title": "Machine Learning Workshop",
            "submission_deadline": datetime(2026, 8, 22, 0, 0, 0, tzinfo=timezone.utc),
            "notification_date": datetime(2026, 9, 15, 0, 0, 0, tzinfo=timezone.utc),
            "camera_ready_deadline": datetime(2026, 10, 1, 0, 0, 0, tzinfo=timezone.utc),
            "event_start_date": date(2026, 10, 24),
            "event_end_date": date(2026, 10, 25),
        }
        coll = DeadlineEvidenceExtractor.extract_from_opportunity_model(opp_dict)
        assert coll.opportunity_id == "12345678-1234-5678-1234-567812345678"
        assert coll.has_type(DeadlineType.SUBMISSION) is True
        assert coll.has_type(DeadlineType.NOTIFICATION) is True
        assert coll.has_type(DeadlineType.CAMERA_READY) is True
        assert coll.has_type(DeadlineType.EVENT_START) is True
        assert coll.has_type(DeadlineType.EVENT_END) is True

        sub = coll.get_primary_submission_deadline()
        assert sub.provenance == DeadlineProvenance.DATABASE_RECORD
        assert sub.parsed_year == 2026
        assert sub.parsed_month == 8
        assert sub.parsed_day == 22


class TestDeterminismAndSerialization:
    """Verifies strict determinism across repeated executions and JSON serialization."""

    def test_100_runs_strict_determinism(self):
        text = "Submission Deadline: Aug 22, 2026 23:59 AoE\nNotification: Sep 15, 2026"
        first_res = DeadlineEvidenceExtractor.extract_from_text(text).to_dict()

        for _ in range(100):
            repeated = DeadlineEvidenceExtractor.extract_from_text(text).to_dict()
            assert repeated == first_res

    def test_evidence_item_to_dict(self):
        ev = DeadlineEvidence(
            deadline_type=DeadlineType.SUBMISSION,
            raw_value="Aug 22, 2026",
            source="wikicfp",
            source_field="submission_deadline",
            extraction_method=ExtractionMethod.DIRECT_FIELD,
            confidence=1.0,
            provenance=DeadlineProvenance.WIKICFP_LIST_PAGE,
            is_present=True,
            precision=DeadlinePrecision.DATE_ONLY,
            timezone_indicator=TimezoneIndicator.UNSPECIFIED,
            parsed_year=2026,
            parsed_month=8,
            parsed_day=22,
        )
        d = ev.to_dict()
        assert d["deadline_type"] == "SUBMISSION"
        assert d["raw_value"] == "Aug 22, 2026"
        assert d["precision"] == "DATE_ONLY"
        assert d["timezone_indicator"] == "UNSPECIFIED"
        assert d["parsed_year"] == 2026
        assert d["parsed_month"] == 8
        assert d["parsed_day"] == 22
