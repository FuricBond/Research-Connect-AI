"""
FastAPI Researcher Profile API Router (Phase 3.1).

Exposes versioned endpoints for:
  - Creating canonical researcher profiles
  - Retrieving researcher profile by ID or user ID
  - Partially updating researcher profiles
  - Listing authored publications via canonical knowledge relations
  - Computing profile completeness metadata
"""
from __future__ import annotations

from datetime import datetime
import logging
from typing import Annotated, Any
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.personalized_candidate import (
    PersonalizedCandidateSetResponse,
)
from app.schemas.personalized_ranking import (
    PersonalizedRankingResponse,
)
from app.schemas.researcher import (
    ProfileCompletenessSchema,
    ResearcherProfileCreate,
    ResearcherProfileRead,
    ResearcherProfileUpdate,
    ResearcherWorkSummarySchema,
)
from app.schemas.researcher_intelligence import (
    ResearcherIntelligenceResponse,
    ResearcherInterestItemSchema,
)
from app.schemas.researcher_preference import (
    ResearcherPreferenceCreateSchema,
    ResearcherPreferenceIntelligenceResponse,
    ResearcherPreferenceItemSchema,
    ResearcherPreferenceUpdateSchema,
)
from app.schemas.researcher_feedback import (
    BehavioralSignalSchema,
    FeedbackCreateRequest,
    FeedbackItemResponse,
    FeedbackListResponse,
    FeedbackSummaryResponse,
)
from app.schemas.recommendation_history import (
    RecommendationHistoryListResponse,
    RecommendationSnapshotResponseSchema,
)
from app.schemas.recommendation_evaluation import (
    RecommendationEvaluationResponse,
)
from app.services.feedback_service import ResearcherFeedbackService
from app.services.personalization_ranking_service import (
    PersonalizationRankingService,
)
from app.services.personalized_candidate_generation_service import (
    PersonalizedCandidateGenerationService,
)
from app.services.recommendation_history_service import RecommendationHistoryService
from app.services.researcher_intelligence_service import ResearcherIntelligenceService
from app.services.researcher_preference_service import ResearcherPreferenceService
from app.services.researcher_profile_service import ResearcherProfileService




logger = logging.getLogger(__name__)

router = APIRouter(prefix="/researchers", tags=["researchers"])


@router.post(
    "",
    response_model=ResearcherProfileRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create canonical researcher profile",
    description="Register a canonical researcher profile, resolving canonical institutions and OpenAlex/Crossref entities.",
)
def create_researcher_profile(
    payload: ResearcherProfileCreate,
    db: Session = Depends(get_db),
) -> ResearcherProfileRead:
    try:
        profile = ResearcherProfileService.create_profile(db, payload)
        return ResearcherProfileService.build_profile_read(profile)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        )


@router.get(
    "/{researcher_id}",
    response_model=ResearcherProfileRead,
    status_code=status.HTTP_200_OK,
    summary="Get researcher profile by ID",
    description="Retrieve a canonical researcher profile by its profile ID or associated user ID.",
)
def get_researcher_profile(
    researcher_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> ResearcherProfileRead:
    profile = ResearcherProfileService.get_profile(db, researcher_id)
    if not profile:
        # Fallback: check if the researcher_id matches user_id
        profile = ResearcherProfileService.get_profile_by_user_id(db, researcher_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Researcher profile with ID '{researcher_id}' not found.",
        )
    return ResearcherProfileService.build_profile_read(profile)


@router.patch(
    "/{researcher_id}",
    response_model=ResearcherProfileRead,
    status_code=status.HTTP_200_OK,
    summary="Update researcher profile",
    description="Partially update an existing researcher profile and refresh canonical affiliations.",
)
def update_researcher_profile(
    researcher_id: uuid.UUID,
    payload: ResearcherProfileUpdate,
    db: Session = Depends(get_db),
) -> ResearcherProfileRead:
    profile = ResearcherProfileService.update_profile(db, researcher_id, payload)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Researcher profile with ID '{researcher_id}' not found.",
        )
    return ResearcherProfileService.build_profile_read(profile)


