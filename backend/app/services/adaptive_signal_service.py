"""
Phase 5.5 — Adaptive Preference Signal Aggregation & Personalization Bridge Service.

Manages recomputation, querying, and explainability for researcher adaptive preference signals:
  - Aggregates historical Phase 5.4 interactions into bounded, deterministic signals
  - Zero ML / Zero LLM / Zero neural networks / Zero collaborative filtering
  - Explicit preferences remain authoritative and are never mutated or overwritten
  - Strict privacy: Signals are strictly scoped to the authenticated researcher profile
  - Zero N+1 queries during aggregation or retrieval
"""
from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Optional, Sequence
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.adaptive_signal import (
    AdaptiveEvidenceState,
    AdaptivePreferenceSignalModel,
    AdaptiveSignalDimension,
)
from app.models.opportunity import OpportunityModel, OpportunityTopicModel
from app.models.research_profile import ResearchProfileModel
from app.models.researcher_interaction import ResearcherInteractionModel
from app.personalization.adaptive_config import (
    DEFAULT_ADAPTIVE_CONFIG,
    AdaptiveSignalConfig,
)
from app.personalization.adaptive_engine import AdaptiveSignalEngine
from app.personalization.adaptive_models import (
    AdaptivePreferenceSignal,
    AdaptiveSignalExplanationResponse,
    AdaptiveSignalsResponse,
)

logger = logging.getLogger(__name__)


