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

import logging
from typing import Annotated
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
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