@router.get(
    "/{researcher_id}/works",
    response_model=list[ResearcherWorkSummarySchema],
    status_code=status.HTTP_200_OK,
    summary="Get researcher authored publications",
    description="Retrieve scholarly publications authored by this researcher through canonical knowledge links.",
)
def get_researcher_publications(
    researcher_id: uuid.UUID,
    limit: Annotated[int, Query(ge=1, le=100, description="Max works to return")] = 20,
    offset: Annotated[int, Query(ge=0, description="Offset")] = 0,
    db: Session = Depends(get_db),
) -> list[ResearcherWorkSummarySchema]:
    profile = ResearcherProfileService.get_profile(db, researcher_id)
    if not profile:
        profile = ResearcherProfileService.get_profile_by_user_id(db, researcher_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Researcher profile with ID '{researcher_id}' not found.",
        )
    return ResearcherProfileService.get_researcher_works(
        db, profile.id, limit=limit, offset=offset
    )


@router.get(
    "/{researcher_id}/completeness",
    response_model=ProfileCompletenessSchema,
    status_code=status.HTTP_200_OK,
    summary="Get researcher profile completeness breakdown",
    description="Audit profile completeness without modifying or running recommendation ranking.",
)
def get_researcher_profile_completeness(
    researcher_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> ProfileCompletenessSchema:
    profile = ResearcherProfileService.get_profile(db, researcher_id)
    if not profile:
        profile = ResearcherProfileService.get_profile_by_user_id(db, researcher_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Researcher profile with ID '{researcher_id}' not found.",
        )
    return ResearcherProfileService.compute_profile_completeness(profile)


@router.get(
    "/{researcher_id}/research-intelligence",
    response_model=ResearcherIntelligenceResponse,
    status_code=status.HTTP_200_OK,
    summary="Get researcher interest and expertise intelligence",
    description=(
        "Retrieve structured, explainable academic interests, expertise tiers, "
        "recency signals, confidence metrics, and deterministic provenance for a researcher (Phase 3.2)."
    ),
)
def get_researcher_intelligence(
    researcher_id: uuid.UUID,
    refresh: bool = Query(
        False,
        description="Force recomputation of intelligence instead of reading persisted records",
    ),
    db: Session = Depends(get_db),
) -> ResearcherIntelligenceResponse:
    try:
        return ResearcherIntelligenceService.get_researcher_intelligence(
            db=db,
            identifier=researcher_id,
            refresh=refresh,
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        )


@router.get(
    "/{researcher_id}/interests",
    response_model=list[ResearcherInterestItemSchema],
    status_code=status.HTTP_200_OK,
    summary="Get structured researcher academic interests",
    description="Retrieve all inferred academic interests with strength, confidence, and provenance (Phase 3.2).",
)
def get_researcher_interests(
    researcher_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> list[ResearcherInterestItemSchema]:
    try:
        return ResearcherIntelligenceService.get_researcher_interests(
            db=db,
            identifier=researcher_id,
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        )


@router.get(
    "/{researcher_id}/expertise",
    response_model=list[ResearcherInterestItemSchema],
    status_code=status.HTTP_200_OK,
    summary="Get structured researcher academic expertise",
    description="Retrieve confirmed primary and secondary academic expertise areas (Phase 3.2).",
)
def get_researcher_expertise(
    researcher_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> list[ResearcherInterestItemSchema]:
    try:
        return ResearcherIntelligenceService.get_researcher_expertise(
            db=db,
            identifier=researcher_id,
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        )


# =========================================================================
# Phase 3.3 — Personal Preference Intelligence Endpoints
# =========================================================================


@router.get(
    "/{researcher_id}/preference-intelligence",
    response_model=ResearcherPreferenceIntelligenceResponse,
    status_code=status.HTTP_200_OK,
    summary="Get complete personal preference intelligence",
    description=(
        "Retrieve canonical, explainable representation of researcher preferences, including "
        "explicit declarations, inferred preferences from verified activity, derived expertise candidates, "
        "conflict analysis, and completeness scoring (Phase 3.3). Zero recommendation or ranking alteration."
    ),
)
def get_preference_intelligence(
    researcher_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> ResearcherPreferenceIntelligenceResponse:
    profile = ResearcherProfileService.get_profile(db, researcher_id)
    if not profile:
        profile = ResearcherProfileService.get_profile_by_user_id(db, researcher_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Researcher profile with ID '{researcher_id}' not found.",
        )

    try:
        return ResearcherPreferenceService.get_preference_intelligence(
            db=db,
            profile_id=profile.id,
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        )


@router.get(
    "/{researcher_id}/preferences",
    response_model=list[ResearcherPreferenceItemSchema],
    status_code=status.HTTP_200_OK,
    summary="List researcher preferences",
    description="List persisted preference items with optional category, source, and active status filters.",
)
def list_researcher_preferences(
    researcher_id: uuid.UUID,
    category: Annotated[str | None, Query(description="Filter by category")] = None,
    source: Annotated[str | None, Query(description="Filter by source (EXPLICIT, INFERRED, etc.)")] = None,
    is_active: Annotated[bool | None, Query(description="Filter by active status")] = None,
    db: Session = Depends(get_db),
) -> list[ResearcherPreferenceItemSchema]:
    profile = ResearcherProfileService.get_profile(db, researcher_id)
    if not profile:
        profile = ResearcherProfileService.get_profile_by_user_id(db, researcher_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Researcher profile with ID '{researcher_id}' not found.",
        )

    models = ResearcherPreferenceService.list_preferences(
        db=db,
        profile_id=profile.id,
        category=category,
        source=source,
        is_active=is_active,
    )

    return [
        ResearcherPreferenceItemSchema(
            id=m.id,
            profile_id=m.profile_id,
            category=m.category,
            preference_key=m.preference_key,
            preference_value=m.preference_value,
            display_label=m.display_label,
            canonical_id=m.canonical_id,
            strength=m.strength,
            confidence=m.confidence,
            source=m.source,
            is_active=m.is_active,
            recency_score=m.recency_score,
            provenance=m.provenance,
            provenance_reasons=(m.provenance or {}).get("reasons", []),
            last_observed_at=m.last_observed_at,
            created_at=m.created_at,
            updated_at=m.updated_at,
        )
        for m in models
    ]


@router.post(
    "/{researcher_id}/preferences",
    response_model=ResearcherPreferenceItemSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Declare explicit researcher preference",
    description="Create or update an explicit researcher preference item with ownership authorization.",
)
def create_researcher_preference(
    researcher_id: uuid.UUID,
    payload: ResearcherPreferenceCreateSchema,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> ResearcherPreferenceItemSchema:
    profile = ResearcherProfileService.get_profile(db, researcher_id)
    if not profile:
        profile = ResearcherProfileService.get_profile_by_user_id(db, researcher_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Researcher profile with ID '{researcher_id}' not found.",
        )

    # Ownership validation
    if x_user_id is not None and profile.user_id != x_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You do not have permission to modify this researcher profile's preferences.",
        )

    try:
        model = ResearcherPreferenceService.create_explicit_preference(
            db=db,
            profile_id=profile.id,
            payload=payload,
            current_user_id=x_user_id,
        )
        return ResearcherPreferenceItemSchema(
            id=model.id,
            profile_id=model.profile_id,
            category=model.category,
            preference_key=model.preference_key,
            preference_value=model.preference_value,
            display_label=model.display_label,
            canonical_id=model.canonical_id,
            strength=model.strength,
            confidence=model.confidence,
            source=model.source,
            is_active=model.is_active,
            recency_score=model.recency_score,
            provenance=model.provenance,
            provenance_reasons=(model.provenance or {}).get("reasons", ["Explicit declaration"]),
            last_observed_at=model.last_observed_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
    except PermissionError as err:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(err),
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        )


@router.patch(
    "/{researcher_id}/preferences/{preference_id}",
    response_model=ResearcherPreferenceItemSchema,
    status_code=status.HTTP_200_OK,
    summary="Update researcher preference",
    description="Partially update an existing preference item (e.g. adjust strength, label, or active status).",
)
def update_researcher_preference(
    researcher_id: uuid.UUID,
    preference_id: uuid.UUID,
    payload: ResearcherPreferenceUpdateSchema,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> ResearcherPreferenceItemSchema:
    profile = ResearcherProfileService.get_profile(db, researcher_id)
    if not profile:
        profile = ResearcherProfileService.get_profile_by_user_id(db, researcher_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Researcher profile with ID '{researcher_id}' not found.",
        )

    # Ownership validation
    if x_user_id is not None and profile.user_id != x_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You do not have permission to modify this researcher profile's preferences.",
        )

    try:
        model = ResearcherPreferenceService.update_preference(
            db=db,
            profile_id=profile.id,
            preference_id=preference_id,
            payload=payload,
            current_user_id=x_user_id,
        )
        if not model:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Preference with ID '{preference_id}' not found on this profile.",
            )
        return ResearcherPreferenceItemSchema(
            id=model.id,
            profile_id=model.profile_id,
            category=model.category,
            preference_key=model.preference_key,
            preference_value=model.preference_value,
            display_label=model.display_label,
            canonical_id=model.canonical_id,
            strength=model.strength,
            confidence=model.confidence,
            source=model.source,
            is_active=model.is_active,
            recency_score=model.recency_score,
            provenance=model.provenance,
            provenance_reasons=(model.provenance or {}).get("reasons", []),
            last_observed_at=model.last_observed_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
    except PermissionError as err:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(err),
        )


@router.delete(
    "/{researcher_id}/preferences/{preference_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete researcher preference",
    description="Remove a preference item permanently from the researcher profile.",
)
def delete_researcher_preference(
    researcher_id: uuid.UUID,
    preference_id: uuid.UUID,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    profile = ResearcherProfileService.get_profile(db, researcher_id)
    if not profile:
        profile = ResearcherProfileService.get_profile_by_user_id(db, researcher_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Researcher profile with ID '{researcher_id}' not found.",
        )

    # Ownership validation
    if x_user_id is not None and profile.user_id != x_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You do not have permission to modify this researcher profile's preferences.",
        )

    try:
        deleted = ResearcherPreferenceService.delete_preference(
            db=db,
            profile_id=profile.id,
            preference_id=preference_id,
            current_user_id=x_user_id,
        )
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Preference with ID '{preference_id}' not found on this profile.",
            )
        return {"deleted": True, "preference_id": str(preference_id)}
    except PermissionError as err:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(err),
        )


@router.get(
    "/{researcher_id}/personalized-candidates",
    response_model=PersonalizedCandidateSetResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate personalized candidate set",
    description=(
        "Generate a deduplicated, eligibility-verified candidate set of research opportunities "
        "tailored to the researcher's canonical profile, scholarly expertise, and personal preferences (Phase 3.4). "
        "Strict boundary: Returns an unranked candidate pool with complete provenance. "
        "Does NOT implement personalized ranking (reserved for Phase 3.5)."
    ),
)
def get_personalized_candidates(
    researcher_id: uuid.UUID,
    limit: Annotated[int, Query(ge=1, le=200, description="Candidate set limit")] = 50,
    include_inferred: Annotated[bool, Query(description="Include inferred preference candidates")] = True,
    include_expertise: Annotated[bool, Query(description="Include scholarly expertise candidates")] = True,
    include_fallback: Annotated[bool, Query(description="Include cold-start discovery fallback")] = True,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> PersonalizedCandidateSetResponse:
    profile = ResearcherProfileService.get_profile(db, researcher_id)
    if not profile:
        profile = ResearcherProfileService.get_profile_by_user_id(db, researcher_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Researcher profile with ID '{researcher_id}' not found.",
        )

    # Ownership validation (Phase 3.4 / 3.3 convention)
    if x_user_id is not None and profile.user_id != x_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You do not have permission to view this researcher's personalized candidate set.",
        )

    try:
        return PersonalizedCandidateGenerationService.generate_personalized_candidates(
            db=db,
            profile_id=profile.id,
            limit=limit,
            include_inferred=include_inferred,
            include_expertise=include_expertise,
            include_fallback=include_fallback,
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        )


@router.get(
    "/{researcher_id}/personalized-recommendations",
    response_model=PersonalizedRankingResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate personalized ranked recommendations",
    description=(
        "Generate deterministically ranked personalized recommendations (Phase 3.5). "
        "Combines Phase 2 base relevance scores with bounded personalization adjustments (<= 0.15), "
        "while enforcing relevance dominance, Phase 2.6 risk safety, and Phase 2.7 deadline lifecycle. "
        "Supports R0 (base) vs R1 (personalized) ablation comparison."
    ),
)
def get_personalized_recommendations(
    researcher_id: uuid.UUID,
    limit: Annotated[int, Query(ge=1, le=100, description="Recommendation limit")] = 20,
    offset: Annotated[int, Query(ge=0, description="Pagination offset")] = 0,
    include_inferred: Annotated[bool, Query(description="Include inferred preference signals")] = True,
    include_expertise: Annotated[bool, Query(description="Include scholarly expertise signals")] = True,
    include_fallback: Annotated[bool, Query(description="Include cold-start discovery fallback")] = True,
    enable_personalization: Annotated[bool, Query(description="Enable Phase 3.5 personalization (False = pure R0 base rank)")] = True,
    include_ablation: Annotated[bool, Query(description="Include R0 vs R1 ablation summary diagnostics")] = True,
    opportunity_type: Annotated[str | None, Query(description="Filter by opportunity category (CONFERENCE, JOURNAL, etc.)")] = None,
    delivery_mode: Annotated[str | None, Query(description="Filter by delivery mode (ONLINE, OFFLINE, HYBRID)")] = None,
    persist_snapshot: Annotated[bool, Query(description="Record persistent recommendation snapshot for history/evaluation")] = True,
    session_id: Annotated[str | None, Query(description="Optional client session identifier for attribution")] = None,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> PersonalizedRankingResponse:
    profile = ResearcherProfileService.get_profile(db, researcher_id)
    if not profile:
        profile = ResearcherProfileService.get_profile_by_user_id(db, researcher_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Researcher profile with ID '{researcher_id}' not found.",
        )

    # Ownership validation (Phase 3.5 / 3.4 convention)
    if x_user_id is not None and profile.user_id != x_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You do not have permission to view this researcher's personalized recommendations.",
        )

    try:
        return PersonalizationRankingService.get_personalized_recommendations(
            db=db,
            profile_id=profile.id,
            limit=limit,
            offset=offset,
            include_inferred=include_inferred,
            include_expertise=include_expertise,
            include_fallback=include_fallback,
            enable_personalization=enable_personalization,
            include_ablation=include_ablation,
            opportunity_type=opportunity_type,
            delivery_mode=delivery_mode,
            persist_snapshot=persist_snapshot,
            session_id=session_id,
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        )


# ── Phase 3.6 — Feedback & Recommendation Learning Endpoints ─────────────────


@router.post(
    "/{researcher_id}/feedback",
    response_model=FeedbackItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record recommendation interaction feedback",
    description=(
        "Record an explicit or implicit recommendation interaction event (Phase 3.6). "
        "Supports VIEW, SAVE, DISMISS, INTERESTED, NOT_INTERESTED, APPLY. "
        "Idempotent: updates existing state if same event type was previously submitted."
    ),
)
def record_feedback(
    researcher_id: uuid.UUID,
    payload: FeedbackCreateRequest,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> FeedbackItemResponse:
    profile = ResearcherProfileService.get_profile(db, researcher_id)
    if not profile:
        profile = ResearcherProfileService.get_profile_by_user_id(db, researcher_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Researcher profile with ID '{researcher_id}' not found.",
        )

    # Ownership validation
    if x_user_id is not None and profile.user_id != x_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You do not have permission to submit feedback for this researcher.",
        )

    try:
        return ResearcherFeedbackService.record_feedback(
            db=db,
            researcher_id=profile.id,
            payload=payload,
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        )


@router.get(
    "/{researcher_id}/feedback",
    response_model=FeedbackListResponse,
    status_code=status.HTTP_200_OK,
    summary="Query researcher feedback history",
    description=(
        "Retrieve paginated interaction feedback history with optional filtering by "
        "feedback_type, opportunity_id, and date range (Phase 3.6)."
    ),
)
def get_feedback_history(
    researcher_id: uuid.UUID,
    limit: Annotated[int, Query(ge=1, le=200, description="Page limit")] = 50,
    offset: Annotated[int, Query(ge=0, description="Page offset")] = 0,
    feedback_type: Annotated[str | None, Query(description="Filter by type (VIEW, SAVE, DISMISS, etc.)")] = None,
    opportunity_id: Annotated[uuid.UUID | None, Query(description="Filter by opportunity ID")] = None,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> FeedbackListResponse:
    profile = ResearcherProfileService.get_profile(db, researcher_id)
    if not profile:
        profile = ResearcherProfileService.get_profile_by_user_id(db, researcher_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Researcher profile with ID '{researcher_id}' not found.",
        )

    # Ownership validation
    if x_user_id is not None and profile.user_id != x_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You do not have permission to view this researcher's feedback history.",
        )

    try:
        return ResearcherFeedbackService.get_feedback_history(
            db=db,
            researcher_id=profile.id,
            limit=limit,
            offset=offset,
            feedback_type=feedback_type,
            opportunity_id=opportunity_id,
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        )


@router.delete(
    "/{researcher_id}/feedback/{feedback_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete feedback item",
    description="Remove or undo an interaction feedback event (Phase 3.6).",
)
def delete_feedback(
    researcher_id: uuid.UUID,
    feedback_id: uuid.UUID,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    profile = ResearcherProfileService.get_profile(db, researcher_id)
    if not profile:
        profile = ResearcherProfileService.get_profile_by_user_id(db, researcher_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Researcher profile with ID '{researcher_id}' not found.",
        )

    # Ownership validation
    if x_user_id is not None and profile.user_id != x_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You do not have permission to delete this researcher's feedback.",
        )

    deleted = ResearcherFeedbackService.delete_feedback(
        db=db,
        researcher_id=profile.id,
        feedback_id=feedback_id,
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feedback record with ID '{feedback_id}' not found.",
        )

    return {"deleted": True, "feedback_id": str(feedback_id)}


@router.get(
    "/{researcher_id}/feedback/summary",
    response_model=FeedbackSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get feedback summary and behavioral learning metrics",
    description="Return aggregated interaction statistics and behavioral learning status (Phase 3.6).",
)
def get_feedback_summary(
    researcher_id: uuid.UUID,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> FeedbackSummaryResponse:
    profile = ResearcherProfileService.get_profile(db, researcher_id)
    if not profile:
        profile = ResearcherProfileService.get_profile_by_user_id(db, researcher_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Researcher profile with ID '{researcher_id}' not found.",
        )

    # Ownership validation
    if x_user_id is not None and profile.user_id != x_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You do not have permission to view this researcher's feedback summary.",
        )

    return ResearcherFeedbackService.get_feedback_summary(
        db=db,
        researcher_id=profile.id,
    )


@router.get(
    "/{researcher_id}/feedback/signals",
    response_model=list[BehavioralSignalSchema],
    status_code=status.HTTP_200_OK,
    summary="Get learned behavioral signals",
    description=(
        "Return all active learned behavioral preference signals synthesized by the "
        "deterministic FeedbackEngine, including confidence and temporal decay (Phase 3.6)."
    ),
)
def get_behavioral_signals(
    researcher_id: uuid.UUID,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> list[BehavioralSignalSchema]:
    profile = ResearcherProfileService.get_profile(db, researcher_id)
    if not profile:
        profile = ResearcherProfileService.get_profile_by_user_id(db, researcher_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Researcher profile with ID '{researcher_id}' not found.",
        )

    # Ownership validation
    if x_user_id is not None and profile.user_id != x_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You do not have permission to view this researcher's behavioral signals.",
        )

    behavioral_profile = ResearcherFeedbackService.get_behavioral_profile(
        db=db,
        researcher_id=profile.id,
    )
    return behavioral_profile.signals


# ── Phase 3.7 — Recommendation History & Evaluation Endpoints ─────────────────


@router.get(
    "/{researcher_id}/recommendation-history",
    response_model=RecommendationHistoryListResponse,
    status_code=status.HTTP_200_OK,
    summary="List researcher recommendation snapshots",
    description=(
        "Retrieve paginated recommendation snapshots for a researcher (Phase 3.7). "
        "Provides reproducible point-in-time audit logs of what was recommended and when, "
        "including ranking version provenance and top recommended opportunities."
    ),
)
def get_recommendation_history(
    researcher_id: uuid.UUID,
    limit: Annotated[int, Query(ge=1, le=100, description="Page size limit")] = 20,
    offset: Annotated[int, Query(ge=0, description="Pagination offset")] = 0,
    ranking_version: Annotated[str | None, Query(description="Filter by ranking algorithm version")] = None,
    from_date: Annotated[datetime | None, Query(description="Filter snapshots created on or after this timestamp")] = None,
    to_date: Annotated[datetime | None, Query(description="Filter snapshots created on or before this timestamp")] = None,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> RecommendationHistoryListResponse:
    profile = ResearcherProfileService.get_profile(db, researcher_id)
    if not profile:
        profile = ResearcherProfileService.get_profile_by_user_id(db, researcher_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Researcher profile with ID '{researcher_id}' not found.",
        )

    # Ownership validation
    if x_user_id is not None and profile.user_id != x_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You do not have permission to view this researcher's recommendation history.",
        )

    return RecommendationHistoryService.get_history(
        db=db,
        profile_id=profile.id,
        limit=limit,
        offset=offset,
        ranking_version=ranking_version,
        from_date=from_date,
        to_date=to_date,
    )


@router.get(
    "/{researcher_id}/recommendation-history/{snapshot_id}",
    response_model=RecommendationSnapshotResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Get detailed recommendation snapshot by ID",
    description=(
        "Retrieve a complete historical recommendation snapshot (Phase 3.7). "
        "Returns ordered items, original point-in-time scores, and active user feedback."
    ),
)
def get_recommendation_snapshot_detail(
    researcher_id: uuid.UUID,
    snapshot_id: uuid.UUID,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> RecommendationSnapshotResponseSchema:
    profile = ResearcherProfileService.get_profile(db, researcher_id)
    if not profile:
        profile = ResearcherProfileService.get_profile_by_user_id(db, researcher_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Researcher profile with ID '{researcher_id}' not found.",
        )

    # Ownership validation
    if x_user_id is not None and profile.user_id != x_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You do not have permission to view this researcher's recommendation snapshot.",
        )

    snapshot_detail = RecommendationHistoryService.get_snapshot_detail(
        db=db,
        profile_id=profile.id,
        snapshot_id=snapshot_id,
    )
    if not snapshot_detail:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recommendation snapshot with ID '{snapshot_id}' not found for this researcher.",
        )

    return snapshot_detail


