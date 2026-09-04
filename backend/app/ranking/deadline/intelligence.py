"""
Deadline Intelligence and Urgency Engine for ResearchConnect AI (Phase 2.7D).

Provides deterministic, milestone-aware temporal assessments, discrete urgency tiers,
bounded monotonic urgency scoring, exact elapsed time computation, and structured explainability.

CRITICAL INVARIANTS:
1. Phase 2.7D evaluates temporal distance and urgency from normalized deadlines.
   It does NOT modify Phase 2.5 ranking weights or recommend re-sorting architectures.
2. The core engine is purely in-memory and deterministic:
   0 DB queries, 0 network calls, and explicit reference_time injection.
3. Missing, invalid, or ambiguous dates NEVER produce fabricated urgency (urgency_score = 0.0,
   urgency_tier = UNKNOWN, status = MISSING/INVALID/AMBIGUOUS).
4. Deadlines are expired ONLY when normalized_utc < reference_time (or local_date < ref.date()).
   A deadline occurring later today is DUE_TODAY, not EXPIRED.
5. Milestone independence: SUBMISSION, ABSTRACT, NOTIFICATION, CAMERA_READY, REGISTRATION,
   EVENT_START, and EVENT_END are assessed independently.
6. Urgency score increases monotonically as deadline approaches:
   T1 < T2 < deadline => urgency(T1) <= urgency(T2).
"""
from __future__ import annotations

from datetime import date, datetime, time, timezone
import logging
from typing import Any

from app.ranking.deadline.models import (
    DeadlineAssessment,
    DeadlinePrecision,
    DeadlineTemporalStatus,
    DeadlineType,
    NormalizationStatus,
    NormalizedDeadline,
    NormalizedDeadlineCollection,
    OpportunityDeadlineAssessment,
    TimezoneSource,
    UrgencyTier,
)
from app.ranking.deadline.normalizers import DeadlineNormalizer

logger = logging.getLogger(__name__)

# ── Urgency Thresholds and Windows ───────────────────────────────────────────

DEFAULT_CRITICAL_WINDOW_DAYS: float = 3.0
DEFAULT_URGENT_WINDOW_DAYS: float = 14.0
DEFAULT_APPROACHING_WINDOW_DAYS: float = 30.0
DEFAULT_MAX_URGENCY_WINDOW_DAYS: float = 90.0

PRIMARY_MILESTONE_PRECEDENCE: list[DeadlineType] = [
    DeadlineType.SUBMISSION,
    DeadlineType.ABSTRACT,
    DeadlineType.REGISTRATION,
    DeadlineType.CAMERA_READY,
    DeadlineType.NOTIFICATION,
    DeadlineType.EVENT_START,
    DeadlineType.EVENT_END,
    DeadlineType.UNKNOWN,
]

MILESTONE_LABELS: dict[DeadlineType, str] = {
    DeadlineType.SUBMISSION: "Submission deadline",
    DeadlineType.ABSTRACT: "Abstract registration deadline",
    DeadlineType.NOTIFICATION: "Author notification date",
    DeadlineType.CAMERA_READY: "Camera-ready deadline",
    DeadlineType.REGISTRATION: "Registration deadline",
    DeadlineType.EVENT_START: "Event start date",
    DeadlineType.EVENT_END: "Event end date",
    DeadlineType.UNKNOWN: "Deadline",
}


