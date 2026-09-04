"""
Dedicated Deadline Evaluation Dataset for Phase 2.7G.

Provides a structured, labeled benchmark dataset of academic deadline scenarios
categorized into:
  - BASIC_DATES: Exact UTC, offsets, IANA zones, date-only, month/year, approximate, missing.
  - ACADEMIC_CONVENTIONS: Explicit AoE, date-only CFP submission (inferred AoE), rollover boundaries.
  - TIMEZONE_DST: UTC, positive/negative offsets, NY EDT/EST, London BST/GMT, Berlin CEST/CET, Tokyo, Kolkata, Sydney.
  - INVALID_AMBIGUOUS: Invalid timezones, invalid calendar dates, slash ambiguities, TBA/TBD/Rolling/N/A.
  - MULTI_MILESTONE: Abstract, submission, notification, camera-ready, registration, event start/end.
  - REVISIONS: Initial, unchanged, equivalent representations, extensions, moved earlier, replacements, retractions.
  - SOURCE_CONFLICTS: Multi-source agreement, authority supersession (Official CFP > Aggregator), equal-authority disputes.
  - SAFETY_INVARIANTS: Unknown timezones, missing metadata, risk/relevance orthogonality, non-conflation.
  - REAL_WORLD_FIXTURES: Parsed WikiCFP detail and list page extractions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from app.ranking.deadline.models import (
    ConflictState,
    DeadlineObservation,
    DeadlineTemporalStatus,
    DeadlineType,
    RevisionClassification,
    SourceAuthorityTier,
    UrgencyTier,
)


class DeadlineEvaluationCategory(str, Enum):
    """Specific category of the evaluation fixture."""

    BASIC_DATES = "BASIC_DATES"
    ACADEMIC_CONVENTIONS = "ACADEMIC_CONVENTIONS"
    TIMEZONE_DST = "TIMEZONE_DST"
    INVALID_AMBIGUOUS = "INVALID_AMBIGUOUS"
    MULTI_MILESTONE = "MULTI_MILESTONE"
    REVISIONS = "REVISIONS"
    SOURCE_CONFLICTS = "SOURCE_CONFLICTS"
    SAFETY_INVARIANTS = "SAFETY_INVARIANTS"
    REAL_WORLD_FIXTURES = "REAL_WORLD_FIXTURES"


@dataclass(frozen=True)
class DeadlineFixture:
    """An individual labeled deadline evaluation fixture."""

    fixture_id: str
    category: DeadlineEvaluationCategory
    description: str
    raw_input: Any
    expected_deadline_type: DeadlineType
    expected_status: DeadlineTemporalStatus
    expected_urgency_tier: UrgencyTier
    expected_conflict_state: ConflictState = ConflictState.NO_CONFLICT
    expected_revision_classification: RevisionClassification = RevisionClassification.INITIAL
    expected_local_date: str | None = None
    expected_timezone_name: str | None = None
    expected_is_aoe: bool = False
    expected_selected_source: str | None = None
    expected_has_extension: bool = False
    expected_is_valid: bool = True
    reference_time: datetime = field(
        default_factory=lambda: datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)
    )
    metadata: dict[str, Any] = field(default_factory=dict)


class DeadlineEvaluationDataset:
    """Container managing the full Phase 2.7G evaluation dataset."""

    def __init__(self) -> None:
        self.fixtures: list[DeadlineFixture] = []
        self._build_dataset()

    def _build_dataset(self) -> None:
        # Standard reference time: 2026-09-01 12:00:00 UTC
        ref = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)

        # ── Group A: Basic Dates ──────────────────────────────────────────────
        self.fixtures.extend([
            DeadlineFixture(
                fixture_id="BASIC-01",
                category=DeadlineEvaluationCategory.BASIC_DATES,
                description="Exact UTC ISO timestamp upcoming",
                raw_input="2026-09-15T23:59:59Z",
                expected_deadline_type=DeadlineType.SUBMISSION,
                expected_status=DeadlineTemporalStatus.UPCOMING,
                expected_urgency_tier=UrgencyTier.APPROACHING,
                expected_local_date="2026-09-15",
                expected_timezone_name="UTC",
                reference_time=ref,
            ),
            DeadlineFixture(
                fixture_id="BASIC-02",
                category=DeadlineEvaluationCategory.BASIC_DATES,
                description="Exact timestamp with positive offset +02:00",
                raw_input="2026-09-03T18:00:00+02:00",
                expected_deadline_type=DeadlineType.SUBMISSION,
                expected_status=DeadlineTemporalStatus.UPCOMING,
                expected_urgency_tier=UrgencyTier.CRITICAL,
                expected_local_date="2026-09-03",
                expected_timezone_name="+02:00",
                reference_time=ref,
            ),
            DeadlineFixture(
                fixture_id="BASIC-03",
                category=DeadlineEvaluationCategory.BASIC_DATES,
                description="Exact IANA timezone in natural language string",
                raw_input="September 20, 2026 17:00 America/New_York",
                expected_deadline_type=DeadlineType.SUBMISSION,
                expected_status=DeadlineTemporalStatus.UPCOMING,
                expected_urgency_tier=UrgencyTier.APPROACHING,
                expected_local_date="2026-09-20",
                expected_timezone_name="America/New_York",
                reference_time=ref,
            ),
            DeadlineFixture(
                fixture_id="BASIC-04",
                category=DeadlineEvaluationCategory.BASIC_DATES,
                description="Date-only submission deadline (defaults to AoE end-of-day)",
                raw_input="2026-09-10",
                expected_deadline_type=DeadlineType.SUBMISSION,
                expected_status=DeadlineTemporalStatus.UPCOMING,
                expected_urgency_tier=UrgencyTier.URGENT,
                expected_local_date="2026-09-10",
                expected_timezone_name="AoE",
                expected_is_aoe=True,
                reference_time=ref,
            ),
            DeadlineFixture(
                fixture_id="BASIC-05",
                category=DeadlineEvaluationCategory.BASIC_DATES,
                description="Expired ISO timestamp in past",
                raw_input="2026-08-15T00:00:00Z",
                expected_deadline_type=DeadlineType.SUBMISSION,
                expected_status=DeadlineTemporalStatus.EXPIRED,
                expected_urgency_tier=UrgencyTier.EXPIRED,
                expected_local_date="2026-08-15",
                expected_timezone_name="UTC",
                reference_time=ref,
            ),
            DeadlineFixture(
                fixture_id="BASIC-06",
                category=DeadlineEvaluationCategory.BASIC_DATES,
                description="Missing deadline string (None)",
                raw_input=None,
                expected_deadline_type=DeadlineType.SUBMISSION,
                expected_status=DeadlineTemporalStatus.MISSING,
                expected_urgency_tier=UrgencyTier.UNKNOWN,
                reference_time=ref,
            ),
            DeadlineFixture(
                fixture_id="BASIC-07",
                category=DeadlineEvaluationCategory.BASIC_DATES,
                description="Empty string deadline",
                raw_input="",
                expected_deadline_type=DeadlineType.SUBMISSION,
                expected_status=DeadlineTemporalStatus.MISSING,
                expected_urgency_tier=UrgencyTier.UNKNOWN,
                reference_time=ref,
            ),
        ])

        # ── Group B: Academic Deadline Conventions (AoE & Rollovers) ──────────
        self.fixtures.extend([
            DeadlineFixture(
                fixture_id="AOE-01",
                category=DeadlineEvaluationCategory.ACADEMIC_CONVENTIONS,
                description="Explicit AoE phrasing with 23:59 cutoff",
                raw_input="August 22, 2026 23:59 AoE",
                expected_deadline_type=DeadlineType.SUBMISSION,
                expected_status=DeadlineTemporalStatus.EXPIRED,
                expected_urgency_tier=UrgencyTier.EXPIRED,
                expected_local_date="2026-08-22",
                expected_timezone_name="AoE",
                expected_is_aoe=True,
                reference_time=ref,
            ),
            DeadlineFixture(
                fixture_id="AOE-02",
                category=DeadlineEvaluationCategory.ACADEMIC_CONVENTIONS,
                description="Explicit Anywhere on Earth phrasing",
                raw_input="September 15, 2026 Anywhere on Earth",
                expected_deadline_type=DeadlineType.SUBMISSION,
                expected_status=DeadlineTemporalStatus.UPCOMING,
                expected_urgency_tier=UrgencyTier.APPROACHING,
                expected_local_date="2026-09-15",
                expected_timezone_name="AoE",
                expected_is_aoe=True,
                reference_time=ref,
            ),
            DeadlineFixture(
                fixture_id="AOE-03",
                category=DeadlineEvaluationCategory.ACADEMIC_CONVENTIONS,
                description="AoE deadline crossing UTC date rollover (+12h in UTC)",
                # 2026-09-01 23:59:59 AoE is 2026-09-02 11:59:59 UTC
                raw_input="2026-09-01 23:59:59 AoE",
                expected_deadline_type=DeadlineType.SUBMISSION,
                expected_status=DeadlineTemporalStatus.DUE_TODAY,
                expected_urgency_tier=UrgencyTier.CRITICAL,
                expected_local_date="2026-09-01",
                expected_timezone_name="AoE",
                expected_is_aoe=True,
                reference_time=ref,
            ),
            DeadlineFixture(
                fixture_id="AOE-04",
                category=DeadlineEvaluationCategory.ACADEMIC_CONVENTIONS,
                description="AoE deadline crossing month boundary (August 31 AoE -> Sept 1 UTC)",
                raw_input="2026-08-31 23:59 AoE",
                expected_deadline_type=DeadlineType.SUBMISSION,
                expected_status=DeadlineTemporalStatus.EXPIRED,
                expected_urgency_tier=UrgencyTier.EXPIRED,
                expected_local_date="2026-08-31",
                expected_timezone_name="AoE",
                expected_is_aoe=True,
                reference_time=ref,
            ),
            DeadlineFixture(
                fixture_id="AOE-05",
                category=DeadlineEvaluationCategory.ACADEMIC_CONVENTIONS,
                description="AoE deadline crossing year boundary (Dec 31 AoE -> Jan 1 UTC)",
                raw_input="2026-12-31 23:59 AoE",
                expected_deadline_type=DeadlineType.SUBMISSION,
                expected_status=DeadlineTemporalStatus.UPCOMING,
                expected_urgency_tier=UrgencyTier.DISTANT,
                expected_local_date="2026-12-31",
                expected_timezone_name="AoE",
                expected_is_aoe=True,
                reference_time=ref,
            ),
        ])

        # ── Group C: Timezones & Daylight Saving Time ─────────────────────────
        self.fixtures.extend([
            DeadlineFixture(
                fixture_id="TZ-01",
                category=DeadlineEvaluationCategory.TIMEZONE_DST,
                description="New York Summer Daylight Time (EDT, UTC-4)",
                raw_input="July 15, 2026 14:00 America/New_York",
                expected_deadline_type=DeadlineType.SUBMISSION,
                expected_status=DeadlineTemporalStatus.EXPIRED,
                expected_urgency_tier=UrgencyTier.EXPIRED,
                expected_local_date="2026-07-15",
                expected_timezone_name="America/New_York",
                reference_time=ref,
            ),
            DeadlineFixture(
                fixture_id="TZ-02",
                category=DeadlineEvaluationCategory.TIMEZONE_DST,
                description="New York Winter Standard Time (EST, UTC-5)",
                raw_input="December 15, 2026 14:00 America/New_York",
                expected_deadline_type=DeadlineType.SUBMISSION,
                expected_status=DeadlineTemporalStatus.UPCOMING,
                expected_urgency_tier=UrgencyTier.DISTANT,
                expected_local_date="2026-12-15",
                expected_timezone_name="America/New_York",
                reference_time=ref,
            ),
            DeadlineFixture(
                fixture_id="TZ-03",
                category=DeadlineEvaluationCategory.TIMEZONE_DST,
                description="London British Summer Time (BST, UTC+1)",
                raw_input="September 10, 2026 12:00 Europe/London",
                expected_deadline_type=DeadlineType.SUBMISSION,
                expected_status=DeadlineTemporalStatus.UPCOMING,
                expected_urgency_tier=UrgencyTier.URGENT,
                expected_local_date="2026-09-10",
                expected_timezone_name="Europe/London",
                reference_time=ref,
            ),
            DeadlineFixture(
                fixture_id="TZ-04",
                category=DeadlineEvaluationCategory.TIMEZONE_DST,
                description="Berlin Central European Summer Time (CEST, UTC+2)",
                raw_input="September 08, 2026 18:00 Europe/Berlin",
                expected_deadline_type=DeadlineType.SUBMISSION,
                expected_status=DeadlineTemporalStatus.UPCOMING,
                expected_urgency_tier=UrgencyTier.URGENT,
                expected_local_date="2026-09-08",
                expected_timezone_name="Europe/Berlin",
                reference_time=ref,
            ),
            DeadlineFixture(
                fixture_id="TZ-05",
                category=DeadlineEvaluationCategory.TIMEZONE_DST,
                description="Tokyo JST without DST (UTC+9)",
                raw_input="September 25, 2026 23:59 Asia/Tokyo",
                expected_deadline_type=DeadlineType.SUBMISSION,
                expected_status=DeadlineTemporalStatus.UPCOMING,
                expected_urgency_tier=UrgencyTier.APPROACHING,
                expected_local_date="2026-09-25",
                expected_timezone_name="Asia/Tokyo",
                reference_time=ref,
            ),
            DeadlineFixture(
                fixture_id="TZ-06",
                category=DeadlineEvaluationCategory.TIMEZONE_DST,
                description="Kolkata IST with fractional 30min offset (UTC+5:30)",
                raw_input="September 05, 2026 17:30 Asia/Kolkata",
                expected_deadline_type=DeadlineType.SUBMISSION,
                expected_status=DeadlineTemporalStatus.UPCOMING,
                expected_urgency_tier=UrgencyTier.CRITICAL,
                expected_local_date="2026-09-05",
                expected_timezone_name="Asia/Kolkata",
                reference_time=ref,
            ),
            DeadlineFixture(
                fixture_id="TZ-07",
                category=DeadlineEvaluationCategory.TIMEZONE_DST,
                description="Sydney Australian Eastern Standard Time (AEST, UTC+10)",
                raw_input="September 18, 2026 17:00 Australia/Sydney",
                expected_deadline_type=DeadlineType.SUBMISSION,
                expected_status=DeadlineTemporalStatus.UPCOMING,
                expected_urgency_tier=UrgencyTier.APPROACHING,
                expected_local_date="2026-09-18",
                expected_timezone_name="Australia/Sydney",
                reference_time=ref,
            ),
        ])

        # ── Group D: Invalid & Ambiguous Data ─────────────────────────────────
        self.fixtures.extend([
            DeadlineFixture(
                fixture_id="INV-01",
                category=DeadlineEvaluationCategory.INVALID_AMBIGUOUS,
                description="Invalid fictional timezone must NOT fall back to UTC silently",
                raw_input="September 20, 2026 17:00 Mars/Olympus",
                expected_deadline_type=DeadlineType.SUBMISSION,
                expected_status=DeadlineTemporalStatus.INVALID,
                expected_urgency_tier=UrgencyTier.UNKNOWN,
                expected_is_valid=False,
                reference_time=ref,
            ),
            DeadlineFixture(
                fixture_id="INV-02",
                category=DeadlineEvaluationCategory.INVALID_AMBIGUOUS,
                description="Impossible date (Feb 31)",
                raw_input="2026-02-31",
                expected_deadline_type=DeadlineType.SUBMISSION,
                expected_status=DeadlineTemporalStatus.INVALID,
                expected_urgency_tier=UrgencyTier.UNKNOWN,
                expected_is_valid=False,
                reference_time=ref,
            ),
            DeadlineFixture(
                fixture_id="INV-03",
                category=DeadlineEvaluationCategory.INVALID_AMBIGUOUS,
                description="Ambiguous numeric date (04/05/2026 - April 5 vs May 4)",
                raw_input="04/05/2026",
                expected_deadline_type=DeadlineType.SUBMISSION,
                expected_status=DeadlineTemporalStatus.AMBIGUOUS,
                expected_urgency_tier=UrgencyTier.UNKNOWN,
                expected_is_valid=False,
                reference_time=ref,
            ),
            DeadlineFixture(
                fixture_id="INV-04",
                category=DeadlineEvaluationCategory.INVALID_AMBIGUOUS,
                description="TBA (To be announced) placeholder string",
                raw_input="TBA",
                expected_deadline_type=DeadlineType.SUBMISSION,
                expected_status=DeadlineTemporalStatus.MISSING,
                expected_urgency_tier=UrgencyTier.UNKNOWN,
                reference_time=ref,
            ),
            DeadlineFixture(
                fixture_id="INV-05",
                category=DeadlineEvaluationCategory.INVALID_AMBIGUOUS,
                description="TBD (To be decided) placeholder string",
                raw_input="TBD",
                expected_deadline_type=DeadlineType.SUBMISSION,
                expected_status=DeadlineTemporalStatus.MISSING,
                expected_urgency_tier=UrgencyTier.UNKNOWN,
                reference_time=ref,
            ),
            DeadlineFixture(
                fixture_id="INV-06",
                category=DeadlineEvaluationCategory.INVALID_AMBIGUOUS,
                description="Rolling deadline placeholder string",
                raw_input="Rolling",
                expected_deadline_type=DeadlineType.SUBMISSION,
                expected_status=DeadlineTemporalStatus.MISSING,
                expected_urgency_tier=UrgencyTier.UNKNOWN,
                reference_time=ref,
            ),
            DeadlineFixture(
                fixture_id="INV-07",
                category=DeadlineEvaluationCategory.INVALID_AMBIGUOUS,
                description="See website placeholder string",
                raw_input="See website",
                expected_deadline_type=DeadlineType.SUBMISSION,
                expected_status=DeadlineTemporalStatus.MISSING,
                expected_urgency_tier=UrgencyTier.UNKNOWN,
                reference_time=ref,
            ),
            DeadlineFixture(
                fixture_id="INV-08",
                category=DeadlineEvaluationCategory.INVALID_AMBIGUOUS,
                description="N/A string",
                raw_input="N/A",
                expected_deadline_type=DeadlineType.SUBMISSION,
                expected_status=DeadlineTemporalStatus.MISSING,
                expected_urgency_tier=UrgencyTier.UNKNOWN,
                reference_time=ref,
            ),
        ])

        # ── Group E: Multi-Milestones ─────────────────────────────────────────
        self.fixtures.extend([
            DeadlineFixture(
                fixture_id="MILE-01",
                category=DeadlineEvaluationCategory.MULTI_MILESTONE,
                description="Abstract deadline evaluated independently of submission",
                raw_input="2026-09-05",
                expected_deadline_type=DeadlineType.ABSTRACT,
                expected_status=DeadlineTemporalStatus.UPCOMING,
                expected_urgency_tier=UrgencyTier.CRITICAL,
                expected_local_date="2026-09-05",
                reference_time=ref,
            ),
            DeadlineFixture(
                fixture_id="MILE-02",
                category=DeadlineEvaluationCategory.MULTI_MILESTONE,
                description="Notification date must never be treated as submission deadline",
                raw_input="2026-10-15",
                expected_deadline_type=DeadlineType.NOTIFICATION,
                expected_status=DeadlineTemporalStatus.UPCOMING,
                expected_urgency_tier=UrgencyTier.DISTANT,
                expected_local_date="2026-10-15",
                reference_time=ref,
            ),
            DeadlineFixture(
                fixture_id="MILE-03",
                category=DeadlineEvaluationCategory.MULTI_MILESTONE,
                description="Camera ready date evaluated as distinct post-acceptance milestone",
                raw_input="2026-11-01",
                expected_deadline_type=DeadlineType.CAMERA_READY,
                expected_status=DeadlineTemporalStatus.UPCOMING,
                expected_urgency_tier=UrgencyTier.DISTANT,
                expected_local_date="2026-11-01",
                reference_time=ref,
            ),
            DeadlineFixture(
                fixture_id="MILE-04",
                category=DeadlineEvaluationCategory.MULTI_MILESTONE,
                description="Event start date must not be conflated with submission deadline",
                raw_input="2026-12-01",
                expected_deadline_type=DeadlineType.EVENT_START,
                expected_status=DeadlineTemporalStatus.UPCOMING,
                expected_urgency_tier=UrgencyTier.DISTANT,
                expected_local_date="2026-12-01",
                reference_time=ref,
            ),
            DeadlineFixture(
                fixture_id="MILE-05",
                category=DeadlineEvaluationCategory.MULTI_MILESTONE,
                description="Complete multi-milestone venue dictionary",
                raw_input={
                    "title": "International AI Conference 2026",
                    "abstract_deadline": "2026-09-05",
                    "submission_deadline": "2026-09-12",
                    "notification_date": "2026-10-20",
                    "camera_ready_deadline": "2026-11-05",
                    "event_start_date": "2026-12-10",
                },
                expected_deadline_type=DeadlineType.SUBMISSION,
                expected_status=DeadlineTemporalStatus.UPCOMING,
                expected_urgency_tier=UrgencyTier.URGENT,
                expected_local_date="2026-09-12",
                reference_time=ref,
            ),
        ])

        # ── Group F: Revisions & Lifecycle Shifts ──────────────────────────────
        self.fixtures.extend([
            DeadlineFixture(
                fixture_id="REV-01",
                category=DeadlineEvaluationCategory.REVISIONS,
                description="Deadline extended by +7 days",
                raw_input={
                    "previous": "2026-09-10 23:59 AoE",
                    "current": "2026-09-17 23:59 AoE",
                },
                expected_deadline_type=DeadlineType.SUBMISSION,
                expected_status=DeadlineTemporalStatus.UPCOMING,
                expected_urgency_tier=UrgencyTier.APPROACHING,
                expected_revision_classification=RevisionClassification.EXTENDED,
                expected_has_extension=True,
                expected_local_date="2026-09-17",
                reference_time=ref,
            ),
            DeadlineFixture(
                fixture_id="REV-02",
                category=DeadlineEvaluationCategory.REVISIONS,
                description="Deadline moved earlier by 3 days",
                raw_input={
                    "previous": "2026-09-20 23:59 AoE",
                    "current": "2026-09-17 23:59 AoE",
                },
                expected_deadline_type=DeadlineType.SUBMISSION,
                expected_status=DeadlineTemporalStatus.UPCOMING,
                expected_urgency_tier=UrgencyTier.APPROACHING,
                expected_revision_classification=RevisionClassification.MOVED_EARLIER,
                expected_local_date="2026-09-17",
                reference_time=ref,
            ),
            DeadlineFixture(
                fixture_id="REV-03",
                category=DeadlineEvaluationCategory.REVISIONS,
                description="Equivalent date representations (ISO vs Natural language)",
                raw_input={
                    "previous": "2026-09-15T00:00:00Z",
                    "current": "September 15, 2026 00:00 UTC",
                },
                expected_deadline_type=DeadlineType.SUBMISSION,
                expected_status=DeadlineTemporalStatus.UPCOMING,
                expected_urgency_tier=UrgencyTier.APPROACHING,
                expected_revision_classification=RevisionClassification.UNCHANGED,
                expected_local_date="2026-09-15",
                reference_time=ref,
            ),
        ])

        # ── Group G: Multi-Source Conflicts & Precedence ───────────────────────
        self.fixtures.extend([
            DeadlineFixture(
                fixture_id="CONF-01",
                category=DeadlineEvaluationCategory.SOURCE_CONFLICTS,
                description="Official CFP supersedes older General Aggregator",
                raw_input=[
                    {
                        "source": "Aggregator Listing",
                        "raw_value": "2026-09-10",
                        "authority_tier": SourceAuthorityTier.GENERAL_AGGREGATOR,
                    },
                    {
                        "source": "Official CFP Homepage",
                        "raw_value": "2026-09-20 23:59 AoE",
                        "authority_tier": SourceAuthorityTier.OFFICIAL_CFP,
                    },
                ],
                expected_deadline_type=DeadlineType.SUBMISSION,
                expected_status=DeadlineTemporalStatus.UPCOMING,
                expected_urgency_tier=UrgencyTier.APPROACHING,
                expected_conflict_state=ConflictState.SUPERSEDED,
                expected_selected_source="Official CFP Homepage",
                expected_local_date="2026-09-20",
                reference_time=ref,
            ),
            DeadlineFixture(
                fixture_id="CONF-02",
                category=DeadlineEvaluationCategory.SOURCE_CONFLICTS,
                description="Equal-authority disagreement preserves dispute without fabricating winner",
                raw_input=[
                    {
                        "source": "WikiCFP Mirror A",
                        "raw_value": "2026-09-10",
                        "authority_tier": SourceAuthorityTier.DETAIL_PAGE,
                    },
                    {
                        "source": "Conference Tracker B",
                        "raw_value": "2026-09-25",
                        "authority_tier": SourceAuthorityTier.DETAIL_PAGE,
                    },
                ],
                expected_deadline_type=DeadlineType.SUBMISSION,
                expected_status=DeadlineTemporalStatus.AMBIGUOUS,
                expected_urgency_tier=UrgencyTier.UNKNOWN,
                expected_conflict_state=ConflictState.SOURCE_CONFLICT,
                expected_selected_source=None,
                reference_time=ref,
            ),
            DeadlineFixture(
                fixture_id="CONF-03",
                category=DeadlineEvaluationCategory.SOURCE_CONFLICTS,
                description="Corroborating agreement across multiple sources",
                raw_input=[
                    {
                        "source": "WikiCFP Detail",
                        "raw_value": "2026-09-15",
                        "authority_tier": SourceAuthorityTier.DETAIL_PAGE,
                    },
                    {
                        "source": "Conference Calendar",
                        "raw_value": "2026-09-15",
                        "authority_tier": SourceAuthorityTier.GENERAL_AGGREGATOR,
                    },
                ],
                expected_deadline_type=DeadlineType.SUBMISSION,
                expected_status=DeadlineTemporalStatus.UPCOMING,
                expected_urgency_tier=UrgencyTier.APPROACHING,
                expected_conflict_state=ConflictState.EQUIVALENT_SOURCES,
                expected_selected_source="WikiCFP Detail",
                expected_local_date="2026-09-15",
                reference_time=ref,
            ),
        ])

        # ── Group H: Safety & Invariants ──────────────────────────────────────
        self.fixtures.extend([
            DeadlineFixture(
                fixture_id="SAFE-01",
                category=DeadlineEvaluationCategory.SAFETY_INVARIANTS,
                description="Missing deadline must never be reported as expired",
                raw_input=None,
                expected_deadline_type=DeadlineType.SUBMISSION,
                expected_status=DeadlineTemporalStatus.MISSING,
                expected_urgency_tier=UrgencyTier.UNKNOWN,
                reference_time=ref,
            ),
            DeadlineFixture(
                fixture_id="SAFE-02",
                category=DeadlineEvaluationCategory.SAFETY_INVARIANTS,
                description="Opportunity with only event dates must leave submission as missing",
                raw_input={
                    "event_start_date": "2026-10-01",
                    "event_end_date": "2026-10-03",
                },
                expected_deadline_type=DeadlineType.SUBMISSION,
                expected_status=DeadlineTemporalStatus.MISSING,
                expected_urgency_tier=UrgencyTier.UNKNOWN,
                reference_time=ref,
            ),
            DeadlineFixture(
                fixture_id="SAFE-03",
                category=DeadlineEvaluationCategory.SAFETY_INVARIANTS,
                description="Invalid timezone must yield INVALID status without silent UTC fallback",
                raw_input="September 20, 2026 17:00 Mars/Olympus",
                expected_deadline_type=DeadlineType.SUBMISSION,
                expected_status=DeadlineTemporalStatus.INVALID,
                expected_urgency_tier=UrgencyTier.UNKNOWN,
                reference_time=ref,
            ),
        ])

        # ── Group I: Real-World Fixtures (Scraped WikiCFP) ─────────────────────
        self.fixtures.extend([
            DeadlineFixture(
                fixture_id="REAL-01",
                category=DeadlineEvaluationCategory.REAL_WORLD_FIXTURES,
                description="WikiCFP Detail Page: ICMLNS 2026 multi-milestone extraction",
                raw_input={
                    "title": "International Conference on Machine Learning and Neural Systems",
                    "abstract_deadline": "Aug 10, 2026",
                    "submission_deadline": "Aug 22, 2026 23:59 AoE",
                    "notification_date": "Sep 15, 2026",
                    "camera_ready_deadline": "Oct 1, 2026",
                    "event_start_date": "Oct 24, 2026",
                    "event_end_date": "Oct 25, 2026",
                },
                expected_deadline_type=DeadlineType.SUBMISSION,
                expected_status=DeadlineTemporalStatus.EXPIRED,
                expected_urgency_tier=UrgencyTier.EXPIRED,
                expected_local_date="2026-08-22",
                expected_timezone_name="AoE",
                expected_is_aoe=True,
                reference_time=ref,
            ),
            DeadlineFixture(
                fixture_id="REAL-02",
                category=DeadlineEvaluationCategory.REAL_WORLD_FIXTURES,
                description="WikiCFP List Page: ICAIT 2026 date-only submission entry",
                raw_input={
                    "title": "15th International Conference on Advanced Computer Science",
                    "submission_deadline": "Aug 22, 2026",
                    "event_start_date": "Oct 24, 2026",
                    "event_end_date": "Oct 25, 2026",
                },
                expected_deadline_type=DeadlineType.SUBMISSION,
                expected_status=DeadlineTemporalStatus.EXPIRED,
                expected_urgency_tier=UrgencyTier.EXPIRED,
                expected_local_date="2026-08-22",
                expected_timezone_name="AoE",
                expected_is_aoe=True,
                reference_time=ref,
            ),
        ])

    def get_fixtures(self, category: DeadlineEvaluationCategory | None = None) -> list[DeadlineFixture]:
        """Return all fixtures, optionally filtered by category."""
        if category is None:
            return list(self.fixtures)
        return [f for f in self.fixtures if f.category == category]

    def summary(self) -> dict[str, Any]:
        """Return structured summary of the dataset."""
        cat_counts = {}
        for f in self.fixtures:
            cat_counts[f.category.value] = cat_counts.get(f.category.value, 0) + 1
        return {
            "total_fixtures": len(self.fixtures),
            "category_distribution": cat_counts,
        }


# Singleton evaluation dataset instance
deadline_evaluation_dataset = DeadlineEvaluationDataset()
