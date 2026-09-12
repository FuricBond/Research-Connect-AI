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
from app.services.personalization_ranking_service import (
    PersonalizationRankingService,
)
from app.services.personalized_candidate_generation_service import (
    PersonalizedCandidateGenerationService,
)
from app.services.feedback_service import ResearcherFeedbackService
from app.services.researcher_intelligence_service import ResearcherIntelligenceService
from app.services.researcher_preference_service import ResearcherPreferenceService
from app.services.researcher_profile_service import ResearcherProfileService
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
    # Researcher profile service (Phase 3.1)
    "ResearcherProfileService",
    # Researcher intelligence service (Phase 3.2)
    "ResearcherIntelligenceService",
    # Researcher preference service (Phase 3.3)
    "ResearcherPreferenceService",
    # Personalized candidate generation service (Phase 3.4)
    "PersonalizedCandidateGenerationService",
    # Personalization ranking service (Phase 3.5)
    "PersonalizationRankingService",
    # Researcher feedback service (Phase 3.6)
    "ResearcherFeedbackService",
]



