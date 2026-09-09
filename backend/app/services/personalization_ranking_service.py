"""
Phase 3.5 — Personalization Ranking Service.

Orchestrates the end-to-end personalization ranking pipeline:
  1. Batch loads canonical researcher profile context (profile, preferences, expertise) in a single pass.
  2. Retrieves high-quality candidate set via Phase 3.4 PersonalizedCandidateGenerationService.
  3. Computes authoritative Phase 2 base relevance scores via Phase 2 HybridRanker.
  4. Applies Phase 3.5 PersonalizationRanker with strictly bounded adjustment (<= 0.15).
  5. Enforces relevance dominance, Phase 2.6 risk safety, and Phase 2.7 deadline eligibility.
  6. Computes deterministic R0 vs R1 ablation summary metrics.
  7. Guarantees zero N+1 database queries.
"""
from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    OpportunityModel,
    ResearcherInterestModel,
    ResearcherPreferenceModel,
    ResearchProfileModel,
)

from app.ranking.hybrid_ranker import HybridRanker, RankingMode, hybrid_ranker
from app.ranking.personalization_ranker import (
    MAX_PERSONALIZATION_CONTRIBUTION,
    PersonalizationRanker,
    ResearcherPersonalizationContext,
    personalization_ranker,
)
from app.schemas.personalized_candidate import (
    PersonalizedCandidateItemSchema,
    PersonalizedCandidateSetResponse,
)
from app.schemas.personalized_ranking import (
    AblationSummarySchema,
    PersonalizedRankedCandidateSchema,
    PersonalizedRankingResponse,
)
from app.services.personalized_candidate_generation_service import (
    PersonalizedCandidateGenerationService,
)

logger = logging.getLogger(__name__)


