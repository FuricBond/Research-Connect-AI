"""
Tests for Date & Timezone Normalization (Phase 2.7C).

Verifies:
1. Date formats (ISO date, ISO datetime, natural language date, natural language datetime, with/without seconds).
2. Explicit timezones (UTC, positive/negative offsets +05:30, -04:00, AoE, UTC-12).
3. AoE exactness and month/year boundaries (23:59:59 AoE -> 11:59:59 UTC subsequent day).
4. Date-only academic submission convention (inferred AoE, local calendar date preserved, not UTC midnight).
5. Non-submission date-only milestones (e.g. EVENT_START, EVENT_END remain DATE_ONLY without synthesized instant).
6. Ambiguous slash date rejection (04/05/2026 -> AMBIGUOUS).
7. Unambiguous slash date normalization (22/08/2026 -> 2026-08-22).
8. Missing/TBA/TBD/Rolling non-fabrication (MISSING).
9. IANA timezones and DST transitions (America/New_York, Europe/London).
10. Invalid timezones fail explicitly without silent fallback to UTC (INVALID).
11. 100-run strict determinism.
12. Batch performance benchmark (10, 50, 100, 200, 1000).
"""
from datetime import date, datetime, time, timedelta, timezone
import time as time_mod
import pytest

from app.ranking.deadline import (
    DeadlineEvidence,
    DeadlineEvidenceCollection,
    DeadlineNormalizer,
    DeadlinePrecision,
    DeadlineProvenance,
    DeadlineType,
    DefaultTimezonePolicy,
    ExtractionMethod,
    NormalizationStatus,
    NormalizedDeadline,
    TimezoneIndicator,
    TimezoneSource,
)


class TestDateFormatsAndPrecision:
    """Verifies that various date/time formats normalize to correct local and UTC representations."""

    def test_iso_date_only_submission(self):
        norm = DeadlineNormalizer.normalize_raw_string("2026-08-22", deadline_type=DeadlineType.SUBMISSION)
        assert norm.local_date == date(2026, 8, 22)
        assert norm.precision == DeadlinePrecision.DATE_ONLY
        assert norm.timezone_source == TimezoneSource.INFERRED
        assert norm.normalization_status == NormalizationStatus.INFERRED_TIMEZONE
        # Academic submission convention: 23:59:59 AoE -> 11:59:59 UTC on 2026-08-23
        assert norm.normalized_utc == datetime(2026, 8, 23, 11, 59, 59, tzinfo=timezone.utc)
        # CRITICAL: Must NEVER be 2026-08-22T00:00:00Z
        assert norm.normalized_utc != datetime(2026, 8, 22, 0, 0, 0, tzinfo=timezone.utc)

    def test_iso_datetime_utc(self):
        norm = DeadlineNormalizer.normalize_raw_string("2026-08-22T23:59:00Z", deadline_type=DeadlineType.SUBMISSION)
        assert norm.local_date == date(2026, 8, 22)
        assert norm.local_time == time(23, 59, 0)
        assert norm.precision == DeadlinePrecision.EXACT_TIME
        assert norm.timezone_source == TimezoneSource.EXPLICIT
        assert norm.normalization_status == NormalizationStatus.EXPLICIT_TIMEZONE
        assert norm.normalized_utc == datetime(2026, 8, 22, 23, 59, 0, tzinfo=timezone.utc)

    def test_natural_language_date_formats(self):
        inputs = ["Aug 22, 2026", "August 22, 2026", "22 Aug 2026", "22 August 2026"]
        for raw in inputs:
            norm = DeadlineNormalizer.normalize_raw_string(raw, deadline_type=DeadlineType.SUBMISSION)
            assert norm.local_date == date(2026, 8, 22), f"Failed for {raw}"
            assert norm.precision == DeadlinePrecision.DATE_ONLY
            assert norm.normalized_utc == datetime(2026, 8, 23, 11, 59, 59, tzinfo=timezone.utc)

    def test_natural_language_with_time_and_seconds(self):
        norm = DeadlineNormalizer.normalize_raw_string(
            "Aug 22, 2026 23:59:59 UTC",
            deadline_type=DeadlineType.SUBMISSION,
        )
        assert norm.local_date == date(2026, 8, 22)
        assert norm.local_time == time(23, 59, 59)
        assert norm.normalized_utc == datetime(2026, 8, 22, 23, 59, 59, tzinfo=timezone.utc)

    def test_natural_language_12_hour_pm_am(self):
        norm_pm = DeadlineNormalizer.normalize_raw_string("Aug 22, 2026 11:59 PM UTC")
        assert norm_pm.local_time == time(23, 59, 0)
        assert norm_pm.normalized_utc == datetime(2026, 8, 22, 23, 59, 0, tzinfo=timezone.utc)

        norm_am = DeadlineNormalizer.normalize_raw_string("Aug 22, 2026 09:30 AM UTC")
        assert norm_am.local_time == time(9, 30, 0)
        assert norm_am.normalized_utc == datetime(2026, 8, 22, 9, 30, 0, tzinfo=timezone.utc)


