from fastapi import APIRouter

from app.schemas.opportunity import Opportunity
from app.services.opportunity_service import list_sample_opportunities

router = APIRouter(prefix="/opportunities", tags=["opportunities"])


@router.get("", response_model=list[Opportunity])
def list_opportunities() -> list[Opportunity]:
    return list_sample_opportunities()
