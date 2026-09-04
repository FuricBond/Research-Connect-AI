"""
Unit and property tests for Phase 2.7E: Conflict, Extension & Multi-Deadline Intelligence.

Validates:
1. Temporal equivalence engine (are_deadlines_equivalent).
2. Revision & extension classification (INITIAL, EXTENDED, MOVED_EARLIER, UNCHANGED, REPLACED, RETRACTED).
3. Multi-source conflict detection (EQUIVALENT_SOURCES, SOURCE_CONFLICT, SUPERSEDED).
4. Evidentiary source authority supersession without fabrication.
5. Retractions vs missing semantics (missing != retracted).
6. Multi-milestone independence and primary precedence.
7. 15 strict safety invariants.
8. 100-run strict determinism.
9. In-memory batch benchmark performance (10, 50, 100, 200, 1000 items).
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import time as pytime
import pytest

from app.ranking.deadline import (
    CanonicalDeadlineView,
    ConflictState,
    DeadlineAssessment,
    DeadlineConflictResolver,
    DeadlineEvidence,
    DeadlineEvidenceCollection,
    DeadlineIntelligence,
    DeadlineNormalizer,
    DeadlineObservation,
    DeadlinePrecision,
    DeadlineProvenance,
    DeadlineRevision,
    DeadlineTemporalStatus,
    DeadlineType,
    DefaultTimezonePolicy,
    ExtractionMethod,
    NormalizationStatus,
    NormalizedDeadline,
    OpportunityCanonicalView,
    RevisionClassification,
    SourceAuthorityTier,
    TimezoneSource,
    UrgencyTier,
    are_deadlines_equivalent,
    classify_revision,
    infer_source_authority,
)


class TestTemporalEquivalence:
    """Validate are_deadlines_equivalent on normalized temporal semantics."""

    def test_exact_same_utc_instant(self):
        dt = datetime(2026, 8, 23, 11, 59, 59, tzinfo=timezone.utc)
        d1 = NormalizedDeadline(
            deadline_type=DeadlineType.SUBMISSION,
            normalized_utc=dt,
            normalization_status=NormalizationStatus.NORMALIZED,
        )
        d2 = NormalizedDeadline(
            deadline_type=DeadlineType.SUBMISSION,
            normalized_utc=dt,
            normalization_status=NormalizationStatus.NORMALIZED,
        )
        assert are_deadlines_equivalent(d1, d2) is True

    def test_aoe_vs_utc_instant_equivalence(self):
        """
        'Aug 22, 2026 AoE' (23:59:59 AoE = 11:59:59 UTC next day)
        must equal '2026-08-23 11:59:59 UTC'.
        """
        d1 = DeadlineNormalizer.normalize_raw_string("Aug 22, 2026 AoE", deadline_type=DeadlineType.SUBMISSION)
        d2 = DeadlineNormalizer.normalize_raw_string("2026-08-23 11:59:59 UTC", deadline_type=DeadlineType.SUBMISSION)

        assert d1.normalized_utc == d2.normalized_utc
        assert are_deadlines_equivalent(d1, d2) is True

    def test_explicit_offset_vs_utc_equivalence(self):
        """
        '2026-08-22 23:59:59 -12:00' must equal '2026-08-23 11:59:59 UTC'.
        """
        d1 = DeadlineNormalizer.normalize_raw_string("2026-08-22 23:59:59 -12:00", deadline_type=DeadlineType.SUBMISSION)
        d2 = DeadlineNormalizer.normalize_raw_string("2026-08-23 11:59:59 UTC", deadline_type=DeadlineType.SUBMISSION)

        assert are_deadlines_equivalent(d1, d2) is True

    def test_iana_dst_summer_vs_utc_equivalence(self):
        """
        July in New York (EDT = UTC-4): 17:00 EDT = 21:00 UTC.
        """
        d1 = DeadlineNormalizer.normalize_raw_string("July 15, 2026 17:00 America/New_York", deadline_type=DeadlineType.SUBMISSION)
        d2 = DeadlineNormalizer.normalize_raw_string("July 15, 2026 21:00 UTC", deadline_type=DeadlineType.SUBMISSION)

        assert are_deadlines_equivalent(d1, d2) is True

    def test_date_only_matching_calendar_date(self):
        # Two date-only deadlines without UTC instants (STRICT_UNKNOWN)
        d1 = NormalizedDeadline(
            deadline_type=DeadlineType.EVENT_START,
            local_date=date(2026, 10, 15),
            normalization_status=NormalizationStatus.DATE_ONLY,
        )
        d2 = NormalizedDeadline(
            deadline_type=DeadlineType.EVENT_START,
            local_date=date(2026, 10, 15),
            normalization_status=NormalizationStatus.DATE_ONLY,
        )
        assert are_deadlines_equivalent(d1, d2) is True

    def test_different_dates_not_equivalent(self):
        d1 = DeadlineNormalizer.normalize_raw_string("Aug 20, 2026", deadline_type=DeadlineType.SUBMISSION)
        d2 = DeadlineNormalizer.normalize_raw_string("Aug 27, 2026", deadline_type=DeadlineType.SUBMISSION)
        assert are_deadlines_equivalent(d1, d2) is False

    def test_different_times_not_equivalent(self):
        d1 = DeadlineNormalizer.normalize_raw_string("2026-08-22 12:00:00 UTC", deadline_type=DeadlineType.SUBMISSION)
        d2 = DeadlineNormalizer.normalize_raw_string("2026-08-22 18:00:00 UTC", deadline_type=DeadlineType.SUBMISSION)
        assert are_deadlines_equivalent(d1, d2) is False

    def test_missing_deadlines_equivalence(self):
        d1 = DeadlineNormalizer.normalize_raw_string(None, deadline_type=DeadlineType.SUBMISSION)
        d2 = DeadlineNormalizer.normalize_raw_string("TBA", deadline_type=DeadlineType.SUBMISSION)
        assert are_deadlines_equivalent(d1, d2) is True

        d3 = DeadlineNormalizer.normalize_raw_string("Aug 20, 2026", deadline_type=DeadlineType.SUBMISSION)
        assert are_deadlines_equivalent(d1, d3) is False


class TestRevisionAndExtensionClassification:
    """Validate classify_revision for INITIAL, EXTENDED, MOVED_EARLIER, UNCHANGED, RETRACTED, REPLACED."""

    def test_initial_observation(self):
        norm = DeadlineNormalizer.normalize_raw_string("Aug 20, 2026", deadline_type=DeadlineType.SUBMISSION)
        obs = DeadlineObservation(
            deadline_type=DeadlineType.SUBMISSION,
            raw_value="Aug 20, 2026",
            normalized_deadline=norm,
            source="wikicfp",
        )
        rev = classify_revision(None, obs)
        assert rev.classification == RevisionClassification.INITIAL
        assert "Initial submission deadline observed" in rev.explanation

    def test_deadline_extension(self):
        norm1 = DeadlineNormalizer.normalize_raw_string("Aug 20, 2026 AoE", deadline_type=DeadlineType.SUBMISSION)
        norm2 = DeadlineNormalizer.normalize_raw_string("Aug 27, 2026 AoE", deadline_type=DeadlineType.SUBMISSION)

        obs1 = DeadlineObservation(
            deadline_type=DeadlineType.SUBMISSION,
            raw_value="Aug 20, 2026 AoE",
            normalized_deadline=norm1,
            source="wikicfp",
            observation_time=datetime(2026, 6, 1, tzinfo=timezone.utc),
        )
        obs2 = DeadlineObservation(
            deadline_type=DeadlineType.SUBMISSION,
            raw_value="Aug 27, 2026 AoE",
            normalized_deadline=norm2,
            source="wikicfp",
            observation_time=datetime(2026, 7, 1, tzinfo=timezone.utc),
        )

        rev = classify_revision(obs1, obs2)
        assert rev.classification == RevisionClassification.EXTENDED
        assert rev.days_diff == 7.0
        assert "extended" in rev.explanation.lower()
        assert "7 days extension" in rev.explanation

    def test_deadline_moved_earlier(self):
        norm1 = DeadlineNormalizer.normalize_raw_string("Aug 27, 2026 AoE", deadline_type=DeadlineType.SUBMISSION)
        norm2 = DeadlineNormalizer.normalize_raw_string("Aug 20, 2026 AoE", deadline_type=DeadlineType.SUBMISSION)

        obs1 = DeadlineObservation(
            deadline_type=DeadlineType.SUBMISSION,
            raw_value="Aug 27, 2026 AoE",
            normalized_deadline=norm1,
        )
        obs2 = DeadlineObservation(
            deadline_type=DeadlineType.SUBMISSION,
            raw_value="Aug 20, 2026 AoE",
            normalized_deadline=norm2,
        )

        rev = classify_revision(obs1, obs2)
        assert rev.classification == RevisionClassification.MOVED_EARLIER
        assert rev.days_diff == -7.0
        assert "moved earlier" in rev.explanation.lower()
        assert "7 days earlier" in rev.explanation

    def test_unchanged_observation(self):
        norm1 = DeadlineNormalizer.normalize_raw_string("Aug 22, 2026 AoE", deadline_type=DeadlineType.SUBMISSION)
        norm2 = DeadlineNormalizer.normalize_raw_string("2026-08-23 11:59:59 UTC", deadline_type=DeadlineType.SUBMISSION)

        obs1 = DeadlineObservation(deadline_type=DeadlineType.SUBMISSION, normalized_deadline=norm1)
        obs2 = DeadlineObservation(deadline_type=DeadlineType.SUBMISSION, normalized_deadline=norm2)

        rev = classify_revision(obs1, obs2)
        assert rev.classification == RevisionClassification.UNCHANGED
        assert rev.days_diff == 0.0
        assert "remains unchanged" in rev.explanation.lower()

    def test_explicit_retraction(self):
        norm1 = DeadlineNormalizer.normalize_raw_string("Aug 22, 2026", deadline_type=DeadlineType.SUBMISSION)
        obs1 = DeadlineObservation(deadline_type=DeadlineType.SUBMISSION, normalized_deadline=norm1)
        obs2 = DeadlineObservation(
            deadline_type=DeadlineType.SUBMISSION,
            is_retracted=True,
            retraction_evidence="Submissions cancelled by organizers",
        )

        rev = classify_revision(obs1, obs2)
        assert rev.classification == RevisionClassification.RETRACTED
        assert "retracted by source" in rev.explanation.lower()
        assert "Submissions cancelled by organizers" in rev.explanation

    def test_missing_observation_is_replaced_not_retracted(self):
        norm1 = DeadlineNormalizer.normalize_raw_string("Aug 22, 2026", deadline_type=DeadlineType.SUBMISSION)
        norm2 = DeadlineNormalizer.normalize_raw_string(None, deadline_type=DeadlineType.SUBMISSION)

        obs1 = DeadlineObservation(deadline_type=DeadlineType.SUBMISSION, normalized_deadline=norm1)
        obs2 = DeadlineObservation(deadline_type=DeadlineType.SUBMISSION, normalized_deadline=norm2, is_retracted=False)

        rev = classify_revision(obs1, obs2)
        assert rev.classification == RevisionClassification.REPLACED
        assert "no explicit retraction evidence was found" in rev.explanation.lower()

    def test_sequential_multiple_extensions(self):
        norm1 = DeadlineNormalizer.normalize_raw_string("Aug 10, 2026 AoE", deadline_type=DeadlineType.SUBMISSION)
        norm2 = DeadlineNormalizer.normalize_raw_string("Aug 20, 2026 AoE", deadline_type=DeadlineType.SUBMISSION)
        norm3 = DeadlineNormalizer.normalize_raw_string("Aug 27, 2026 AoE", deadline_type=DeadlineType.SUBMISSION)

        obs = [
            DeadlineObservation(deadline_type=DeadlineType.SUBMISSION, normalized_deadline=norm1, observation_time=datetime(2026, 5, 1, tzinfo=timezone.utc)),
            DeadlineObservation(deadline_type=DeadlineType.SUBMISSION, normalized_deadline=norm2, observation_time=datetime(2026, 6, 1, tzinfo=timezone.utc)),
            DeadlineObservation(deadline_type=DeadlineType.SUBMISSION, normalized_deadline=norm3, observation_time=datetime(2026, 7, 1, tzinfo=timezone.utc)),
        ]

        history = DeadlineConflictResolver.build_revision_history(obs)
        assert len(history) == 3
        assert history[0].classification == RevisionClassification.INITIAL
        assert history[1].classification == RevisionClassification.EXTENDED
        assert history[1].days_diff == 10.0
        assert history[2].classification == RevisionClassification.EXTENDED
        assert history[2].days_diff == 7.0


class TestMultiSourceConflictAndSupersession:
    """Validate multi-source conflict resolution, equivalence, and authority supersession."""

    def test_two_sources_equivalent_deadlines(self):
        d_wikicfp = DeadlineNormalizer.normalize_raw_string("Aug 22, 2026 AoE", deadline_type=DeadlineType.SUBMISSION)
        d_official = DeadlineNormalizer.normalize_raw_string("2026-08-23 11:59:59 UTC", deadline_type=DeadlineType.SUBMISSION)

        obs1 = DeadlineObservation(
            deadline_type=DeadlineType.SUBMISSION,
            raw_value="Aug 22, 2026 AoE",
            normalized_deadline=d_wikicfp,
            source="wikicfp",
            authority_tier=SourceAuthorityTier.LIST_PAGE,
        )
        obs2 = DeadlineObservation(
            deadline_type=DeadlineType.SUBMISSION,
            raw_value="2026-08-23 11:59:59 UTC",
            normalized_deadline=d_official,
            source="official_site",
            authority_tier=SourceAuthorityTier.OFFICIAL_CFP,
        )

        view = DeadlineConflictResolver.resolve_milestone(
            DeadlineType.SUBMISSION,
            [obs1, obs2],
        )
        assert view.conflict_state == ConflictState.EQUIVALENT_SOURCES
        assert view.canonical_deadline is not None
        assert view.canonical_deadline.normalized_utc == datetime(2026, 8, 23, 11, 59, 59, tzinfo=timezone.utc)
        assert "equivalent across 2 sources" in view.explanation

    def test_official_source_supersedes_aggregator(self):
        """
        Official site reports Aug 27 AoE; aggregator list page still has Aug 20 AoE.
        Official site (Tier 4) must supersede aggregator (Tier 2).
        """
        d_old = DeadlineNormalizer.normalize_raw_string("Aug 20, 2026 AoE", deadline_type=DeadlineType.SUBMISSION)
        d_new = DeadlineNormalizer.normalize_raw_string("Aug 27, 2026 AoE", deadline_type=DeadlineType.SUBMISSION)

        obs_aggregator = DeadlineObservation(
            deadline_type=DeadlineType.SUBMISSION,
            raw_value="Aug 20, 2026 AoE",
            normalized_deadline=d_old,
            source="wikicfp",
            authority_tier=SourceAuthorityTier.LIST_PAGE,
        )
        obs_official = DeadlineObservation(
            deadline_type=DeadlineType.SUBMISSION,
            raw_value="Aug 27, 2026 AoE",
            normalized_deadline=d_new,
            source="official_portal",
            authority_tier=SourceAuthorityTier.OFFICIAL_CFP,
        )

        view = DeadlineConflictResolver.resolve_milestone(
            DeadlineType.SUBMISSION,
            [obs_aggregator, obs_official],
        )
        assert view.conflict_state == ConflictState.SUPERSEDED
        assert view.canonical_deadline is not None
        assert view.canonical_deadline.normalized_utc == d_new.normalized_utc
        assert view.selected_source == "official_portal"
        assert len(view.unresolved_alternatives) == 1
        assert "supersedes older or lower-authority" in view.explanation

    def test_equal_authority_conflict_preserved_without_fabrication(self):
        """
        Two aggregators (both Tier 2) report conflicting deadlines.
        Neither supersedes the other -> ConflictState.SOURCE_CONFLICT.
        Canonical deadline must remain None!
        """
        d1 = DeadlineNormalizer.normalize_raw_string("Aug 20, 2026 AoE", deadline_type=DeadlineType.SUBMISSION)
        d2 = DeadlineNormalizer.normalize_raw_string("Aug 27, 2026 AoE", deadline_type=DeadlineType.SUBMISSION)

        obs1 = DeadlineObservation(
            deadline_type=DeadlineType.SUBMISSION,
            raw_value="Aug 20, 2026 AoE",
            normalized_deadline=d1,
            source="aggregator_a",
            authority_tier=SourceAuthorityTier.LIST_PAGE,
        )
        obs2 = DeadlineObservation(
            deadline_type=DeadlineType.SUBMISSION,
            raw_value="Aug 27, 2026 AoE",
            normalized_deadline=d2,
            source="aggregator_b",
            authority_tier=SourceAuthorityTier.LIST_PAGE,
        )

        view = DeadlineConflictResolver.resolve_milestone(
            DeadlineType.SUBMISSION,
            [obs1, obs2],
        )
        assert view.conflict_state == ConflictState.SOURCE_CONFLICT
        assert view.canonical_deadline is None
        assert view.canonical_assessment is None
        assert view.confidence == 0.0
        assert len(view.unresolved_alternatives) == 2
        assert "unresolved due to equal-authority conflict" in view.explanation

    def test_three_sources_two_against_one_equal_authority(self):
        d_majority = DeadlineNormalizer.normalize_raw_string("Aug 20, 2026 AoE", deadline_type=DeadlineType.SUBMISSION)
        d_minority = DeadlineNormalizer.normalize_raw_string("Aug 27, 2026 AoE", deadline_type=DeadlineType.SUBMISSION)

        obs1 = DeadlineObservation(deadline_type=DeadlineType.SUBMISSION, normalized_deadline=d_majority, source="agg_1", authority_tier=SourceAuthorityTier.LIST_PAGE)
        obs2 = DeadlineObservation(deadline_type=DeadlineType.SUBMISSION, normalized_deadline=d_majority, source="agg_2", authority_tier=SourceAuthorityTier.LIST_PAGE)
        obs3 = DeadlineObservation(deadline_type=DeadlineType.SUBMISSION, normalized_deadline=d_minority, source="agg_3", authority_tier=SourceAuthorityTier.LIST_PAGE)

        view = DeadlineConflictResolver.resolve_milestone(
            DeadlineType.SUBMISSION,
            [obs1, obs2, obs3],
        )
        # Even with 2-against-1, all are equal Tier 2 aggregators without official provenance; conflict is preserved
        assert view.conflict_state == ConflictState.SOURCE_CONFLICT
        assert view.canonical_deadline is None


class TestMultiMilestoneIsolationAndPrecedence:
    """Validate milestone independence and primary view selection."""

    def test_different_milestones_never_conflict(self):
        d_sub = DeadlineNormalizer.normalize_raw_string("2026-08-20", deadline_type=DeadlineType.SUBMISSION)
        d_notif = DeadlineNormalizer.normalize_raw_string("2026-09-10", deadline_type=DeadlineType.NOTIFICATION)
        d_camera = DeadlineNormalizer.normalize_raw_string("2026-09-25", deadline_type=DeadlineType.CAMERA_READY)
        d_event = DeadlineNormalizer.normalize_raw_string("2026-10-15", deadline_type=DeadlineType.EVENT_START)

        obs = [
            DeadlineObservation(deadline_type=DeadlineType.SUBMISSION, normalized_deadline=d_sub, source="wikicfp"),
            DeadlineObservation(deadline_type=DeadlineType.NOTIFICATION, normalized_deadline=d_notif, source="wikicfp"),
            DeadlineObservation(deadline_type=DeadlineType.CAMERA_READY, normalized_deadline=d_camera, source="wikicfp"),
            DeadlineObservation(deadline_type=DeadlineType.EVENT_START, normalized_deadline=d_event, source="wikicfp"),
        ]

        opp_view = DeadlineConflictResolver.resolve_opportunity(obs)
        assert opp_view.primary_milestone == DeadlineType.SUBMISSION
        assert opp_view.primary_view.conflict_state == ConflictState.NO_CONFLICT

        # All milestones resolved cleanly without conflict
        assert opp_view.get_view(DeadlineType.SUBMISSION).conflict_state == ConflictState.NO_CONFLICT
        assert opp_view.get_view(DeadlineType.NOTIFICATION).conflict_state == ConflictState.NO_CONFLICT
        assert opp_view.get_view(DeadlineType.CAMERA_READY).conflict_state == ConflictState.NO_CONFLICT
        assert opp_view.get_view(DeadlineType.EVENT_START).conflict_state == ConflictState.NO_CONFLICT

    def test_missing_submission_selects_event_start_without_conflation(self):
        d_event = DeadlineNormalizer.normalize_raw_string("2026-10-15", deadline_type=DeadlineType.EVENT_START)
        obs = [
            DeadlineObservation(deadline_type=DeadlineType.EVENT_START, normalized_deadline=d_event, source="wikicfp"),
        ]

        opp_view = DeadlineConflictResolver.resolve_opportunity(obs)
        assert opp_view.primary_milestone == DeadlineType.EVENT_START
        assert opp_view.primary_view.deadline_type == DeadlineType.EVENT_START
        assert opp_view.get_view(DeadlineType.SUBMISSION) is None

    def test_primary_view_preserves_submission_conflict(self):
        """If submission has a conflict, primary view reflects that conflict."""
        d1 = DeadlineNormalizer.normalize_raw_string("Aug 20, 2026 AoE", deadline_type=DeadlineType.SUBMISSION)
        d2 = DeadlineNormalizer.normalize_raw_string("Aug 27, 2026 AoE", deadline_type=DeadlineType.SUBMISSION)
        d_event = DeadlineNormalizer.normalize_raw_string("Oct 15, 2026", deadline_type=DeadlineType.EVENT_START)

        obs = [
            DeadlineObservation(deadline_type=DeadlineType.SUBMISSION, normalized_deadline=d1, source="src1", authority_tier=SourceAuthorityTier.LIST_PAGE),
            DeadlineObservation(deadline_type=DeadlineType.SUBMISSION, normalized_deadline=d2, source="src2", authority_tier=SourceAuthorityTier.LIST_PAGE),
            DeadlineObservation(deadline_type=DeadlineType.EVENT_START, normalized_deadline=d_event, source="src1"),
        ]

        opp_view = DeadlineConflictResolver.resolve_opportunity(obs)
        assert opp_view.primary_milestone == DeadlineType.SUBMISSION
        assert opp_view.primary_view.conflict_state == ConflictState.SOURCE_CONFLICT
        assert opp_view.primary_view.canonical_deadline is None


class TestSafetyInvariants:
    """Validate all 15 Phase 2.7E safety invariants."""

    def test_invariant_1_missing_not_expired(self):
        norm = DeadlineNormalizer.normalize_raw_string(None, deadline_type=DeadlineType.SUBMISSION)
        obs = DeadlineObservation(deadline_type=DeadlineType.SUBMISSION, normalized_deadline=norm)
        view = DeadlineConflictResolver.resolve_milestone(DeadlineType.SUBMISSION, [obs])
        assert view.conflict_state == ConflictState.INSUFFICIENT_EVIDENCE
        assert view.canonical_assessment is None or view.canonical_assessment.is_expired() is False

    def test_invariant_2_missing_not_retracted(self):
        norm1 = DeadlineNormalizer.normalize_raw_string("Aug 20, 2026", deadline_type=DeadlineType.SUBMISSION)
        norm2 = DeadlineNormalizer.normalize_raw_string(None, deadline_type=DeadlineType.SUBMISSION)
        obs1 = DeadlineObservation(deadline_type=DeadlineType.SUBMISSION, normalized_deadline=norm1)
        obs2 = DeadlineObservation(deadline_type=DeadlineType.SUBMISSION, normalized_deadline=norm2)
        rev = classify_revision(obs1, obs2)
        assert rev.classification != RevisionClassification.RETRACTED
        assert rev.classification == RevisionClassification.REPLACED

    def test_invariant_3_unknown_tz_not_known_tz(self):
        norm_strict = DeadlineNormalizer.normalize_raw_string(
            "Aug 20, 2026",
            deadline_type=DeadlineType.EVENT_START,
            policy=DefaultTimezonePolicy.STRICT_UNKNOWN,
        )
        assert norm_strict.timezone_source == TimezoneSource.UNKNOWN
        assert norm_strict.normalized_utc is None

    def test_invariant_4_ambiguous_date_not_fabricated(self):
        norm = DeadlineNormalizer.normalize_raw_string("04/05/2026", deadline_type=DeadlineType.SUBMISSION)
        obs = DeadlineObservation(deadline_type=DeadlineType.SUBMISSION, normalized_deadline=norm)
        view = DeadlineConflictResolver.resolve_milestone(DeadlineType.SUBMISSION, [obs])
        assert view.canonical_deadline.normalization_status == NormalizationStatus.AMBIGUOUS
        assert view.canonical_assessment.urgency_score == 0.0

    def test_invariant_5_equivalent_dates_not_conflict(self):
        d1 = DeadlineNormalizer.normalize_raw_string("Aug 22, 2026 AoE", deadline_type=DeadlineType.SUBMISSION)
        d2 = DeadlineNormalizer.normalize_raw_string("2026-08-23 11:59:59 UTC", deadline_type=DeadlineType.SUBMISSION)
        obs1 = DeadlineObservation(deadline_type=DeadlineType.SUBMISSION, normalized_deadline=d1)
        obs2 = DeadlineObservation(deadline_type=DeadlineType.SUBMISSION, normalized_deadline=d2)
        view = DeadlineConflictResolver.resolve_milestone(DeadlineType.SUBMISSION, [obs1, obs2])
        assert view.conflict_state == ConflictState.EQUIVALENT_SOURCES

    def test_invariant_6_different_milestones_not_conflict(self):
        d1 = DeadlineNormalizer.normalize_raw_string("Aug 20, 2026", deadline_type=DeadlineType.SUBMISSION)
        d2 = DeadlineNormalizer.normalize_raw_string("Oct 10, 2026", deadline_type=DeadlineType.NOTIFICATION)
        obs = [
            DeadlineObservation(deadline_type=DeadlineType.SUBMISSION, normalized_deadline=d1),
            DeadlineObservation(deadline_type=DeadlineType.NOTIFICATION, normalized_deadline=d2),
        ]
        opp_view = DeadlineConflictResolver.resolve_opportunity(obs)
        assert opp_view.get_view(DeadlineType.SUBMISSION).conflict_state == ConflictState.NO_CONFLICT
        assert opp_view.get_view(DeadlineType.NOTIFICATION).conflict_state == ConflictState.NO_CONFLICT

    def test_invariant_7_obs_time_not_deadline_time(self):
        norm = DeadlineNormalizer.normalize_raw_string("Aug 20, 2026", deadline_type=DeadlineType.SUBMISSION)
        obs_time = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        obs = DeadlineObservation(
            deadline_type=DeadlineType.SUBMISSION,
            normalized_deadline=norm,
            observation_time=obs_time,
        )
        assert obs.observation_time != norm.normalized_utc

    def test_invariant_8_newer_ingestion_not_auto_higher_authority(self):
        """A newer observation from a low-authority aggregator does not beat an older official source."""
        d_official = DeadlineNormalizer.normalize_raw_string("Aug 27, 2026", deadline_type=DeadlineType.SUBMISSION)
        d_agg = DeadlineNormalizer.normalize_raw_string("Aug 20, 2026", deadline_type=DeadlineType.SUBMISSION)

        obs_official = DeadlineObservation(
            deadline_type=DeadlineType.SUBMISSION,
            normalized_deadline=d_official,
            source="official_portal",
            authority_tier=SourceAuthorityTier.OFFICIAL_CFP,
            observation_time=datetime(2026, 6, 1, tzinfo=timezone.utc),
        )
        obs_agg = DeadlineObservation(
            deadline_type=DeadlineType.SUBMISSION,
            normalized_deadline=d_agg,
            source="wikicfp_list",
            authority_tier=SourceAuthorityTier.LIST_PAGE,
            observation_time=datetime(2026, 7, 1, tzinfo=timezone.utc),  # Newer ingestion timestamp!
        )

        view = DeadlineConflictResolver.resolve_milestone(DeadlineType.SUBMISSION, [obs_official, obs_agg])
        assert view.conflict_state == ConflictState.SUPERSEDED
        assert view.selected_source == "official_portal"
        assert view.canonical_deadline.normalized_utc == d_official.normalized_utc

    def test_invariant_9_to_13_ranking_and_risk_orthogonality(self):
        """Conflict or extension state must not alter risk score or ranking weights."""
        norm_ext = DeadlineNormalizer.normalize_raw_string("Aug 27, 2026", deadline_type=DeadlineType.SUBMISSION)
        obs = DeadlineObservation(deadline_type=DeadlineType.SUBMISSION, normalized_deadline=norm_ext)
        view = DeadlineConflictResolver.resolve_milestone(DeadlineType.SUBMISSION, [obs])

        # Assert no risk attributes or ranking boosts exist in CanonicalDeadlineView
        view_dict = view.to_dict()
        assert "risk_score" not in view_dict
        assert "predatory" not in view_dict
        assert "relevance_boost" not in view_dict

    def test_invariant_14_determinism_across_100_runs(self):
        norm1 = DeadlineNormalizer.normalize_raw_string("Aug 20, 2026 AoE", deadline_type=DeadlineType.SUBMISSION)
        norm2 = DeadlineNormalizer.normalize_raw_string("Aug 27, 2026 AoE", deadline_type=DeadlineType.SUBMISSION)
        obs = [
            DeadlineObservation(deadline_type=DeadlineType.SUBMISSION, normalized_deadline=norm1, source="src1", authority_tier=SourceAuthorityTier.LIST_PAGE),
            DeadlineObservation(deadline_type=DeadlineType.SUBMISSION, normalized_deadline=norm2, source="src2", authority_tier=SourceAuthorityTier.OFFICIAL_CFP),
        ]
        ref = datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc)

        baseline = DeadlineConflictResolver.resolve_milestone(DeadlineType.SUBMISSION, obs, reference_time=ref).to_dict()
        for _ in range(100):
            run = DeadlineConflictResolver.resolve_milestone(DeadlineType.SUBMISSION, obs, reference_time=ref).to_dict()
            assert run == baseline

    def test_invariant_15_no_silent_evidence_loss(self):
        norm1 = DeadlineNormalizer.normalize_raw_string("Aug 20, 2026 AoE", deadline_type=DeadlineType.SUBMISSION)
        norm2 = DeadlineNormalizer.normalize_raw_string("Aug 27, 2026 AoE", deadline_type=DeadlineType.SUBMISSION)
        obs1 = DeadlineObservation(deadline_type=DeadlineType.SUBMISSION, normalized_deadline=norm1, source="src1")
        obs2 = DeadlineObservation(deadline_type=DeadlineType.SUBMISSION, normalized_deadline=norm2, source="src2")

        view = DeadlineConflictResolver.resolve_milestone(DeadlineType.SUBMISSION, [obs1, obs2])
        assert len(view.all_observations) == 2
        assert obs1 in view.all_observations
        assert obs2 in view.all_observations


class TestBatchBenchmarkPerformance:
    """Benchmark in-memory conflict resolution and revision scaling."""

    @pytest.mark.parametrize("candidate_count", [10, 50, 100, 200, 1000])
    def test_batch_resolution_scaling(self, candidate_count):
        ref = datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc)
        test_obs = [
            DeadlineObservation(
                deadline_type=DeadlineType.SUBMISSION,
                normalized_deadline=DeadlineNormalizer.normalize_raw_string(
                    "Aug 20, 2026 AoE", deadline_type=DeadlineType.SUBMISSION
                ),
                source="aggregator",
                authority_tier=SourceAuthorityTier.LIST_PAGE,
            ),
            DeadlineObservation(
                deadline_type=DeadlineType.SUBMISSION,
                normalized_deadline=DeadlineNormalizer.normalize_raw_string(
                    "Aug 27, 2026 AoE", deadline_type=DeadlineType.SUBMISSION
                ),
                source="official",
                authority_tier=SourceAuthorityTier.OFFICIAL_CFP,
            ),
        ]

        start_time = pytime.perf_counter()
        results = [
            DeadlineConflictResolver.resolve_milestone(
                DeadlineType.SUBMISSION,
                test_obs,
                reference_time=ref,
            )
            for _ in range(candidate_count)
        ]
        duration = pytime.perf_counter() - start_time

        assert len(results) == candidate_count
        avg_ms = (duration * 1000.0) / candidate_count
        # Target: < 0.1 ms/candidate
        assert avg_ms < 0.1, f"Candidate count {candidate_count}: {avg_ms:.4f} ms exceeds target 0.1 ms"