class DeadlineIntelligence:
    """
    Deterministic, timezone-aware deadline intelligence and urgency engine.
    """

    @classmethod
    def assess_deadline(
        cls,
        normalized_deadline: NormalizedDeadline | None,
        reference_time: datetime | None = None,
        window_days: float | None = None,
        deadline_type_override: DeadlineType | None = None,
    ) -> DeadlineAssessment:
        """
        Assess temporal urgency, status, and explainability for a normalized deadline.

        Parameters
        ----------
        normalized_deadline:
            Normalized deadline from Phase 2.7C.
        reference_time:
            Explicit UTC reference timestamp. Defaults to current UTC time.
        window_days:
            Urgency horizon in days (defaults to 90.0 days).
        deadline_type_override:
            Optional override for milestone type when assessing missing inputs.

        Returns
        -------
        DeadlineAssessment:
            Deterministic assessment with exact distance, tier, score, and explanation.
        """
        # 1. Normalize reference time to UTC tz-aware
        if reference_time is None:
            ref = datetime.now(timezone.utc)
        elif reference_time.tzinfo is None:
            ref = reference_time.replace(tzinfo=timezone.utc)
        else:
            ref = reference_time.astimezone(timezone.utc)

        max_window = (
            window_days
            if window_days is not None and window_days > 0
            else DEFAULT_MAX_URGENCY_WINDOW_DAYS
        )

        effective_type = (
            deadline_type_override
            or (normalized_deadline.deadline_type if normalized_deadline else DeadlineType.SUBMISSION)
        )
        label = MILESTONE_LABELS.get(effective_type, "Deadline")

        # 2. Handle missing or None deadline
        if (
            normalized_deadline is None
            or normalized_deadline.normalization_status == NormalizationStatus.MISSING
        ):
            return DeadlineAssessment(
                deadline_type=effective_type,
                reference_time=ref,
                normalized_deadline=normalized_deadline,
                status=DeadlineTemporalStatus.MISSING,
                urgency_tier=UrgencyTier.UNKNOWN,
                urgency_score=0.0,
                seconds_remaining=None,
                minutes_remaining=None,
                hours_remaining=None,
                days_remaining=None,
                confidence=0.0,
                explanation=f"No deadline specified for {label.lower()}.",
                metadata={"reason": "missing_or_unspecified_date"},
            )

        # 3. Handle invalid normalization status
        if normalized_deadline.normalization_status == NormalizationStatus.INVALID:
            return DeadlineAssessment(
                deadline_type=effective_type,
                reference_time=ref,
                normalized_deadline=normalized_deadline,
                status=DeadlineTemporalStatus.INVALID,
                urgency_tier=UrgencyTier.UNKNOWN,
                urgency_score=0.0,
                seconds_remaining=None,
                minutes_remaining=None,
                hours_remaining=None,
                days_remaining=None,
                confidence=0.0,
                explanation=f"Deadline could not be parsed or contains invalid timezone for {label.lower()}.",
                metadata={"reason": "invalid_date_or_timezone"},
            )

        # 4. Handle ambiguous normalization status
        if normalized_deadline.normalization_status == NormalizationStatus.AMBIGUOUS:
            return DeadlineAssessment(
                deadline_type=effective_type,
                reference_time=ref,
                normalized_deadline=normalized_deadline,
                status=DeadlineTemporalStatus.AMBIGUOUS,
                urgency_tier=UrgencyTier.UNKNOWN,
                urgency_score=0.0,
                seconds_remaining=None,
                minutes_remaining=None,
                hours_remaining=None,
                days_remaining=None,
                confidence=0.0,
                explanation=f"Deadline could not be normalized because the date is ambiguous for {label.lower()}.",
                metadata={"reason": "ambiguous_date_representation"},
            )

        # 5. Handle date-only without normalized UTC instant
        if normalized_deadline.normalized_utc is None:
            if normalized_deadline.local_date is not None:
                days_diff = (normalized_deadline.local_date - ref.date()).days
                if days_diff < 0:
                    status = DeadlineTemporalStatus.EXPIRED
                    tier = UrgencyTier.EXPIRED
                    score = 0.0
                    abs_d = abs(days_diff)
                    expl = (
                        f"{label} passed 1 day ago."
                        if abs_d == 1
                        else f"{label} passed {abs_d} days ago."
                    )
                elif days_diff == 0:
                    status = DeadlineTemporalStatus.DUE_TODAY
                    tier = UrgencyTier.DUE_TODAY
                    score = 1.0
                    expl = f"{label} is today."
                else:
                    status = DeadlineTemporalStatus.UPCOMING
                    if days_diff <= DEFAULT_CRITICAL_WINDOW_DAYS:
                        tier = UrgencyTier.CRITICAL
                    elif days_diff <= DEFAULT_URGENT_WINDOW_DAYS:
                        tier = UrgencyTier.URGENT
                    elif days_diff <= DEFAULT_APPROACHING_WINDOW_DAYS:
                        tier = UrgencyTier.APPROACHING
                    else:
                        tier = UrgencyTier.DISTANT

                    if days_diff >= max_window:
                        score = 0.0
                    else:
                        score = round(max(0.0, min(1.0, 1.0 - (days_diff / max_window))), 6)

                    expl = (
                        f"{label} is 1 day away."
                        if days_diff == 1
                        else f"{label} is {days_diff} days away."
                    )

                conf = round(
                    normalized_deadline.normalization_confidence * 0.85, 4
                )
                return DeadlineAssessment(
                    deadline_type=effective_type,
                    reference_time=ref,
                    normalized_deadline=normalized_deadline,
                    status=status,
                    urgency_tier=tier,
                    urgency_score=score,
                    seconds_remaining=float(days_diff * 86400),
                    minutes_remaining=float(days_diff * 1440),
                    hours_remaining=float(days_diff * 24),
                    days_remaining=float(days_diff),
                    confidence=conf,
                    explanation=expl,
                    metadata={"precision": "calendar_date_only"},
                )

            # Fallback if both normalized_utc and local_date are None
            return DeadlineAssessment(
                deadline_type=effective_type,
                reference_time=ref,
                normalized_deadline=normalized_deadline,
                status=DeadlineTemporalStatus.MISSING,
                urgency_tier=UrgencyTier.UNKNOWN,
                urgency_score=0.0,
                confidence=0.0,
                explanation=f"No usable temporal data for {label.lower()}.",
            )

        # 6. High-precision path: Normalized UTC instant is present
        diff_seconds = (normalized_deadline.normalized_utc - ref).total_seconds()
        sec_rem = round(diff_seconds, 2)
        min_rem = round(diff_seconds / 60.0, 2)
        hr_rem = round(diff_seconds / 3600.0, 2)
        day_rem = round(diff_seconds / 86400.0, 4)

        # 7. Check expiration semantics: strictly instant < reference_time
        if diff_seconds < 0.0:
            status = DeadlineTemporalStatus.EXPIRED
            tier = UrgencyTier.EXPIRED
            score = 0.0

            abs_days = abs(int(day_rem))
            abs_hours = abs(int(hr_rem))
            if abs_days == 0:
                h_text = f"{abs_hours} hour" if abs_hours == 1 else f"{abs_hours} hours"
                expl = f"{label} passed {h_text} ago."
            elif abs_days == 1:
                expl = f"{label} passed 1 day ago."
            else:
                expl = f"{label} passed {abs_days} days ago."

        else:
            # 8. Check DUE_TODAY semantics
            # True if deadline is in the future AND falls on the same calendar day
            is_same_calendar_day = (
                normalized_deadline.normalized_utc.date() == ref.date()
                or (
                    normalized_deadline.local_date is not None
                    and normalized_deadline.local_date == ref.date()
                )
            )

            if is_same_calendar_day:
                status = DeadlineTemporalStatus.DUE_TODAY
                tier = UrgencyTier.DUE_TODAY
                # Urgency score approaches 1.0 monotonically
                raw_score = 1.0 - (max(0.0, day_rem) / max_window)
                score = round(max(0.0, min(1.0, raw_score)), 6)
                h_int = max(0, int(hr_rem))
                h_text = f"{h_int} hour" if h_int == 1 else f"{h_int} hours"
                expl = f"{label} is today ({h_text} remaining)."

            else:
                # 9. Upcoming future deadline
                status = DeadlineTemporalStatus.UPCOMING

                if day_rem <= DEFAULT_CRITICAL_WINDOW_DAYS:
                    tier = UrgencyTier.CRITICAL
                elif day_rem <= DEFAULT_URGENT_WINDOW_DAYS:
                    tier = UrgencyTier.URGENT
                elif day_rem <= DEFAULT_APPROACHING_WINDOW_DAYS:
                    tier = UrgencyTier.APPROACHING
                else:
                    tier = UrgencyTier.DISTANT

                # Linear decay score bounded in [0.0, 1.0]
                if day_rem >= max_window:
                    score = 0.0
                else:
                    raw_score = 1.0 - (day_rem / max_window)
                    score = round(max(0.0, min(1.0, raw_score)), 6)

                if hr_rem < 24.0:
                    h_int = max(1, int(hr_rem))
                    h_text = f"{h_int} hour" if h_int == 1 else f"{h_int} hours"
                    expl = f"{label} is {h_text} away."
                else:
                    d_int = max(1, int(day_rem))
                    d_text = f"{d_int} day" if d_int == 1 else f"{d_int} days"
                    expl = f"{label} is {d_text} away."

        # Add timezone annotation if inferred
        if normalized_deadline.timezone_source == TimezoneSource.INFERRED:
            expl += " Timezone inferred from academic date convention."

        # 10. Compute confidence
        base_conf = normalized_deadline.normalization_confidence
        tz_factor = (
            1.0
            if normalized_deadline.timezone_source == TimezoneSource.EXPLICIT
            else (0.90 if normalized_deadline.timezone_source == TimezoneSource.INFERRED else 0.75)
        )
        prec_factor = (
            1.0 if normalized_deadline.precision == DeadlinePrecision.EXACT_TIME else 0.95
        )
        ev_conf = (
            normalized_deadline.source_evidence.confidence
            if normalized_deadline.source_evidence is not None
            else 1.0
        )
        conf = round(min(1.0, max(0.0, base_conf * tz_factor * prec_factor * ev_conf)), 4)

        return DeadlineAssessment(
            deadline_type=effective_type,
            reference_time=ref,
            normalized_deadline=normalized_deadline,
            status=status,
            urgency_tier=tier,
            urgency_score=score,
            seconds_remaining=sec_rem,
            minutes_remaining=min_rem,
            hours_remaining=hr_rem,
            days_remaining=day_rem,
            confidence=conf,
            explanation=expl,
            metadata={
                "timezone_source": normalized_deadline.timezone_source.value,
                "precision": normalized_deadline.precision.value,
                "is_end_of_day_inferred": normalized_deadline.is_end_of_day_inferred,
            },
        )

    @classmethod
    def assess_collection(
        cls,
        normalized_collection: NormalizedDeadlineCollection,
        reference_time: datetime | None = None,
        window_days: float | None = None,
    ) -> OpportunityDeadlineAssessment:
        """
        Assess an entire collection of normalized deadlines for an opportunity.

        Selects the primary milestone assessment according to authoritative precedence.
        """
        if reference_time is None:
            ref = datetime.now(timezone.utc)
        elif reference_time.tzinfo is None:
            ref = reference_time.replace(tzinfo=timezone.utc)
        else:
            ref = reference_time.astimezone(timezone.utc)

        assessments: list[DeadlineAssessment] = []
        for norm_item in normalized_collection.items:
            assessment = cls.assess_deadline(
                norm_item,
                reference_time=ref,
                window_days=window_days,
            )
            assessments.append(assessment)

        # Select primary assessment
        primary: DeadlineAssessment | None = None
        for p_type in PRIMARY_MILESTONE_PRECEDENCE:
            candidates = [a for a in assessments if a.deadline_type == p_type]
            if not candidates:
                continue

            # Check if any candidate is not MISSING
            valid_candidates = [
                a for a in candidates if a.status != DeadlineTemporalStatus.MISSING
            ]
            if valid_candidates:
                # Prefer upcoming/due_today over expired, then highest confidence
                def _sort_key(a: DeadlineAssessment) -> tuple[int, float]:
                    status_rank = (
                        3 if a.status in (DeadlineTemporalStatus.DUE_TODAY, DeadlineTemporalStatus.UPCOMING)
                        else (2 if a.status == DeadlineTemporalStatus.EXPIRED else 1)
                    )
                    return (status_rank, a.confidence)

                primary = max(valid_candidates, key=_sort_key)
                break

        # If no preferred valid candidate found, pick first assessment or generate default missing
        if primary is None:
            if assessments:
                primary = assessments[0]
            else:
                primary = cls.assess_deadline(
                    None,
                    reference_time=ref,
                    window_days=window_days,
                    deadline_type_override=DeadlineType.SUBMISSION,
                )

        return OpportunityDeadlineAssessment(
            opportunity_id=normalized_collection.opportunity_id,
            reference_time=ref,
            primary_assessment=primary,
            milestone_assessments=assessments,
            metadata={"item_count": len(assessments)},
        )

    @classmethod
    def assess_opportunity_model(
        cls,
        model: Any,
        reference_time: datetime | None = None,
        window_days: float | None = None,
    ) -> OpportunityDeadlineAssessment:
        """
        Extract, normalize, and assess all deadlines from an OpportunityModel or dict.
        """
        norm_collection = DeadlineNormalizer.normalize_opportunity_model(model)
        return cls.assess_collection(
            norm_collection,
            reference_time=reference_time,
            window_days=window_days,
        )
