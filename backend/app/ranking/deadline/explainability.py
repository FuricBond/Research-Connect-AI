"""
Deterministic Deadline Explainability Service for ResearchConnect AI (Phase 2.7F).

Translates Phase 2.7B–2.7E deadline intelligence and canonical views into
structured, loss-aware API schemas and deterministic, human-readable explanations.

CRITICAL INVARIANTS:
1. 100% offline, pure deterministic execution: 0 DB queries, 0 network calls, 0 LLM calls.
2. The domain layer (Phases 2.7B–2.7E) is the sole authority for dates, urgency, and conflicts.
3. Loss-aware: distinguishes UPCOMING, DUE_TODAY, EXPIRED, MISSING, INVALID, AMBIGUOUS,
   SOURCE_CONFLICT, SUPERSEDED, and EQUIVALENT_SOURCES without mapping to null.
4. Explains:
   - Primary milestone rationale
   - Evidentiary source selection
   - Conflict detection and why a canonical date cannot safely be fabricated
   - Historical revisions and extensions
"""
from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any

from app.ranking.deadline.extractors import DeadlineEvidenceExtractor
from app.ranking.deadline.intelligence import MILESTONE_LABELS
from app.ranking.deadline.models import (
    CanonicalDeadlineView,
    ConflictState,
    DeadlineAssessment,
    DeadlineEvidence,
    DeadlineObservation,
    DeadlineRevision,
    DeadlineType,
    NormalizedDeadline,
    OpportunityCanonicalView,
    RevisionClassification,
    SourceAuthorityTier,
)
from app.ranking.deadline.resolvers import DeadlineConflictResolver, _format_obs_date
from app.schemas.deadline import (
    CanonicalDeadlineViewSchema,
    DeadlineAssessmentSchema,
    DeadlineEvidenceSchema,
    DeadlineObservationSchema,
    DeadlineRevisionSchema,
    NormalizedDeadlineSchema,
    OpportunityDeadlineSchema,
)

logger = logging.getLogger(__name__)

_PRIMARY_MILESTONE_REASONS: dict[DeadlineType, str] = {
    DeadlineType.SUBMISSION: "Paper submission is the primary academic author milestone.",
    DeadlineType.ABSTRACT: "Abstract registration is the earliest mandatory author milestone.",
    DeadlineType.NOTIFICATION: "Notification date is the primary author decision milestone.",
    DeadlineType.CAMERA_READY: "Camera-ready deadline is the final publication manuscript cutoff.",
    DeadlineType.REGISTRATION: "Registration deadline is the author attendance commitment milestone.",
    DeadlineType.EVENT_START: "Event start date is the primary conference convening milestone.",
    DeadlineType.EVENT_END: "Event conclusion milestone.",
    DeadlineType.UNKNOWN: "Unspecified milestone.",
}


