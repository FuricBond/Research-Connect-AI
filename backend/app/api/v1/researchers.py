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

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.db.session import get_db
from app.models.calendar import CalendarEventType
from app.models.opportunity import OpportunityModel, OpportunityTopicModel
from app.models.research_profile import ResearchProfileModel
from app.personalization import (
    BatchOpportunityPreferenceMatchRequest,
    BatchOpportunityPreferenceMatchResponse,
    BatchPersonalizationRequest,
    BatchPersonalizationResponse,
    PersonalizationAssessment,
    PersonalizationScorer,
    PreferenceInterpreter,
    PreferencePersonalizationAssessment,
)
from app.schemas.calendar import ResearcherCalendarViewResponse
from app.services.research_calendar_service import ResearchCalendarService
from app.schemas.notification import (
    NotificationListResponse,
    NotificationPreferenceRead,
    NotificationPreferenceUpdate,
    NotificationRead,
    NotificationUnreadCountResponse,
    ReminderRuleCreate,
    ReminderRuleListResponse,
    ReminderRuleRead,
    ReminderRuleUpdate,
)
from app.services.notification_service import NotificationService
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
    BulkPreferencesUpdateSchema,
    ResearcherPreferenceCreateSchema,
    ResearcherPreferenceIntelligenceResponse,
    ResearcherPreferenceItemSchema,
    ResearcherPreferenceUpdateSchema,
    StructuredPreferencesResponseSchema,
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
from app.schemas.recommendation_explanation import (
    PersonalizationSummaryResponse,
    RecommendationExplanationSchema,
)
from app.schemas.research_intelligence import (
    UnifiedOpportunityIntelligenceSchema,
    UnifiedRecommendationResponseSchema,
    UnifiedResearcherContextSchema,
)
from app.services.feedback_service import ResearcherFeedbackService
from app.services.personalization_explanation_service import (
    PersonalizationExplanationService,
)
from app.services.research_intelligence_integration_service import (
    ResearchIntelligenceIntegrationService,
)
from app.services.personalization_ranking_service import (
    PersonalizationRankingService,
)
from app.services.personalized_candidate_generation_service import (
    PersonalizedCandidateGenerationService,
)
from app.services.recommendation_history_service import RecommendationHistoryService
from app.services.researcher_intelligence_service import ResearcherIntelligenceService
from app.services.researcher_interaction_service import ResearcherInteractionService
from app.services.researcher_preference_service import ResearcherPreferenceService
from app.services.researcher_profile_service import ResearcherProfileService
from app.models.adaptive_signal import (
    AdaptiveEvidenceState,
    AdaptiveSignalDimension,
)
from app.personalization.adaptive_models import (
    AdaptivePreferenceSignal,
    AdaptiveSignalExplanationResponse,
    AdaptiveSignalsResponse,
)
from app.schemas.adaptive_signal import AdaptiveSignalRecomputeRequest
from app.services.adaptive_signal_service import AdaptivePreferenceSignalService
from app.models.personalization_calibration import CalibrationState
from app.schemas.personalization_calibration import (
    CalibrationRecomputeRequest,
    PersonalizationCalibrationDetailResponse,
    PersonalizationCalibrationResponse,
    PersonalizationCalibrationSchema,
)
from app.services.personalization_calibration_service import PersonalizationCalibrationService
from app.schemas.personalization_quality import (
    ContextualAdaptationsResponse,
    PersonalizationQualityResponse,
    QualityRecomputeRequest,
    SignalQualityResponse,
)
from app.services.personalization_quality_service import PersonalizationQualityService
from app.schemas.personalization_governance import (
    GovernanceRecomputeRequest,
    PersonalizationDriftResponse,
    PersonalizationGovernanceHistoryResponse,
    PersonalizationHealthResponse,
)
from app.services.personalization_governance_service import PersonalizationGovernanceService
from app.schemas.researcher_interaction import (
    InteractionCreateRequest,
    InteractionResponse,
    OpportunityInteractionHistoryResponse,
    ResearcherInteractionSummaryResponse,
)





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
    description="List persisted preference items with optional category, source, active status, and preference type filters.",
)
def list_researcher_preferences(
    researcher_id: uuid.UUID,
    category: Annotated[str | None, Query(description="Filter by category")] = None,
    source: Annotated[str | None, Query(description="Filter by source (EXPLICIT, INFERRED, etc.)")] = None,
    is_active: Annotated[bool | None, Query(description="Filter by active status")] = None,
    preference_type: Annotated[str | None, Query(description="Filter by preference type (PREFERRED, EXCLUDED)")] = None,
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
        preference_type=preference_type,
    )

    return [
        ResearcherPreferenceItemSchema(
            id=m.id,
            profile_id=m.profile_id,
            category=m.category,
            preference_type=m.preference_type,
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


@router.get(
    "/{researcher_id}/preferences/structured",
    response_model=StructuredPreferencesResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Get structured researcher preferences",
    description="Retrieve structured hierarchical preferences partitioned into research interests, opportunities, geography, funding, academic, and exclusions.",
)
def get_structured_researcher_preferences(
    researcher_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> StructuredPreferencesResponseSchema:
    profile = ResearcherProfileService.get_profile(db, researcher_id)
    if not profile:
        profile = ResearcherProfileService.get_profile_by_user_id(db, researcher_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Researcher profile with ID '{researcher_id}' not found.",
        )

    try:
        return ResearcherPreferenceService.get_structured_preferences(
            db=db,
            profile_id=profile.id,
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        )


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
            preference_type=model.preference_type,
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


@router.put(
    "/{researcher_id}/preferences",
    response_model=list[ResearcherPreferenceItemSchema],
    status_code=status.HTTP_200_OK,
    summary="Bulk update researcher preferences",
    description="Atomically synchronize multiple preferences. If replace_existing=True, existing explicit preferences are replaced.",
)
def bulk_update_researcher_preferences(
    researcher_id: uuid.UUID,
    payload: BulkPreferencesUpdateSchema,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
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

    # Ownership validation
    if x_user_id is not None and profile.user_id != x_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You do not have permission to modify this researcher profile's preferences.",
        )

    try:
        models = ResearcherPreferenceService.bulk_sync_preferences(
            db=db,
            profile_id=profile.id,
            payload=payload,
            current_user_id=x_user_id,
        )
        return [
            ResearcherPreferenceItemSchema(
                id=m.id,
                profile_id=m.profile_id,
                category=m.category,
                preference_type=m.preference_type,
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
    description="Partially update an existing preference item (e.g. adjust strength, label, active status, or preference type).",
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
            preference_type=model.preference_type,
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


# ── Phase 3.8 — Personalization Explainability Endpoints ─────────────────────


@router.get(
    "/{researcher_id}/personalization-summary",
    response_model=PersonalizationSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get comprehensive personalization summary and learned signals",
    description=(
        "Returns a holistic personalization summary for the researcher (Phase 3.8). "
        "Includes counts of active research interests, verified expertise, explicit preferences, "
        "learned behavioral signals, overall personalization confidence, and learned attribute affinities."
    ),
)
def get_personalization_summary(
    researcher_id: uuid.UUID,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> PersonalizationSummaryResponse:
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
            detail="Forbidden: You do not have permission to view this researcher's personalization summary.",
        )

    return PersonalizationExplanationService.get_personalization_summary(
        db=db,
        profile_id=profile.id,
    )


@router.get(
    "/{researcher_id}/personalized-recommendations/{opportunity_id}/explanation",
    response_model=RecommendationExplanationSchema,
    status_code=status.HTTP_200_OK,
    summary="Get structured explanation for an active recommendation",
    description=(
        "Returns a detailed, human-understandable, and machine-inspectable explanation "
        "for why an opportunity was recommended to this researcher (Phase 3.8). "
        "Explains matched explicit preferences, scholarly expertise, behavioral feedback signals, "
        "deadline urgency, and publication trust/safety status."
    ),
)
def get_recommendation_explanation(
    researcher_id: uuid.UUID,
    opportunity_id: uuid.UUID,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> RecommendationExplanationSchema:
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
            detail="Forbidden: You do not have permission to inspect this recommendation explanation.",
        )

    try:
        return PersonalizationExplanationService.explain_opportunity_for_researcher(
            db=db,
            profile_id=profile.id,
            opportunity_id=opportunity_id,
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        )


@router.get(
    "/{researcher_id}/recommendation-history/{snapshot_id}/items/{opportunity_id}/explanation",
    response_model=RecommendationExplanationSchema,
    status_code=status.HTTP_200_OK,
    summary="Get frozen historical explanation for a past recommendation",
    description=(
        "Returns an immutable point-in-time explanation for why an opportunity was recommended "
        "within a historical snapshot (Phase 3.8). Strictly uses frozen historical scores and metadata."
    ),
)
def get_historical_recommendation_explanation(
    researcher_id: uuid.UUID,
    snapshot_id: uuid.UUID,
    opportunity_id: uuid.UUID,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> RecommendationExplanationSchema:
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
            detail="Forbidden: You do not have permission to inspect this historical recommendation explanation.",
        )

    try:
        return PersonalizationExplanationService.explain_historical_recommendation(
            db=db,
            profile_id=profile.id,
            snapshot_id=snapshot_id,
            opportunity_id=opportunity_id,
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        )


@router.get(
    "/{researcher_id}/calendar",
    response_model=ResearcherCalendarViewResponse,
    status_code=status.HTTP_200_OK,
    summary="Get consolidated researcher calendar",
    description="Retrieve the researcher's primary planning calendar, projected deadlines, and custom milestones.",
)
def get_researcher_calendar(
    researcher_id: uuid.UUID,
    start_date: datetime | None = Query(default=None, description="Filter events on or after this timestamp"),
    end_date: datetime | None = Query(default=None, description="Filter events on or before this timestamp"),
    event_type: CalendarEventType | None = Query(default=None, description="Filter by event category"),
    opportunity_id: uuid.UUID | None = Query(default=None, description="Filter by opportunity ID"),
    submission_id: uuid.UUID | None = Query(default=None, description="Filter by submission ID"),
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> ResearcherCalendarViewResponse:
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
            detail="Forbidden: You do not have permission to access this researcher calendar.",
        )

    return ResearchCalendarService.get_researcher_calendar_view(
        db=db,
        researcher_id=profile.id,
        user_id=profile.user_id,
        start_date=start_date,
        end_date=end_date,
        event_type=event_type,
        opportunity_id=opportunity_id,
        submission_id=submission_id,
    )


@router.get(
    "/{researcher_id}/calendar.ics",
    status_code=status.HTTP_200_OK,
    summary="Export researcher calendar to iCalendar (.ics)",
    description="Export the researcher's planning calendar and deadlines as a standard RFC 5545 iCalendar (.ics) file.",
)
def export_researcher_calendar_ics(
    researcher_id: uuid.UUID,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> Response:
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
            detail="Forbidden: You do not have permission to export this researcher calendar.",
        )

    calendar = ResearchCalendarService.get_or_create_default_calendar(db, user_id=profile.user_id)
    ical_content = ResearchCalendarService.generate_ical_feed(db, calendar.id, user_id=profile.user_id)

    return Response(
        content=ical_content,
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="researcher_{profile.id}_calendar.ics"',
            "Cache-Control": "no-cache, no-store, must-revalidate",
        },
    )


# ----------------------------------------------------------------------------
# Phase 4.5: Researcher Notifications & Reminder Rules Endpoints
# ----------------------------------------------------------------------------

def _resolve_researcher_profile_auth(
    researcher_id: uuid.UUID,
    x_user_id: uuid.UUID | None,
    db: Session,
) -> ResearchProfileModel:
    profile = ResearcherProfileService.get_profile(db, researcher_id)
    if not profile:
        profile = ResearcherProfileService.get_profile_by_user_id(db, researcher_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Researcher profile with ID '{researcher_id}' not found.",
        )
    if x_user_id is not None and profile.user_id != x_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You do not have permission to access this researcher resource.",
        )
    return profile


@router.get(
    "/{researcher_id}/notifications",
    response_model=NotificationListResponse,
    status_code=status.HTTP_200_OK,
    summary="List notifications for a researcher",
)
def get_researcher_notifications(
    researcher_id: uuid.UUID,
    unread_only: bool = Query(default=False),
    notification_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> NotificationListResponse:
    profile = _resolve_researcher_profile_auth(researcher_id, x_user_id, db)
    items, total, unread = NotificationService.list_notifications(
        db=db,
        profile_id=profile.id,
        unread_only=unread_only,
        notification_type=notification_type,
        limit=limit,
        offset=offset,
    )
    return NotificationListResponse(
        notifications=[NotificationRead.model_validate(n) for n in items],
        total=total,
        unread_count=unread,
    )


@router.get(
    "/{researcher_id}/notifications/unread-count",
    response_model=NotificationUnreadCountResponse,
    status_code=status.HTTP_200_OK,
    summary="Get unread notifications count for a researcher",
)
def get_researcher_unread_count(
    researcher_id: uuid.UUID,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> NotificationUnreadCountResponse:
    profile = _resolve_researcher_profile_auth(researcher_id, x_user_id, db)
    count = NotificationService.get_unread_count(db, profile.id)
    return NotificationUnreadCountResponse(
        profile_id=profile.id,
        unread_count=count,
    )


@router.post(
    "/{researcher_id}/notifications/{notification_id}/read",
    response_model=NotificationRead,
    status_code=status.HTTP_200_OK,
    summary="Mark a researcher notification as read",
)
def mark_researcher_notification_read(
    researcher_id: uuid.UUID,
    notification_id: uuid.UUID,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> NotificationRead:
    profile = _resolve_researcher_profile_auth(researcher_id, x_user_id, db)
    try:
        notif = NotificationService.mark_as_read(db, profile.id, notification_id)
        return NotificationRead.model_validate(notif)
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Notification belongs to another researcher.",
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        )


@router.post(
    "/{researcher_id}/notifications/read-all",
    response_model=dict[str, int],
    status_code=status.HTTP_200_OK,
    summary="Mark all researcher notifications as read",
)
def mark_all_researcher_notifications_read(
    researcher_id: uuid.UUID,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> dict[str, int]:
    profile = _resolve_researcher_profile_auth(researcher_id, x_user_id, db)
    count = NotificationService.mark_all_as_read(db, profile.id)
    return {"marked_read_count": count}


@router.get(
    "/{researcher_id}/notification-preferences",
    response_model=NotificationPreferenceRead,
    status_code=status.HTTP_200_OK,
    summary="Get researcher notification preferences",
)
def get_researcher_notification_preferences(
    researcher_id: uuid.UUID,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> NotificationPreferenceRead:
    profile = _resolve_researcher_profile_auth(researcher_id, x_user_id, db)
    prefs = NotificationService.get_or_create_preferences(db, profile.id)
    return NotificationPreferenceRead.model_validate(prefs)


@router.patch(
    "/{researcher_id}/notification-preferences",
    response_model=NotificationPreferenceRead,
    status_code=status.HTTP_200_OK,
    summary="Update researcher notification preferences",
)
def update_researcher_notification_preferences(
    researcher_id: uuid.UUID,
    payload: NotificationPreferenceUpdate,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> NotificationPreferenceRead:
    profile = _resolve_researcher_profile_auth(researcher_id, x_user_id, db)
    prefs = NotificationService.update_preferences(db, profile.id, payload)
    return NotificationPreferenceRead.model_validate(prefs)


@router.get(
    "/{researcher_id}/reminder-rules",
    response_model=ReminderRuleListResponse,
    status_code=status.HTTP_200_OK,
    summary="List researcher reminder rules",
)
def list_researcher_reminder_rules(
    researcher_id: uuid.UUID,
    is_active: bool | None = Query(default=None),
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> ReminderRuleListResponse:
    profile = _resolve_researcher_profile_auth(researcher_id, x_user_id, db)
    rules = NotificationService.list_reminder_rules(db, profile.id, is_active=is_active)
    if not rules:
        rules = NotificationService.bootstrap_default_reminder_rules(db, profile.id)
    return ReminderRuleListResponse(
        rules=[ReminderRuleRead.model_validate(r) for r in rules],
        total=len(rules),
    )


@router.post(
    "/{researcher_id}/reminder-rules",
    response_model=ReminderRuleRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create researcher reminder rule",
)
def create_researcher_reminder_rule(
    researcher_id: uuid.UUID,
    payload: ReminderRuleCreate,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> ReminderRuleRead:
    profile = _resolve_researcher_profile_auth(researcher_id, x_user_id, db)
    rule = NotificationService.create_reminder_rule(db, profile.id, payload)
    return ReminderRuleRead.model_validate(rule)


@router.patch(
    "/{researcher_id}/reminder-rules/{rule_id}",
    response_model=ReminderRuleRead,
    status_code=status.HTTP_200_OK,
    summary="Update researcher reminder rule",
)
def update_researcher_reminder_rule(
    researcher_id: uuid.UUID,
    rule_id: uuid.UUID,
    payload: ReminderRuleUpdate,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> ReminderRuleRead:
    profile = _resolve_researcher_profile_auth(researcher_id, x_user_id, db)
    try:
        rule = NotificationService.update_reminder_rule(db, profile.id, rule_id, payload)
        return ReminderRuleRead.model_validate(rule)
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Reminder rule belongs to another researcher.",
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        )


@router.delete(
    "/{researcher_id}/reminder-rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete researcher reminder rule",
)
def delete_researcher_reminder_rule(
    researcher_id: uuid.UUID,
    rule_id: uuid.UUID,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> Response:
    profile = _resolve_researcher_profile_auth(researcher_id, x_user_id, db)
    try:
        NotificationService.delete_reminder_rule(db, profile.id, rule_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Reminder rule belongs to another researcher.",
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        )


# ----------------------------------------------------------------------------
# Phase 4.7: Unified Research Intelligence & Recommendations Endpoints
# ----------------------------------------------------------------------------


@router.get(
    "/{researcher_id}/intelligence/unified",
    response_model=UnifiedResearcherContextSchema,
    status_code=status.HTTP_200_OK,
    summary="Get unified research intelligence context",
    description="Retrieve comprehensive researcher intelligence context including profile signals, interest topics, explicit preferences, behavioral signals, and identity resolution status.",
)
def get_unified_research_intelligence(
    researcher_id: uuid.UUID,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> UnifiedResearcherContextSchema:
    profile = _resolve_researcher_profile_auth(researcher_id, x_user_id, db)
    return ResearchIntelligenceIntegrationService.build_unified_researcher_context(db, profile.id)


@router.get(
    "/{researcher_id}/recommendations/unified",
    response_model=UnifiedRecommendationResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Get unified research-intelligence recommendations",
    description="Retrieve hybrid ranked opportunities enriched with researcher intelligence, bounded personalization, deadline & risk context, workspace status, and 6-tier explainability evidence.",
)
def get_unified_recommendations(
    researcher_id: uuid.UUID,
    limit: int = Query(default=20, ge=1, le=100, description="Max number of recommendations to return"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    opportunity_type: str | None = Query(default=None),
    delivery_mode: str | None = Query(default=None),
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> UnifiedRecommendationResponseSchema:
    profile = _resolve_researcher_profile_auth(researcher_id, x_user_id, db)
    return ResearchIntelligenceIntegrationService.get_unified_recommendations(
        db=db,
        profile_id=profile.id,
        limit=limit,
        offset=offset,
        opportunity_type=opportunity_type,
        delivery_mode=delivery_mode,
    )


@router.get(
    "/{researcher_id}/recommendations/unified/{opportunity_id}/intelligence",
    response_model=UnifiedOpportunityIntelligenceSchema,
    status_code=status.HTTP_200_OK,
    summary="Get unified intelligence and evidence for a specific opportunity",
    description="Retrieve full multi-tier evidence explanation (relevance, researcher match, research interests, preferences, deadline, risk, workspace context) for an opportunity in the context of this researcher.",
)
def get_opportunity_intelligence(
    researcher_id: uuid.UUID,
    opportunity_id: uuid.UUID,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> UnifiedOpportunityIntelligenceSchema:
    profile = _resolve_researcher_profile_auth(researcher_id, x_user_id, db)
    try:
        intel = ResearchIntelligenceIntegrationService.explain_opportunity_intelligence(
            db=db,
            profile_id=profile.id,
            opportunity_id=opportunity_id,
        )
        return intel
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        )


@router.get(
    "/{researcher_id}/opportunities/{opportunity_id}/preference-match",
    response_model=PreferencePersonalizationAssessment,
    status_code=status.HTTP_200_OK,
    summary="Get deterministic preference match evaluation for an opportunity",
    description="Evaluates a specific opportunity against all explicit researcher preferences, returning structured match signals and explanations.",
)
def get_opportunity_preference_match(
    researcher_id: uuid.UUID,
    opportunity_id: uuid.UUID,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> PreferencePersonalizationAssessment:
    profile = _resolve_researcher_profile_auth(researcher_id, x_user_id, db)
    stmt = (
        select(OpportunityModel)
        .where(OpportunityModel.id == opportunity_id)
        .options(
            selectinload(OpportunityModel.topic_associations).joinedload(
                OpportunityTopicModel.topic
            )
        )
    )
    opp = db.execute(stmt).scalar_one_or_none()
    if not opp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Opportunity {opportunity_id} not found",
        )

    structured_prefs = ResearcherPreferenceService.get_structured_preferences(db, profile.id)
    return PreferenceInterpreter.evaluate_opportunity(
        profile_id=profile.id,
        preferences=structured_prefs,
        opportunity=opp,
    )


@router.post(
    "/{researcher_id}/opportunities/preference-matches",
    response_model=BatchOpportunityPreferenceMatchResponse,
    status_code=status.HTTP_200_OK,
    summary="Batch evaluate opportunities against researcher preferences",
    description="Evaluates a list of opportunities in memory against researcher preferences with zero N+1 queries.",
)
def batch_opportunity_preference_matches(
    researcher_id: uuid.UUID,
    payload: BatchOpportunityPreferenceMatchRequest,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> BatchOpportunityPreferenceMatchResponse:
    profile = _resolve_researcher_profile_auth(researcher_id, x_user_id, db)
    
    stmt = (
        select(OpportunityModel)
        .where(OpportunityModel.id.in_(payload.opportunity_ids))
        .options(
            selectinload(OpportunityModel.topic_associations).joinedload(
                OpportunityTopicModel.topic
            )
        )
    )
    opps = list(db.execute(stmt).scalars().unique().all())

    structured_prefs = ResearcherPreferenceService.get_structured_preferences(db, profile.id)
    
    batch_results = PreferenceInterpreter.evaluate_opportunities_batch(
        profile_id=profile.id,
        preferences=structured_prefs,
        opportunities=opps,
    )

    ordered_assessments = [
        batch_results[opp_id]
        for opp_id in payload.opportunity_ids
        if opp_id in batch_results
    ]

    return BatchOpportunityPreferenceMatchResponse(
        profile_id=profile.id,
        assessments=ordered_assessments,
        evaluated_count=len(ordered_assessments),
    )


@router.get(
    "/{researcher_id}/opportunities/{opportunity_id}/personalization",
    response_model=PersonalizationAssessment,
    status_code=status.HTTP_200_OK,
    summary="Get personalization score and explainability breakdown for an opportunity",
    description="Computes a bounded, deterministic personalization score and structured explanation breakdown for a specific opportunity against explicit researcher preferences.",
)
def get_opportunity_personalization(
    researcher_id: uuid.UUID,
    opportunity_id: uuid.UUID,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> PersonalizationAssessment:
    profile = _resolve_researcher_profile_auth(researcher_id, x_user_id, db)
    stmt = (
        select(OpportunityModel)
        .where(OpportunityModel.id == opportunity_id)
        .options(
            selectinload(OpportunityModel.topic_associations).joinedload(
                OpportunityTopicModel.topic
            )
        )
    )
    opp = db.execute(stmt).scalar_one_or_none()
    if not opp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Opportunity {opportunity_id} not found",
        )

    structured_prefs = ResearcherPreferenceService.get_structured_preferences(db, profile.id)
    adaptive_signals = AdaptivePreferenceSignalService.get_adaptive_signals(db, profile.id)
    calibrations = PersonalizationCalibrationService.get_calibrations(db, profile.id)
    contextual_adaptations = PersonalizationQualityService.get_contextual_adaptations(db, profile.id)
    governance_state = PersonalizationGovernanceService.get_active_governance_state(db, profile.id)
    return PersonalizationScorer.score_opportunity(
        profile_id=profile.id,
        preferences=structured_prefs,
        opportunity=opp,
        adaptive_signals=adaptive_signals,
        calibrations=calibrations,
        contextual_adaptations=contextual_adaptations,
        governance_state=governance_state,
    )


@router.post(
    "/{researcher_id}/opportunities/personalization",
    response_model=BatchPersonalizationResponse,
    status_code=status.HTTP_200_OK,
    summary="Batch evaluate personalization scores and breakdowns for opportunities",
    description="Scores a list of opportunities in memory against researcher explicit preferences with zero N+1 queries.",
)
def batch_opportunity_personalization(
    researcher_id: uuid.UUID,
    payload: BatchPersonalizationRequest,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> BatchPersonalizationResponse:
    profile = _resolve_researcher_profile_auth(researcher_id, x_user_id, db)

    stmt = (
        select(OpportunityModel)
        .where(OpportunityModel.id.in_(payload.opportunity_ids))
        .options(
            selectinload(OpportunityModel.topic_associations).joinedload(
                OpportunityTopicModel.topic
            )
        )
    )
    opps = list(db.execute(stmt).scalars().unique().all())

    structured_prefs = ResearcherPreferenceService.get_structured_preferences(db, profile.id)
    adaptive_signals = AdaptivePreferenceSignalService.get_adaptive_signals(db, profile.id)
    calibrations = PersonalizationCalibrationService.get_calibrations(db, profile.id)
    contextual_adaptations = PersonalizationQualityService.get_contextual_adaptations(db, profile.id)
    governance_state = PersonalizationGovernanceService.get_active_governance_state(db, profile.id)

    batch_results = PersonalizationScorer.score_opportunities_batch(
        profile_id=profile.id,
        preferences=structured_prefs,
        opportunities=opps,
        adaptive_signals=adaptive_signals,
        calibrations=calibrations,
        contextual_adaptations=contextual_adaptations,
        governance_state=governance_state,
    )

    ordered_assessments = [
        batch_results[opp_id]
        for opp_id in payload.opportunity_ids
        if opp_id in batch_results
    ]

    return BatchPersonalizationResponse(
        profile_id=profile.id,
        assessments=ordered_assessments,
        evaluated_count=len(ordered_assessments),
    )



# ----------------------------------------------------------------------------
# Phase 5.4: Researcher Feedback & Interaction Signal Endpoints
# ----------------------------------------------------------------------------

@router.post(
    "/{researcher_id}/opportunities/{opportunity_id}/interactions",
    response_model=InteractionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record a researcher-opportunity interaction",
    description="Records an auditable researcher interaction (e.g. VIEWED, OPENED, SAVED, DISMISSED, HIDDEN, INTERESTED, NOT_INTERESTED, APPLIED, SHARED) with idempotency protection.",
)
def record_opportunity_interaction(
    researcher_id: uuid.UUID,
    opportunity_id: uuid.UUID,
    payload: InteractionCreateRequest,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> InteractionResponse:
    profile = _resolve_researcher_profile_auth(researcher_id, x_user_id, db)
    try:
        return ResearcherInteractionService.record_interaction(
            db=db,
            profile_id=profile.id,
            opportunity_id=opportunity_id,
            payload=payload,
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        )


@router.get(
    "/{researcher_id}/opportunities/{opportunity_id}/interactions",
    response_model=OpportunityInteractionHistoryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get interaction history for an opportunity",
    description="Retrieves the chronological list of interaction events recorded by this researcher for a specific opportunity.",
)
def get_opportunity_interactions(
    researcher_id: uuid.UUID,
    opportunity_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> OpportunityInteractionHistoryResponse:
    profile = _resolve_researcher_profile_auth(researcher_id, x_user_id, db)
    try:
        return ResearcherInteractionService.get_opportunity_interactions(
            db=db,
            profile_id=profile.id,
            opportunity_id=opportunity_id,
            limit=limit,
            offset=offset,
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        )


@router.get(
    "/{researcher_id}/interactions/summary",
    response_model=ResearcherInteractionSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get researcher interaction signals summary",
    description="Retrieves aggregated counts, positive/negative breakdown, and recent interaction events across all opportunities for a researcher.",
)
def get_researcher_interaction_summary(
    researcher_id: uuid.UUID,
    recent_limit: int = Query(default=10, ge=1, le=50),
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> ResearcherInteractionSummaryResponse:
    profile = _resolve_researcher_profile_auth(researcher_id, x_user_id, db)
    try:
        return ResearcherInteractionService.get_researcher_interaction_summary(
            db=db,
            profile_id=profile.id,
            recent_limit=recent_limit,
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        )


# ----------------------------------------------------------------------------
# Phase 5.5: Adaptive Preference Signal Endpoints
# ----------------------------------------------------------------------------

@router.get(
    "/{researcher_id}/adaptive-signals",
    response_model=AdaptiveSignalsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get researcher adaptive preference signals",
    description="Retrieves aggregated, bounded behavioral preference signals derived deterministically from researcher interactions.",
)
def get_researcher_adaptive_signals(
    researcher_id: uuid.UUID,
    dimension: AdaptiveSignalDimension | None = Query(default=None, description="Filter by signal dimension"),
    state: AdaptiveEvidenceState | None = Query(default=None, description="Filter by evidence state"),
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> AdaptiveSignalsResponse:
    profile = _resolve_researcher_profile_auth(researcher_id, x_user_id, db)
    signals = AdaptivePreferenceSignalService.get_adaptive_signals(
        db=db,
        profile_id=profile.id,
        dimension=dimension,
        state=state,
    )
    return AdaptiveSignalsResponse(
        profile_id=profile.id,
        items=signals,
        total_count=len(signals),
    )


@router.get(
    "/{researcher_id}/adaptive-signals/explanation",
    response_model=AdaptiveSignalExplanationResponse,
    status_code=status.HTTP_200_OK,
    summary="Get deterministic summary explanation of adaptive signals",
    description="Retrieves structured, transparent natural language explanations summarizing the researcher's behavioral signals.",
)
def get_researcher_adaptive_signals_explanation(
    researcher_id: uuid.UUID,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> AdaptiveSignalExplanationResponse:
    profile = _resolve_researcher_profile_auth(researcher_id, x_user_id, db)
    return AdaptivePreferenceSignalService.get_adaptive_signals_summary_explanation(
        db=db,
        profile_id=profile.id,
    )


@router.get(
    "/{researcher_id}/adaptive-signals/{signal_id}",
    response_model=AdaptivePreferenceSignal,
    status_code=status.HTTP_200_OK,
    summary="Get a specific adaptive preference signal",
    description="Retrieves a specific adaptive preference signal for a researcher by ID, ensuring researcher isolation.",
)
def get_adaptive_signal_by_id(
    researcher_id: uuid.UUID,
    signal_id: uuid.UUID,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> AdaptivePreferenceSignal:
    profile = _resolve_researcher_profile_auth(researcher_id, x_user_id, db)
    signal = AdaptivePreferenceSignalService.get_adaptive_signal_by_id(
        db=db,
        profile_id=profile.id,
        signal_id=signal_id,
    )
    if not signal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Adaptive signal with ID '{signal_id}' not found.",
        )
    return signal


@router.post(
    "/{researcher_id}/adaptive-signals/recompute",
    response_model=AdaptiveSignalsResponse,
    status_code=status.HTTP_200_OK,
    summary="Recompute researcher adaptive preference signals",
    description="Recomputes all bounded adaptive signals from the researcher's historical interaction records deterministically.",
)
def recompute_researcher_adaptive_signals(
    researcher_id: uuid.UUID,
    payload: AdaptiveSignalRecomputeRequest | None = None,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> AdaptiveSignalsResponse:
    profile = _resolve_researcher_profile_auth(researcher_id, x_user_id, db)
    signals = AdaptivePreferenceSignalService.recompute_adaptive_signals(
        db=db,
        profile_id=profile.id,
    )
    db.commit()
    return AdaptiveSignalsResponse(
        profile_id=profile.id,
        items=signals,
        total_count=len(signals),
    )


# ----------------------------------------------------------------------------
# Phase 5.6: Personalization Calibration Endpoints
# ----------------------------------------------------------------------------

@router.get(
    "/{researcher_id}/personalization/calibration",
    response_model=PersonalizationCalibrationResponse,
    status_code=status.HTTP_200_OK,
    summary="Get researcher personalization calibration summary and signals",
    description="Retrieves aggregated, bounded calibration records measuring feedback performance for personalization signals.",
)
def get_researcher_personalization_calibrations(
    researcher_id: uuid.UUID,
    dimension: str | None = Query(default=None, description="Filter by signal dimension"),
    state: CalibrationState | None = Query(default=None, description="Filter by calibration state"),
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> PersonalizationCalibrationResponse:
    profile = _resolve_researcher_profile_auth(researcher_id, x_user_id, db)
    return PersonalizationCalibrationService.get_calibration_response(
        db=db,
        profile_id=profile.id,
        dimension=dimension,
        state=state,
    )


@router.get(
    "/{researcher_id}/personalization/calibration/{signal_id}",
    response_model=PersonalizationCalibrationDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get a specific personalization signal calibration detail",
    description="Retrieves calibration details and recent granular attribution events for a specific signal.",
)
def get_personalization_calibration_by_signal_id(
    researcher_id: uuid.UUID,
    signal_id: uuid.UUID,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> PersonalizationCalibrationDetailResponse:
    profile = _resolve_researcher_profile_auth(researcher_id, x_user_id, db)
    detail = PersonalizationCalibrationService.get_calibration_by_signal_id(
        db=db,
        profile_id=profile.id,
        signal_id=signal_id,
    )
    if not detail:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Calibration record with ID '{signal_id}' not found.",
        )
    return detail


@router.post(
    "/{researcher_id}/personalization/calibration/recompute",
    response_model=PersonalizationCalibrationResponse,
    status_code=status.HTTP_200_OK,
    summary="Recompute researcher personalization calibration",
    description="Recomputes all bounded calibration modifiers and attribution events from recommendation and interaction history deterministically.",
)
def recompute_researcher_personalization_calibration(
    researcher_id: uuid.UUID,
    payload: CalibrationRecomputeRequest | None = None,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> PersonalizationCalibrationResponse:
    profile = _resolve_researcher_profile_auth(researcher_id, x_user_id, db)

    from app.personalization.calibration_config import PersonalizationCalibrationConfig
    config = PersonalizationCalibrationConfig()
    if payload and payload.attribution_window_days is not None:
        config = PersonalizationCalibrationConfig(
            attribution_window_days=payload.attribution_window_days
        )

    PersonalizationCalibrationService.recompute_calibrations(
        db=db,
        profile_id=profile.id,
        config=config,
    )
    db.commit()

    return PersonalizationCalibrationService.get_calibration_response(
        db=db,
        profile_id=profile.id,
    )


# ----------------------------------------------------------------------------
# Phase 5.7: Personalization Quality & Contextual Adaptation Endpoints
# ----------------------------------------------------------------------------

@router.get(
    "/{researcher_id}/personalization/quality",
    response_model=PersonalizationQualityResponse,
    status_code=status.HTTP_200_OK,
    summary="Get researcher personalization quality evaluation and lift",
    description=(
        "Retrieves deterministic personalization quality metrics, observed personalization lift, "
        "positive/negative engagement rates, diversity, novelty, and deterministic explanations."
    ),
)
def get_researcher_personalization_quality(
    researcher_id: uuid.UUID,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> PersonalizationQualityResponse:
    profile = _resolve_researcher_profile_auth(researcher_id, x_user_id, db)
    return PersonalizationQualityService.get_quality_response(
        db=db,
        profile_id=profile.id,
    )


@router.get(
    "/{researcher_id}/personalization/quality/contexts",
    response_model=ContextualAdaptationsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get contextual adaptation breakdown for researcher",
    description="Retrieves bounded contextual adaptation records and hierarchical fallback levels across opportunity contexts.",
)
def get_researcher_contextual_adaptations(
    researcher_id: uuid.UUID,
    context_dimension: str | None = Query(default=None, description="Filter by context dimension (e.g. OPPORTUNITY_TYPE, DEADLINE_HORIZON)"),
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> ContextualAdaptationsResponse:
    profile = _resolve_researcher_profile_auth(researcher_id, x_user_id, db)
    return PersonalizationQualityService.get_contextual_adaptations_response(
        db=db,
        profile_id=profile.id,
        context_dimension=context_dimension,
    )


@router.get(
    "/{researcher_id}/personalization/quality/signals",
    response_model=SignalQualityResponse,
    status_code=status.HTTP_200_OK,
    summary="Get signal-level personalization quality breakdown",
    description="Retrieves personalization quality evaluation metrics grouped per individual behavioral signal.",
)
def get_researcher_signal_qualities(
    researcher_id: uuid.UUID,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> SignalQualityResponse:
    profile = _resolve_researcher_profile_auth(researcher_id, x_user_id, db)
    return PersonalizationQualityService.get_signal_quality_response(
        db=db,
        profile_id=profile.id,
    )


@router.post(
    "/{researcher_id}/personalization/quality/recompute",
    response_model=PersonalizationQualityResponse,
    status_code=status.HTTP_200_OK,
    summary="Recompute researcher personalization quality evaluation and contextual adaptations",
    description=(
        "Recomputes all personalization quality metrics, observed lift, and bounded contextual "
        "adaptations from recommendation and interaction history deterministically."
    ),
)
def recompute_researcher_personalization_quality(
    researcher_id: uuid.UUID,
    payload: QualityRecomputeRequest | None = None,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> PersonalizationQualityResponse:
    profile = _resolve_researcher_profile_auth(researcher_id, x_user_id, db)

    ref_time = payload.reference_time if payload else None
    eval_period = payload.evaluation_period_days if payload and payload.evaluation_period_days is not None else 30.0

    PersonalizationQualityService.recompute_personalization_quality(
        db=db,
        profile_id=profile.id,
        reference_time=ref_time,
        evaluation_period_days=eval_period,
    )
    db.commit()

    return PersonalizationQualityService.get_quality_response(
        db=db,
        profile_id=profile.id,
    )


# ----------------------------------------------------------------------------
# Phase 5.8: Personalization Governance, Drift Detection & Adaptation Safety Endpoints
# ----------------------------------------------------------------------------

@router.get(
    "/{researcher_id}/personalization/health",
    response_model=PersonalizationHealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Get researcher personalization health and governance status",
    description=(
        "Retrieves multi-dimensional personalization health state, signal freshness, evidence sufficiency, "
        "quality stability, preference alignment, governance gate decision, and adaptation level."
    ),
)
def get_researcher_personalization_health(
    researcher_id: uuid.UUID,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> PersonalizationHealthResponse:
    profile = _resolve_researcher_profile_auth(researcher_id, x_user_id, db)
    return PersonalizationGovernanceService.get_health_response(
        db=db,
        profile_id=profile.id,
    )


@router.get(
    "/{researcher_id}/personalization/drift",
    response_model=PersonalizationDriftResponse,
    status_code=status.HTTP_200_OK,
    summary="Get researcher behavioral signal drift report",
    description=(
        "Retrieves granular signal drift classifications comparing historical vs recent observation windows, "
        "including emerging, persistent, reversing, and stale signals."
    ),
)
def get_researcher_personalization_drift(
    researcher_id: uuid.UUID,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> PersonalizationDriftResponse:
    profile = _resolve_researcher_profile_auth(researcher_id, x_user_id, db)
    return PersonalizationGovernanceService.get_drift_response(
        db=db,
        profile_id=profile.id,
    )


@router.get(
    "/{researcher_id}/personalization/governance",
    response_model=PersonalizationGovernanceHistoryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get paginated personalization governance audit events",
    description="Retrieves the append-only, immutable audit trail of governance gate state changes, suspensions, and recoveries.",
)
def get_researcher_governance_events(
    researcher_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> PersonalizationGovernanceHistoryResponse:
    profile = _resolve_researcher_profile_auth(researcher_id, x_user_id, db)
    return PersonalizationGovernanceService.get_governance_events_response(
        db=db,
        profile_id=profile.id,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/{researcher_id}/personalization/health/recompute",
    response_model=PersonalizationHealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Recompute researcher personalization health and governance gate",
    description="Deterministically recomputes signal drift, multi-dimensional health, and governance gate state from history.",
)
def recompute_researcher_personalization_health(
    researcher_id: uuid.UUID,
    payload: GovernanceRecomputeRequest | None = None,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> PersonalizationHealthResponse:
    profile = _resolve_researcher_profile_auth(researcher_id, x_user_id, db)

    ref_time = payload.reference_time if payload else None
    hist_days = payload.historical_window_days if payload and payload.historical_window_days is not None else 60.0
    recent_days = payload.recent_window_days if payload and payload.recent_window_days is not None else 14.0

    PersonalizationGovernanceService.recompute_governance(
        db=db,
        profile_id=profile.id,
        reference_time=ref_time,
        historical_window_days=hist_days,
        recent_window_days=recent_days,
    )
    db.commit()

    return PersonalizationGovernanceService.get_health_response(
        db=db,
        profile_id=profile.id,
    )