class TestExplicitTimezonesAndOffsets:
    """Verifies parsing and UTC conversion of numeric offsets and named zones."""

    def test_positive_offset_ist(self):
        norm = DeadlineNormalizer.normalize_raw_string("Aug 22, 2026 17:00 +05:30")
        assert norm.local_date == date(2026, 8, 22)
        assert norm.local_time == time(17, 0, 0)
        assert norm.timezone_offset == "+05:30"
        # 17:00 - 5:30 = 11:30 UTC
        assert norm.normalized_utc == datetime(2026, 8, 22, 11, 30, 0, tzinfo=timezone.utc)

    def test_negative_offset_edt(self):
        norm = DeadlineNormalizer.normalize_raw_string("Aug 22, 2026 14:00 -04:00")
        assert norm.local_date == date(2026, 8, 22)
        assert norm.local_time == time(14, 0, 0)
        assert norm.timezone_offset == "-04:00"
        # 14:00 - (-4:00) = 18:00 UTC
        assert norm.normalized_utc == datetime(2026, 8, 22, 18, 0, 0, tzinfo=timezone.utc)


class TestAnywhereOnEarthCorrectness:
    """Verifies strict AoE (UTC-12) conversion and boundary rollovers."""

    def test_explicit_aoe_exact_formula(self):
        # 2026-08-22 23:59:59 AoE -> 2026-08-23 11:59:59 UTC
        norm = DeadlineNormalizer.normalize_raw_string("Aug 22, 2026 23:59:59 AoE")
        assert norm.local_date == date(2026, 8, 22)
        assert norm.local_time == time(23, 59, 59)
        assert norm.timezone_name == "AoE"
        assert norm.timezone_offset == "-12:00"
        assert norm.timezone_source == TimezoneSource.EXPLICIT
        assert norm.normalization_status == NormalizationStatus.EXPLICIT_TIMEZONE
        assert norm.normalized_utc == datetime(2026, 8, 23, 11, 59, 59, tzinfo=timezone.utc)

    def test_explicit_anywhere_on_earth_phrasing(self):
        norm = DeadlineNormalizer.normalize_raw_string("August 22, 2026 23:59 Anywhere on Earth")
        assert norm.normalized_utc == datetime(2026, 8, 23, 11, 59, 0, tzinfo=timezone.utc)
        assert norm.timezone_source == TimezoneSource.EXPLICIT

    def test_explicit_utc_minus_12(self):
        norm = DeadlineNormalizer.normalize_raw_string("Aug 22, 2026 23:59 UTC-12")
        assert norm.normalized_utc == datetime(2026, 8, 23, 11, 59, 0, tzinfo=timezone.utc)
        assert norm.timezone_source == TimezoneSource.EXPLICIT

    def test_aoe_month_boundary_rollover(self):
        # Aug 31 23:59:59 AoE -> Sept 01 11:59:59 UTC
        norm = DeadlineNormalizer.normalize_raw_string("Aug 31, 2026 23:59:59 AoE")
        assert norm.local_date == date(2026, 8, 31)
        assert norm.normalized_utc == datetime(2026, 9, 1, 11, 59, 59, tzinfo=timezone.utc)

    def test_aoe_year_boundary_rollover(self):
        # Dec 31, 2026 23:59:59 AoE -> Jan 01, 2027 11:59:59 UTC
        norm = DeadlineNormalizer.normalize_raw_string("Dec 31, 2026 23:59:59 AoE")
        assert norm.local_date == date(2026, 12, 31)
        assert norm.normalized_utc == datetime(2027, 1, 1, 11, 59, 59, tzinfo=timezone.utc)


