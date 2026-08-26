"""
Services layer for ResearchConnect AI.
"""
from app.services.hybrid_search_service import (
    HybridSearchResult,
    HybridSearchService,
    calculate_candidate_limit,
    hybrid_search_service,
)
from app.services.opportunity_service import (
    DeliveryMode,
    OpportunitySort,
    OpportunityStatus,
    OpportunityType,
    get_opportunity_by_id,
    list_opportunities,
)

__all__ = [
    # Opportunity service
    "DeliveryMode",
    "OpportunitySort",
    "OpportunityStatus",
    "OpportunityType",
    "list_opportunities",
    "get_opportunity_by_id",
    # Hybrid search service
    "HybridSearchResult",
    "HybridSearchService",
    "calculate_candidate_limit",
    "hybrid_search_service",
]
