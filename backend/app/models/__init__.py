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
from app.models.research_profile import AcademicStatus, ResearchProfileModel
from app.models.researcher_interest import ResearcherInterestModel
from app.models.researcher_preference import ResearcherPreferenceModel
from app.models.researcher_interaction import InteractionType, ResearcherInteractionModel
from app.models.adaptive_signal import (
    AdaptiveEvidenceState,
    AdaptivePreferenceSignalModel,
    AdaptiveSignalDimension,
)
from app.models.personalization_calibration import (
    AttributionConfidence,
    CalibrationState,
    FeedbackOutcomeType,
    PersonalizationCalibrationModel,
    RecommendationFeedbackAttributionModel,
)
from app.models.personalization_quality import (
    ContextualFallbackLevel,
    PersonalizationContextualAdaptationModel,
    PersonalizationQualityEvaluationModel,
    QualityEvaluationState,
)
from app.models.researcher_feedback import ResearcherRecommendationFeedbackModel
from app.models.recommendation_history import (
    ResearcherRecommendationSnapshotModel,
    ResearcherRecommendationItemModel,
)
from app.models.research_submission import (
    ResearchSubmissionModel,
    SubmissionStatus,
    SubmissionType,
)
from app.models.submission_document import (
    DocumentStatus,
    DocumentType,
    ResearchSubmissionDocumentModel,
    ResearchSubmissionDocumentVersionModel,
    ResearchSubmissionEventModel,
    SubmissionEventType,
)
from app.models.saved_opportunity import (
    ResearchOpportunityWorkspaceModel,
    SavedOpportunityModel,
    WorkspacePriority,
    WorkspaceStatus,
)
from app.models.source import SourceModel
from app.models.topic import TopicAliasModel, TopicModel
from app.models.user import UserModel

from app.models.calendar import (
    CalendarEventStatus,
    CalendarEventType,
    ResearchCalendarEventModel,
    ResearchCalendarModel,
)
from app.models.notification import (
    DeliveryChannel,
    DeliveryStatus,
    NotificationDeliveryAttemptModel,
    NotificationModel,
    NotificationPreferenceModel,
    NotificationType,
    OffsetUnit,
    ReminderRuleModel,
)
from app.models.workspace_collaboration import (
    ActivityType,
    InvitationStatus,
    MemberStatus,
    TaskPriority,
    TaskStatus,
    WorkspaceActivityModel,
    WorkspaceInvitationModel,
    WorkspaceMemberModel,
    WorkspaceRole,
    WorkspaceTaskModel,
)

__all__ = [
    "Base",
    "TimestampMixin",
    "UserModel",
    "AcademicStatus",
    "ResearchProfileModel",
    "ResearcherInterestModel",
    "ResearcherPreferenceModel",
    "ResearcherInteractionModel",
    "InteractionType",
    "AdaptivePreferenceSignalModel",
    "AdaptiveSignalDimension",
    "AdaptiveEvidenceState",
    "ResearcherRecommendationFeedbackModel",
    "ResearcherRecommendationSnapshotModel",
    "ResearcherRecommendationItemModel",
    "SourceModel",
    "TopicModel",
    "TopicAliasModel",
    "OpportunityModel",
    "OpportunityTopicModel",
    "SavedOpportunityModel",
    "ResearchOpportunityWorkspaceModel",
    "WorkspaceStatus",
    "WorkspacePriority",
    "ResearchSubmissionModel",
    "SubmissionStatus",
    "SubmissionType",
    "ResearchSubmissionDocumentModel",
    "ResearchSubmissionDocumentVersionModel",
    "ResearchSubmissionEventModel",
    "DocumentType",
    "DocumentStatus",
    "SubmissionEventType",
    "ResearchCalendarModel",
    "ResearchCalendarEventModel",
    "CalendarEventType",
    "CalendarEventStatus",
    "NotificationModel",
    "NotificationPreferenceModel",
    "ReminderRuleModel",
    "NotificationDeliveryAttemptModel",
    "NotificationType",
    "DeliveryChannel",
    "DeliveryStatus",
    "OffsetUnit",
    "IngestionRunModel",
    # Collaboration (Phase 4.6)
    "WorkspaceRole",
    "MemberStatus",
    "InvitationStatus",
    "TaskStatus",
    "TaskPriority",
    "ActivityType",
    "WorkspaceMemberModel",
    "WorkspaceInvitationModel",
    "WorkspaceTaskModel",
    "WorkspaceActivityModel",
    # Research knowledge (Phase 2.2A / 2.2B / 2.3A)
    "ResearcherModel",
    "ResearchSourceModel",
    "InstitutionModel",
    "ResearchWorkModel",
    "ResearchWorkAuthorModel",
    "ResearchWorkInstitutionModel",
    "ResearchWorkTopicModel",
    # Adaptive Signals (Phase 5.5)
    "AdaptivePreferenceSignalModel",
    "AdaptiveSignalDimension",
    "AdaptiveEvidenceState",
    # Personalization Calibration (Phase 5.6)
    "PersonalizationCalibrationModel",
    "RecommendationFeedbackAttributionModel",
    "CalibrationState",
    "AttributionConfidence",
    "FeedbackOutcomeType",
    # Personalization Quality & Contextual Adaptation (Phase 5.7)
    "PersonalizationQualityEvaluationModel",
    "PersonalizationContextualAdaptationModel",
    "QualityEvaluationState",
    "ContextualFallbackLevel",
]