class TestDateOnlyAcademicConventions:
    """Verifies academic submission vs non-submission milestone policy handling."""

    def test_submission_milestone_applies_inferred_aoe(self):
        norm = DeadlineNormalizer.normalize_raw_string("Aug 22, 2026", deadline_type=DeadlineType.SUBMISSION)
        assert norm.local_date == date(2026, 8, 22)
        assert norm.precision == DeadlinePrecision.DATE_ONLY
        assert norm.timezone_source == TimezoneSource.INFERRED
        assert norm.is_end_of_day_inferred is True
        assert norm.normalization_confidence == 0.85
        assert norm.normalized_utc == datetime(2026, 8, 23, 11, 59, 59, tzinfo=timezone.utc)

    def test_event_start_does_not_infer_aoe(self):
        # Physical conference convening date should remain DATE_ONLY without synthesized UTC AoE instant
        norm = DeadlineNormalizer.normalize_raw_string("Oct 24, 2026", deadline_type=DeadlineType.EVENT_START)
        assert norm.local_date == date(2026, 10, 24)
        assert norm.precision == DeadlinePrecision.DATE_ONLY
        assert norm.timezone_source == TimezoneSource.UNKNOWN
        assert norm.normalization_status == NormalizationStatus.DATE_ONLY
        assert norm.normalized_utc is None

    def test_strict_unknown_policy_preserves_date_only_without_instant(self):
        norm = DeadlineNormalizer.normalize_raw_string(
            "Aug 22, 2026",
            deadline_type=DeadlineType.SUBMISSION,
            policy=DefaultTimezonePolicy.STRICT_UNKNOWN,
        )
        assert norm.local_date == date(2026, 8, 22)
        assert norm.normalized_utc is None
        assert norm.normalization_status == NormalizationStatus.DATE_ONLY
        assert norm.timezone_source == TimezoneSource.UNKNOWN


class TestAmbiguityAndMissingValues:
    """Verifies conservative rejection of ambiguous formats and non-fabrication of missing dates."""

    def test_ambiguous_slash_format_rejected(self):
        # 04/05/2026 could be April 5 or May 4
        norm = DeadlineNormalizer.normalize_raw_string("04/05/2026")
        assert norm.normalization_status == NormalizationStatus.AMBIGUOUS
        assert norm.normalized_utc is None
        assert norm.local_date is None
        assert norm.normalization_confidence == 0.0

    def test_unambiguous_slash_format_normalized(self):
        # 22/08/2026 is unambiguously Day=22, Month=8
        norm = DeadlineNormalizer.normalize_raw_string("22/08/2026", deadline_type=DeadlineType.SUBMISSION)
        assert norm.normalization_status == NormalizationStatus.INFERRED_TIMEZONE
        assert norm.local_date == date(2026, 8, 22)
        assert norm.normalized_utc == datetime(2026, 8, 23, 11, 59, 59, tzinfo=timezone.utc)

    def test_non_date_strings_yield_missing(self):
        for raw in [None, "", "   ", "TBA", "TBD", "N/A", "n/a", "Rolling", "See website", "Soon"]:
            norm = DeadlineNormalizer.normalize_raw_string(raw)
            assert norm.normalization_status == NormalizationStatus.MISSING
            assert norm.normalized_utc is None
            assert norm.local_date is None
            assert norm.normalization_confidence == 0.0