class PersonalizationRankingService:
    """
    Production-grade service orchestrating Phase 3.5 Personalized Ranking.
    """

    DEFAULT_LIMIT = 20
    MAX_LIMIT = 100

    @classmethod
    def get_personalized_recommendations(
        cls,
        db: Session,
        profile_id: uuid.UUID,
        *,
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
        include_inferred: bool = True,
        include_expertise: bool = True,
        include_fallback: bool = True,
        enable_personalization: bool = True,
        include_ablation: bool = True,
        opportunity_type: str | None = None,
        delivery_mode: str | None = None,
        reference_time: datetime | None = None,
    ) -> PersonalizedRankingResponse:
        """
        Produce deterministically ranked personalized recommendations for a researcher.

        Parameters
        ----------
        db : Session
            Active SQLAlchemy database session.
        profile_id : uuid.UUID
            Canonical ResearchProfileModel ID.
        limit : int
            Number of ranked recommendations to return (1-100).
        offset : int
            Pagination offset.
        include_inferred : bool
            Whether to include inferred preferences in scoring and candidate generation.
        include_expertise : bool
            Whether to include scholarly expertise in scoring and candidate generation.
        include_fallback : bool
            Whether to include cold-start/general fallback candidates if candidate pool is small.
        enable_personalization : bool
            If False, returns pure Phase 2 base ranking (R0 baseline).
        include_ablation : bool
            Whether to generate diagnostic ablation comparison metrics (R0 vs R1).
        opportunity_type : str | None
            Optional post-retrieval filter on opportunity category.
        delivery_mode : str | None
            Optional post-retrieval filter on delivery mode (ONLINE, OFFLINE, HYBRID).
        reference_time : datetime | None
            Reference evaluation timestamp (defaults to current UTC time).
        """
        # ── 1. Reference Timestamp Normalization ──────────────────────────────
        if reference_time is None:
            ref_time = datetime.now(timezone.utc)
        elif reference_time.tzinfo is None:
            ref_time = reference_time.replace(tzinfo=timezone.utc)
        else:
            ref_time = reference_time.astimezone(timezone.utc)

        safe_limit = max(1, min(limit, cls.MAX_LIMIT))
        safe_offset = max(0, offset)

        # ── 2. Batch Load Profile and Personalization Context (Zero N+1) ──────
        profile = db.execute(
            select(ResearchProfileModel).where(ResearchProfileModel.id == profile_id)
        ).scalar_one_or_none()
        if not profile:
            raise ValueError(f"Researcher profile '{profile_id}' not found.")

        # Batch load active preferences
        preferences = (
            db.execute(
                select(ResearcherPreferenceModel).where(
                    ResearcherPreferenceModel.profile_id == profile.id,
                    ResearcherPreferenceModel.is_active == True,  # noqa: E712
                )
            )
            .scalars()
            .all()
        )
        explicit_prefs = [p for p in preferences if p.source == "EXPLICIT"]
        inferred_prefs = [
            p
            for p in preferences
            if p.source == "INFERRED" and (p.confidence or 0.0) >= 0.40
        ]

        # Batch load scholarly interests/expertise
        interests = list(
            db.execute(
                select(ResearcherInterestModel).where(
                    ResearcherInterestModel.profile_id == profile.id
                )
            )
            .scalars()
            .all()
        )
        expertise_items = [
            i
            for i in interests
            if i.classification
            in ("PRIMARY_EXPERTISE", "SECONDARY_EXPERTISE", "EMERGING_INTEREST")
        ]

        profile_keywords = tuple(
            kw.strip() for kw in (profile.keywords or []) if kw and kw.strip()
        )
        profile_target_types = tuple(
            tt.strip().upper()
            for tt in (profile.target_opportunity_types or [])
            if tt and tt.strip()
        )

        is_cold_start = (
            len(explicit_prefs) == 0
            and len(inferred_prefs) == 0
            and len(expertise_items) == 0
            and len(profile_keywords) == 0
            and len(profile_target_types) == 0
        )

        context = ResearcherPersonalizationContext(
            profile_id=profile.id,
            explicit_preferences=tuple(explicit_prefs),
            inferred_preferences=tuple(inferred_prefs if include_inferred else []),
            expertise_items=tuple(expertise_items if include_expertise else []),
            profile_keywords=profile_keywords,
            target_opportunity_types=profile_target_types,
            institution=profile.institution,
            academic_status=profile.academic_status,
            is_cold_start=is_cold_start,
        )

        # ── 3. Candidate Pool Retrieval via Phase 3.4 ─────────────────────────
        pool_limit = max(50, min(200, (safe_limit + safe_offset) * 2))
        candidate_response = (
            PersonalizedCandidateGenerationService.generate_personalized_candidates(
                db=db,
                profile_id=profile.id,
                limit=pool_limit,
                include_inferred=include_inferred,
                include_expertise=include_expertise,
                include_fallback=include_fallback,
                reference_time=ref_time,
            )
        )

        raw_candidates = list(candidate_response.candidates)

        # Apply optional filters
        if opportunity_type:
            opp_type_filter = opportunity_type.strip().upper()
            raw_candidates = [
                c
                for c in raw_candidates
                if c.opportunity.opportunity_type.upper() == opp_type_filter
            ]
        if delivery_mode:
            del_mode_filter = delivery_mode.strip().upper()
            raw_candidates = [
                c
                for c in raw_candidates
                if c.opportunity.delivery_mode.upper() == del_mode_filter
            ]

        if not raw_candidates:
            return PersonalizedRankingResponse(
                researcher_id=profile.id,
                total_candidates=0,
                ranked_count=0,
                is_cold_start=is_cold_start,
                personalization_enabled=enable_personalization,
                max_personalization_contribution=MAX_PERSONALIZATION_CONTRIBUTION,
                recommendations=[],
                ablation_summary=AblationSummarySchema(
                    total_candidates=0,
                    reordered_candidates_count=0,
                    max_rank_promotion=0,
                    max_rank_demotion=0,
                    average_personalization_adjustment=0.0,
                    invariants_verified=True,
                )
                if include_ablation
                else None,
                metadata={
                    "offset": safe_offset,
                    "limit": safe_limit,
                    "generated_at": ref_time.isoformat(),
                },
            )

        # ── 4. Authoritative Phase 2 Base Relevance Computation ───────────────
        # Extract opportunity IDs and batch load opportunity models for Phase 2 ranker
        opp_ids = [c.opportunity.id for c in raw_candidates]
        opp_models_map = {
            m.id: m
            for m in db.execute(
                select(OpportunityModel).where(OpportunityModel.id.in_(opp_ids))
            )
            .scalars()
            .all()
        }

        # Build candidate objects for Phase 2 HybridRanker
        phase2_candidates = []
        for c in raw_candidates:
            opp_model = opp_models_map.get(c.opportunity.id)
            if opp_model:
                phase2_candidates.append(
                    {
                        "entity_id": opp_model.id,
                        "id": opp_model.id,
                        "opportunity_id": opp_model.id,
                        "entity_type": "opportunity",
                        "opportunity": opp_model,
                        "entity": opp_model,
                        "candidate": opp_model,
                        "indexing": opp_model.indexing,
                        "is_predatory_flag": opp_model.is_predatory_flag,
                        "risk_score": float(opp_model.risk_score or 0.0),
                        "submission_deadline": opp_model.submission_deadline,
                        "status": opp_model.status,
                    }
                )


        # Run Phase 2 HybridRanker in RESEARCH_OPPORTUNITY mode
        base_scores: dict[uuid.UUID, float] = {}
        if phase2_candidates:
            ranked_base = hybrid_ranker.rank(
                candidates=phase2_candidates,
                mode=RankingMode.RESEARCH_OPPORTUNITY,
                limit=len(phase2_candidates),
                reference_time=ref_time,
                session=db,
            )
            for rc in ranked_base:
                base_scores[rc.entity_id] = rc.final_score

        # ── 5. Personalization Ranking Layer (Phase 3.5) ───────────────────────
        all_ranked = personalization_ranker.rank(
            candidates=raw_candidates,
            context=context,
            enable_personalization=enable_personalization,
            base_scores=base_scores,
            limit=safe_limit,
            offset=safe_offset,
            reference_time=ref_time,
        )

        total_candidates_count = len(raw_candidates)

        # ── 6. Deterministic Ablation Summary (R0 vs R1) ───────────────────────
        ablation_summary: AblationSummarySchema | None = None
        if include_ablation and all_ranked:
            reordered_count = 0
            max_prom = 0
            max_dem = 0
            adj_sum = 0.0
            invariants_ok = True

            for r in all_ranked:
                delta = r.rank_delta
                if delta != 0:
                    reordered_count += 1
                if delta > max_prom:
                    max_prom = delta
                if delta < max_dem:
                    max_dem = delta
                adj_sum += r.personalization_adjustment

                # Verify individual invariant: adjustment <= 0.15
                if r.personalization_adjustment > MAX_PERSONALIZATION_CONTRIBUTION + 1e-6:
                    invariants_ok = False

                # Verify safety: high risk opportunities receive zero adjustment
                if (
                    r.opportunity.is_predatory_flag
                    or r.opportunity.risk_level == "HIGH_RISK"
                    or (r.opportunity.risk_score or 0.0) >= 0.70
                ):
                    if r.personalization_adjustment > 0.0:
                        invariants_ok = False

            # Verify pairwise monotonicity: if base(A) - base(B) > 0.15, B cannot outrank A
            for i in range(len(all_ranked)):
                for j in range(i + 1, len(all_ranked)):
                    item_a = all_ranked[i]
                    item_b = all_ranked[j]
                    # item_a has rank < item_b (higher rank position)
                    # If base(B) - base(A) > 0.15, item_b should have outranked item_a
                    if (item_b.base_relevance_score - item_a.base_relevance_score) > (
                        MAX_PERSONALIZATION_CONTRIBUTION + 1e-6
                    ):
                        invariants_ok = False

            avg_adj = round(adj_sum / max(1, len(all_ranked)), 4)
            ablation_summary = AblationSummarySchema(
                total_candidates=total_candidates_count,
                reordered_candidates_count=reordered_count,
                max_rank_promotion=max_prom,
                max_rank_demotion=max_dem,
                average_personalization_adjustment=avg_adj,
                invariants_verified=invariants_ok,
            )

        return PersonalizedRankingResponse(
            researcher_id=profile.id,
            total_candidates=total_candidates_count,
            ranked_count=len(all_ranked),
            is_cold_start=is_cold_start,
            personalization_enabled=enable_personalization,
            max_personalization_contribution=MAX_PERSONALIZATION_CONTRIBUTION,
            recommendations=all_ranked,
            ablation_summary=ablation_summary,
            metadata={
                "offset": safe_offset,
                "limit": safe_limit,
                "explicit_preference_count": len(explicit_prefs),
                "inferred_preference_count": len(inferred_prefs),
                "expertise_count": len(expertise_items),
                "profile_keyword_count": len(profile_keywords),
                "generated_at": ref_time.isoformat(),
            },
        )