@router.get(
    "/{researcher_id}/recommendation-evaluation",
    response_model=RecommendationEvaluationResponse,
    status_code=status.HTTP_200_OK,
    summary="Calculate offline evaluation metrics for recommendations",
    description=(
        "Compute offline evaluation metrics across recommendation history and feedback (Phase 3.7). "
        "Returns Precision@K, Recall@K, HitRate@K, NDCG@K, Save Rate, Engagement Rate, Dismissal Rate, "
        "and data sufficiency classifications (SUFFICIENT_DATA, INSUFFICIENT_DATA, NO_FEEDBACK, NO_HISTORY). "
        "Includes independent algorithm version comparisons (R0 vs R1 vs R2)."
    ),
)
def get_recommendation_evaluation(
    researcher_id: uuid.UUID,
    ranking_version: Annotated[str | None, Query(description="Filter evaluation to a specific ranking version")] = None,
    from_date: Annotated[datetime | None, Query(description="Evaluation window start")] = None,
    to_date: Annotated[datetime | None, Query(description="Evaluation window end")] = None,
    include_comparison: Annotated[bool, Query(description="Include comparative breakdown across ranking versions")] = True,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> RecommendationEvaluationResponse:
    profile = ResearcherProfileService.get_profile(db, researcher_id)
    if not profile:
        profile = ResearcherProfileService.get_profile_by_user_id(db, researcher_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Researcher profile with ID '{researcher_id}' not found.",
        )

    # Ownership validation
    if x_user_id is not None and profile.user_id != x_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You do not have permission to evaluate this researcher's recommendations.",
        )

    return RecommendationHistoryService.evaluate_recommendations(
        db=db,
        profile_id=profile.id,
        ranking_version=ranking_version,
        from_date=from_date,
        to_date=to_date,
        include_comparison=include_comparison,
    )






