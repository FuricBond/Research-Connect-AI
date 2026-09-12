"""
Phase 3.6 — Researcher Feedback & Behavioral Learning Service.

Manages recording, querying, and aggregating feedback events with:
  - Idempotent event capture
  - Synchronized SavedOpportunityModel entity integration
  - Zero N+1 query batching with joined loads
  - Deterministic BehavioralProfile synthesis via FeedbackEngine
  - Negative signal opportunity suppression sets
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import Any, Sequence
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.opportunity import OpportunityModel, OpportunityTopicModel
from app.models.research_profile import ResearchProfileModel
from app.models.researcher_feedback import ResearcherRecommendationFeedbackModel
from app.models.researcher_preference import ResearcherPreferenceModel
from app.models.saved_opportunity import SavedOpportunityModel
from app.ranking.feedback_config import (
    FEEDBACK_EVENT_WEIGHTS,
    NEGATIVE_FEEDBACK_TYPES,
    POSITIVE_FEEDBACK_TYPES,
    SUPPRESSION_TTL_DAYS,
)
from app.ranking.feedback_engine import BehavioralProfile, FeedbackEngine
from app.schemas.researcher_feedback import (
    BehavioralSignalSchema,
    FeedbackCreateRequest,
    FeedbackItemResponse,
    FeedbackListResponse,
    FeedbackSummaryResponse,
    FeedbackType,
    FeedbackUpdateRequest,
)

logger = logging.getLogger(__name__)


class ResearcherFeedbackService:
    """
    Service managing persistent researcher feedback and behavioral learning (Phase 3.6).
    """

    @classmethod
    def record_feedback(
        cls,
        db: Session,
        researcher_id: uuid.UUID,
        payload: FeedbackCreateRequest,
    ) -> FeedbackItemResponse:
        """
        Record a feedback interaction event idempotently.

        Guarantees:
          - If feedback of the same type already exists for (researcher_id, opportunity_id),
            it updates the timestamp, notes, rank_position, and session info rather than duplicating.
          - If feedback is SAVE, synchronizes SavedOpportunityModel to maintain backwards compatibility.
          - Zero N+1: Returns joined opportunity metadata in response.
        """
        # 1. Resolve Profile
        profile = db.execute(
            select(ResearchProfileModel).where(ResearchProfileModel.id == researcher_id)
        ).scalar_one_or_none()
        if not profile:
            # Fallback: check if researcher_id is user_id
            profile = db.execute(
                select(ResearchProfileModel).where(ResearchProfileModel.user_id == researcher_id)
            ).scalar_one_or_none()

        if not profile:
            raise ValueError(f"Researcher profile with ID '{researcher_id}' not found.")

        # 2. Resolve Opportunity
        opp = db.execute(
            select(OpportunityModel)
            .options(joinedload(OpportunityModel.topic_associations))
            .where(OpportunityModel.id == payload.opportunity_id)
        ).unique().scalar_one_or_none()

        if not opp:
            raise ValueError(f"Opportunity with ID '{payload.opportunity_id}' not found.")

        f_type_str = payload.feedback_type.value.upper()
        now_utc = datetime.now(timezone.utc)

        # 3. Check for existing feedback of this type
        existing = db.execute(
            select(ResearcherRecommendationFeedbackModel).where(
                ResearcherRecommendationFeedbackModel.researcher_id == profile.id,
                ResearcherRecommendationFeedbackModel.opportunity_id == opp.id,
                ResearcherRecommendationFeedbackModel.feedback_type == f_type_str,
            )
        ).scalar_one_or_none()

        if existing:
            # Idempotent update
            existing.notes = payload.notes if payload.notes is not None else existing.notes
            existing.source = payload.source.value
            existing.rank_position = payload.rank_position if payload.rank_position is not None else existing.rank_position
            existing.recommendation_session_id = payload.recommendation_session_id or existing.recommendation_session_id
            if payload.metadata_snapshot:
                existing.metadata_snapshot = payload.metadata_snapshot
            existing.updated_at = now_utc
            feedback_record = existing
        else:
            # Create new feedback record
            feedback_record = ResearcherRecommendationFeedbackModel(
                id=uuid.uuid4(),
                researcher_id=profile.id,
                opportunity_id=opp.id,
                feedback_type=f_type_str,
                source=payload.source.value,
                notes=payload.notes,
                rank_position=payload.rank_position,
                recommendation_session_id=payload.recommendation_session_id,
                metadata_snapshot=payload.metadata_snapshot or {},
                created_at=now_utc,
                updated_at=now_utc,
            )
            db.add(feedback_record)

        # 4. Synchronize with SavedOpportunityModel on SAVE
        if f_type_str == FeedbackType.SAVE.value:
            saved_opp = db.execute(
                select(SavedOpportunityModel).where(
                    SavedOpportunityModel.user_id == profile.user_id,
                    SavedOpportunityModel.opportunity_id == opp.id,
                )
            ).scalar_one_or_none()

            if not saved_opp:
                new_saved = SavedOpportunityModel(
                    id=uuid.uuid4(),
                    user_id=profile.user_id,
                    opportunity_id=opp.id,
                    notes=payload.notes,
                    created_at=now_utc,
                )
                db.add(new_saved)
            elif payload.notes:
                saved_opp.notes = payload.notes

        db.commit()
        db.refresh(feedback_record)

        return FeedbackItemResponse(
            id=feedback_record.id,
            researcher_id=feedback_record.researcher_id,
            opportunity_id=feedback_record.opportunity_id,
            feedback_type=feedback_record.feedback_type,
            source=feedback_record.source,
            notes=feedback_record.notes,
            rank_position=feedback_record.rank_position,
            recommendation_session_id=feedback_record.recommendation_session_id,
            metadata_snapshot=feedback_record.metadata_snapshot,
            created_at=feedback_record.created_at,
            updated_at=feedback_record.updated_at,
            opportunity_title=opp.title,
            opportunity_type=opp.opportunity_type,
            delivery_mode=opp.delivery_mode,
            location=opp.location,
        )

    @classmethod
    def get_feedback_history(
        cls,
        db: Session,
        researcher_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
        feedback_type: str | None = None,
        opportunity_id: uuid.UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> FeedbackListResponse:
        """
        Query paginated feedback events with zero N+1 eagerly loaded opportunity metadata.
        """
        profile = db.execute(
            select(ResearchProfileModel).where(ResearchProfileModel.id == researcher_id)
        ).scalar_one_or_none()
        if not profile:
            profile = db.execute(
                select(ResearchProfileModel).where(ResearchProfileModel.user_id == researcher_id)
            ).scalar_one_or_none()
        if not profile:
            raise ValueError(f"Researcher profile with ID '{researcher_id}' not found.")

        # Build query
        base_stmt = select(ResearcherRecommendationFeedbackModel).where(
            ResearcherRecommendationFeedbackModel.researcher_id == profile.id
        )

        if feedback_type:
            base_stmt = base_stmt.where(
                ResearcherRecommendationFeedbackModel.feedback_type == feedback_type.strip().upper()
            )
        if opportunity_id:
            base_stmt = base_stmt.where(
                ResearcherRecommendationFeedbackModel.opportunity_id == opportunity_id
            )
        if date_from:
            if date_from.tzinfo is None:
                date_from = date_from.replace(tzinfo=timezone.utc)
            base_stmt = base_stmt.where(ResearcherRecommendationFeedbackModel.created_at >= date_from)
        if date_to:
            if date_to.tzinfo is None:
                date_to = date_to.replace(tzinfo=timezone.utc)
            base_stmt = base_stmt.where(ResearcherRecommendationFeedbackModel.created_at <= date_to)

        # Count total matching
        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total = db.execute(count_stmt).scalar() or 0

        # Fetch page with eager loaded opportunity
        fetch_stmt = (
            base_stmt.options(joinedload(ResearcherRecommendationFeedbackModel.opportunity))
            .order_by(ResearcherRecommendationFeedbackModel.created_at.desc())
            .limit(max(1, min(limit, 200)))
            .offset(max(0, offset))
        )
        records = db.execute(fetch_stmt).scalars().all()

        items = []
        for r in records:
            opp = r.opportunity
            items.append(
                FeedbackItemResponse(
                    id=r.id,
                    researcher_id=r.researcher_id,
                    opportunity_id=r.opportunity_id,
                    feedback_type=r.feedback_type,
                    source=r.source,
                    notes=r.notes,
                    rank_position=r.rank_position,
                    recommendation_session_id=r.recommendation_session_id,
                    metadata_snapshot=r.metadata_snapshot,
                    created_at=r.created_at,
                    updated_at=r.updated_at,
                    opportunity_title=opp.title if opp else None,
                    opportunity_type=opp.opportunity_type if opp else None,
                    delivery_mode=opp.delivery_mode if opp else None,
                    location=opp.location if opp else None,
                )
            )

        return FeedbackListResponse(
            items=items,
            total=total,
            limit=limit,
            offset=offset,
        )

    @classmethod
    def delete_feedback(
        cls,
        db: Session,
        researcher_id: uuid.UUID,
        feedback_id: uuid.UUID,
    ) -> bool:
        """
        Delete a feedback record and synchronize SavedOpportunityModel if applicable.
        """
        profile = db.execute(
            select(ResearchProfileModel).where(ResearchProfileModel.id == researcher_id)
        ).scalar_one_or_none()
        if not profile:
            profile = db.execute(
                select(ResearchProfileModel).where(ResearchProfileModel.user_id == researcher_id)
            ).scalar_one_or_none()
        if not profile:
            raise ValueError(f"Researcher profile with ID '{researcher_id}' not found.")

        record = db.execute(
            select(ResearcherRecommendationFeedbackModel).where(
                ResearcherRecommendationFeedbackModel.id == feedback_id,
                ResearcherRecommendationFeedbackModel.researcher_id == profile.id,
            )
        ).scalar_one_or_none()

        if not record:
            return False

        # If it was a SAVE event, clean up corresponding SavedOpportunityModel
        if record.feedback_type == FeedbackType.SAVE.value:
            saved_opp = db.execute(
                select(SavedOpportunityModel).where(
                    SavedOpportunityModel.user_id == profile.user_id,
                    SavedOpportunityModel.opportunity_id == record.opportunity_id,
                )
            ).scalar_one_or_none()
            if saved_opp:
                db.delete(saved_opp)

        db.delete(record)
        db.commit()
        return True

    @classmethod
    def get_behavioral_profile(
        cls,
        db: Session,
        researcher_id: uuid.UUID,
        reference_time: datetime | None = None,
        explicit_preferences: Sequence[ResearcherPreferenceModel] | None = None,
    ) -> BehavioralProfile:
        """
        Compute deterministic behavioral profile for researcher.

        Batch loads all feedback events and opportunities in a single query (zero N+1).
        """
        profile = db.execute(
            select(ResearchProfileModel).where(ResearchProfileModel.id == researcher_id)
        ).scalar_one_or_none()
        if not profile:
            profile = db.execute(
                select(ResearchProfileModel).where(ResearchProfileModel.user_id == researcher_id)
            ).scalar_one_or_none()
        if not profile:
            raise ValueError(f"Researcher profile with ID '{researcher_id}' not found.")

        # Batch load active explicit preferences for conflict protection if not provided
        if explicit_preferences is None:
            explicit_prefs = db.execute(
                select(ResearcherPreferenceModel).where(
                    ResearcherPreferenceModel.profile_id == profile.id,
                    ResearcherPreferenceModel.is_active == True,  # noqa: E712
                    ResearcherPreferenceModel.source == "EXPLICIT",
                )
            ).scalars().all()
        else:
            explicit_prefs = list(explicit_preferences)

        # Batch load all feedback with eager opportunity & topic associations (zero N+1)
        feedback_events = db.execute(
            select(ResearcherRecommendationFeedbackModel)
            .options(
                joinedload(ResearcherRecommendationFeedbackModel.opportunity)
                .selectinload(OpportunityModel.topic_associations)
                .joinedload(OpportunityTopicModel.topic)
            )
            .where(ResearcherRecommendationFeedbackModel.researcher_id == profile.id)
            .order_by(ResearcherRecommendationFeedbackModel.created_at.asc())
        ).unique().scalars().all()

        return FeedbackEngine.aggregate_feedback(
            researcher_id=profile.id,
            feedback_events=feedback_events,
            reference_time=reference_time,
            explicit_preferences=explicit_prefs,
        )

    @classmethod
    def get_feedback_summary(
        cls,
        db: Session,
        researcher_id: uuid.UUID,
        reference_time: datetime | None = None,
    ) -> FeedbackSummaryResponse:
        """
        Compute high-level feedback summary statistics and behavioral overview.
        """
        behavioral_profile = cls.get_behavioral_profile(
            db=db,
            researcher_id=researcher_id,
            reference_time=reference_time,
        )

        counts: dict[str, int] = {}
        for ft in FeedbackType:
            counts[ft.value] = 0

        # Query counts grouped by feedback_type
        group_stmt = (
            select(
                ResearcherRecommendationFeedbackModel.feedback_type,
                func.count(ResearcherRecommendationFeedbackModel.id),
            )
            .where(ResearcherRecommendationFeedbackModel.researcher_id == behavioral_profile.researcher_id)
            .group_by(ResearcherRecommendationFeedbackModel.feedback_type)
        )
        for ftype, cnt in db.execute(group_stmt).all():
            counts[ftype] = cnt

        return FeedbackSummaryResponse(
            total_feedback_count=behavioral_profile.total_feedback_events,
            counts_by_type=counts,
            top_positive_topics=behavioral_profile.top_positive_topics,
            top_negative_topics=behavioral_profile.top_negative_topics,
            overall_confidence=behavioral_profile.overall_confidence,
            suppressed_count=len(behavioral_profile.suppressed_opportunity_ids),
            is_cold_start=behavioral_profile.is_cold_start,
        )

    @classmethod
    def get_suppressed_opportunity_ids(
        cls,
        db: Session,
        researcher_id: uuid.UUID,
        reference_time: datetime | None = None,
    ) -> set[uuid.UUID]:
        """
        Return set of opportunity IDs suppressed by negative feedback.
        Single direct query with temporal TTL cutoff.
        """
        now = reference_time or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        cutoff = now - timedelta(days=SUPPRESSION_TTL_DAYS)

        stmt = select(ResearcherRecommendationFeedbackModel.opportunity_id).where(
            ResearcherRecommendationFeedbackModel.researcher_id == researcher_id,
            ResearcherRecommendationFeedbackModel.feedback_type.in_(
                [FeedbackType.DISMISS.value, FeedbackType.NOT_INTERESTED.value]
            ),
            ResearcherRecommendationFeedbackModel.created_at >= cutoff,
        )
        return set(db.execute(stmt).scalars().all())
