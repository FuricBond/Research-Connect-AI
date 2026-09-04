"""
Unit tests for Deadline Intelligence and Urgency Engine (Phase 2.7D).

Validates:
1. Lifecycle-independent temporal status (UPCOMING, DUE_TODAY, EXPIRED, MISSING, INVALID, AMBIGUOUS).
2. Urgency tiers (CRITICAL, URGENT, APPROACHING, DISTANT, DUE_TODAY, EXPIRED, UNKNOWN).
3. Urgency score properties (bounded in [0.0, 1.0], monotonic approach, no fabrication).
4. Exact elapsed time calculations (seconds, minutes, hours, days remaining).
5. Due-today calendar day semantics.
6. Expired semantics (< 0 seconds remaining).
7. AoE cross-boundary handling (regular dates, month rollover, year rollover).
8. DST handling with IANA timezones.
9. Milestone independence (no collapsing milestones).
10. Primary deadline selection precedence.
11. Deadline confidence scoring.
12. Structured deterministic explanations.
13. 100-run determinism test.
14. Benchmark performance across candidate counts (10, 50, 100, 200, 1000 items).
15. Backward compatibility with calculate_urgency().
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import time as pytime
import pytest

from app.ranking.deadline import (
    DEFAULT_APPROACHING_WINDOW_DAYS,
    DEFAULT_CRITICAL_WINDOW_DAYS,
    DEFAULT_MAX_URGENCY_WINDOW_DAYS,
    DEFAULT_URGENT_WINDOW_DAYS,
    DeadlineAssessment,
    DeadlineIntelligence,
    DeadlineNormalizer,
    DeadlinePrecision,
    DeadlineTemporalStatus,
    DeadlineType,
    DefaultTimezonePolicy,
    NormalizationStatus,
    NormalizedDeadline,
    NormalizedDeadlineCollection,
    OpportunityDeadlineAssessment,
    TimezoneSource,
    UrgencyTier,
)
from app.ranking.signals import calculate_urgency


class TestDeadlineTemporalStatus:
    """Test lifecycle-independent temporal status classification."""

    def test_upcoming_status(self):
        ref = datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc)
        deadline_dt = datetime(2026, 8, 25, 12, 0, 0, tzinfo=timezone.utc)
        norm = NormalizedDeadline(
            deadline_type=DeadlineType.SUBMISSION,
            normalized_utc=deadline_dt,
            normalization_status=NormalizationStatus.NORMALIZED,
            timezone_source=TimezoneSource.EXPLICIT,
        )
        assessment = DeadlineIntelligence.assess_deadline(norm, reference_time=ref)
        assert assessment.status == DeadlineTemporalStatus.UPCOMING
        assert assessment.seconds_remaining == 5 * 86400
        assert assessment.days_remaining == 5.0
        assert assessment.is_expired() is False

    def test_due_today_status(self):
        ref = datetime(2026, 8, 22, 10, 0, 0, tzinfo=timezone.utc)
        deadline_dt = datetime(2026, 8, 22, 23, 59, 59, tzinfo=timezone.utc)
        norm = NormalizedDeadline(
            deadline_type=DeadlineType.SUBMISSION,
            normalized_utc=deadline_dt,
            normalization_status=NormalizationStatus.NORMALIZED,
            timezone_source=TimezoneSource.EXPLICIT,
        )
        assessment = DeadlineIntelligence.assess_deadline(norm, reference_time=ref)
        assert assessment.status == DeadlineTemporalStatus.DUE_TODAY
        assert assessment.urgency_tier == UrgencyTier.DUE_TODAY
        assert assessment.seconds_remaining > 0
        assert assessment.is_expired() is False

    def test_expired_status(self):
        ref = datetime(2026, 8, 22, 10, 0, 0, tzinfo=timezone.utc)
        deadline_dt = datetime(2026, 8, 21, 23, 59, 59, tzinfo=timezone.utc)
        norm = NormalizedDeadline(
            deadline_type=DeadlineType.SUBMISSION,
            normalized_utc=deadline_dt,
            normalization_status=NormalizationStatus.NORMALIZED,
            timezone_source=TimezoneSource.EXPLICIT,
        )
        assessment = DeadlineIntelligence.assess_deadline(norm, reference_time=ref)
        assert assessment.status == DeadlineTemporalStatus.EXPIRED
        assert assessment.urgency_tier == UrgencyTier.EXPIRED
        assert assessment.urgency_score == 0.0
        assert assessment.seconds_remaining < 0
        assert assessment.is_expired() is True

    def test_missing_status(self):
        ref = datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc)
        norm = DeadlineNormalizer.normalize_raw_string(None, deadline_type=DeadlineType.SUBMISSION)
        assessment = DeadlineIntelligence.assess_deadline(norm, reference_time=ref)
        assert assessment.status == DeadlineTemporalStatus.MISSING
        assert assessment.urgency_tier == UrgencyTier.UNKNOWN
        assert assessment.urgency_score == 0.0
        assert assessment.seconds_remaining is None
        assert assessment.is_expired() is False

    def test_invalid_status(self):
        ref = datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc)
        norm = DeadlineNormalizer.normalize_raw_string("2026-02-31", deadline_type=DeadlineType.SUBMISSION)
        assessment = DeadlineIntelligence.assess_deadline(norm, reference_time=ref)
        assert assessment.status == DeadlineTemporalStatus.INVALID
        assert assessment.urgency_tier == UrgencyTier.UNKNOWN
        assert assessment.urgency_score == 0.0
        assert assessment.confidence == 0.0
        assert assessment.is_expired() is False

    def test_ambiguous_status(self):
        ref = datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc)
        norm = DeadlineNormalizer.normalize_raw_string("04/05/2026", deadline_type=DeadlineType.SUBMISSION)
        assessment = DeadlineIntelligence.assess_deadline(norm, reference_time=ref)
        assert assessment.status == DeadlineTemporalStatus.AMBIGUOUS
        assert assessment.urgency_tier == UrgencyTier.UNKNOWN
        assert assessment.urgency_score == 0.0
        assert assessment.confidence == 0.0
        assert assessment.is_expired() is False


class TestUrgencyTiersAndBoundaries:
    """Test discrete urgency tier assignments based on remaining time."""

    @pytest.fixture
    def ref_time(self):
        return datetime(2026, 8, 20, 0, 0, 0, tzinfo=timezone.utc)

    def test_critical_tier(self, ref_time):
        # 2 days away (<= 3.0 days)
        deadline = ref_time + timedelta(days=2)
        norm = NormalizedDeadline(
            deadline_type=DeadlineType.SUBMISSION,
            normalized_utc=deadline,
            normalization_status=NormalizationStatus.NORMALIZED,
            timezone_source=TimezoneSource.EXPLICIT,
        )
        assessment = DeadlineIntelligence.assess_deadline(norm, reference_time=ref_time)
        assert assessment.urgency_tier == UrgencyTier.CRITICAL
        assert assessment.status == DeadlineTemporalStatus.UPCOMING

    def test_urgent_tier(self, ref_time):
        # 10 days away (3.0 < days <= 14.0)
        deadline = ref_time + timedelta(days=10)
        norm = NormalizedDeadline(
            deadline_type=DeadlineType.SUBMISSION,
            normalized_utc=deadline,
            normalization_status=NormalizationStatus.NORMALIZED,
            timezone_source=TimezoneSource.EXPLICIT,
        )
        assessment = DeadlineIntelligence.assess_deadline(norm, reference_time=ref_time)
        assert assessment.urgency_tier == UrgencyTier.URGENT
        assert assessment.status == DeadlineTemporalStatus.UPCOMING

    def test_approaching_tier(self, ref_time):
        # 25 days away (14.0 < days <= 30.0)
        deadline = ref_time + timedelta(days=25)
        norm = NormalizedDeadline(
            deadline_type=DeadlineType.SUBMISSION,
            normalized_utc=deadline,
            normalization_status=NormalizationStatus.NORMALIZED,
            timezone_source=TimezoneSource.EXPLICIT,
        )
        assessment = DeadlineIntelligence.assess_deadline(norm, reference_time=ref_time)
        assert assessment.urgency_tier == UrgencyTier.APPROACHING
        assert assessment.status == DeadlineTemporalStatus.UPCOMING

    def test_distant_tier(self, ref_time):
        # 60 days away (> 30.0 days)
        deadline = ref_time + timedelta(days=60)
        norm = NormalizedDeadline(
            deadline_type=DeadlineType.SUBMISSION,
            normalized_utc=deadline,
            normalization_status=NormalizationStatus.NORMALIZED,
            timezone_source=TimezoneSource.EXPLICIT,
        )
        assessment = DeadlineIntelligence.assess_deadline(norm, reference_time=ref_time)
        assert assessment.urgency_tier == UrgencyTier.DISTANT
        assert assessment.status == DeadlineTemporalStatus.UPCOMING

    def test_distant_beyond_window(self, ref_time):
        # 120 days away (> 90.0 days max window)
        deadline = ref_time + timedelta(days=120)
        norm = NormalizedDeadline(
            deadline_type=DeadlineType.SUBMISSION,
            normalized_utc=deadline,
            normalization_status=NormalizationStatus.NORMALIZED,
            timezone_source=TimezoneSource.EXPLICIT,
        )
        assessment = DeadlineIntelligence.assess_deadline(norm, reference_time=ref_time)
        assert assessment.urgency_tier == UrgencyTier.DISTANT
        assert assessment.urgency_score == 0.0


class TestUrgencyScoreProperties:
    """Test mathematical invariants: monotonicity, boundedness, and zero-fabrication."""

    @pytest.fixture
    def fixed_deadline(self):
        return datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)

    def test_score_boundedness(self, fixed_deadline):
        """Urgency score must always remain in [0.0, 1.0]."""
        test_offsets = [-50, -1, 0, 1, 5, 14, 30, 45, 89, 90, 150, 365]
        for days in test_offsets:
            ref = fixed_deadline - timedelta(days=days)
            norm = NormalizedDeadline(
                deadline_type=DeadlineType.SUBMISSION,
                normalized_utc=fixed_deadline,
                normalization_status=NormalizationStatus.NORMALIZED,
                timezone_source=TimezoneSource.EXPLICIT,
            )
            assessment = DeadlineIntelligence.assess_deadline(norm, reference_time=ref)
            assert 0.0 <= assessment.urgency_score <= 1.0

    def test_strict_monotonicity(self, fixed_deadline):
        """
        For any T1 < T2 < deadline, urgency(T1) <= urgency(T2).
        """
        times = [
            fixed_deadline - timedelta(days=80),
            fixed_deadline - timedelta(days=50),
            fixed_deadline - timedelta(days=30),
            fixed_deadline - timedelta(days=14),
            fixed_deadline - timedelta(days=7),
            fixed_deadline - timedelta(days=3),
            fixed_deadline - timedelta(days=1),
            fixed_deadline - timedelta(hours=6),
            fixed_deadline - timedelta(hours=1),
            fixed_deadline - timedelta(minutes=1),
            fixed_deadline,
        ]

        norm = NormalizedDeadline(
            deadline_type=DeadlineType.SUBMISSION,
            normalized_utc=fixed_deadline,
            normalization_status=NormalizationStatus.NORMALIZED,
            timezone_source=TimezoneSource.EXPLICIT,
        )

        scores = [
            DeadlineIntelligence.assess_deadline(norm, reference_time=t).urgency_score
            for t in times
        ]

        for i in range(len(scores) - 1):
            assert scores[i] <= scores[i + 1], f"Monotonicity failed at step {i}: {scores[i]} > {scores[i+1]}"

        # Maximum urgency at deadline instant
        assert scores[-1] == 1.0

    def test_no_urgency_fabrication_for_missing_and_invalid(self):
        ref = datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc)
        for raw in [None, "", "   ", "TBA", "TBD", "N/A", "Rolling", "not-a-date"]:
            norm = DeadlineNormalizer.normalize_raw_string(raw, deadline_type=DeadlineType.SUBMISSION)
            assessment = DeadlineIntelligence.assess_deadline(norm, reference_time=ref)
            assert assessment.urgency_score == 0.0
            assert assessment.urgency_tier == UrgencyTier.UNKNOWN


class TestDueTodayAndExpiredSemantics:
    """Validate due-today vs expired semantics."""

    def test_due_today_not_expired(self):
        # 10:00 UTC vs 23:59:59 UTC same day
        ref = datetime(2026, 8, 22, 10, 0, 0, tzinfo=timezone.utc)
        deadline = datetime(2026, 8, 22, 23, 59, 59, tzinfo=timezone.utc)
        norm = NormalizedDeadline(
            deadline_type=DeadlineType.SUBMISSION,
            normalized_utc=deadline,
            normalization_status=NormalizationStatus.NORMALIZED,
            timezone_source=TimezoneSource.EXPLICIT,
        )
        assessment = DeadlineIntelligence.assess_deadline(norm, reference_time=ref)
        assert assessment.status == DeadlineTemporalStatus.DUE_TODAY
        assert assessment.urgency_tier == UrgencyTier.DUE_TODAY
        assert assessment.is_expired() is False
        assert "today" in assessment.explanation.lower()
        assert "14 hours remaining" in assessment.explanation

    def test_expired_by_one_second(self):
        ref = datetime(2026, 8, 22, 12, 0, 1, tzinfo=timezone.utc)
        deadline = datetime(2026, 8, 22, 12, 0, 0, tzinfo=timezone.utc)
        norm = NormalizedDeadline(
            deadline_type=DeadlineType.SUBMISSION,
            normalized_utc=deadline,
            normalization_status=NormalizationStatus.NORMALIZED,
            timezone_source=TimezoneSource.EXPLICIT,
        )
        assessment = DeadlineIntelligence.assess_deadline(norm, reference_time=ref)
        assert assessment.status == DeadlineTemporalStatus.EXPIRED
        assert assessment.urgency_tier == UrgencyTier.EXPIRED
        assert assessment.urgency_score == 0.0
        assert assessment.seconds_remaining == -1.0
        assert assessment.is_expired() is True

    def test_expired_several_days_ago(self):
        ref = datetime(2026, 8, 25, 12, 0, 0, tzinfo=timezone.utc)
        deadline = datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc)
        norm = NormalizedDeadline(
            deadline_type=DeadlineType.SUBMISSION,
            normalized_utc=deadline,
            normalization_status=NormalizationStatus.NORMALIZED,
            timezone_source=TimezoneSource.EXPLICIT,
        )
        assessment = DeadlineIntelligence.assess_deadline(norm, reference_time=ref)
        assert assessment.status == DeadlineTemporalStatus.EXPIRED
        assert assessment.urgency_tier == UrgencyTier.EXPIRED
        assert assessment.days_remaining == -5.0
        assert "passed 5 days ago" in assessment.explanation


class TestAnywhereOnEarthAndBoundaryCrossings:
    """Test Anywhere on Earth (AoE) deadline assessment across day, month, and year boundaries."""

    def test_aoe_regular_date_due_today(self):
        # 2026-08-22 date-only submission normalizes to 2026-08-23 11:59:59 UTC
        norm = DeadlineNormalizer.normalize_raw_string("Aug 22, 2026", deadline_type=DeadlineType.SUBMISSION)
        assert norm.normalized_utc == datetime(2026, 8, 23, 11, 59, 59, tzinfo=timezone.utc)

        # Reference time on August 22 at 18:00 UTC -> Calendar day is 2026-08-22 -> DUE_TODAY!
        ref = datetime(2026, 8, 22, 18, 0, 0, tzinfo=timezone.utc)
        assessment = DeadlineIntelligence.assess_deadline(norm, reference_time=ref)
        assert assessment.status == DeadlineTemporalStatus.DUE_TODAY
        assert assessment.urgency_tier == UrgencyTier.DUE_TODAY
        assert assessment.is_expired() is False
        assert "Timezone inferred from academic date convention" in assessment.explanation

    def test_aoe_month_boundary(self):
        # Aug 31, 2026 AoE -> Sep 1, 2026 11:59:59 UTC
        norm = DeadlineNormalizer.normalize_raw_string("2026-08-31 AoE", deadline_type=DeadlineType.SUBMISSION)
        assert norm.normalized_utc == datetime(2026, 9, 1, 11, 59, 59, tzinfo=timezone.utc)

        ref = datetime(2026, 8, 31, 22, 0, 0, tzinfo=timezone.utc)
        assessment = DeadlineIntelligence.assess_deadline(norm, reference_time=ref)
        assert assessment.status == DeadlineTemporalStatus.DUE_TODAY
        assert assessment.urgency_tier == UrgencyTier.DUE_TODAY
        assert assessment.is_expired() is False

    def test_aoe_year_boundary(self):
        # Dec 31, 2026 AoE -> Jan 1, 2027 11:59:59 UTC
        norm = DeadlineNormalizer.normalize_raw_string("2026-12-31 AoE", deadline_type=DeadlineType.SUBMISSION)
        assert norm.normalized_utc == datetime(2027, 1, 1, 11, 59, 59, tzinfo=timezone.utc)

        ref = datetime(2026, 12, 31, 20, 0, 0, tzinfo=timezone.utc)
        assessment = DeadlineIntelligence.assess_deadline(norm, reference_time=ref)
        assert assessment.status == DeadlineTemporalStatus.DUE_TODAY
        assert assessment.urgency_tier == UrgencyTier.DUE_TODAY
        assert assessment.is_expired() is False


class TestTimezonesAndDST:
    """Test timezone-aware calculations and DST handling."""

    def test_eastern_daylight_time_summer(self):
        # July in New York (EDT = UTC-4)
        norm = DeadlineNormalizer.normalize_raw_string(
            "July 15, 2026 17:00 America/New_York",
            deadline_type=DeadlineType.SUBMISSION,
        )
        assert norm.normalized_utc == datetime(2026, 7, 15, 21, 0, 0, tzinfo=timezone.utc)

        # Reference time: 2026-07-15 03:00 UTC (18 hours before deadline)
        ref = datetime(2026, 7, 15, 3, 0, 0, tzinfo=timezone.utc)
        assessment = DeadlineIntelligence.assess_deadline(norm, reference_time=ref)
        assert assessment.hours_remaining == 18.0
        assert assessment.status == DeadlineTemporalStatus.DUE_TODAY
        assert assessment.urgency_tier == UrgencyTier.DUE_TODAY

    def test_eastern_standard_time_winter(self):
        # January in New York (EST = UTC-5)
        norm = DeadlineNormalizer.normalize_raw_string(
            "January 15, 2026 17:00 America/New_York",
            deadline_type=DeadlineType.SUBMISSION,
        )
        assert norm.normalized_utc == datetime(2026, 1, 15, 22, 0, 0, tzinfo=timezone.utc)

        ref = datetime(2026, 1, 10, 22, 0, 0, tzinfo=timezone.utc)
        assessment = DeadlineIntelligence.assess_deadline(norm, reference_time=ref)
        assert assessment.days_remaining == 5.0
        assert assessment.urgency_tier == UrgencyTier.URGENT


class TestMilestoneSeparationAndPrecedence:
    """Validate independent milestone assessment and primary milestone selection."""

    def test_milestone_independence(self):
        ref = datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc)
        sub_norm = DeadlineNormalizer.normalize_raw_string("2026-08-25", deadline_type=DeadlineType.SUBMISSION)
        notif_norm = DeadlineNormalizer.normalize_raw_string("2026-10-15", deadline_type=DeadlineType.NOTIFICATION)

        sub_assess = DeadlineIntelligence.assess_deadline(sub_norm, reference_time=ref)
        notif_assess = DeadlineIntelligence.assess_deadline(notif_norm, reference_time=ref)

        assert sub_assess.deadline_type == DeadlineType.SUBMISSION
        assert "Submission deadline" in sub_assess.explanation
        assert sub_assess.urgency_tier in (UrgencyTier.CRITICAL, UrgencyTier.URGENT)

        assert notif_assess.deadline_type == DeadlineType.NOTIFICATION
        assert "Author notification date" in notif_assess.explanation
        assert notif_assess.urgency_tier == UrgencyTier.DISTANT

    def test_primary_submission_precedence(self):
        ref = datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc)
        collection = NormalizedDeadlineCollection(opportunity_id="opp-100")
        collection.add(DeadlineNormalizer.normalize_raw_string("2026-11-01", deadline_type=DeadlineType.EVENT_START))
        collection.add(DeadlineNormalizer.normalize_raw_string("2026-09-01", deadline_type=DeadlineType.SUBMISSION))
        collection.add(DeadlineNormalizer.normalize_raw_string("2026-10-01", deadline_type=DeadlineType.NOTIFICATION))

        opp_assess = DeadlineIntelligence.assess_collection(collection, reference_time=ref)
        assert opp_assess.primary_assessment is not None
        assert opp_assess.primary_assessment.deadline_type == DeadlineType.SUBMISSION
        assert len(opp_assess.milestone_assessments) == 3

    def test_event_start_not_conflated_with_submission(self):
        # Opportunity with ONLY event date, no submission deadline
        ref = datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc)
        collection = NormalizedDeadlineCollection(opportunity_id="opp-event-only")
        collection.add(DeadlineNormalizer.normalize_raw_string("2026-09-15", deadline_type=DeadlineType.EVENT_START))

        opp_assess = DeadlineIntelligence.assess_collection(collection, reference_time=ref)
        assert opp_assess.primary_assessment is not None
        assert opp_assess.primary_assessment.deadline_type == DeadlineType.EVENT_START
        assert "Event start date" in opp_assess.primary_assessment.explanation
        assert "Submission deadline" not in opp_assess.primary_assessment.explanation


class TestDeadlineConfidence:
    """Validate confidence calculation reflects provenance, precision, and timezone source."""

    def test_explicit_datetime_high_confidence(self):
        ref = datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc)
        norm = DeadlineNormalizer.normalize_raw_string("2026-08-25 23:59:00 UTC", deadline_type=DeadlineType.SUBMISSION)
        assessment = DeadlineIntelligence.assess_deadline(norm, reference_time=ref)
        assert assessment.confidence == 1.0

    def test_date_only_inferred_aoe_confidence(self):
        ref = datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc)
        norm = DeadlineNormalizer.normalize_raw_string("Aug 25, 2026", deadline_type=DeadlineType.SUBMISSION)
        assessment = DeadlineIntelligence.assess_deadline(norm, reference_time=ref)
        # Expected confidence ~ 0.7268 (base 0.85 * tz 0.90 * precision 0.95)
        assert 0.70 <= assessment.confidence <= 0.80

    def test_missing_zero_confidence(self):
        ref = datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc)
        norm = DeadlineNormalizer.normalize_raw_string(None, deadline_type=DeadlineType.SUBMISSION)
        assessment = DeadlineIntelligence.assess_deadline(norm, reference_time=ref)
        assert assessment.confidence == 0.0


class TestDeterminismAndPerformance:
    """Verify 100-run strict determinism and benchmark performance."""

    def test_100_runs_strict_determinism(self):
        ref = datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc)
        norm = DeadlineNormalizer.normalize_raw_string("2026-08-25 18:00:00 UTC", deadline_type=DeadlineType.SUBMISSION)

        baseline = DeadlineIntelligence.assess_deadline(norm, reference_time=ref).to_dict()

        for _ in range(100):
            run = DeadlineIntelligence.assess_deadline(norm, reference_time=ref).to_dict()
            assert run == baseline

    @pytest.mark.parametrize("candidate_count", [10, 50, 100, 200, 1000])
    def test_batch_assessment_performance(self, candidate_count):
        ref = datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc)
        test_dates = [
            "Aug 22, 2026",
            "2026-08-25 18:00:00 UTC",
            "2026-09-01 AoE",
            "2026-10-15",
            None,
            "TBA",
            "04/05/2026",
            "2026-08-15 12:00:00 UTC",  # Expired
        ]

        normalized_items = [
            DeadlineNormalizer.normalize_raw_string(
                test_dates[i % len(test_dates)],
                deadline_type=DeadlineType.SUBMISSION,
            )
            for i in range(candidate_count)
        ]

        start_time = pytime.perf_counter()
        results = [
            DeadlineIntelligence.assess_deadline(item, reference_time=ref)
            for item in normalized_items
        ]
        duration = pytime.perf_counter() - start_time

        assert len(results) == candidate_count
        avg_ms_per_candidate = (duration * 1000.0) / candidate_count
        # Target: < 0.1 ms/candidate
        assert avg_ms_per_candidate < 0.1, f"Candidate count {candidate_count}: {avg_ms_per_candidate:.4f} ms/candidate exceeds 0.1 ms"


class TestCalculateUrgencyCompatibility:
    """Test backward and forward compatibility with calculate_urgency()."""

    def test_compatibility_with_deadline_assessment(self):
        ref = datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc)
        deadline = datetime(2026, 8, 25, 12, 0, 0, tzinfo=timezone.utc)
        norm = NormalizedDeadline(
            deadline_type=DeadlineType.SUBMISSION,
            normalized_utc=deadline,
            normalization_status=NormalizationStatus.NORMALIZED,
            timezone_source=TimezoneSource.EXPLICIT,
        )
        assessment = DeadlineIntelligence.assess_deadline(norm, reference_time=ref, window_days=90.0)

        urgency = calculate_urgency(submission_deadline=assessment)
        assert urgency == assessment.urgency_score
        assert urgency == 0.944444

    def test_compatibility_with_normalized_deadline(self):
        ref = datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc)
        deadline = datetime(2026, 8, 25, 12, 0, 0, tzinfo=timezone.utc)
        norm = NormalizedDeadline(
            deadline_type=DeadlineType.SUBMISSION,
            normalized_utc=deadline,
            normalization_status=NormalizationStatus.NORMALIZED,
            timezone_source=TimezoneSource.EXPLICIT,
        )

        urgency = calculate_urgency(
            submission_deadline=norm,
            reference_time=ref,
            window_days=90.0,
        )
        assert urgency == 0.944444

    def test_compatibility_with_string_and_datetime(self):
        ref = datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc)
        dt = datetime(2026, 8, 25, 12, 0, 0, tzinfo=timezone.utc)
        score_dt = calculate_urgency(submission_deadline=dt, reference_time=ref, window_days=90.0)
        score_str = calculate_urgency(
            submission_deadline="2026-08-25T12:00:00+00:00",
            reference_time=ref,
            window_days=90.0,
        )
        assert score_dt == score_str == 0.944444