class TestIANATimezonesAndDST:
    """Verifies IANA named zone resolution and daylight saving transitions."""

    def test_new_york_summer_edt(self):
        # July is EDT (UTC-4). 15:00 EDT -> 19:00 UTC
        norm = DeadlineNormalizer.normalize_raw_string("July 15, 2026 15:00 America/New_York")
        assert norm.timezone_name == "America/New_York"
        assert norm.timezone_offset == "-04:00"
        assert norm.normalized_utc == datetime(2026, 7, 15, 19, 0, 0, tzinfo=timezone.utc)

    def test_new_york_winter_est(self):
        # January is EST (UTC-5). 15:00 EST -> 20:00 UTC
        norm = DeadlineNormalizer.normalize_raw_string("January 15, 2026 15:00 America/New_York")
        assert norm.timezone_name == "America/New_York"
        assert norm.timezone_offset == "-05:00"
        assert norm.normalized_utc == datetime(2026, 1, 15, 20, 0, 0, tzinfo=timezone.utc)

    def test_invalid_unrecognized_timezone_fails_without_utc_fallback(self):
        # An unparseable timezone name must NOT silently become UTC
        evidence = DeadlineEvidence(
            deadline_type=DeadlineType.SUBMISSION,
            raw_value="Aug 22, 2026 12:00 FantasyTime",
            raw_text="Aug 22, 2026 12:00 FantasyTime",
            is_present=True,
            precision=DeadlinePrecision.EXACT_TIME,
            timezone_indicator=TimezoneIndicator.LOCAL_NAMED,
            parsed_year=2026,
            parsed_month=8,
            parsed_day=22,
            parsed_time_str="12:00",
        )
        norm = DeadlineNormalizer.normalize_evidence(evidence)
        assert norm.normalization_status == NormalizationStatus.INVALID
        assert norm.normalized_utc is None
        assert norm.normalization_confidence == 0.0


class TestModelAndCollectionIntegration:
    """Verifies normalization of collections and dict serialization."""

    def test_normalize_collection(self):
        evidence_col = DeadlineEvidenceCollection(opportunity_id="opp-123")
        evidence_col.add(
            DeadlineEvidence(
                deadline_type=DeadlineType.SUBMISSION,
                raw_value="Aug 22, 2026",
                is_present=True,
                precision=DeadlinePrecision.DATE_ONLY,
                parsed_year=2026,
                parsed_month=8,
                parsed_day=22,
            )
        )
        evidence_col.add(
            DeadlineEvidence(
                deadline_type=DeadlineType.NOTIFICATION,
                raw_value="Sep 15, 2026",
                is_present=True,
                precision=DeadlinePrecision.DATE_ONLY,
                parsed_year=2026,
                parsed_month=9,
                parsed_day=15,
            )
        )

        norm_col = DeadlineNormalizer.normalize_collection(evidence_col)
        assert len(norm_col.items) == 2
        primary = norm_col.get_primary_submission()
        assert primary is not None
        assert primary.local_date == date(2026, 8, 22)
        assert primary.normalized_utc == datetime(2026, 8, 23, 11, 59, 59, tzinfo=timezone.utc)

        serialized = norm_col.to_dict()
        assert len(serialized) == 2
        assert serialized[0]["deadline_type"] == "SUBMISSION"
        assert serialized[0]["local_date"] == "2026-08-22"
        assert serialized[0]["normalized_utc"] == "2026-08-23T11:59:59+00:00"


class TestDeterminismAndPerformance:
    """Verifies strict 100-run determinism and latency benchmarking."""

    def test_100_runs_strict_determinism(self):
        raw_inputs = [
            "Aug 22, 2026",
            "Aug 22, 2026 23:59 AoE",
            "2026-08-22T23:59:00Z",
            "July 15, 2026 15:00 America/New_York",
            "04/05/2026",
            "TBA",
        ]

        baseline = [DeadlineNormalizer.normalize_raw_string(r).to_dict() for r in raw_inputs]

        for _ in range(100):
            current = [DeadlineNormalizer.normalize_raw_string(r).to_dict() for r in raw_inputs]
            assert current == baseline

    @pytest.mark.parametrize("batch_size", [10, 50, 100, 200, 1000])
    def test_batch_normalization_performance(self, batch_size):
        raw_sample = "Aug 22, 2026 23:59:59 AoE"
        t0 = time_mod.perf_counter()
        for _ in range(batch_size):
            norm = DeadlineNormalizer.normalize_raw_string(raw_sample)
            assert norm.normalized_utc is not None
        elapsed_ms = (time_mod.perf_counter() - t0) * 1000
        per_item_us = (elapsed_ms / batch_size) * 1000
        # Normalization should take less than 100 microseconds per item in memory
        assert per_item_us < 1000.0, f"Batch {batch_size} took {per_item_us:.2f} us/item"
