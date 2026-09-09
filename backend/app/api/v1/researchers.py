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

from fastapi import APIRouter, Depends, HTTPException, Query, status
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
from app.services.researcher_intelligence_service import ResearcherIntelligenceService
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

