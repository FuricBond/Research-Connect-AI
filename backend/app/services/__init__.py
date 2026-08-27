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
from app.services.research_opportunity_matching_service import (
    ResearchOpportunityMatch,
    ResearchOpportunityMatchingService,
    calculate_topic_compatibility,
    calculate_type_compatibility,
    research_opportunity_matching_service,
)
from app.services.similar_research_service import (
    MissingEmbeddingError,
    ResearchWorkNotFoundError,
    SimilarResearchResult,
    SimilarResearchService,
    calculate_topic_similarity,
    normalize_lexical_score,
    similar_research_service,
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
    # Similar research service
    "SimilarResearchResult",
    "SimilarResearchService",
    "ResearchWorkNotFoundError",
    "MissingEmbeddingError",
    "calculate_topic_similarity",
    "normalize_lexical_score",
    "similar_research_service",
    # Research opportunity matching service
    "ResearchOpportunityMatch",
    "ResearchOpportunityMatchingService",
    "calculate_topic_compatibility",
    "calculate_type_compatibility",
    "research_opportunity_matching_service",
]