class AdaptivePreferenceSignalService:
    """
    Service responsible for aggregating researcher interaction history into
    bounded, deterministic adaptive preference signals.
    """

    @classmethod
    def resolve_profile_id(cls, db: Session, identifier: uuid.UUID) -> uuid.UUID:
        """Resolve a ResearchProfileModel id from either profile_id or user_id."""
        profile = db.execute(
            select(ResearchProfileModel.id).where(ResearchProfileModel.id == identifier)
        ).scalar_one_or_none()
        if profile:
            return profile

        profile = db.execute(
            select(ResearchProfileModel.id).where(ResearchProfileModel.user_id == identifier)
        ).scalar_one_or_none()
        if profile:
            return profile

        raise ValueError(f"Researcher profile with ID '{identifier}' not found.")

    @staticmethod
    def _get_reset_cutoff(db: Session, profile_id: uuid.UUID) -> Optional[datetime]:
        """
        Returns the researcher's last personalization reset instant, or None if they have
        never reset. Derived-signal recomputation must ignore evidence at or before it.
        Tolerates schemas without the Phase 5.9 settings table.
        """
        from app.services.feedback_service import ResearcherFeedbackService

        return ResearcherFeedbackService.resolve_reset_cutoff(db, profile_id)

    @classmethod
    def recompute_adaptive_signals(
        cls,
        db: Session,
        profile_id: uuid.UUID,
        config: AdaptiveSignalConfig = DEFAULT_ADAPTIVE_CONFIG,
        reference_time: Optional[datetime] = None,
    ) -> list[AdaptivePreferenceSignal]:
        """
        Recompute all adaptive preference signals for a researcher from their interaction history.

        Guarantees:
          - Deterministic: identical interactions + reference time = identical signals.
          - Zero N+1: eager-loads opportunity metadata and topic associations in a single query.
          - Upserts into adaptive_preference_signals table, removing obsolete signals.
          - Preserves immutable Phase 5.4 interaction records.
          - Never alters explicit preferences (ResearcherPreferenceModel).
        """
        resolved_id = cls.resolve_profile_id(db, profile_id)
        ref_time = reference_time or datetime.now(timezone.utc)

        # 1. Fetch interaction records for this profile in a single query with eager-loaded
        #    opportunities, excluding anything recorded at or before the researcher's last
        #    personalization reset (Phase 5.9). Interactions stay in the append-only store
        #    for audit, but a reset is a cold start: pre-reset behaviour must not be
        #    re-aggregated into fresh signals.
        reset_cutoff = cls._get_reset_cutoff(db, resolved_id)
        stmt = (
            select(ResearcherInteractionModel)
            .options(
                joinedload(ResearcherInteractionModel.opportunity)
                .joinedload(OpportunityModel.topic_associations)
                .joinedload(OpportunityTopicModel.topic)
            )
            .where(ResearcherInteractionModel.profile_id == resolved_id)
            .order_by(ResearcherInteractionModel.created_at.desc())
        )
        if reset_cutoff is not None:
            stmt = stmt.where(ResearcherInteractionModel.created_at > reset_cutoff)
        interactions = db.execute(stmt).unique().scalars().all()

        # 2. Run pure deterministic aggregation engine
        computed_signals = AdaptiveSignalEngine.aggregate_interactions(
            profile_id=resolved_id,
            interactions=interactions,
            config=config,
            reference_time=ref_time,
        )

        # 3. Upsert into database
        existing_models = db.execute(
            select(AdaptivePreferenceSignalModel).where(
                AdaptivePreferenceSignalModel.profile_id == resolved_id
            )
        ).scalars().all()

        existing_by_key = {
            (m.dimension, m.signal_value): m for m in existing_models
        }

        new_keys: set[tuple[AdaptiveSignalDimension, str]] = set()

        for sig in computed_signals:
            key = (sig.dimension, sig.signal_value)
            new_keys.add(key)
            existing = existing_by_key.get(key)

            if existing:
                existing.positive_evidence_count = sig.positive_evidence_count
                existing.negative_evidence_count = sig.negative_evidence_count
                existing.total_evidence_count = sig.total_evidence_count
                existing.decay_adjusted_positive_weight = sig.decay_adjusted_positive_weight
                existing.decay_adjusted_negative_weight = sig.decay_adjusted_negative_weight
                existing.weighted_signal_strength = sig.weighted_signal_strength
                existing.confidence = sig.confidence
                existing.evidence_state = sig.evidence_state
                existing.evidence_window_days = sig.evidence_window_days
                existing.latest_evidence_timestamp = sig.latest_evidence_timestamp
                existing.algorithm_version = sig.algorithm_version
                existing.deterministic_explanation = sig.deterministic_explanation
                existing.updated_at = ref_time
            else:
                db_model = AdaptivePreferenceSignalModel(
                    id=sig.id,
                    profile_id=resolved_id,
                    dimension=sig.dimension,
                    signal_value=sig.signal_value,
                    positive_evidence_count=sig.positive_evidence_count,
                    negative_evidence_count=sig.negative_evidence_count,
                    total_evidence_count=sig.total_evidence_count,
                    decay_adjusted_positive_weight=sig.decay_adjusted_positive_weight,
                    decay_adjusted_negative_weight=sig.decay_adjusted_negative_weight,
                    weighted_signal_strength=sig.weighted_signal_strength,
                    confidence=sig.confidence,
                    evidence_state=sig.evidence_state,
                    evidence_window_days=sig.evidence_window_days,
                    latest_evidence_timestamp=sig.latest_evidence_timestamp,
                    algorithm_version=sig.algorithm_version,
                    deterministic_explanation=sig.deterministic_explanation,
                    created_at=sig.created_at,
                    updated_at=sig.updated_at,
                )
                db.add(db_model)

        # Clean up stale signals that no longer have evidence
        for key, old_model in existing_by_key.items():
            if key not in new_keys:
                db.delete(old_model)

        db.flush()
        logger.info(
            "Recomputed %d adaptive signals for profile %s (algorithm version: %s)",
            len(computed_signals),
            resolved_id,
            config.algorithm_version,
        )

        # Phase 5.8 governance is derived from the same behavioural history, and it was only
        # ever recalculated when someone happened to read the health or drift endpoint. It is
        # refreshed here so the gate that damps live ranking tracks the signals it governs.
        # A governance failure must not discard a valid signal recomputation, so it is
        # logged and swallowed; the gate then keeps its previous (or default) state.
        try:
            from app.services.personalization_governance_service import (
                PersonalizationGovernanceService,
            )

            PersonalizationGovernanceService.recompute_governance(
                db=db,
                profile_id=resolved_id,
                reference_time=ref_time,
            )
        except Exception as exc:
            logger.warning(
                "Governance recomputation after adaptive signal refresh failed",
                extra={"profile_id": str(resolved_id), "error": str(exc)},
            )

        return computed_signals

    @classmethod
    def get_adaptive_signals(
        cls,
        db: Session,
        profile_id: uuid.UUID,
        dimension: Optional[AdaptiveSignalDimension] = None,
        state: Optional[AdaptiveEvidenceState] = None,
    ) -> list[AdaptivePreferenceSignal]:
        """Retrieve persisted adaptive signals for a researcher, with optional dimension/state filtering."""
        resolved_id = cls.resolve_profile_id(db, profile_id)

        stmt = select(AdaptivePreferenceSignalModel).where(
            AdaptivePreferenceSignalModel.profile_id == resolved_id
        )

        if dimension is not None:
            stmt = stmt.where(AdaptivePreferenceSignalModel.dimension == dimension)
        if state is not None:
            stmt = stmt.where(AdaptivePreferenceSignalModel.evidence_state == state)

        stmt = stmt.order_by(
            AdaptivePreferenceSignalModel.weighted_signal_strength.desc(),
            AdaptivePreferenceSignalModel.confidence.desc(),
        )

        try:
            models = db.execute(stmt).scalars().all()
            return [AdaptivePreferenceSignal.model_validate(m) for m in models]
        except Exception as err:
            logger.warning("Could not query adaptive_preference_signals: %s", err)
            return []


    @classmethod
    def get_adaptive_signal_by_id(
        cls,
        db: Session,
        profile_id: uuid.UUID,
        signal_id: uuid.UUID,
    ) -> Optional[AdaptivePreferenceSignal]:
        """Retrieve a specific adaptive signal ensuring researcher isolation."""
        resolved_id = cls.resolve_profile_id(db, profile_id)

        model = db.execute(
            select(AdaptivePreferenceSignalModel).where(
                AdaptivePreferenceSignalModel.id == signal_id,
                AdaptivePreferenceSignalModel.profile_id == resolved_id,
            )
        ).scalar_one_or_none()

        if not model:
            return None
        return AdaptivePreferenceSignal.model_validate(model)

    @classmethod
    def get_adaptive_signals_summary_explanation(
        cls,
        db: Session,
        profile_id: uuid.UUID,
    ) -> AdaptiveSignalExplanationResponse:
        """Generate a deterministic, structured summary explanation of all adaptive signals for a researcher."""
        signals = cls.get_adaptive_signals(db, profile_id)
        resolved_id = cls.resolve_profile_id(db, profile_id)

        established_count = sum(1 for s in signals if s.evidence_state == AdaptiveEvidenceState.ESTABLISHED or s.evidence_state == AdaptiveEvidenceState.STRONG)
        emerging_count = sum(1 for s in signals if s.evidence_state == AdaptiveEvidenceState.EMERGING)
        insufficient_count = sum(1 for s in signals if s.evidence_state == AdaptiveEvidenceState.INSUFFICIENT_EVIDENCE)
        conflict_count = sum(
            1
            for s in signals
            if s.positive_evidence_count > 0
            and s.negative_evidence_count > 0
            and abs(s.weighted_signal_strength) < 0.30
        )


        dim_explanations: dict[str, list[str]] = {}
        for s in signals:
            dim_key = s.dimension.value
            dim_explanations.setdefault(dim_key, []).append(s.deterministic_explanation)

        if not signals or (established_count == 0 and emerging_count == 0):
            summary = "Insufficient interaction evidence to establish adaptive preference signals. As you save, express interest, or dismiss opportunities, bounded behavioral patterns will emerge."
        else:
            summary = (
                f"Adaptive behavioral profile: {established_count} established interest(s), "
                f"{emerging_count} emerging pattern(s), and {conflict_count} mixed/conflicting signal(s) "
                f"derived deterministically from your recent opportunity activity."
            )

        return AdaptiveSignalExplanationResponse(
            profile_id=resolved_id,
            established_signals_count=established_count,
            emerging_signals_count=emerging_count,
            insufficient_signals_count=insufficient_count,
            conflict_signals_count=conflict_count,
            summary_explanation=summary,
            dimension_explanations=dim_explanations,
        )
