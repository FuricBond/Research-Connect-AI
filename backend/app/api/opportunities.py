import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.ranking.deadline import deadline_explainability_service
from app.ranking.risk import assess_opportunity_risk, risk_explainability_service
from app.schemas.deadline import OpportunityDeadlineSchema
from app.schemas.opportunity import (
    OpportunityListResponse,
    OpportunityRead,
    RiskExplanationSchema,
)
from app.services.opportunity_service import (
    DeliveryMode,
    OpportunitySort,
    OpportunityStatus,
    OpportunityType,
    get_opportunity_by_id,
    list_opportunities,
)

router = APIRouter(prefix="/opportunities", tags=["opportunities"])

DbDep = Annotated[Session, Depends(get_db)]


@router.get("", response_model=OpportunityListResponse)
def list_opportunities_route(
    db: DbDep,
    search: Annotated[str | None, Query(description="Full-text search on title, summary, description")] = None,
    opportunity_type: Annotated[OpportunityType | None, Query(description="Filter by opportunity type")] = None,
    status: Annotated[OpportunityStatus | None, Query(description="Filter by lifecycle status")] = None,
    delivery_mode: Annotated[DeliveryMode | None, Query(description="Filter by delivery mode")] = None,
    source_id: Annotated[uuid.UUID | None, Query(description="Filter by source UUID")] = None,
    upcoming: Annotated[bool, Query(description="Only show opportunities with a future submission deadline")] = False,
    sort: Annotated[OpportunitySort, Query(description="Sort order: newest | deadline | title")] = OpportunitySort.newest,
    page: Annotated[int, Query(ge=1, description="Page number (1-indexed)")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Items per page (max 100)")] = 20,
) -> OpportunityListResponse:
    """List opportunities with optional filtering, search, and pagination."""
    return list_opportunities(
        db,
        search=search,
        opportunity_type=opportunity_type.value if opportunity_type else None,
        status=status.value if status else None,
        delivery_mode=delivery_mode.value if delivery_mode else None,
        source_id=source_id,
        upcoming=upcoming,
        sort=sort,
        page=page,
        page_size=page_size,
    )


@router.get("/{opportunity_id}", response_model=OpportunityRead)
def get_opportunity_route(
    opportunity_id: uuid.UUID,
    db: DbDep,
) -> OpportunityRead:
    """Get a single opportunity by UUID with additive deadline intelligence."""
    opportunity = get_opportunity_by_id(db, opportunity_id)
    if opportunity is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    opp_read = OpportunityRead.model_validate(opportunity)
    opp_read.deadline_intelligence = deadline_explainability_service.explain_opportunity_from_model(opportunity)
    return opp_read


@router.get(
    "/{opportunity_id}/risk-explanation",
    response_model=RiskExplanationSchema,
    summary="Get Deterministic Risk & Trust Explanation",
    description="Retrieve structured, provenance-backed trust and risk explanation for an academic opportunity (Phase 2.6F).",
)
def get_opportunity_risk_explanation_route(
    opportunity_id: uuid.UUID,
    db: DbDep,
) -> RiskExplanationSchema:
    """Get deterministic trust & risk explanation for an opportunity by UUID."""
    opportunity = get_opportunity_by_id(db, opportunity_id)
    if opportunity is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    assessment = assess_opportunity_risk(opportunity)
    explanation = risk_explainability_service.explain(assessment, opportunity=opportunity)
    return RiskExplanationSchema.model_validate(explanation.to_dict())


@router.get(
    "/{opportunity_id}/deadlines",
    response_model=OpportunityDeadlineSchema,
    summary="Get Canonical Deadline Intelligence",
    description="Retrieve structured, loss-aware canonical deadline views, revision history, multi-source conflict states, and deterministic explainability for an academic opportunity (Phase 2.7F).",
)
def get_opportunity_deadlines_route(
    opportunity_id: uuid.UUID,
    db: DbDep,
) -> OpportunityDeadlineSchema:
    """Get canonical deadline intelligence for an opportunity by UUID."""
    opportunity = get_opportunity_by_id(db, opportunity_id)
    if opportunity is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    return deadline_explainability_service.explain_opportunity_from_model(opportunity)