class DeadlineExplainabilityService:
    """
    Deterministic explainability service for academic deadline intelligence.
    """

    @classmethod
    def evidence_to_schema(cls, ev: DeadlineEvidence | None) -> DeadlineEvidenceSchema | None:
        """Convert domain DeadlineEvidence to Pydantic schema."""
        if ev is None:
            return None
        return DeadlineEvidenceSchema.model_validate(ev.to_dict())

    @classmethod
    def normalized_to_schema(cls, norm: NormalizedDeadline | None) -> NormalizedDeadlineSchema | None:
        """Convert domain NormalizedDeadline to Pydantic schema."""
        if norm is None:
            return None
        return NormalizedDeadlineSchema.model_validate(norm.to_dict())

    @classmethod
    def assessment_to_schema(cls, ass: DeadlineAssessment | None) -> DeadlineAssessmentSchema | None:
        """Convert domain DeadlineAssessment to Pydantic schema."""
        if ass is None:
            return None
        return DeadlineAssessmentSchema.model_validate(ass.to_dict())

    @classmethod
    def observation_to_schema(cls, obs: DeadlineObservation | None) -> DeadlineObservationSchema | None:
        """Convert domain DeadlineObservation to Pydantic schema."""
        if obs is None:
            return None
        return DeadlineObservationSchema.model_validate(obs.to_dict())

    @classmethod
    def revision_to_schema(cls, rev: DeadlineRevision | None) -> DeadlineRevisionSchema | None:
        """Convert domain DeadlineRevision to Pydantic schema."""
        if rev is None:
            return None
        return DeadlineRevisionSchema.model_validate(rev.to_dict())

    @classmethod
    def explain_canonical_view(
        cls,
        view: CanonicalDeadlineView,
    ) -> CanonicalDeadlineViewSchema:
        """
        Synthesize explainability rationales and convert CanonicalDeadlineView to schema.
        """
        label = MILESTONE_LABELS.get(view.deadline_type, "Deadline")

        # 1. Source selection rationale
        source_selection_reason: str | None = None
        if view.selected_source:
            if view.conflict_state == ConflictState.SUPERSEDED:
                tier_val = (
                    view.selected_observation.authority_tier.name
                    if view.selected_observation
                    else "Authoritative"
                )
                source_selection_reason = (
                    f"Selected authoritative source '{view.selected_source}' ({tier_val}) "
                    f"which supersedes lower-tier or older aggregator records."
                )
            elif view.conflict_state == ConflictState.EQUIVALENT_SOURCES:
                source_selection_reason = (
                    f"Selected '{view.selected_source}' from {len(view.all_observations)} "
                    f"sources reporting temporally equivalent deadlines."
                )
            elif view.conflict_state == ConflictState.NO_CONFLICT:
                source_selection_reason = (
                    f"Single verified source '{view.selected_source}'."
                )

        # 2. Conflict rationale
        conflict_reason: str | None = None
        unresolved_reason: str | None = None
        if view.conflict_state == ConflictState.SOURCE_CONFLICT:
            sources_summary = ", ".join(
                f"{obs.source} ({_format_obs_date(obs)})"
                for obs in view.unresolved_alternatives[:3]
            )
            conflict_reason = (
                f"Conflicting deadlines reported across {len(view.unresolved_alternatives)} "
                f"equal-authority sources: {sources_summary}."
            )
            unresolved_reason = (
                f"Canonical deadline for {label.lower()} remains unresolved to prevent "
                f"fabricating a winner without authoritative evidence."
            )
        elif view.conflict_state == ConflictState.INSUFFICIENT_EVIDENCE:
            unresolved_reason = f"Insufficient evidence to verify {label.lower()}."

        # 3. Extension rationale
        extension_reason: str | None = None
        if view.latest_revision:
            rev = view.latest_revision
            if rev.classification == RevisionClassification.EXTENDED:
                prev_d = (
                    _format_obs_date(rev.previous_observation)
                    if rev.previous_observation
                    else "earlier"
                )
                curr_d = _format_obs_date(rev.current_observation)
                d_str = (
                    f"{rev.days_diff:g} days"
                    if rev.days_diff is not None
                    else "extended"
                )
                extension_reason = (
                    f"{label} extended by {d_str} ({prev_d} -> {curr_d})."
                )
            elif rev.classification == RevisionClassification.MOVED_EARLIER:
                prev_d = (
                    _format_obs_date(rev.previous_observation)
                    if rev.previous_observation
                    else "later"
                )
                curr_d = _format_obs_date(rev.current_observation)
                d_str = (
                    f"{abs(rev.days_diff):g} days"
                    if rev.days_diff is not None
                    else "moved earlier"
                )
                extension_reason = (
                    f"{label} moved earlier by {d_str} ({prev_d} -> {curr_d})."
                )

        # 4. Deterministic composite explanation
        parts: list[str] = []
        if view.canonical_assessment:
            parts.append(view.canonical_assessment.explanation)
        elif view.explanation:
            parts.append(view.explanation)

        if extension_reason:
            parts.append(extension_reason)

        if conflict_reason:
            parts.append(conflict_reason)

        if unresolved_reason and view.conflict_state == ConflictState.SOURCE_CONFLICT:
            parts.append(unresolved_reason)

        deterministic_explanation = " ".join(parts).strip()

        return CanonicalDeadlineViewSchema(
            deadline_type=view.deadline_type.value,
            canonical_deadline=cls.normalized_to_schema(view.canonical_deadline),
            canonical_assessment=cls.assessment_to_schema(view.canonical_assessment),
            selected_source=view.selected_source,
            selected_observation=cls.observation_to_schema(view.selected_observation),
            all_observations=[
                cls.observation_to_schema(obs)  # type: ignore[misc]
                for obs in view.all_observations
                if obs is not None
            ],
            revision_history=[
                cls.revision_to_schema(rev)  # type: ignore[misc]
                for rev in view.revision_history
                if rev is not None
            ],
            latest_revision=cls.revision_to_schema(view.latest_revision),
            conflict_state=view.conflict_state.value,
            confidence=round(view.confidence, 4),
            explanation=view.explanation,
            unresolved_alternatives=[
                cls.observation_to_schema(obs)  # type: ignore[misc]
                for obs in view.unresolved_alternatives
                if obs is not None
            ],
            deterministic_explanation=deterministic_explanation,
            source_selection_reason=source_selection_reason,
            conflict_reason=conflict_reason,
            extension_reason=extension_reason,
            unresolved_reason=unresolved_reason,
            metadata=view.metadata,
        )

    @classmethod
    def explain_opportunity(
        cls,
        canonical_opp: OpportunityCanonicalView,
        opportunity: Any = None,
    ) -> OpportunityDeadlineSchema:
        """
        Synthesize composite opportunity deadline intelligence container with full explainability.
        """
        primary_schema = (
            cls.explain_canonical_view(canonical_opp.primary_view)
            if canonical_opp.primary_view
            else None
        )

        milestone_schemas: dict[str, CanonicalDeadlineViewSchema] = {}
        for m_type, m_view in canonical_opp.milestone_views.items():
            milestone_schemas[m_type.value] = cls.explain_canonical_view(m_view)

        has_extension = any(
            v.latest_revision is not None
            and v.latest_revision.classification == RevisionClassification.EXTENDED.value
            for v in milestone_schemas.values()
        )

        has_conflict = any(
            v.conflict_state == ConflictState.SOURCE_CONFLICT.value
            for v in milestone_schemas.values()
        )

        primary_reason = _PRIMARY_MILESTONE_REASONS.get(
            canonical_opp.primary_milestone,
            "Primary milestone determined by academic lifecycle precedence.",
        )

        # Composite summary string
        summary_parts: list[str] = []
        if primary_schema:
            if primary_schema.canonical_assessment:
                ass = primary_schema.canonical_assessment
                label = MILESTONE_LABELS.get(canonical_opp.primary_milestone, "Deadline")
                norm = primary_schema.canonical_deadline
                date_str = ""
                if norm and norm.local_date:
                    tz_suffix = f" {norm.timezone_name}" if norm.timezone_name else ""
                    date_str = f" {norm.local_date.isoformat()}{tz_suffix}"

                if ass.status == "UPCOMING":
                    days_str = (
                        f"{ass.days_remaining:g}d left"
                        if ass.days_remaining is not None
                        else "upcoming"
                    )
                    summary_parts.append(
                        f"{label}{date_str} • {ass.urgency_tier.capitalize()} ({days_str})"
                    )
                elif ass.status == "DUE_TODAY":
                    hours_str = (
                        f"{ass.hours_remaining:g}h left"
                        if ass.hours_remaining is not None
                        else "today"
                    )
                    summary_parts.append(f"{label} due today ({hours_str})")
                elif ass.status == "EXPIRED":
                    summary_parts.append(f"{label} expired{date_str}")
                else:
                    summary_parts.append(f"{label}: {ass.status.replace('_', ' ').capitalize()}")
            elif primary_schema.conflict_state == ConflictState.SOURCE_CONFLICT.value:
                summary_parts.append("Deadline conflict detected across sources (unresolved)")
            elif primary_schema.conflict_state == ConflictState.INSUFFICIENT_EVIDENCE.value:
                summary_parts.append("No active deadline specified")
            else:
                summary_parts.append(primary_schema.explanation or "Deadline intelligence active")

            if primary_schema.extension_reason:
                summary_parts.append(f"({primary_schema.extension_reason})")

        summary = " • ".join(summary_parts) if summary_parts else "Deadline intelligence active"

        return OpportunityDeadlineSchema(
            opportunity_id=canonical_opp.opportunity_id,
            reference_time=canonical_opp.reference_time,
            primary_milestone=canonical_opp.primary_milestone.value,
            primary_view=primary_schema,
            milestone_views=milestone_schemas,
            summary=summary,
            has_extension=has_extension,
            has_conflict=has_conflict,
            primary_reason=primary_reason,
            metadata=canonical_opp.metadata,
        )

    @classmethod
    def explain_opportunity_from_model(
        cls,
        opportunity: Any,
        reference_time: datetime | None = None,
    ) -> OpportunityDeadlineSchema:
        """
        Convenience endpoint helper: extracts evidence from an OpportunityModel or dict,
        resolves multi-milestones canonical views, and synthesizes full explainability.

        100% in-memory, 0 DB queries, 0 network calls.
        """
        ref = reference_time or datetime.now(timezone.utc)
        if ref.tzinfo is None:
            ref = ref.replace(tzinfo=timezone.utc)

        evidence_collection = DeadlineEvidenceExtractor.extract_from_opportunity_model(opportunity)
        canonical_opp = DeadlineConflictResolver.resolve_opportunity(
            evidence_collection,
            reference_time=ref,
            opportunity_id=str(getattr(opportunity, "id", None) or (opportunity.get("id") if isinstance(opportunity, dict) else None)),
        )
        return cls.explain_opportunity(canonical_opp, opportunity=opportunity)


# Global singleton instance
deadline_explainability_service = DeadlineExplainabilityService()
