from app.models.base import Base, TimestampMixin
from app.models.ingestion_run import IngestionRunModel
from app.models.opportunity import OpportunityModel, OpportunityTopicModel
from app.models.research_knowledge import (
    InstitutionModel,
    ResearcherModel,
    ResearchSourceModel,
    ResearchWorkAuthorModel,
    ResearchWorkInstitutionModel,
    ResearchWorkModel,
    ResearchWorkTopicModel,
)
from app.models.research_profile import ResearchProfileModel
from app.models.saved_opportunity import SavedOpportunityModel
from app.models.source import SourceModel
from app.models.topic import TopicAliasModel, TopicModel
from app.models.user import UserModel

__all__ = [
    "Base",
    "TimestampMixin",
    "UserModel",
    "ResearchProfileModel",
    "SourceModel",
    "TopicModel",
    "TopicAliasModel",
    "OpportunityModel",
    "OpportunityTopicModel",
    "SavedOpportunityModel",
    "IngestionRunModel",
    # Research knowledge (Phase 2.2A / 2.2B / 2.3A)
    "ResearcherModel",
    "ResearchSourceModel",
    "InstitutionModel",
    "ResearchWorkModel",
    "ResearchWorkAuthorModel",
    "ResearchWorkInstitutionModel",
    "ResearchWorkTopicModel",
]
