"""
Phase 3.7 — Recommendation History Service.

Orchestrates recommendation snapshot recording, idempotency/cooldown deduplication,
historical auditing, and batch offline evaluation.

Strict Architectural Boundaries:
  - Point-in-time immutability: historical records are never mutated after creation.
  - Zero N+1 queries: all history and evaluation queries are batched.
  - Evaluation is strictly read-only and never modifies weights or preferences.
  - Polling deduplication: prevents rapid client queries from bloating history tables.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import logging
from typing import Any, Sequence
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.opportunity import OpportunityModel
from app.models.recommendation_history import (
    ResearcherRecommendationItemModel,
    ResearcherRecommendationSnapshotModel,
)
from app.models.research_profile import ResearchProfileModel
from app.models.researcher_feedback import ResearcherRecommendationFeedbackModel
from app.ranking.recommendation_evaluation_engine import (
    BINARY_RELEVANT_FEEDBACK_TYPES,
    RecommendationEvaluationEngine,
)
from app.schemas.personalized_ranking import PersonalizedRankedCandidateSchema
from app.schemas.recommendation_evaluation import (
    DataSufficiencyStatus,
    EvaluationMetricsSchema,
    RecommendationEvaluationResponse,
    VersionComparisonSummary,
)
from app.schemas.recommendation_history import (
    RecommendationHistoryListResponse,
    RecommendationItemSnapshotSchema,
    RecommendationOpportunityBriefSchema,
    RecommendationSnapshotResponseSchema,
    RecommendationSnapshotSummarySchema,
)

logger = logging.getLogger(__name__)


class RecommendationHistoryService:
    """
    Production-grade service managing recommendation snapshots and offline evaluation.
    """

    DEFAULT_COOLDOWN_MINUTES: int = 5

    @classmethod
    def compute_request_hash(
        cls,
        profile_id: uuid.UUID,
        ranking_version: str,
        ordered_opportunity_ids: Sequence[uuid.UUID],
    ) -> str:
        """
        Deterministic SHA-256 hash identifying recommendation outputs for polling deduplication.
        """
        raw_key = f"{profile_id}:{ranking_version}:{','.join(str(oid) for oid in ordered_opportunity_ids)}"
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    @classmethod
    def record_snapshot(
        cls,
        db: Session,
        profile_id: uuid.UUID,
        ranking_version: str,
        recommendations: Sequence[PersonalizedRankedCandidateSchema],
        candidate_count: int,
        request_context: dict[str, Any] | None = None,
        session_id: str | None = None,
        cooldown_minutes: int = DEFAULT_COOLDOWN_MINUTES,
        reference_time: datetime | None = None,
    ) -> ResearcherRecommendationSnapshotModel:
        """
        Atomically record an immutable snapshot of presented recommendations.

        Applies idempotency checks:
          1. If session_id is provided and already exists for this researcher, returns existing snapshot.
          2. If identical recommendations were recorded within cooldown_minutes, returns existing snapshot.
        """
        now = reference_time or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        ordered_opp_ids = [r.opportunity_id for r in recommendations]
        req_hash = cls.compute_request_hash(profile_id, ranking_version, ordered_opp_ids)

        # ── 1. Idempotency Check by session_id ────────────────────────────────
        if session_id:
            existing_by_session = (
                db.execute(
                    select(ResearcherRecommendationSnapshotModel)
                    .options(selectinload(ResearcherRecommendationSnapshotModel.items))
                    .where(
                        ResearcherRecommendationSnapshotModel.researcher_id == profile_id,
                        ResearcherRecommendationSnapshotModel.session_id == session_id,
                    )
                )
                .scalar_one_or_none()
            )
            if existing_by_session:
                return existing_by_session

        # ── 2. Polling Deduplication by request_hash + cooldown ───────────────
        if cooldown_minutes > 0:
            cutoff_time = now - timedelta(minutes=cooldown_minutes)
            recent_duplicate = (
                db.execute(
                    select(ResearcherRecommendationSnapshotModel)
                    .options(selectinload(ResearcherRecommendationSnapshotModel.items))
                    .where(
                        ResearcherRecommendationSnapshotModel.researcher_id == profile_id,
                        ResearcherRecommendationSnapshotModel.request_hash == req_hash,
                        ResearcherRecommendationSnapshotModel.created_at >= cutoff_time,
                    )
                    .order_by(ResearcherRecommendationSnapshotModel.created_at.desc())
                )
                .scalars()
                .first()
            )
            if recent_duplicate:
                return recent_duplicate

        # ── 3. Create Immutable Snapshot & Items ──────────────────────────────
        snapshot = ResearcherRecommendationSnapshotModel(
            researcher_id=profile_id,
            ranking_version=ranking_version,
            candidate_count=candidate_count,
            returned_count=len(recommendations),
            request_context=request_context or {},
            request_hash=req_hash,
            session_id=session_id,
            created_at=now,
        )
        db.add(snapshot)
        db.flush()

        for rec in recommendations:
            # Extract behavioral contribution safely if available
            beh_adj = 0.0
            if hasattr(rec, "score_breakdown") and rec.score_breakdown:
                beh_adj = float(rec.score_breakdown.behavioral_adjustment or 0.0)

            # Extract risk and deadline intelligence from opportunity schema
            risk_level = None
            deadline_status = None
            if hasattr(rec, "opportunity") and rec.opportunity:
                risk_level = rec.opportunity.risk_level
                deadline_status = rec.opportunity.deadline_status

            item = ResearcherRecommendationItemModel(
                snapshot_id=snapshot.id,
                opportunity_id=rec.opportunity_id,
                rank=rec.rank,
                base_relevance_score=round(float(rec.base_relevance_score), 4),
                personalization_score=round(float(rec.personalization_score), 4),
                behavioral_adjustment=round(beh_adj, 4),
                final_score=round(float(rec.final_score), 4),
                risk_level=risk_level,
                deadline_status=deadline_status,
                created_at=now,
            )
            db.add(item)

        db.commit()
        db.refresh(snapshot)
        return snapshot

    @classmethod
    def get_history(
        cls,
        db: Session,
        profile_id: uuid.UUID,
        limit: int = 20,
        offset: int = 0,
        ranking_version: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> RecommendationHistoryListResponse:
        """
        Retrieve paginated recommendation history for a researcher with zero N+1 queries.
        """
        safe_limit = max(1, min(limit, 100))
        safe_offset = max(0, offset)

        base_filter = [ResearcherRecommendationSnapshotModel.researcher_id == profile_id]

        if ranking_version:
            base_filter.append(ResearcherRecommendationSnapshotModel.ranking_version == ranking_version)
        if from_date:
            base_filter.append(ResearcherRecommendationSnapshotModel.created_at >= from_date)
        if to_date:
            base_filter.append(ResearcherRecommendationSnapshotModel.created_at <= to_date)

        # Count total matching snapshots
        total = db.scalar(
            select(func.count(ResearcherRecommendationSnapshotModel.id)).where(*base_filter)
        ) or 0

        # Fetch paginated snapshots with items eagerly loaded
        snapshots = (
            db.execute(
                select(ResearcherRecommendationSnapshotModel)
                .options(selectinload(ResearcherRecommendationSnapshotModel.items))
                .where(*base_filter)
                .order_by(ResearcherRecommendationSnapshotModel.created_at.desc())
                .offset(safe_offset)
                .limit(safe_limit)
            )
            .scalars()
            .all()
        )

        # Batch load top opportunity titles for summary presentation (zero N+1)
        top_opp_ids = set()
        for snap in snapshots:
            top_3 = sorted(snap.items, key=lambda i: i.rank)[:3]
            for item in top_3:
                top_opp_ids.add(item.opportunity_id)

        title_map: dict[uuid.UUID, str] = {}
        if top_opp_ids:
            title_rows = db.execute(
                select(OpportunityModel.id, OpportunityModel.title).where(
                    OpportunityModel.id.in_(top_opp_ids)
                )
            ).all()
            title_map = {row[0]: row[1] for row in title_rows}

        summaries: list[RecommendationSnapshotSummarySchema] = []
        for snap in snapshots:
            top_3_items = sorted(snap.items, key=lambda i: i.rank)[:3]
            top_titles = [
                title_map.get(item.opportunity_id, f"Opportunity {item.opportunity_id}")
                for item in top_3_items
            ]
            summaries.append(
                RecommendationSnapshotSummarySchema(
                    id=snap.id,
                    researcher_id=snap.researcher_id,
                    ranking_version=snap.ranking_version,
                    candidate_count=snap.candidate_count,
                    returned_count=snap.returned_count,
                    request_context=snap.request_context or {},
                    created_at=snap.created_at,
                    top_opportunity_titles=top_titles,
                )
            )

        return RecommendationHistoryListResponse(
            researcher_id=profile_id,
            items=summaries,
            total=total,
            limit=safe_limit,
            offset=safe_offset,
        )

    @classmethod
    def get_snapshot_detail(
        cls,
        db: Session,
        profile_id: uuid.UUID,
        snapshot_id: uuid.UUID,
    ) -> RecommendationSnapshotResponseSchema | None:
        """
        Retrieve detail of a specific recommendation snapshot, including opportunity metadata and feedback.
        """
        snapshot = (
            db.execute(
                select(ResearcherRecommendationSnapshotModel)
                .options(selectinload(ResearcherRecommendationSnapshotModel.items))
                .where(
                    ResearcherRecommendationSnapshotModel.id == snapshot_id,
                    ResearcherRecommendationSnapshotModel.researcher_id == profile_id,
                )
            )
            .scalar_one_or_none()
        )
        if not snapshot:
            return None

        # Batch load opportunities and feedback for items (2 queries total)
        item_opp_ids = [item.opportunity_id for item in snapshot.items]

        opps_map: dict[uuid.UUID, OpportunityModel] = {}
        if item_opp_ids:
            opp_models = (
                db.execute(
                    select(OpportunityModel).where(OpportunityModel.id.in_(item_opp_ids))
                )
                .scalars()
                .all()
            )
            opps_map = {opp.id: opp for opp in opp_models}

        feedback_map: dict[uuid.UUID, list[str]] = {}
        if item_opp_ids:
            feedbacks = (
                db.execute(
                    select(ResearcherRecommendationFeedbackModel).where(
                        ResearcherRecommendationFeedbackModel.researcher_id == profile_id,
                        ResearcherRecommendationFeedbackModel.opportunity_id.in_(item_opp_ids),
                    )
                )
                .scalars()
                .all()
            )
            for fb in feedbacks:
                feedback_map.setdefault(fb.opportunity_id, []).append(fb.feedback_type)

        sorted_items = sorted(snapshot.items, key=lambda i: i.rank)
        item_schemas: list[RecommendationItemSnapshotSchema] = []

        for item in sorted_items:
            opp = opps_map.get(item.opportunity_id)
            opp_brief = None
            if opp:
                opp_brief = RecommendationOpportunityBriefSchema(
                    id=opp.id,
                    title=opp.title,
                    opportunity_type=opp.opportunity_type,
                    delivery_mode=opp.delivery_mode,
                    organizer=opp.organizer,
                    submission_deadline=opp.submission_deadline,
                )

            item_schemas.append(
                RecommendationItemSnapshotSchema(
                    id=item.id,
                    snapshot_id=item.snapshot_id,
                    opportunity_id=item.opportunity_id,
                    rank=item.rank,
                    base_relevance_score=item.base_relevance_score,
                    personalization_score=item.personalization_score,
                    behavioral_adjustment=item.behavioral_adjustment,
                    final_score=item.final_score,
                    risk_level=item.risk_level,
                    deadline_status=item.deadline_status,
                    created_at=item.created_at,
                    opportunity=opp_brief,
                    user_feedback=feedback_map.get(item.opportunity_id, []),
                )
            )

        return RecommendationSnapshotResponseSchema(
            id=snapshot.id,
            researcher_id=snapshot.researcher_id,
            ranking_version=snapshot.ranking_version,
            candidate_count=snapshot.candidate_count,
            returned_count=snapshot.returned_count,
            request_context=snapshot.request_context or {},
            created_at=snapshot.created_at,
            items=item_schemas,
        )

    @classmethod
    def evaluate_recommendations(
        cls,
        db: Session,
        profile_id: uuid.UUID,
        ranking_version: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        include_comparison: bool = True,
        reference_time: datetime | None = None,
    ) -> RecommendationEvaluationResponse:
        """
        Execute offline evaluation across recommendation history and researcher feedback.

        Guarantees:
          - Zero N+1 queries: exactly 2 queries (1 for snapshots/items, 1 for feedback).
          - Strictly read-only: zero mutations.
          - Reproducible and deterministic.
        """
        ref_time = reference_time or datetime.now(timezone.utc)
        if ref_time.tzinfo is None:
            ref_time = ref_time.replace(tzinfo=timezone.utc)

        # ── Query 1: Batch load all matching snapshots + items ────────────────
        filters = [ResearcherRecommendationSnapshotModel.researcher_id == profile_id]
        if ranking_version:
            filters.append(ResearcherRecommendationSnapshotModel.ranking_version == ranking_version)
        if from_date:
            filters.append(ResearcherRecommendationSnapshotModel.created_at >= from_date)
        if to_date:
            filters.append(ResearcherRecommendationSnapshotModel.created_at <= to_date)

        snapshots = (
            db.execute(
                select(ResearcherRecommendationSnapshotModel)
                .options(selectinload(ResearcherRecommendationSnapshotModel.items))
                .where(*filters)
                .order_by(ResearcherRecommendationSnapshotModel.created_at.asc())
            )
            .scalars()
            .all()
        )

        total_snapshots = len(snapshots)
        total_recommendations = sum(len(s.items) for s in snapshots)

        # ── Query 2: Batch load all feedback for this researcher ──────────────
        feedback_rows = (
            db.execute(
                select(ResearcherRecommendationFeedbackModel).where(
                    ResearcherRecommendationFeedbackModel.researcher_id == profile_id
                )
            )
            .scalars()
            .all()
        )

        feedback_by_opp: dict[uuid.UUID, list[str]] = {}
        all_researcher_relevant_ids: set[uuid.UUID] = set()
        for fb in feedback_rows:
            feedback_by_opp.setdefault(fb.opportunity_id, []).append(fb.feedback_type)
            if fb.feedback_type.upper() in BINARY_RELEVANT_FEEDBACK_TYPES:
                all_researcher_relevant_ids.add(fb.opportunity_id)

        # Prepare ordered items per snapshot
        snapshots_ordered_items = [
            [item.opportunity_id for item in sorted(s.items, key=lambda i: i.rank)]
            for s in snapshots
        ]

        # Calculate primary aggregate metrics
        primary_metrics = RecommendationEvaluationEngine.calculate_aggregate_metrics(
            snapshots_with_ordered_items=snapshots_ordered_items,
            feedback_by_opp=feedback_by_opp,
            all_researcher_relevant_ids=all_researcher_relevant_ids,
        )

        # ── Ranking Comparison (R0 Baseline vs R1 Personalized vs R2 Behavioral)
        version_comparison: dict[str, VersionComparisonSummary] = {}
        if include_comparison and total_snapshots > 0:
            # Group snapshots by ranking_version
            snapshots_by_version: dict[str, list[list[uuid.UUID]]] = {}
            for s in snapshots:
                ordered = [item.opportunity_id for item in sorted(s.items, key=lambda i: i.rank)]
                snapshots_by_version.setdefault(s.ranking_version, []).append(ordered)

            version_display_names = {
                "phase2-baseline": "R0: Phase 2 Baseline Ranker",
                "phase3.5-personalized": "R1: Phase 3.5 Personalized Ranker",
                "phase3.7-v1": "R2: Phase 3.7 Behavioral Personalization",
            }

            for v_key, v_snapshots in snapshots_by_version.items():
                v_metrics = RecommendationEvaluationEngine.calculate_aggregate_metrics(
                    snapshots_with_ordered_items=v_snapshots,
                    feedback_by_opp=feedback_by_opp,
                    all_researcher_relevant_ids=all_researcher_relevant_ids,
                )
                display = version_display_names.get(v_key, f"Version: {v_key}")
                version_comparison[v_key] = VersionComparisonSummary(
                    ranking_version=v_key,
                    display_name=display,
                    sample_size=v_metrics.sample_size,
                    data_status=v_metrics.data_status,
                    metrics=v_metrics,
                )

        return RecommendationEvaluationResponse(
            researcher_id=profile_id,
            ranking_version=ranking_version,
            total_snapshots=total_snapshots,
            total_recommendations=total_recommendations,
            total_feedback_events=primary_metrics.feedback_count,
            data_status=primary_metrics.data_status,
            metrics=primary_metrics,
            ranking_comparison=version_comparison if include_comparison else None,
            evaluated_at=ref_time,
        )
