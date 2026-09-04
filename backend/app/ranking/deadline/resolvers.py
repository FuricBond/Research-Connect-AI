"""
Deadline Conflict, Extension and Multi-Source Intelligence Engine (Phase 2.7E).

Provides deterministic temporal equivalence comparison, revision/extension classification,
source authority supersession, multi-milestone isolation, and canonical deadline views.

CRITICAL INVARIANTS:
1. Phase 2.7E analyzes revisions and multi-source conflicts. It does NOT modify
   Phase 2.5 ranking weights, academic features, or Phase 2.6 predatory risk scoring.
2. Equivalence is evaluated on normalized temporal semantics, NEVER raw text strings.
   (e.g. 'Aug 22, 2026 AoE' and '2026-08-23T11:59:59Z' are equivalent).
3. Missing != Retracted. Missing fields are never treated as retractions without affirmative evidence.
4. Different milestones (Submission vs Notification vs Event Start) are independent and NEVER conflict.
5. Ingestion order != Source authority. A newer database scrape does not automatically supersede a trusted source.
6. When equal-authority sources report conflicting deadlines without superseding evidence,
   the conflict MUST be preserved (canonical_deadline = None, conflict_state = SOURCE_CONFLICT).
   Never fabricate a winner.
7. Pure, deterministic, in-memory execution: 0 DB queries, 0 network calls.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import logging
from typing import Any

from app.ranking.deadline.intelligence import (
    DEFAULT_MAX_URGENCY_WINDOW_DAYS,
    MILESTONE_LABELS,
    PRIMARY_MILESTONE_PRECEDENCE,
    DeadlineIntelligence,
)
from app.ranking.deadline.models import (
    CanonicalDeadlineView,
    ConflictState,
    DeadlineAssessment,
    DeadlineEvidence,
    DeadlineEvidenceCollection,
    DeadlineObservation,
    DeadlinePrecision,
    DeadlineProvenance,
    DeadlineRevision,
    DeadlineType,
    DefaultTimezonePolicy,
    ExtractionMethod,
    NormalizationStatus,
    NormalizedDeadline,
    OpportunityCanonicalView,
    RevisionClassification,
    SourceAuthorityTier,
    TimezoneSource,
)
from app.ranking.deadline.normalizers import DeadlineNormalizer

logger = logging.getLogger(__name__)


# ── Temporal Equivalence ──────────────────────────────────────────────────────


def are_deadlines_equivalent(
    d1: NormalizedDeadline | None,
    d2: NormalizedDeadline | None,
) -> bool:
    """
    Determine whether two normalized deadlines express the identical temporal instant or date.

    Compares normalized temporal semantics, NOT raw string syntax.

    Parameters
    ----------
    d1:
        First normalized deadline.
    d2:
        Second normalized deadline.

    Returns
    -------
    bool:
        True if temporally equivalent, False otherwise.
    """
    if d1 is None and d2 is None:
        return True
    if d1 is None or d2 is None:
        return False

    # Status matching for non-normalized deadlines
    if (
        d1.normalization_status == NormalizationStatus.MISSING
        and d2.normalization_status == NormalizationStatus.MISSING
    ):
        return True

    if (
        d1.normalization_status != NormalizationStatus.NORMALIZED
        and d1.normalization_status == d2.normalization_status
        and d1.local_date == d2.local_date
        and d1.normalized_utc == d2.normalized_utc
    ):
        return True

    # High-precision UTC instant comparison
    if d1.normalized_utc is not None and d2.normalized_utc is not None:
        utc1 = (
            d1.normalized_utc
            if d1.normalized_utc.tzinfo is not None
            else d1.normalized_utc.replace(tzinfo=timezone.utc)
        )
        utc2 = (
            d2.normalized_utc
            if d2.normalized_utc.tzinfo is not None
            else d2.normalized_utc.replace(tzinfo=timezone.utc)
        )
        diff_seconds = abs((utc1 - utc2).total_seconds())
        # Identical instant within 1 second tolerance
        return diff_seconds < 1.0

    # Date-only fallback when UTC instants are not synthesized
    if d1.local_date is not None and d2.local_date is not None:
        return d1.local_date == d2.local_date

    return False


# ── Source Authority Inference ────────────────────────────────────────────────


def infer_source_authority(
    source: str | None = None,
    provenance: DeadlineProvenance | None = None,
    source_url: str | None = None,
) -> SourceAuthorityTier:
    """
    Infer evidentiary authority tier for deadline conflict resolution.

    CRITICAL: Determines source reliability for deadline dates only.
    Must not be used for Phase 2.5 ranking or Phase 2.6 risk scoring.
    """
    # 1. Detail page provenance on aggregators
    if provenance == DeadlineProvenance.WIKICFP_DETAIL_PAGE:
        return SourceAuthorityTier.DETAIL_PAGE

    # 2. Inspect source URL if available
    if source_url:
        u_lower = source_url.lower()
        if any(
            token in u_lower
            for token in ("official", "conference", "symposium", ".edu/", ".ac.uk", ".org/")
        ):
            if "wikicfp" not in u_lower and "openalex" not in u_lower and "crossref" not in u_lower:
                return SourceAuthorityTier.OFFICIAL_CFP

    # 3. Inspect source name
    if source:
        s_lower = source.lower()
        if "official" in s_lower or "organizer" in s_lower or "primary_cfp" in s_lower:
            return SourceAuthorityTier.OFFICIAL_CFP
        if "wikicfp_detail" in s_lower or "detail" in s_lower:
            return SourceAuthorityTier.DETAIL_PAGE
        if "wikicfp" in s_lower:
            return SourceAuthorityTier.LIST_PAGE
        if "openalex" in s_lower or "crossref" in s_lower:
            return SourceAuthorityTier.GENERAL_AGGREGATOR

    if provenance == DeadlineProvenance.WIKICFP_LIST_PAGE:
        return SourceAuthorityTier.LIST_PAGE

    if provenance in (DeadlineProvenance.OPENALEX, DeadlineProvenance.CROSSREF):
        return SourceAuthorityTier.GENERAL_AGGREGATOR

    return SourceAuthorityTier.UNKNOWN


def _format_obs_date(obs: DeadlineObservation) -> str:
    """Format an observation date for human explanations."""
    if obs.is_retracted:
        return "Retracted"
    if obs.normalized_deadline is not None:
        nd = obs.normalized_deadline
        if nd.local_date is not None:
            tz_tag = f" {nd.timezone_name}" if nd.timezone_name else ""
            return f"{nd.local_date.isoformat()}{tz_tag}"
        if nd.normalized_utc is not None:
            return nd.normalized_utc.strftime("%Y-%m-%d %H:%M UTC")
    if obs.raw_value:
        return obs.raw_value.strip()
    return "unspecified"


# ── Revision and Extension Classification ─────────────────────────────────────


def classify_revision(
    previous_obs: DeadlineObservation | None,
    current_obs: DeadlineObservation,
) -> DeadlineRevision:
    """
    Classify transition between two sequential deadline observations.

    Distinguishes INITIAL, EXTENDED, MOVED_EARLIER, UNCHANGED, REPLACED, RETRACTED.
    """
    effective_type = current_obs.deadline_type
    milestone_label = MILESTONE_LABELS.get(effective_type, "Deadline")

    # 1. Retraction handling
    if current_obs.is_retracted:
        expl = f"{milestone_label} retracted by source"
        if current_obs.retraction_evidence:
            expl += f": {current_obs.retraction_evidence}."
        else:
            expl += "."
        return DeadlineRevision(
            deadline_type=effective_type,
            previous_observation=previous_obs,
            current_observation=current_obs,
            classification=RevisionClassification.RETRACTED,
            days_diff=None,
            hours_diff=None,
            explanation=expl,
            metadata={"is_retracted": True},
        )

    # 2. Initial observation
    if previous_obs is None:
        expl = f"Initial {milestone_label.lower()} observed: {_format_obs_date(current_obs)}."
        return DeadlineRevision(
            deadline_type=effective_type,
            previous_observation=None,
            current_observation=current_obs,
            classification=RevisionClassification.INITIAL,
            days_diff=None,
            hours_diff=None,
            explanation=expl,
            metadata={"status": "initial_observation"},
        )

    # 3. Reinstatement after retraction
    if previous_obs.is_retracted and not current_obs.is_retracted:
        expl = f"{milestone_label} reinstated after previous retraction: {_format_obs_date(current_obs)}."
        return DeadlineRevision(
            deadline_type=effective_type,
            previous_observation=previous_obs,
            current_observation=current_obs,
            classification=RevisionClassification.INITIAL,
            days_diff=None,
            hours_diff=None,
            explanation=expl,
            metadata={"reinstated": True},
        )

    # 4. Previous missing / newly populated
    if (
        previous_obs.normalized_deadline is None
        or previous_obs.normalized_deadline.normalization_status == NormalizationStatus.MISSING
    ):
        if (
            current_obs.normalized_deadline is not None
            and current_obs.normalized_deadline.normalization_status != NormalizationStatus.MISSING
        ):
            expl = f"{milestone_label} established: {_format_obs_date(current_obs)}."
            return DeadlineRevision(
                deadline_type=effective_type,
                previous_observation=previous_obs,
                current_observation=current_obs,
                classification=RevisionClassification.INITIAL,
                days_diff=None,
                hours_diff=None,
                explanation=expl,
            )

    # 5. Current observation dropped / unobserved (without explicit retraction)
    if (
        current_obs.normalized_deadline is None
        or current_obs.normalized_deadline.normalization_status == NormalizationStatus.MISSING
    ):
        expl = f"{milestone_label} observation removed, but no explicit retraction evidence was found."
        return DeadlineRevision(
            deadline_type=effective_type,
            previous_observation=previous_obs,
            current_observation=current_obs,
            classification=RevisionClassification.REPLACED,
            days_diff=None,
            hours_diff=None,
            explanation=expl,
            metadata={"missing_not_retracted": True},
        )

    # 6. Temporal equivalence check
    if are_deadlines_equivalent(previous_obs.normalized_deadline, current_obs.normalized_deadline):
        expl = f"{milestone_label} remains unchanged ({_format_obs_date(current_obs)})."
        return DeadlineRevision(
            deadline_type=effective_type,
            previous_observation=previous_obs,
            current_observation=current_obs,
            classification=RevisionClassification.UNCHANGED,
            days_diff=0.0,
            hours_diff=0.0,
            explanation=expl,
        )

    # 7. Exact UTC instant comparison for EXTENDED vs MOVED_EARLIER
    p_norm = previous_obs.normalized_deadline
    c_norm = current_obs.normalized_deadline

    if p_norm.normalized_utc is not None and c_norm.normalized_utc is not None:
        p_utc = (
            p_norm.normalized_utc
            if p_norm.normalized_utc.tzinfo is not None
            else p_norm.normalized_utc.replace(tzinfo=timezone.utc)
        )
        c_utc = (
            c_norm.normalized_utc
            if c_norm.normalized_utc.tzinfo is not None
            else c_norm.normalized_utc.replace(tzinfo=timezone.utc)
        )
        diff_seconds = (c_utc - p_utc).total_seconds()
        days_diff = round(diff_seconds / 86400.0, 2)
        hours_diff = round(diff_seconds / 3600.0, 2)

        if diff_seconds > 0:
            d_str = f"{days_diff:g} day" if abs(days_diff) == 1 else f"{days_diff:g} days"
            expl = (
                f"{milestone_label} extended from {_format_obs_date(previous_obs)} "
                f"to {_format_obs_date(current_obs)} ({d_str} extension)."
            )
            return DeadlineRevision(
                deadline_type=effective_type,
                previous_observation=previous_obs,
                current_observation=current_obs,
                classification=RevisionClassification.EXTENDED,
                days_diff=days_diff,
                hours_diff=hours_diff,
                explanation=expl,
            )
        elif diff_seconds < 0:
            d_str = (
                f"{abs(days_diff):g} day" if abs(days_diff) == 1 else f"{abs(days_diff):g} days"
            )
            expl = (
                f"{milestone_label} moved earlier from {_format_obs_date(previous_obs)} "
                f"to {_format_obs_date(current_obs)} ({d_str} earlier)."
            )
            return DeadlineRevision(
                deadline_type=effective_type,
                previous_observation=previous_obs,
                current_observation=current_obs,
                classification=RevisionClassification.MOVED_EARLIER,
                days_diff=days_diff,
                hours_diff=hours_diff,
                explanation=expl,
            )

    # 8. Date-only fallback comparison
    if p_norm.local_date is not None and c_norm.local_date is not None:
        d_diff = float((c_norm.local_date - p_norm.local_date).days)
        h_diff = d_diff * 24.0

        if d_diff > 0:
            d_str = f"{int(d_diff)} day" if d_diff == 1 else f"{int(d_diff)} days"
            expl = (
                f"{milestone_label} extended from {p_norm.local_date.isoformat()} "
                f"to {c_norm.local_date.isoformat()} ({d_str} extension)."
            )
            return DeadlineRevision(
                deadline_type=effective_type,
                previous_observation=previous_obs,
                current_observation=current_obs,
                classification=RevisionClassification.EXTENDED,
                days_diff=d_diff,
                hours_diff=h_diff,
                explanation=expl,
            )
        elif d_diff < 0:
            d_str = f"{abs(int(d_diff))} day" if abs(d_diff) == 1 else f"{abs(int(d_diff))} days"
            expl = (
                f"{milestone_label} moved earlier from {p_norm.local_date.isoformat()} "
                f"to {c_norm.local_date.isoformat()} ({d_str} earlier)."
            )
            return DeadlineRevision(
                deadline_type=effective_type,
                previous_observation=previous_obs,
                current_observation=current_obs,
                classification=RevisionClassification.MOVED_EARLIER,
                days_diff=d_diff,
                hours_diff=h_diff,
                explanation=expl,
            )

    # 9. Format replacement or unresolvable transition
    expl = f"{milestone_label} replaced from {_format_obs_date(previous_obs)} to {_format_obs_date(current_obs)}."
    return DeadlineRevision(
        deadline_type=effective_type,
        previous_observation=previous_obs,
        current_observation=current_obs,
        classification=RevisionClassification.REPLACED,
        days_diff=None,
        hours_diff=None,
        explanation=expl,
    )


# ── Canonical Conflict Resolver ───────────────────────────────────────────────


class DeadlineConflictResolver:
    """
    Authoritative conflict detection, source supersession, and canonical view synthesizer.
    """

    classify_revision = staticmethod(classify_revision)

    @classmethod
    def build_revision_history(
        cls,
        observations: list[DeadlineObservation],
    ) -> list[DeadlineRevision]:
        """
        Build step-by-step revision history across chronological observations.
        """
        if not observations:
            return []

        # Sort by observation_time if available, maintaining stable ordering
        def _sort_key(obs: DeadlineObservation) -> datetime:
            return obs.observation_time or datetime.min.replace(tzinfo=timezone.utc)

        sorted_obs = sorted(observations, key=_sort_key)
        revisions: list[DeadlineRevision] = []

        # First observation
        revisions.append(classify_revision(None, sorted_obs[0]))

        # Subsequent transitions
        for i in range(len(sorted_obs) - 1):
            revisions.append(classify_revision(sorted_obs[i], sorted_obs[i + 1]))

        return revisions

    @classmethod
    def resolve_milestone(
        cls,
        deadline_type: DeadlineType,
        observations: list[DeadlineObservation],
        reference_time: datetime | None = None,
        window_days: float | None = None,
    ) -> CanonicalDeadlineView:
        """
        Synthesize canonical deadline view for a single milestone across all source observations.

        Detects equivalence, applies source authority precedence, and transparently preserves conflicts.
        """
        label = MILESTONE_LABELS.get(deadline_type, "Deadline")
        ref = reference_time or datetime.now(timezone.utc)
        if ref.tzinfo is None:
            ref = ref.replace(tzinfo=timezone.utc)

        # 1. Zero observations
        if not observations:
            return CanonicalDeadlineView(
                deadline_type=deadline_type,
                canonical_deadline=None,
                canonical_assessment=None,
                selected_source=None,
                selected_observation=None,
                all_observations=[],
                revision_history=[],
                latest_revision=None,
                conflict_state=ConflictState.INSUFFICIENT_EVIDENCE,
                confidence=0.0,
                explanation=f"Insufficient evidence for {label.lower()}.",
                unresolved_alternatives=[],
            )

        # Build chronological revision history
        rev_history = cls.build_revision_history(observations)
        latest_rev = rev_history[-1] if rev_history else None

        # Filter active (non-retracted, present) observations
        active_obs = [
            obs
            for obs in observations
            if obs.is_current
            and not obs.is_retracted
            and obs.normalized_deadline is not None
            and obs.normalized_deadline.normalization_status != NormalizationStatus.MISSING
        ]

        # Check if all observations are retracted
        retracted_obs = [obs for obs in observations if obs.is_retracted]
        if not active_obs and retracted_obs:
            return CanonicalDeadlineView(
                deadline_type=deadline_type,
                canonical_deadline=None,
                canonical_assessment=None,
                selected_source=retracted_obs[-1].source,
                selected_observation=retracted_obs[-1],
                all_observations=observations,
                revision_history=rev_history,
                latest_revision=latest_rev,
                conflict_state=ConflictState.NO_CONFLICT,
                confidence=0.0,
                explanation=f"{label} explicitly retracted by source.",
                unresolved_alternatives=[],
            )

        # If no active observations remain
        if not active_obs:
            return CanonicalDeadlineView(
                deadline_type=deadline_type,
                canonical_deadline=None,
                canonical_assessment=None,
                selected_source=observations[-1].source,
                selected_observation=observations[-1],
                all_observations=observations,
                revision_history=rev_history,
                latest_revision=latest_rev,
                conflict_state=ConflictState.INSUFFICIENT_EVIDENCE,
                confidence=0.0,
                explanation=f"No active deadline specified for {label.lower()}.",
                unresolved_alternatives=[],
            )

        # Single active observation
        if len(active_obs) == 1:
            single = active_obs[0]
            assessment = DeadlineIntelligence.assess_deadline(
                single.normalized_deadline,
                reference_time=ref,
                window_days=window_days,
            )
            return CanonicalDeadlineView(
                deadline_type=deadline_type,
                canonical_deadline=single.normalized_deadline,
                canonical_assessment=assessment,
                selected_source=single.source,
                selected_observation=single,
                all_observations=observations,
                revision_history=rev_history,
                latest_revision=latest_rev,
                conflict_state=ConflictState.NO_CONFLICT,
                confidence=assessment.confidence,
                explanation=assessment.explanation,
                unresolved_alternatives=[],
            )

        # 2. Multiple active observations: Cluster by temporal equivalence
        clusters: list[list[DeadlineObservation]] = []
        for obs in active_obs:
            matched = False
            for cluster in clusters:
                if are_deadlines_equivalent(
                    obs.normalized_deadline,
                    cluster[0].normalized_deadline,
                ):
                    cluster.append(obs)
                    matched = True
                    break
            if not matched:
                clusters.append([obs])

        # Case A: Exactly 1 cluster — all sources report equivalent deadlines!
        if len(clusters) == 1:
            cluster = clusters[0]
            # Pick observation with highest authority tier and confidence
            def _best_obs_key(o: DeadlineObservation) -> tuple[int, float, float]:
                return (
                    o.authority_tier.value,
                    o.normalization_confidence,
                    o.source_confidence,
                )

            selected = max(cluster, key=_best_obs_key)
            assessment = DeadlineIntelligence.assess_deadline(
                selected.normalized_deadline,
                reference_time=ref,
                window_days=window_days,
            )
            expl = f"{label} is equivalent across {len(active_obs)} sources."
            return CanonicalDeadlineView(
                deadline_type=deadline_type,
                canonical_deadline=selected.normalized_deadline,
                canonical_assessment=assessment,
                selected_source=selected.source,
                selected_observation=selected,
                all_observations=observations,
                revision_history=rev_history,
                latest_revision=latest_rev,
                conflict_state=ConflictState.EQUIVALENT_SOURCES,
                confidence=assessment.confidence,
                explanation=expl,
                unresolved_alternatives=[],
                metadata={"cluster_count": 1, "source_count": len(active_obs)},
            )

        # Case B: Multiple distinct non-equivalent deadline clusters
        # Evaluate source authority precedence of each cluster
        cluster_scores: list[tuple[int, int, list[DeadlineObservation]]] = []
        for cluster in clusters:
            max_tier = max(o.authority_tier.value for o in cluster)
            cluster_scores.append((max_tier, len(cluster), cluster))

        # Sort clusters by authority tier descending, then by consensus size
        cluster_scores.sort(key=lambda x: (x[0], x[1]), reverse=True)

        top_tier, top_count, top_cluster = cluster_scores[0]
        second_tier, second_count, second_cluster = cluster_scores[1]

        # Check if top cluster strictly supersedes the second cluster by authority
        if top_tier > second_tier:
            # Authoritative source supersedes lower-tier source!
            def _best_obs_key(o: DeadlineObservation) -> tuple[int, float, float]:
                return (
                    o.authority_tier.value,
                    o.normalization_confidence,
                    o.source_confidence,
                )

            selected = max(top_cluster, key=_best_obs_key)
            assessment = DeadlineIntelligence.assess_deadline(
                selected.normalized_deadline,
                reference_time=ref,
                window_days=window_days,
            )
            # Alternatives are observations from superseded clusters
            alternatives = [obs for _, _, c in cluster_scores[1:] for obs in c]
            expl = f"{selected.source} supersedes older or lower-authority aggregator deadline."

            return CanonicalDeadlineView(
                deadline_type=deadline_type,
                canonical_deadline=selected.normalized_deadline,
                canonical_assessment=assessment,
                selected_source=selected.source,
                selected_observation=selected,
                all_observations=observations,
                revision_history=rev_history,
                latest_revision=latest_rev,
                conflict_state=ConflictState.SUPERSEDED,
                confidence=round(assessment.confidence * 0.90, 4),  # Slight penalty for conflict existence
                explanation=expl,
                unresolved_alternatives=alternatives,
                metadata={
                    "superseding_tier": top_tier,
                    "superseded_tier": second_tier,
                },
            )

        # Equal-authority sources disagree without safe precedence:
        # CRITICAL INVARIANT: PRESERVE CONFLICT. Never fabricate a canonical deadline.
        all_conflicting = active_obs
        expl = (
            f"{label} differs across {len(active_obs)} sources; "
            f"canonical deadline unresolved due to equal-authority conflict."
        )

        return CanonicalDeadlineView(
            deadline_type=deadline_type,
            canonical_deadline=None,
            canonical_assessment=None,
            selected_source=None,
            selected_observation=None,
            all_observations=observations,
            revision_history=rev_history,
            latest_revision=latest_rev,
            conflict_state=ConflictState.SOURCE_CONFLICT,
            confidence=0.0,
            explanation=expl,
            unresolved_alternatives=all_conflicting,
            metadata={
                "conflicting_clusters": len(clusters),
                "authority_tier": top_tier,
            },
        )

    @classmethod
    def resolve_opportunity(
        cls,
        observations: list[DeadlineObservation] | DeadlineEvidenceCollection,
        reference_time: datetime | None = None,
        window_days: float | None = None,
        opportunity_id: str | None = None,
    ) -> OpportunityCanonicalView:
        """
        Synthesize canonical views across all milestones for an opportunity.

        Selects the primary milestone view following authoritative precedence.
        """
        ref = reference_time or datetime.now(timezone.utc)
        if ref.tzinfo is None:
            ref = ref.replace(tzinfo=timezone.utc)

        # Convert DeadlineEvidenceCollection to observations if passed
        obs_list: list[DeadlineObservation] = []
        eff_opp_id = opportunity_id

        if isinstance(observations, DeadlineEvidenceCollection):
            eff_opp_id = eff_opp_id or observations.opportunity_id
            for ev in observations.items:
                norm = DeadlineNormalizer.normalize_evidence(ev)
                tier = infer_source_authority(
                    source=ev.source,
                    provenance=ev.provenance,
                    source_url=ev.source_url,
                )
                obs = DeadlineObservation(
                    opportunity_id=eff_opp_id,
                    deadline_type=ev.deadline_type,
                    raw_value=ev.raw_value,
                    normalized_deadline=norm,
                    source=ev.source,
                    source_url=ev.source_url,
                    provenance=ev.provenance,
                    extraction_method=ev.extraction_method,
                    authority_tier=tier,
                    normalization_confidence=norm.normalization_confidence,
                    source_confidence=ev.confidence,
                    is_current=True,
                    is_retracted=not ev.is_present and (ev.raw_value is not None and "retract" in ev.raw_value.lower()),
                )
                obs_list.append(obs)
        else:
            obs_list = observations
            if obs_list and eff_opp_id is None:
                eff_opp_id = obs_list[0].opportunity_id

        # Group observations by milestone type
        grouped: dict[DeadlineType, list[DeadlineObservation]] = {}
        for obs in obs_list:
            grouped.setdefault(obs.deadline_type, []).append(obs)

        # Resolve each milestone independently
        views: dict[DeadlineType, CanonicalDeadlineView] = {}
        for m_type, m_obs in grouped.items():
            views[m_type] = cls.resolve_milestone(
                deadline_type=m_type,
                observations=m_obs,
                reference_time=ref,
                window_days=window_days,
            )

        # Select primary view according to established precedence
        primary_view: CanonicalDeadlineView | None = None
        primary_milestone: DeadlineType = DeadlineType.SUBMISSION

        for p_type in PRIMARY_MILESTONE_PRECEDENCE:
            if p_type in views:
                v = views[p_type]
                # If valid canonical deadline or valid active conflict, select as primary
                if (
                    v.conflict_state != ConflictState.INSUFFICIENT_EVIDENCE
                    or v.canonical_deadline is not None
                ):
                    primary_view = v
                    primary_milestone = p_type
                    break

        if primary_view is None:
            if views:
                primary_milestone = next(iter(views.keys()))
                primary_view = views[primary_milestone]
            else:
                primary_milestone = DeadlineType.SUBMISSION
                primary_view = cls.resolve_milestone(
                    deadline_type=DeadlineType.SUBMISSION,
                    observations=[],
                    reference_time=ref,
                    window_days=window_days,
                )

        return OpportunityCanonicalView(
            opportunity_id=eff_opp_id,
            reference_time=ref,
            primary_milestone=primary_milestone,
            primary_view=primary_view,
            milestone_views=views,
            metadata={"milestone_count": len(views)},
        )
