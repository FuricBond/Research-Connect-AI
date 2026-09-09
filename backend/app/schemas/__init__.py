from app.schemas.discovery import (
    ExplanationSchema,
    OpportunityMatchItem,
    OpportunityMatchResponse,
    ProvenanceEvidenceSchema,
    ResearchSearchResponse,
    ResearchSearchResultItem,
    ResearchWorkRead,
    SignalContributionSchema,
    SimilarResearchItem,
    SimilarResearchResponse,
    TopicEvidenceSchema,
)
from app.schemas.opportunity import (
    IngestionRunRead,
    IngestionRunStatus,
    OpportunityFee,
    OpportunityListItem,
    OpportunityListResponse,
    OpportunityRead,
)
from app.schemas.researcher import (
    AcademicStatus,
    CompletenessLevel,
    ExternalIdentifiersSchema,
    InstitutionSummarySchema,
    ProfileCompletenessSchema,
    ResearcherProfileCreate,
    ResearcherProfileRead,
    ResearcherProfileUpdate,
    ResearcherWorkSummarySchema,
)
from app.schemas.researcher_intelligence import (
    ExpertiseClassification,
    ResearcherIntelligenceResponse,
    ResearcherIntelligenceSummarySchema,
    ResearcherInterestItemSchema,
    SupportingWorkReferenceSchema,
)
from app.schemas.researcher_preference import (
    PreferenceCategory,
    PreferenceCompletenessSchema,
    PreferenceConflictSchema,
    PreferenceIntelligenceSummarySchema,
    PreferenceSource,
    ResearcherPreferenceCreateSchema,
    ResearcherPreferenceIntelligenceResponse,
    ResearcherPreferenceItemSchema,
    ResearcherPreferenceUpdateSchema,
)
from app.schemas.personalized_candidate import (
    CandidateProvenanceSchema,
    CandidateSourceCoverageSchema,
    CandidateSourceType,
    PersonalizedCandidateItemSchema,
    PersonalizedCandidateOpportunitySchema,
    PersonalizedCandidateSetResponse,
)
from app.schemas.personalized_ranking import (
    AblationSummarySchema,
    MatchedPersonalizationSignalsSchema,
    PersonalizationScoreBreakdownSchema,
    PersonalizedRankedCandidateSchema,
    PersonalizedRankingResponse,
)

__all__ = [
    "OpportunityFee",
    "OpportunityListItem",
    "OpportunityListResponse",
    "OpportunityRead",
    "IngestionRunRead",
    "IngestionRunStatus",
    "ResearchWorkRead",
    "SignalContributionSchema",
    "TopicEvidenceSchema",
    "ProvenanceEvidenceSchema",
    "ExplanationSchema",
    "ResearchSearchResultItem",
    "ResearchSearchResponse",
    "SimilarResearchItem",
    "SimilarResearchResponse",
    "OpportunityMatchItem",
    "OpportunityMatchResponse",
    # Phase 3.1 Researcher Profile Schemas
    "AcademicStatus",
    "CompletenessLevel",
    "ExternalIdentifiersSchema",
    "InstitutionSummarySchema",
    "ResearcherWorkSummarySchema",
    "ProfileCompletenessSchema",
    "ResearcherProfileCreate",
    "ResearcherProfileUpdate",
    "ResearcherProfileRead",
    # Phase 3.2 Researcher Intelligence Schemas
    "ExpertiseClassification",
    "SupportingWorkReferenceSchema",
    "ResearcherInterestItemSchema",
    "ResearcherIntelligenceSummarySchema",
    "ResearcherIntelligenceResponse",
    # Phase 3.3 Personal Preference Intelligence Schemas
    "PreferenceCategory",
    "PreferenceSource",
    "PreferenceConflictSchema",
    "PreferenceCompletenessSchema",
    "ResearcherPreferenceItemSchema",
    "ResearcherPreferenceCreateSchema",
    "ResearcherPreferenceUpdateSchema",
    "PreferenceIntelligenceSummarySchema",
    "ResearcherPreferenceIntelligenceResponse",
    # Phase 3.4 Personalized Candidate Generation Schemas
    "CandidateSourceType",
    "CandidateProvenanceSchema",
    "PersonalizedCandidateOpportunitySchema",
    "PersonalizedCandidateItemSchema",
    "CandidateSourceCoverageSchema",
    "PersonalizedCandidateSetResponse",
    # Phase 3.5 Personalized Ranking Schemas
    "PersonalizationScoreBreakdownSchema",
    "MatchedPersonalizationSignalsSchema",
    "PersonalizedRankedCandidateSchema",
    "AblationSummarySchema",
    "PersonalizedRankingResponse",
]




