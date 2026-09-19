"""
Phase 5.4 — Researcher Feedback & Interaction Signal Foundation Service.

Manages recording, querying, and aggregating researcher-opportunity interactions:
  - Append-only auditable event logging
  - Explicit feedback vs passive observation classification
  - Idempotency & rapid-fire deduplication protection
  - Zero N+1 query aggregation for summaries and histories
  - Strict independence: Never modifies explicit preferences, rankings, risk, or deadlines
  - Zero ML / Zero LLM / Zero external network calls
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import Sequence
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.opportunity import OpportunityModel
from app.models.research_profile import ResearchProfileModel
from app.models.researcher_interaction import (
    EXPLICIT_FEEDBACK_TYPES,
    NEGATIVE_EXPLICIT_TYPES,
    PASSIVE_OBSERVATION_TYPES,
    POSITIVE_EXPLICIT_TYPES,
    InteractionType,
    ResearcherInteractionModel,
)
from app.schemas.researcher_interaction import (
    InteractionCreateRequest,
    InteractionResponse,
    OpportunityInteractionHistoryResponse,
    ResearcherInteractionSummaryResponse,
)

logger = logging.getLogger(__name__)

# Deduplication window for rapid identical clicks (in seconds)
RAPID_DEDUPLICATION_WINDOW_SECONDS = 2.0


class ResearcherInteractionService:
    """
    Service responsible for recording and retrieving researcher interactions with opportunities.
    """

    @classmethod
    def record_interaction(
        cls,
        db: Session,
        profile_id: uuid.UUID,
        opportunity_id: uuid.UUID,
        payload: InteractionCreateRequest,
    ) -> InteractionResponse:
        """
        Record a researcher-opportunity interaction event idempotently.

        Guarantees:
          - Validates researcher profile and opportunity existence.
          - Append-only: historical events are preserved for auditability.
          - Idempotency:
            1. If client_event_id is provided and already recorded for this profile,
               returns the existing event without duplicating.
            2. If an identical event (profile, opportunity, type) was recorded within
               the rapid deduplication window (2s), returns the existing event.
          - Strict classification: VIEWED and OPENED have is_explicit_feedback=False.
            INTERESTED, NOT_INTERESTED, DISMISSED, HIDDEN, SAVED, APPLIED, SHARED
            have is_explicit_feedback=True.
          - Inviolability: Never mutates ResearcherPreferenceModel, Phase 4 ranking,
            Phase 2.6 risk, or Phase 2.7 deadline intelligence.
        """
        # 1. Resolve Profile
        profile = db.execute(
            select(ResearchProfileModel).where(ResearchProfileModel.id == profile_id)
        ).scalar_one_or_none()
        if not profile:
            profile = db.execute(
                select(ResearchProfileModel).where(ResearchProfileModel.user_id == profile_id)
            ).scalar_one_or_none()
        if not profile:
            raise ValueError(f"Researcher profile with ID '{profile_id}' not found.")

        # 2. Resolve Opportunity
        opp = db.execute(
            select(OpportunityModel).where(OpportunityModel.id == opportunity_id)
        ).scalar_one_or_none()
        if not opp:
            raise ValueError(f"Opportunity with ID '{opportunity_id}' not found.")

        now_utc = datetime.now(timezone.utc)
        i_type = payload.interaction_type
        i_type_str = i_type.value

        # 3. Check client_event_id idempotency
        if payload.client_event_id:
            existing_by_client_id = db.execute(
                select(ResearcherInteractionModel).where(
                    ResearcherInteractionModel.profile_id == profile.id,
                    ResearcherInteractionModel.client_event_id == payload.client_event_id,
                )
            ).scalar_one_or_none()
            if existing_by_client_id:
                logger.info(
                    "Idempotency hit for client_event_id %s (profile=%s)",
                    payload.client_event_id,
                    profile.id,
                )
                return InteractionResponse.model_validate(existing_by_client_id)

        # 4. Check rapid-fire deduplication window
        window_start = now_utc - timedelta(seconds=RAPID_DEDUPLICATION_WINDOW_SECONDS)
        recent_duplicate = db.execute(
            select(ResearcherInteractionModel)
            .where(
                ResearcherInteractionModel.profile_id == profile.id,
                ResearcherInteractionModel.opportunity_id == opp.id,
                ResearcherInteractionModel.interaction_type == i_type_str,
                ResearcherInteractionModel.created_at >= window_start,
            )
            .order_by(ResearcherInteractionModel.created_at.desc())
        ).scalars().first()

        if recent_duplicate:
            logger.info(
                "Rapid deduplication hit for %s on opportunity %s (profile=%s)",
                i_type_str,
                opp.id,
                profile.id,
            )
            return InteractionResponse.model_validate(recent_duplicate)

        # 5. Determine explicit vs passive feedback
        is_explicit = i_type in EXPLICIT_FEEDBACK_TYPES

        # 6. Append interaction record
        interaction_record = ResearcherInteractionModel(
            id=uuid.uuid4(),
            profile_id=profile.id,
            opportunity_id=opp.id,
            interaction_type=i_type_str,
            is_explicit_feedback=is_explicit,
            source=payload.source,
            client_event_id=payload.client_event_id,
            metadata_payload=payload.metadata_payload or {},
            created_at=now_utc,
        )
        db.add(interaction_record)
        db.commit()
        db.refresh(interaction_record)

        return InteractionResponse.model_validate(interaction_record)

    @classmethod
    def get_opportunity_interactions(
        cls,
        db: Session,
        profile_id: uuid.UUID,
        opportunity_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> OpportunityInteractionHistoryResponse:
        """
        Retrieve chronological interaction history for a specific opportunity in the context of a researcher.
        """
        profile = db.execute(
            select(ResearchProfileModel).where(ResearchProfileModel.id == profile_id)
        ).scalar_one_or_none()
        if not profile:
            profile = db.execute(
                select(ResearchProfileModel).where(ResearchProfileModel.user_id == profile_id)
            ).scalar_one_or_none()
        if not profile:
            raise ValueError(f"Researcher profile with ID '{profile_id}' not found.")

        opp = db.execute(
            select(OpportunityModel).where(OpportunityModel.id == opportunity_id)
        ).scalar_one_or_none()
        if not opp:
            raise ValueError(f"Opportunity with ID '{opportunity_id}' not found.")

        base_stmt = select(ResearcherInteractionModel).where(
            ResearcherInteractionModel.profile_id == profile.id,
            ResearcherInteractionModel.opportunity_id == opp.id,
        )

        # Count total
        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total = db.execute(count_stmt).scalar() or 0

        # Fetch page ordered chronologically descending
        fetch_stmt = (
            base_stmt.order_by(
                ResearcherInteractionModel.created_at.desc(),
                ResearcherInteractionModel.id.desc(),
            )
            .limit(max(1, min(limit, 200)))
            .offset(max(0, offset))
        )
        records = db.execute(fetch_stmt).scalars().all()

        return OpportunityInteractionHistoryResponse(
            opportunity_id=opp.id,
            profile_id=profile.id,
            interactions=[InteractionResponse.model_validate(r) for r in records],
            total_count=total,
            limit=limit,
            offset=offset,
        )

    @classmethod
    def get_researcher_interaction_summary(
        cls,
        db: Session,
        profile_id: uuid.UUID,
        recent_limit: int = 10,
    ) -> ResearcherInteractionSummaryResponse:
        """
        Compute deterministic summary statistics of researcher interaction signals.
        Zero N+1: executed via single aggregation query + single indexed recent-events query.
        """
        profile = db.execute(
            select(ResearchProfileModel).where(ResearchProfileModel.id == profile_id)
        ).scalar_one_or_none()
        if not profile:
            profile = db.execute(
                select(ResearchProfileModel).where(ResearchProfileModel.user_id == profile_id)
            ).scalar_one_or_none()
        if not profile:
            raise ValueError(f"Researcher profile with ID '{profile_id}' not found.")

        # Initialize count dictionary with 0 for all supported types
        counts_by_type: dict[str, int] = {t.value: 0 for t in InteractionType}

        # Query counts grouped by interaction_type
        group_stmt = (
            select(
                ResearcherInteractionModel.interaction_type,
                func.count(ResearcherInteractionModel.id),
            )
            .where(ResearcherInteractionModel.profile_id == profile.id)
            .group_by(ResearcherInteractionModel.interaction_type)
        )
        for itype, cnt in db.execute(group_stmt).all():
            counts_by_type[itype] = cnt

        total_interactions = sum(counts_by_type.values())
        positive_explicit_count = sum(counts_by_type.get(t.value, 0) for t in POSITIVE_EXPLICIT_TYPES)
        negative_explicit_count = sum(counts_by_type.get(t.value, 0) for t in NEGATIVE_EXPLICIT_TYPES)

        # Fetch recent interactions
        recent_stmt = (
            select(ResearcherInteractionModel)
            .where(ResearcherInteractionModel.profile_id == profile.id)
            .order_by(
                ResearcherInteractionModel.created_at.desc(),
                ResearcherInteractionModel.id.desc(),
            )
            .limit(max(1, min(recent_limit, 50)))
        )
        recent_records = db.execute(recent_stmt).scalars().all()
        recent_interactions = [InteractionResponse.model_validate(r) for r in recent_records]
        most_recent = recent_interactions[0] if recent_interactions else None

        # Transparent bounded heuristic signal: [-1.0, 1.0]
        # (positive - negative) / (positive + negative + 1.0)
        interaction_strength: float | None = None
        explicit_total = positive_explicit_count + negative_explicit_count
        if explicit_total > 0:
            interaction_strength = round(
                (positive_explicit_count - negative_explicit_count) / (explicit_total + 1.0),
                4,
            )

        return ResearcherInteractionSummaryResponse(
            profile_id=profile.id,
            total_interactions=total_interactions,
            positive_explicit_count=positive_explicit_count,
            negative_explicit_count=negative_explicit_count,
            saved_count=counts_by_type.get(InteractionType.SAVED.value, 0),
            dismissed_count=counts_by_type.get(InteractionType.DISMISSED.value, 0),
            hidden_count=counts_by_type.get(InteractionType.HIDDEN.value, 0),
            interested_count=counts_by_type.get(InteractionType.INTERESTED.value, 0),
            not_interested_count=counts_by_type.get(InteractionType.NOT_INTERESTED.value, 0),
            viewed_count=counts_by_type.get(InteractionType.VIEWED.value, 0),
            opened_count=counts_by_type.get(InteractionType.OPENED.value, 0),
            applied_count=counts_by_type.get(InteractionType.APPLIED.value, 0),
            shared_count=counts_by_type.get(InteractionType.SHARED.value, 0),
            counts_by_type=counts_by_type,
            most_recent_interaction=most_recent,
            recent_interactions=recent_interactions,
            interaction_strength_signal=interaction_strength,
        )

    @classmethod
    def get_recent_interactions(
        cls,
        db: Session,
        profile_id: uuid.UUID,
        limit: int = 20,
        interaction_types: Sequence[InteractionType | str] | None = None,
    ) -> list[InteractionResponse]:
        """
        Retrieve recent interactions for a researcher, optionally filtered by interaction types.
        """
        profile = db.execute(
            select(ResearchProfileModel).where(ResearchProfileModel.id == profile_id)
        ).scalar_one_or_none()
        if not profile:
            profile = db.execute(
                select(ResearchProfileModel).where(ResearchProfileModel.user_id == profile_id)
            ).scalar_one_or_none()
        if not profile:
            raise ValueError(f"Researcher profile with ID '{profile_id}' not found.")

        stmt = select(ResearcherInteractionModel).where(
            ResearcherInteractionModel.profile_id == profile.id
        )
        if interaction_types:
            type_strs = [
                t.value if isinstance(t, InteractionType) else t
                for t in interaction_types
            ]
            stmt = stmt.where(ResearcherInteractionModel.interaction_type.in_(type_strs))

        stmt = stmt.order_by(
            ResearcherInteractionModel.created_at.desc(),
            ResearcherInteractionModel.id.desc(),
        ).limit(max(1, min(limit, 100)))

        records = db.execute(stmt).scalars().all()
        return [InteractionResponse.model_validate(r) for r in records]

    @classmethod
    def get_batch_opportunity_interaction_counts(
        cls,
        db: Session,
        profile_id: uuid.UUID,
        opportunity_ids: Sequence[uuid.UUID],
    ) -> dict[uuid.UUID, dict[str, int]]:
        """
        Aggregate interaction counts per opportunity for a batch of opportunities in a single query (zero N+1).
        """
        if not opportunity_ids:
            return {}

        profile = db.execute(
            select(ResearchProfileModel).where(ResearchProfileModel.id == profile_id)
        ).scalar_one_or_none()
        if not profile:
            profile = db.execute(
                select(ResearchProfileModel).where(ResearchProfileModel.user_id == profile_id)
            ).scalar_one_or_none()
        if not profile:
            raise ValueError(f"Researcher profile with ID '{profile_id}' not found.")

        stmt = (
            select(
                ResearcherInteractionModel.opportunity_id,
                ResearcherInteractionModel.interaction_type,
                func.count(ResearcherInteractionModel.id),
            )
            .where(
                ResearcherInteractionModel.profile_id == profile.id,
                ResearcherInteractionModel.opportunity_id.in_(list(opportunity_ids)),
            )
            .group_by(
                ResearcherInteractionModel.opportunity_id,
                ResearcherInteractionModel.interaction_type,
            )
        )

        results: dict[uuid.UUID, dict[str, int]] = {opp_id: {} for opp_id in opportunity_ids}
        for opp_id, itype, cnt in db.execute(stmt).all():
            results[opp_id][itype] = cnt

        return results
