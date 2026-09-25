import type {
  OpportunityDeadline,
  OpportunityListResponse,
  OpportunityRead,
  RiskExplanation,
} from "../types/opportunity";
import type {
  OpportunityMatchParams,
  OpportunityMatchResponse,
  ResearchSearchParams,
  ResearchSearchResponse,
  SimilarResearchParams,
  SimilarResearchResponse,
} from "../types/discovery";
import type {
  WorkspaceFilterParams,
  WorkspaceItem,
  WorkspaceItemCreatePayload,
  WorkspaceItemUpdatePayload,
  WorkspaceListResponse,
  WorkspaceStatus,
  WorkspaceSummaryResponse,
} from "../types/workspace";
import type {
  DocumentFilterParams,
  DocumentStatus,
  DocumentType,
  ResearchSubmission,
  ResearchSubmissionCreate,
  ResearchSubmissionDocument,
  ResearchSubmissionListResponse,
  ResearchSubmissionUpdate,
  SubmissionDocumentCreate,
  SubmissionDocumentListResponse,
  SubmissionDocumentUpdate,
  SubmissionDocumentVersion,
  SubmissionHistoryEvent,
  SubmissionHistoryResponse,
  SubmissionReadinessResponse,
  SubmissionStatus,
  SubmissionStatusTransition,
  SubmissionSummaryResponse,
  SubmissionType,
} from "../types/submission";
import type {
  CalendarCreatePayload,
  CalendarEventCreatePayload,
  CalendarEventFilterParams,
  CalendarEventUpdatePayload,
  CalendarUpdatePayload,
  OpportunityProjectPayload,
  OpportunityProjectResponse,
  ResearchCalendar,
  ResearchCalendarEvent,
  ResearcherCalendarViewResponse,
} from "../types/calendar";
import type {
  NotificationItem,
  NotificationListResponse,
  NotificationPreference,
  NotificationPreferenceUpdate,
  NotificationType,
  NotificationUnreadCountResponse,
  ReminderRule,
  ReminderRuleCreate,
  ReminderRuleListResponse,
  ReminderRuleUpdate,
  ReminderRunSummary,
} from "../types/notification";
import type {
  TaskFilterParams,
  WorkspaceActivity,
  WorkspaceActivityListResponse,
  WorkspaceCommentCreatePayload,
  WorkspaceInvitation,
  WorkspaceInvitationCreatePayload,
  WorkspaceInvitationCreateResponse,
  WorkspaceInvitationListResponse,
  WorkspaceMember,
  WorkspaceMemberAddPayload,
  WorkspaceMemberListResponse,
  WorkspaceMemberRoleUpdatePayload,
  WorkspaceRole,
  WorkspaceTask,
  WorkspaceTaskAssignPayload,
  WorkspaceTaskCreatePayload,
  WorkspaceTaskListResponse,
  WorkspaceTaskUpdatePayload,
} from "../types/collaboration";
import type {
  UnifiedResearcherContext,
  UnifiedRecommendationResponse,
  UnifiedOpportunityIntelligence,
} from "../types/research_intelligence";
import type {
  PreferencePersonalizationAssessment,
  BatchOpportunityPreferenceMatchResponse,
  PersonalizationAssessment,
  BatchPersonalizationResponse,
  InteractionCreateRequest,
  InteractionResponse,

  OpportunityInteractionHistoryResponse,
  ResearcherInteractionSummaryResponse,
  AdaptivePreferenceSignal,
  AdaptiveSignalsResponse,
  AdaptiveSignalExplanationResponse,
  AdaptiveSignalRecomputeRequest,
  AdaptiveSignalDimension,
  AdaptiveEvidenceState,
  CalibrationState,
  PersonalizationCalibration,
  PersonalizationCalibrationResponse,
  PersonalizationCalibrationDetailResponse,
  CalibrationRecomputeRequest,
  QualityEvaluationState,
  ContextualFallbackLevel,
  PersonalizationQualityEvaluation,
  PersonalizationContextualAdaptation,
  ContextualSummaryItem,
  SignalQualitySummaryItem,
  PersonalizationQualityResponse,
  ContextualAdaptationsResponse,
  SignalQualityResponse,
  QualityRecomputeRequest,
  PersonalizationHealthState,
  GovernanceGateState,
  AdaptationState,
  DriftType,
  EvidenceStrength,
  SignalFreshnessState,
  PreferenceAlignmentState,
  GovernanceEventType,
  SignalDriftItem,
  PersonalizationDriftEvaluation,
  PersonalizationGovernanceEvent,
  PersonalizationHealthResponse,
  PersonalizationDriftResponse,
  PersonalizationGovernanceHistoryResponse,
  GovernanceRecomputeRequest,
  PersonalizationImpact,
  PersonalizationControlEventType,
  ResearcherPersonalizationSettings,
  ResearcherPersonalizationSettingsUpdate,
  PersonalizationControlEvent,
  PersonalizationControlHistoryResponse,
  PersonalizationFactor,
  RecommendationPersonalizationExplanation,
  PersonalizationResetResponse,
} from "../types/personalization";
import type {
  ApplicationCreatePayload,
  ApplicationListResponse,
  ApplicationStatus,
  ApplicationSummaryResponse,
  PostingApplication,
  PostingCreatePayload,
  PostingFilterParams,
  PostingStatus,
  PostingSummaryResponse,
  PostingType,
  PostingUpdatePayload,
  ResearchPosting,
  ResearchPostingListResponse,
} from "../types/posting";
import type {
  DiscoverySettings,
  DiscoverySettingsUpdate,
  CollaborationInterest,
  PeerMatchResponse,
} from "../types/peer";
import { getAuthHeaders } from "./auth";

// NEXT_PUBLIC_API_URL replaces former VITE_API_URL
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  public status: number;
  public detail?: string;

  constructor(status: number, message: string, detail?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_URL}${path}`;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (init?.headers) {
    if (init.headers instanceof Headers) {
      init.headers.forEach((value, key) => {
        headers[key] = value;
      });
    } else if (Array.isArray(init.headers)) {
      init.headers.forEach(([key, value]) => {
        headers[key] = value;
      });
    } else {
      Object.assign(headers, init.headers);
    }
  }

  const authHeaders = getAuthHeaders();
  if (headers["Authorization"] || authHeaders["Authorization"]) {
    // A Bearer token is authoritative in production.  Several legacy wrapper
    // methods still accept a developer user ID, so remove that fallback header
    // whenever either an explicit or stored Bearer token is available.
    delete headers["X-User-ID"];
    if (!headers["Authorization"]) {
      headers["Authorization"] = authHeaders["Authorization"];
    }
  } else if (!headers["X-User-ID"]) {
    Object.assign(headers, authHeaders);
  }

  const response = await fetch(url, {
    ...init,
    headers,
  });

  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`;
    try {
      const errJson = await response.json();
      if (errJson && typeof errJson.detail === "string") {
        detail = errJson.detail;
      }
    } catch {
      // Non-JSON error body fallback
    }

    if (response.status === 429) {
      detail = "Rate limit exceeded (maximum 60 discovery requests/minute). Please slow down and try again shortly.";
    }

    throw new ApiError(response.status, detail, detail);
  }

  if (response.status === 204) {
    return undefined as unknown as T;
  }

  return response.json() as Promise<T>;
}

// ── Legacy Opportunities API ──────────────────────────────────────────────────

export type OpportunityFilters = {
  search?: string;
  opportunity_type?: string;
  status?: string;
  delivery_mode?: string;
  upcoming?: boolean;
  sort?: "newest" | "deadline" | "title";
  page?: number;
  page_size?: number;
};

export async function fetchOpportunities(
  filters: OpportunityFilters = {},
  signal?: AbortSignal
): Promise<OpportunityListResponse> {
  const params = new URLSearchParams();
  if (filters.search) params.set("search", filters.search);
  if (filters.opportunity_type) params.set("opportunity_type", filters.opportunity_type);
  if (filters.status) params.set("status", filters.status);
  if (filters.delivery_mode) params.set("delivery_mode", filters.delivery_mode);
  if (filters.upcoming) params.set("upcoming", "true");
  if (filters.sort) params.set("sort", filters.sort);
  if (filters.page) params.set("page", String(filters.page));
  if (filters.page_size) params.set("page_size", String(filters.page_size));

  const query = params.toString();
  return fetchJson<OpportunityListResponse>(
    `/api/opportunities${query ? `?${query}` : ""}`,
    { signal }
  );
}

export async function fetchOpportunity(
  id: string,
  signal?: AbortSignal
): Promise<OpportunityRead> {
  return fetchJson<OpportunityRead>(`/api/opportunities/${id}`, { signal });
}

/**
 * Fetch deterministic trust & risk explanation for an academic opportunity (Phase 2.6F).
 */
export async function fetchOpportunityRiskExplanation(
  id: string,
  signal?: AbortSignal
): Promise<RiskExplanation> {
  return fetchJson<RiskExplanation>(`/api/opportunities/${id}/risk-explanation`, { signal });
}

/**
 * Fetch canonical deadline intelligence and multi-milestone timeline for an academic opportunity (Phase 2.7F).
 */
export async function fetchOpportunityDeadlines(
  id: string,
  signal?: AbortSignal
): Promise<OpportunityDeadline> {
  return fetchJson<OpportunityDeadline>(`/api/opportunities/${id}/deadlines`, { signal });
}

// ── Phase 2.4 Discovery APIs ──────────────────────────────────────────────────

/**
 * Execute multi-channel hybrid search (semantic + lexical + topic) over research works.
 */
export async function searchResearchWorks(
  params: ResearchSearchParams,
  signal?: AbortSignal
): Promise<ResearchSearchResponse> {
  const searchParams = new URLSearchParams();
  searchParams.set("q", params.q);

  if (params.limit !== undefined) searchParams.set("limit", String(params.limit));
  if (params.offset !== undefined) searchParams.set("offset", String(params.offset));
  if (params.publication_year !== undefined) searchParams.set("publication_year", String(params.publication_year));
  if (params.min_year !== undefined) searchParams.set("min_year", String(params.min_year));
  if (params.max_year !== undefined) searchParams.set("max_year", String(params.max_year));
  if (params.work_type) searchParams.set("work_type", params.work_type);
  if (params.language) searchParams.set("language", params.language);
  if (params.primary_source_id) searchParams.set("primary_source_id", params.primary_source_id);
  if (params.is_oa !== undefined) searchParams.set("is_oa", String(params.is_oa));
  if (params.min_citations !== undefined) searchParams.set("min_citations", String(params.min_citations));
  if (params.ranking_mode) searchParams.set("ranking_mode", params.ranking_mode);
  if (params.explain !== undefined) searchParams.set("explain", String(params.explain));
  if (params.include_query_intelligence !== undefined) {
    searchParams.set("include_query_intelligence", String(params.include_query_intelligence));
  }

  const query = searchParams.toString();
  return fetchJson<ResearchSearchResponse>(
    `/api/v1/discovery/research/search${query ? `?${query}` : ""}`,
    { signal }
  );
}

/**
 * Retrieve research works similar to a specified source work based on semantic embeddings and topic proximity.
 */
export async function getSimilarResearch(
  workId: string,
  params: SimilarResearchParams = {},
  signal?: AbortSignal
): Promise<SimilarResearchResponse> {
  const searchParams = new URLSearchParams();
  if (params.limit !== undefined) searchParams.set("limit", String(params.limit));
  if (params.offset !== undefined) searchParams.set("offset", String(params.offset));
  if (params.publication_year !== undefined) searchParams.set("publication_year", String(params.publication_year));
  if (params.min_year !== undefined) searchParams.set("min_year", String(params.min_year));
  if (params.max_year !== undefined) searchParams.set("max_year", String(params.max_year));
  if (params.work_type) searchParams.set("work_type", params.work_type);
  if (params.language) searchParams.set("language", params.language);
  if (params.primary_source_id) searchParams.set("primary_source_id", params.primary_source_id);
  if (params.is_oa !== undefined) searchParams.set("is_oa", String(params.is_oa));
  if (params.min_citations !== undefined) searchParams.set("min_citations", String(params.min_citations));
  if (params.ranking_mode) searchParams.set("ranking_mode", params.ranking_mode);
  if (params.explain !== undefined) searchParams.set("explain", String(params.explain));
  if (params.require_embedding !== undefined) searchParams.set("require_embedding", String(params.require_embedding));

  const query = searchParams.toString();
  return fetchJson<SimilarResearchResponse>(
    `/api/v1/discovery/research/${workId}/similar${query ? `?${query}` : ""}`,
    { signal }
  );
}

/**
 * Match and rank relevant academic opportunities for a given research work.
 */
export async function matchOpportunitiesForResearch(
  workId: string,
  params: OpportunityMatchParams = {},
  signal?: AbortSignal
): Promise<OpportunityMatchResponse> {
  const searchParams = new URLSearchParams();
  if (params.limit !== undefined) searchParams.set("limit", String(params.limit));
  if (params.offset !== undefined) searchParams.set("offset", String(params.offset));
  if (params.opportunity_type) searchParams.set("opportunity_type", params.opportunity_type);
  if (params.status) searchParams.set("status", params.status);
  if (params.delivery_mode) searchParams.set("delivery_mode", params.delivery_mode);
  if (params.source_id) searchParams.set("source_id", params.source_id);
  if (params.upcoming_only !== undefined) searchParams.set("upcoming_only", String(params.upcoming_only));
  if (params.submission_deadline_after) searchParams.set("submission_deadline_after", params.submission_deadline_after);
  if (params.max_apc_usd !== undefined) searchParams.set("max_apc_usd", String(params.max_apc_usd));
  if (params.require_known_apc !== undefined) searchParams.set("require_known_apc", String(params.require_known_apc));
  if (params.location) searchParams.set("location", params.location);
  if (params.ranking_mode) searchParams.set("ranking_mode", params.ranking_mode);
  if (params.explain !== undefined) searchParams.set("explain", String(params.explain));
  if (params.require_embedding !== undefined) searchParams.set("require_embedding", String(params.require_embedding));

  const query = searchParams.toString();
  return fetchJson<OpportunityMatchResponse>(
    `/api/v1/discovery/research/${workId}/opportunities${query ? `?${query}` : ""}`,
    { signal }
  );
}

// ── Researcher Profile API (Phase 3.1) ────────────────────────────────────────

import type {
  BehavioralSignal,
  BulkPreferencesUpdatePayload,
  FeedbackCreatePayload,
  FeedbackItem,
  FeedbackListResponse,
  FeedbackSummaryResponse,
  FeedbackType,
  PersonalizationSummaryResponse,
  PersonalizedCandidateSetResponse,
  PersonalizedRankingResponse,
  ProfileCompleteness,
  RecommendationEvaluationResponse,
  RecommendationExplanation,
  RecommendationHistoryResponse,
  RecommendationSnapshotDetail,
  ResearcherIntelligenceResponse,
  ResearcherInterestItem,
  ResearcherPreferenceCreatePayload,
  ResearcherPreferenceIntelligenceResponse,
  ResearcherPreferenceItem,
  ResearcherPreferenceUpdatePayload,
  ResearcherProfile,
  ResearcherProfileCreatePayload,
  ResearcherProfileUpdatePayload,
  ResearcherWorkSummary,
  StructuredPreferencesResponse,
} from "../types/researcher";



export async function fetchResearcherProfile(
  id: string,
  signal?: AbortSignal
): Promise<ResearcherProfile> {
  return fetchJson<ResearcherProfile>(`/api/v1/researchers/${id}`, { signal });
}

export async function createResearcherProfile(
  payload: ResearcherProfileCreatePayload,
  signal?: AbortSignal
): Promise<ResearcherProfile> {
  return fetchJson<ResearcherProfile>("/api/v1/researchers", {
    method: "POST",
    body: JSON.stringify(payload),
    signal,
  });
}

export async function updateResearcherProfile(
  id: string,
  payload: ResearcherProfileUpdatePayload,
  signal?: AbortSignal
): Promise<ResearcherProfile> {
  return fetchJson<ResearcherProfile>(`/api/v1/researchers/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
    signal,
  });
}

export async function fetchResearcherWorks(
  id: string,
  limit: number = 20,
  offset: number = 0,
  signal?: AbortSignal
): Promise<ResearcherWorkSummary[]> {
  return fetchJson<ResearcherWorkSummary[]>(
    `/api/v1/researchers/${id}/works?limit=${limit}&offset=${offset}`,
    { signal }
  );
}

export async function fetchProfileCompleteness(
  id: string,
  signal?: AbortSignal
): Promise<ProfileCompleteness> {
  return fetchJson<ProfileCompleteness>(
    `/api/v1/researchers/${id}/completeness`,
    { signal }
  );
}

export async function fetchResearcherIntelligence(
  id: string,
  refresh: boolean = false,
  signal?: AbortSignal
): Promise<ResearcherIntelligenceResponse> {
  return fetchJson<ResearcherIntelligenceResponse>(
    `/api/v1/researchers/${id}/research-intelligence?refresh=${refresh}`,
    { signal }
  );
}

export async function fetchResearcherInterests(
  id: string,
  signal?: AbortSignal
): Promise<ResearcherInterestItem[]> {
  return fetchJson<ResearcherInterestItem[]>(
    `/api/v1/researchers/${id}/interests`,
    { signal }
  );
}

export async function fetchResearcherExpertise(
  id: string,
  signal?: AbortSignal
): Promise<ResearcherInterestItem[]> {
  return fetchJson<ResearcherInterestItem[]>(
    `/api/v1/researchers/${id}/expertise`,
    { signal }
  );
}

// ── Phase 3.3 — Personal Preference Intelligence API ────────────────────────

export async function fetchResearcherPreferenceIntelligence(
  id: string,
  signal?: AbortSignal
): Promise<ResearcherPreferenceIntelligenceResponse> {
  return fetchJson<ResearcherPreferenceIntelligenceResponse>(
    `/api/v1/researchers/${id}/preference-intelligence`,
    { signal }
  );
}

export async function fetchResearcherPreferences(
  id: string,
  category?: string,
  source?: string,
  isActive?: boolean,
  preferenceType?: string,
  signal?: AbortSignal
): Promise<ResearcherPreferenceItem[]> {
  const params = new URLSearchParams();
  if (category) params.set("category", category);
  if (source) params.set("source", source);
  if (isActive !== undefined) params.set("is_active", String(isActive));
  if (preferenceType) params.set("preference_type", preferenceType);
  const query = params.toString();
  return fetchJson<ResearcherPreferenceItem[]>(
    `/api/v1/researchers/${id}/preferences${query ? `?${query}` : ""}`,
    { signal }
  );
}

export async function fetchStructuredResearcherPreferences(
  id: string,
  signal?: AbortSignal
): Promise<StructuredPreferencesResponse> {
  return fetchJson<StructuredPreferencesResponse>(
    `/api/v1/researchers/${id}/preferences/structured`,
    { signal }
  );
}

export async function createResearcherPreference(
  id: string,
  payload: ResearcherPreferenceCreatePayload,
  userId?: string,
  signal?: AbortSignal
): Promise<ResearcherPreferenceItem> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }
  return fetchJson<ResearcherPreferenceItem>(
    `/api/v1/researchers/${id}/preferences`,
    {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
      signal,
    }
  );
}

export async function bulkUpdateResearcherPreferences(
  id: string,
  payload: BulkPreferencesUpdatePayload,
  userId?: string,
  signal?: AbortSignal
): Promise<ResearcherPreferenceItem[]> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }
  return fetchJson<ResearcherPreferenceItem[]>(
    `/api/v1/researchers/${id}/preferences`,
    {
      method: "PUT",
      headers,
      body: JSON.stringify(payload),
      signal,
    }
  );
}

export async function updateResearcherPreference(
  id: string,
  preferenceId: string,
  payload: ResearcherPreferenceUpdatePayload,
  userId?: string,
  signal?: AbortSignal
): Promise<ResearcherPreferenceItem> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }
  return fetchJson<ResearcherPreferenceItem>(
    `/api/v1/researchers/${id}/preferences/${preferenceId}`,
    {
      method: "PATCH",
      headers,
      body: JSON.stringify(payload),
      signal,
    }
  );
}

export async function deleteResearcherPreference(
  id: string,
  preferenceId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<{ deleted: boolean; preference_id: string }> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }
  return fetchJson<{ deleted: boolean; preference_id: string }>(
    `/api/v1/researchers/${id}/preferences/${preferenceId}`,
    {
      method: "DELETE",
      headers,
      signal,
    }
  );
}

// ── Phase 3.4 — Personalized Candidate Generation API ────────────────────────

export async function fetchPersonalizedCandidates(
  id: string,
  options?: {
    limit?: number;
    includeInferred?: boolean;
    includeExpertise?: boolean;
    includeFallback?: boolean;
  },
  userId?: string,
  signal?: AbortSignal
): Promise<PersonalizedCandidateSetResponse> {
  const params = new URLSearchParams();
  if (options?.limit) params.set("limit", String(options.limit));
  if (options?.includeInferred !== undefined)
    params.set("include_inferred", String(options.includeInferred));
  if (options?.includeExpertise !== undefined)
    params.set("include_expertise", String(options.includeExpertise));
  if (options?.includeFallback !== undefined)
    params.set("include_fallback", String(options.includeFallback));

  const query = params.toString();
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }

  return fetchJson<PersonalizedCandidateSetResponse>(
    `/api/v1/researchers/${id}/personalized-candidates${query ? `?${query}` : ""}`,
    {
      headers,
      signal,
    }
  );
}

// ── Phase 3.5 — Personalization Ranking API ───────────────────────────────────

export async function fetchPersonalizedRecommendations(
  id: string,
  options?: {
    limit?: number;
    offset?: number;
    includeInferred?: boolean;
    includeExpertise?: boolean;
    includeFallback?: boolean;
    enablePersonalization?: boolean;
    includeAblation?: boolean;
    opportunityType?: string;
    deliveryMode?: string;
  },
  userId?: string,
  signal?: AbortSignal
): Promise<PersonalizedRankingResponse> {
  const params = new URLSearchParams();
  if (options?.limit) params.set("limit", String(options.limit));
  if (options?.offset) params.set("offset", String(options.offset));
  if (options?.includeInferred !== undefined)
    params.set("include_inferred", String(options.includeInferred));
  if (options?.includeExpertise !== undefined)
    params.set("include_expertise", String(options.includeExpertise));
  if (options?.includeFallback !== undefined)
    params.set("include_fallback", String(options.includeFallback));
  if (options?.enablePersonalization !== undefined)
    params.set("enable_personalization", String(options.enablePersonalization));
  if (options?.includeAblation !== undefined)
    params.set("include_ablation", String(options.includeAblation));
  if (options?.opportunityType)
    params.set("opportunity_type", options.opportunityType);
  if (options?.deliveryMode)
    params.set("delivery_mode", options.deliveryMode);

  const query = params.toString();
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }

  return fetchJson<PersonalizedRankingResponse>(
    `/api/v1/researchers/${id}/personalized-recommendations${query ? `?${query}` : ""}`,
    {
      headers,
      signal,
    }
  );
}
 
// ── Phase 3.6 — Feedback & Recommendation Learning API ────────────────────────

export async function recordRecommendationFeedback(
  id: string,
  payload: FeedbackCreatePayload,
  userId?: string,
  signal?: AbortSignal
): Promise<FeedbackItem> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }
  return fetchJson<FeedbackItem>(
    `/api/v1/researchers/${id}/feedback`,
    {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
      signal,
    }
  );
}

export async function fetchRecommendationFeedbackHistory(
  id: string,
  options?: {
    limit?: number;
    offset?: number;
    feedbackType?: string;
    opportunityId?: string;
  },
  userId?: string,
  signal?: AbortSignal
): Promise<FeedbackListResponse> {
  const params = new URLSearchParams();
  if (options?.limit) params.set("limit", String(options.limit));
  if (options?.offset) params.set("offset", String(options.offset));
  if (options?.feedbackType) params.set("feedback_type", options.feedbackType);
  if (options?.opportunityId) params.set("opportunity_id", options.opportunityId);

  const query = params.toString();
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }

  return fetchJson<FeedbackListResponse>(
    `/api/v1/researchers/${id}/feedback${query ? `?${query}` : ""}`,
    {
      headers,
      signal,
    }
  );
}

export async function deleteRecommendationFeedback(
  id: string,
  feedbackId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<{ deleted: boolean; feedback_id: string }> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }
  return fetchJson<{ deleted: boolean; feedback_id: string }>(
    `/api/v1/researchers/${id}/feedback/${feedbackId}`,
    {
      method: "DELETE",
      headers,
      signal,
    }
  );
}

export async function fetchFeedbackSummary(
  id: string,
  userId?: string,
  signal?: AbortSignal
): Promise<FeedbackSummaryResponse> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }
  return fetchJson<FeedbackSummaryResponse>(
    `/api/v1/researchers/${id}/feedback/summary`,
    {
      headers,
      signal,
    }
  );
}

export async function fetchBehavioralSignals(
  id: string,
  userId?: string,
  signal?: AbortSignal
): Promise<{ researcher_id: string; signals: BehavioralSignal[] }> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }
  return fetchJson<{ researcher_id: string; signals: BehavioralSignal[] }>(
    `/api/v1/researchers/${id}/feedback/signals`,
    {
      headers,
      signal,
    }
  );
}

// ── Phase 3.7 — Recommendation History & Evaluation API ───────────────────────

export async function fetchRecommendationHistory(
  id: string,
  options?: {
    limit?: number;
    offset?: number;
    rankingVersion?: string;
    fromDate?: string;
    toDate?: string;
  },
  userId?: string,
  signal?: AbortSignal
): Promise<RecommendationHistoryResponse> {
  const params = new URLSearchParams();
  if (options?.limit) params.set("limit", String(options.limit));
  if (options?.offset) params.set("offset", String(options.offset));
  if (options?.rankingVersion) params.set("ranking_version", options.rankingVersion);
  if (options?.fromDate) params.set("from_date", options.fromDate);
  if (options?.toDate) params.set("to_date", options.toDate);

  const query = params.toString();
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }

  return fetchJson<RecommendationHistoryResponse>(
    `/api/v1/researchers/${id}/recommendation-history${query ? `?${query}` : ""}`,
    {
      headers,
      signal,
    }
  );
}

export async function fetchRecommendationSnapshotDetail(
  id: string,
  snapshotId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<RecommendationSnapshotDetail> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }

  return fetchJson<RecommendationSnapshotDetail>(
    `/api/v1/researchers/${id}/recommendation-history/${snapshotId}`,
    {
      headers,
      signal,
    }
  );
}

export async function fetchRecommendationEvaluation(
  id: string,
  options?: {
    rankingVersion?: string;
    fromDate?: string;
    toDate?: string;
    includeComparison?: boolean;
  },
  userId?: string,
  signal?: AbortSignal
): Promise<RecommendationEvaluationResponse> {
  const params = new URLSearchParams();
  if (options?.rankingVersion) params.set("ranking_version", options.rankingVersion);
  if (options?.fromDate) params.set("from_date", options.fromDate);
  if (options?.toDate) params.set("to_date", options.toDate);
  if (options?.includeComparison !== undefined)
    params.set("include_comparison", String(options.includeComparison));

  const query = params.toString();
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }

  return fetchJson<RecommendationEvaluationResponse>(
    `/api/v1/researchers/${id}/recommendation-evaluation${query ? `?${query}` : ""}`,
    {
      headers,
      signal,
    }
  );
}

// ── Phase 3.8 — Personalization Explainability & Summary API ─────────────────

export async function fetchPersonalizationSummary(
  id: string,
  userId?: string,
  signal?: AbortSignal
): Promise<PersonalizationSummaryResponse> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }

  return fetchJson<PersonalizationSummaryResponse>(
    `/api/v1/researchers/${id}/personalization-summary`,
    {
      headers,
      signal,
    }
  );
}

export async function fetchRecommendationExplanation(
  id: string,
  opportunityId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<RecommendationExplanation> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }

  return fetchJson<RecommendationExplanation>(
    `/api/v1/researchers/${id}/personalized-recommendations/${opportunityId}/explanation`,
    {
      headers,
      signal,
    }
  );
}

export async function fetchHistoricalRecommendationExplanation(
  id: string,
  snapshotId: string,
  opportunityId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<RecommendationExplanation> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }

  return fetchJson<RecommendationExplanation>(
    `/api/v1/researchers/${id}/recommendation-history/${snapshotId}/items/${opportunityId}/explanation`,
    {
      headers,
      signal,
    }
  );
}

// ── Phase 4.1 Opportunity Workspace API ──────────────────────────────────────

export async function fetchWorkspaceItems(
  filters: WorkspaceFilterParams = {},
  userId?: string,
  signal?: AbortSignal
): Promise<WorkspaceListResponse> {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.priority) params.set("priority", filters.priority);
  if (filters.tag) params.set("tag", filters.tag);
  if (filters.search) params.set("search", filters.search);
  if (filters.include_archived) params.set("include_archived", "true");
  if (filters.sort_by) params.set("sort_by", filters.sort_by);
  if (filters.sort_order) params.set("sort_order", filters.sort_order);
  if (filters.limit) params.set("limit", String(filters.limit));
  if (filters.offset) params.set("offset", String(filters.offset));

  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }

  const query = params.toString();
  return fetchJson<WorkspaceListResponse>(
    `/api/v1/workspace${query ? `?${query}` : ""}`,
    {
      headers,
      signal,
    }
  );
}

export async function fetchWorkspaceSummary(
  userId?: string,
  signal?: AbortSignal
): Promise<WorkspaceSummaryResponse> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }

  return fetchJson<WorkspaceSummaryResponse>("/api/v1/workspace/summary", {
    headers,
    signal,
  });
}

export async function fetchWorkspaceItem(
  itemId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<WorkspaceItem> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }

  return fetchJson<WorkspaceItem>(`/api/v1/workspace/${itemId}`, {
    headers,
    signal,
  });
}

export async function addOpportunityToWorkspace(
  payload: WorkspaceItemCreatePayload,
  userId?: string,
  signal?: AbortSignal
): Promise<WorkspaceItem> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }

  return fetchJson<WorkspaceItem>("/api/v1/workspace", {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
    signal,
  });
}

export async function updateWorkspaceItem(
  itemId: string,
  payload: WorkspaceItemUpdatePayload,
  userId?: string,
  signal?: AbortSignal
): Promise<WorkspaceItem> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }

  return fetchJson<WorkspaceItem>(`/api/v1/workspace/${itemId}`, {
    method: "PATCH",
    headers,
    body: JSON.stringify(payload),
    signal,
  });
}

export async function transitionWorkspaceStatus(
  itemId: string,
  targetStatus: WorkspaceStatus,
  notes?: string,
  userId?: string,
  signal?: AbortSignal
): Promise<WorkspaceItem> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }

  return fetchJson<WorkspaceItem>(`/api/v1/workspace/${itemId}/transition`, {
    method: "POST",
    headers,
    body: JSON.stringify({ target_status: targetStatus, notes }),
    signal,
  });
}

export async function archiveWorkspaceItem(
  itemId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<WorkspaceItem> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }

  return fetchJson<WorkspaceItem>(`/api/v1/workspace/${itemId}/archive`, {
    method: "POST",
    headers,
    signal,
  });
}

export async function unarchiveWorkspaceItem(
  itemId: string,
  targetStatus: WorkspaceStatus = "SAVED",
  userId?: string,
  signal?: AbortSignal
): Promise<WorkspaceItem> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }

  return fetchJson<WorkspaceItem>(
    `/api/v1/workspace/${itemId}/unarchive?target_status=${targetStatus}`,
    {
      method: "POST",
      headers,
      signal,
    }
  );
}

export async function removeWorkspaceItem(
  itemId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<void> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }

  const url = `${API_URL}/api/v1/workspace/${itemId}`;
  const response = await fetch(url, {
    method: "DELETE",
    headers,
    signal,
  });

  if (!response.ok && response.status !== 204) {
    let detail = `Delete failed with status ${response.status}`;
    try {
      const errJson = await response.json();
      if (errJson && typeof errJson.detail === "string") {
        detail = errJson.detail;
      }
    } catch {}
    throw new ApiError(response.status, detail, detail);
  }
}

// ── Phase 4.2 — Research Submission Management & Tracking API ───────────────

export interface SubmissionFilterParams {
  status?: SubmissionStatus;
  submission_type?: SubmissionType;
  workspace_item_id?: string;
  search?: string;
  sort_by?: string;
  sort_order?: "asc" | "desc";
  limit?: number;
  offset?: number;
}

export async function fetchSubmissions(
  filters: SubmissionFilterParams = {},
  userId?: string,
  signal?: AbortSignal
): Promise<ResearchSubmissionListResponse> {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.submission_type) params.set("submission_type", filters.submission_type);
  if (filters.workspace_item_id) params.set("workspace_item_id", filters.workspace_item_id);
  if (filters.search) params.set("search", filters.search);
  if (filters.sort_by) params.set("sort_by", filters.sort_by);
  if (filters.sort_order) params.set("sort_order", filters.sort_order);
  if (filters.limit) params.set("limit", String(filters.limit));
  if (filters.offset) params.set("offset", String(filters.offset));

  const qs = params.toString();
  const endpoint = qs ? `/api/v1/submissions?${qs}` : "/api/v1/submissions";

  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }

  return fetchJson<ResearchSubmissionListResponse>(endpoint, { headers, signal });
}

export async function fetchSubmissionSummary(
  userId?: string,
  signal?: AbortSignal
): Promise<SubmissionSummaryResponse> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }
  return fetchJson<SubmissionSummaryResponse>("/api/v1/submissions/summary", {
    headers,
    signal,
  });
}

export async function fetchSubmission(
  submissionId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<ResearchSubmission> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }
  return fetchJson<ResearchSubmission>(`/api/v1/submissions/${submissionId}`, {
    headers,
    signal,
  });
}

export async function fetchWorkspaceSubmissions(
  workspaceItemId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<ResearchSubmissionListResponse> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }
  return fetchJson<ResearchSubmissionListResponse>(
    `/api/v1/workspace/${workspaceItemId}/submissions`,
    {
      headers,
      signal,
    }
  );
}

export async function createSubmission(
  payload: ResearchSubmissionCreate,
  userId?: string,
  signal?: AbortSignal
): Promise<ResearchSubmission> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }
  return fetchJson<ResearchSubmission>("/api/v1/submissions", {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
    signal,
  });
}

export async function updateSubmission(
  submissionId: string,
  payload: ResearchSubmissionUpdate,
  userId?: string,
  signal?: AbortSignal
): Promise<ResearchSubmission> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }
  return fetchJson<ResearchSubmission>(`/api/v1/submissions/${submissionId}`, {
    method: "PATCH",
    headers,
    body: JSON.stringify(payload),
    signal,
  });
}

export async function transitionSubmissionStatus(
  submissionId: string,
  payload: SubmissionStatusTransition,
  userId?: string,
  signal?: AbortSignal
): Promise<ResearchSubmission> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }
  return fetchJson<ResearchSubmission>(
    `/api/v1/submissions/${submissionId}/transition`,
    {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
      signal,
    }
  );
}

export async function deleteSubmission(
  submissionId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<void> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }
  const url = `${API_URL}/api/v1/submissions/${submissionId}`;
  const response = await fetch(url, {
    method: "DELETE",
    headers,
    signal,
  });

  if (!response.ok && response.status !== 204) {
    let detail = `Delete failed with status ${response.status}`;
    try {
      const errJson = await response.json();
      if (errJson && typeof errJson.detail === "string") {
        detail = errJson.detail;
      }
    } catch {}
    throw new ApiError(response.status, detail, detail);
  }
}

// ── Phase 4.3 — Submission Documents, Versions, Readiness & History API ─────

export async function fetchSubmissionDocuments(
  submissionId: string,
  filters: DocumentFilterParams = {},
  userId?: string,
  signal?: AbortSignal
): Promise<SubmissionDocumentListResponse> {
  const params = new URLSearchParams();
  if (filters.document_type) params.set("document_type", filters.document_type);
  if (filters.status) params.set("status", filters.status);
  if (filters.is_required !== undefined) params.set("is_required", String(filters.is_required));
  if (filters.limit) params.set("limit", String(filters.limit));
  if (filters.offset) params.set("offset", String(filters.offset));

  const qs = params.toString();
  const endpoint = qs
    ? `/api/v1/submissions/${submissionId}/documents?${qs}`
    : `/api/v1/submissions/${submissionId}/documents`;

  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }

  return fetchJson<SubmissionDocumentListResponse>(endpoint, { headers, signal });
}

export async function fetchSubmissionDocument(
  submissionId: string,
  documentId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<ResearchSubmissionDocument> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }
  return fetchJson<ResearchSubmissionDocument>(
    `/api/v1/submissions/${submissionId}/documents/${documentId}`,
    { headers, signal }
  );
}

export async function createSubmissionDocument(
  submissionId: string,
  payload: SubmissionDocumentCreate,
  userId?: string,
  signal?: AbortSignal
): Promise<ResearchSubmissionDocument> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }
  return fetchJson<ResearchSubmissionDocument>(
    `/api/v1/submissions/${submissionId}/documents`,
    {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
      signal,
    }
  );
}

export async function updateSubmissionDocument(
  submissionId: string,
  documentId: string,
  payload: SubmissionDocumentUpdate,
  userId?: string,
  signal?: AbortSignal
): Promise<ResearchSubmissionDocument> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }
  return fetchJson<ResearchSubmissionDocument>(
    `/api/v1/submissions/${submissionId}/documents/${documentId}`,
    {
      method: "PATCH",
      headers,
      body: JSON.stringify(payload),
      signal,
    }
  );
}

export async function deleteSubmissionDocument(
  submissionId: string,
  documentId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<void> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }
  const url = `${API_URL}/api/v1/submissions/${submissionId}/documents/${documentId}`;
  const response = await fetch(url, {
    method: "DELETE",
    headers,
    signal,
  });

  if (!response.ok && response.status !== 204) {
    let detail = `Delete failed with status ${response.status}`;
    try {
      const errJson = await response.json();
      if (errJson && typeof errJson.detail === "string") {
        detail = errJson.detail;
      }
    } catch {}
    throw new ApiError(response.status, detail, detail);
  }
}

export async function fetchDocumentVersions(
  submissionId: string,
  documentId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<SubmissionDocumentVersion[]> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }
  return fetchJson<SubmissionDocumentVersion[]>(
    `/api/v1/submissions/${submissionId}/documents/${documentId}/versions`,
    { headers, signal }
  );
}

export async function fetchSubmissionReadiness(
  submissionId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<SubmissionReadinessResponse> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }
  return fetchJson<SubmissionReadinessResponse>(
    `/api/v1/submissions/${submissionId}/readiness`,
    { headers, signal }
  );
}

export async function fetchSubmissionHistory(
  submissionId: string,
  options: { limit?: number; offset?: number } = {},
  userId?: string,
  signal?: AbortSignal
): Promise<SubmissionHistoryResponse> {
  const params = new URLSearchParams();
  if (options.limit) params.set("limit", String(options.limit));
  if (options.offset) params.set("offset", String(options.offset));

  const qs = params.toString();
  const endpoint = qs
    ? `/api/v1/submissions/${submissionId}/history?${qs}`
    : `/api/v1/submissions/${submissionId}/history`;

  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }

  return fetchJson<SubmissionHistoryResponse>(endpoint, { headers, signal });
}

// ── Phase 4.4 — Research Calendar & Visual Planning API ──────────────────────────

export async function fetchDefaultCalendar(
  userId?: string,
  signal?: AbortSignal
): Promise<ResearchCalendar> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<ResearchCalendar>("/api/v1/calendar/default", { headers, signal });
}

export async function fetchCalendars(
  userId?: string,
  signal?: AbortSignal
): Promise<{ calendars: ResearchCalendar[]; total: number }> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<{ calendars: ResearchCalendar[]; total: number }>("/api/v1/calendar", {
    headers,
    signal,
  });
}

export async function createCalendar(
  payload: CalendarCreatePayload,
  userId?: string,
  signal?: AbortSignal
): Promise<ResearchCalendar> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<ResearchCalendar>("/api/v1/calendar", {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
    signal,
  });
}

export async function fetchCalendar(
  calendarId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<ResearchCalendar> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<ResearchCalendar>(`/api/v1/calendar/${calendarId}`, { headers, signal });
}

export async function updateCalendar(
  calendarId: string,
  payload: CalendarUpdatePayload,
  userId?: string,
  signal?: AbortSignal
): Promise<ResearchCalendar> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<ResearchCalendar>(`/api/v1/calendar/${calendarId}`, {
    method: "PATCH",
    headers,
    body: JSON.stringify(payload),
    signal,
  });
}

export async function fetchCalendarEvents(
  calendarId: string,
  filters: CalendarEventFilterParams = {},
  userId?: string,
  signal?: AbortSignal
): Promise<{ events: ResearchCalendarEvent[]; total: number }> {
  const params = new URLSearchParams();
  if (filters.start_date) params.set("start_date", filters.start_date);
  if (filters.end_date) params.set("end_date", filters.end_date);
  if (filters.event_type) params.set("event_type", filters.event_type);
  if (filters.opportunity_id) params.set("opportunity_id", filters.opportunity_id);
  if (filters.submission_id) params.set("submission_id", filters.submission_id);

  const qs = params.toString();
  const endpoint = qs
    ? `/api/v1/calendar/${calendarId}/events?${qs}`
    : `/api/v1/calendar/${calendarId}/events`;

  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;

  return fetchJson<{ events: ResearchCalendarEvent[]; total: number }>(endpoint, {
    headers,
    signal,
  });
}

export async function createCalendarEvent(
  calendarId: string,
  payload: CalendarEventCreatePayload,
  userId?: string,
  signal?: AbortSignal
): Promise<ResearchCalendarEvent> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<ResearchCalendarEvent>(`/api/v1/calendar/${calendarId}/events`, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
    signal,
  });
}

export async function updateCalendarEvent(
  calendarId: string,
  eventId: string,
  payload: CalendarEventUpdatePayload,
  userId?: string,
  signal?: AbortSignal
): Promise<ResearchCalendarEvent> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<ResearchCalendarEvent>(`/api/v1/calendar/${calendarId}/events/${eventId}`, {
    method: "PATCH",
    headers,
    body: JSON.stringify(payload),
    signal,
  });
}

export async function deleteCalendarEvent(
  calendarId: string,
  eventId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<{ message: string }> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<{ message: string }>(`/api/v1/calendar/${calendarId}/events/${eventId}`, {
    method: "DELETE",
    headers,
    signal,
  });
}

export async function projectOpportunityToCalendar(
  calendarId: string,
  payload: OpportunityProjectPayload,
  userId?: string,
  signal?: AbortSignal
): Promise<OpportunityProjectResponse> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  const q = new URLSearchParams();
  if (payload.submission_id) q.set("submission_id", payload.submission_id);
  const queryStr = q.toString() ? `?${q.toString()}` : "";
  return fetchJson<OpportunityProjectResponse>(
    `/api/v1/calendar/${calendarId}/opportunities/${payload.opportunity_id}/project${queryStr}`,
    {
      method: "POST",
      headers,
      signal,
    }
  );
}

export async function fetchResearcherCalendar(
  researcherId: string,
  filters: CalendarEventFilterParams = {},
  userId?: string,
  signal?: AbortSignal
): Promise<ResearcherCalendarViewResponse> {
  const params = new URLSearchParams();
  if (filters.start_date) params.set("start_date", filters.start_date);
  if (filters.end_date) params.set("end_date", filters.end_date);
  if (filters.event_type) params.set("event_type", filters.event_type);
  if (filters.opportunity_id) params.set("opportunity_id", filters.opportunity_id);
  if (filters.submission_id) params.set("submission_id", filters.submission_id);

  const qs = params.toString();
  const endpoint = qs
    ? `/api/v1/researchers/${researcherId}/calendar?${qs}`
    : `/api/v1/researchers/${researcherId}/calendar`;

  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;

  return fetchJson<ResearcherCalendarViewResponse>(endpoint, { headers, signal });
}

export function getCalendarExportUrl(calendarId: string, userId?: string): string {
  const base = `${API_URL}/api/v1/calendar/${calendarId}/export.ics`;
  if (userId) {
    return `${base}?user_id=${encodeURIComponent(userId)}`;
  }
  return base;
}

export function getResearcherCalendarExportUrl(researcherId: string, userId?: string): string {
  const base = `${API_URL}/api/v1/researchers/${researcherId}/calendar.ics`;
  if (userId) {
    return `${base}?user_id=${encodeURIComponent(userId)}`;
  }
  return base;
}

// ── Phase 4.5 — Deadline Reminders & Notifications API ───────────────────────

export async function fetchNotifications(
  filters?: {
    unreadOnly?: boolean;
    notificationType?: NotificationType;
    limit?: number;
    offset?: number;
  },
  userId?: string,
  signal?: AbortSignal
): Promise<NotificationListResponse> {
  const params = new URLSearchParams();
  if (filters?.unreadOnly !== undefined) params.set("unread_only", String(filters.unreadOnly));
  if (filters?.notificationType) params.set("notification_type", filters.notificationType);
  if (filters?.limit) params.set("limit", String(filters.limit));
  if (filters?.offset) params.set("offset", String(filters.offset));

  const qs = params.toString();
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;

  return fetchJson<NotificationListResponse>(
    `/api/v1/notifications${qs ? `?${qs}` : ""}`,
    { headers, signal }
  );
}

export async function fetchNotificationUnreadCount(
  userId?: string,
  signal?: AbortSignal
): Promise<NotificationUnreadCountResponse> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<NotificationUnreadCountResponse>(
    `/api/v1/notifications/unread-count`,
    { headers, signal }
  );
}

export async function markNotificationAsRead(
  notificationId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<NotificationItem> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<NotificationItem>(
    `/api/v1/notifications/${notificationId}/read`,
    { method: "POST", headers, signal }
  );
}

export async function markAllNotificationsAsRead(
  userId?: string,
  signal?: AbortSignal
): Promise<{ marked_read_count: number }> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<{ marked_read_count: number }>(
    `/api/v1/notifications/read-all`,
    { method: "POST", headers, signal }
  );
}

export async function fetchNotificationPreferences(
  userId?: string,
  signal?: AbortSignal
): Promise<NotificationPreference> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<NotificationPreference>(
    `/api/v1/notifications/preferences`,
    { headers, signal }
  );
}

export async function updateNotificationPreferences(
  payload: NotificationPreferenceUpdate,
  userId?: string,
  signal?: AbortSignal
): Promise<NotificationPreference> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<NotificationPreference>(
    `/api/v1/notifications/preferences`,
    { method: "PATCH", headers, body: JSON.stringify(payload), signal }
  );
}

export async function fetchReminderRules(
  userId?: string,
  signal?: AbortSignal
): Promise<ReminderRuleListResponse> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<ReminderRuleListResponse>(
    `/api/v1/notifications/rules`,
    { headers, signal }
  );
}

export async function createReminderRule(
  payload: ReminderRuleCreate,
  userId?: string,
  signal?: AbortSignal
): Promise<ReminderRule> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<ReminderRule>(
    `/api/v1/notifications/rules`,
    { method: "POST", headers, body: JSON.stringify(payload), signal }
  );
}

export async function updateReminderRule(
  ruleId: string,
  payload: ReminderRuleUpdate,
  userId?: string,
  signal?: AbortSignal
): Promise<ReminderRule> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<ReminderRule>(
    `/api/v1/notifications/rules/${ruleId}`,
    { method: "PATCH", headers, body: JSON.stringify(payload), signal }
  );
}

export async function deleteReminderRule(
  ruleId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<void> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  await fetch(`${API_URL}/api/v1/notifications/rules/${ruleId}`, {
    method: "DELETE",
    headers,
    signal,
  });
}

export async function triggerReminderScheduler(
  userId?: string,
  signal?: AbortSignal
): Promise<ReminderRunSummary> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<ReminderRunSummary>(
    `/api/v1/notifications/trigger-reminders`,
    { method: "POST", headers, signal }
  );
}

// ── Phase 4.6 Workspace Collaboration API Methods ──

export async function getWorkspaceMembers(
  workspaceId: string,
  status?: string,
  userId?: string,
  signal?: AbortSignal
): Promise<WorkspaceMemberListResponse> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  return fetchJson<WorkspaceMemberListResponse>(
    `/api/v1/workspaces/${workspaceId}/members${query}`,
    { headers, signal }
  );
}

export async function addWorkspaceMember(
  workspaceId: string,
  payload: WorkspaceMemberAddPayload,
  userId?: string,
  signal?: AbortSignal
): Promise<WorkspaceMember> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<WorkspaceMember>(
    `/api/v1/workspaces/${workspaceId}/members`,
    { method: "POST", headers, body: JSON.stringify(payload), signal }
  );
}

export async function updateWorkspaceMemberRole(
  workspaceId: string,
  memberId: string,
  payload: WorkspaceMemberRoleUpdatePayload,
  userId?: string,
  signal?: AbortSignal
): Promise<WorkspaceMember> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<WorkspaceMember>(
    `/api/v1/workspaces/${workspaceId}/members/${memberId}/role`,
    { method: "PATCH", headers, body: JSON.stringify(payload), signal }
  );
}

export async function removeWorkspaceMember(
  workspaceId: string,
  memberId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<void> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  await fetch(`${API_URL}/api/v1/workspaces/${workspaceId}/members/${memberId}`, {
    method: "DELETE",
    headers,
    signal,
  });
}

export async function getWorkspaceInvitations(
  workspaceId: string,
  status?: string,
  userId?: string,
  signal?: AbortSignal
): Promise<WorkspaceInvitationListResponse> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  return fetchJson<WorkspaceInvitationListResponse>(
    `/api/v1/workspaces/${workspaceId}/invitations${query}`,
    { headers, signal }
  );
}

export async function createWorkspaceInvitation(
  workspaceId: string,
  payload: WorkspaceInvitationCreatePayload,
  userId?: string,
  signal?: AbortSignal
): Promise<WorkspaceInvitationCreateResponse> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<WorkspaceInvitationCreateResponse>(
    `/api/v1/workspaces/${workspaceId}/invitations`,
    { method: "POST", headers, body: JSON.stringify(payload), signal }
  );
}

export async function acceptWorkspaceInvitation(
  token: string,
  userId?: string,
  signal?: AbortSignal
): Promise<WorkspaceMember> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<WorkspaceMember>(
    `/api/v1/workspaces/invitations/${encodeURIComponent(token)}/accept`,
    { method: "POST", headers, signal }
  );
}

export async function declineWorkspaceInvitation(
  token: string,
  userId?: string,
  signal?: AbortSignal
): Promise<void> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<void>(
    `/api/v1/workspaces/invitations/${encodeURIComponent(token)}/decline`,
    { method: "POST", headers, signal }
  );
}

export async function revokeWorkspaceInvitation(
  workspaceId: string,
  invitationId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<void> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<void>(
    `/api/v1/workspaces/${workspaceId}/invitations/${invitationId}`,
    { method: "DELETE", headers, signal }
  );
}

export async function getWorkspaceTasks(
  workspaceId: string,
  params?: TaskFilterParams,
  userId?: string,
  signal?: AbortSignal
): Promise<WorkspaceTaskListResponse> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;

  const q = new URLSearchParams();
  if (params?.assignee_id) q.set("assignee_id", params.assignee_id);
  if (params?.status) q.set("status", params.status);
  if (params?.priority) q.set("priority", params.priority);
  if (params?.due_before) q.set("due_before", params.due_before);
  if (params?.limit) q.set("limit", String(params.limit));
  if (params?.offset) q.set("offset", String(params.offset));

  const qs = q.toString() ? `?${q.toString()}` : "";
  return fetchJson<WorkspaceTaskListResponse>(
    `/api/v1/workspaces/${workspaceId}/tasks${qs}`,
    { headers, signal }
  );
}

export async function createWorkspaceTask(
  workspaceId: string,
  payload: WorkspaceTaskCreatePayload,
  userId?: string,
  signal?: AbortSignal
): Promise<WorkspaceTask> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<WorkspaceTask>(
    `/api/v1/workspaces/${workspaceId}/tasks`,
    { method: "POST", headers, body: JSON.stringify(payload), signal }
  );
}

export async function updateWorkspaceTask(
  workspaceId: string,
  taskId: string,
  payload: WorkspaceTaskUpdatePayload,
  userId?: string,
  signal?: AbortSignal
): Promise<WorkspaceTask> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<WorkspaceTask>(
    `/api/v1/workspaces/${workspaceId}/tasks/${taskId}`,
    { method: "PATCH", headers, body: JSON.stringify(payload), signal }
  );
}

export async function assignWorkspaceTask(
  workspaceId: string,
  taskId: string,
  payload: WorkspaceTaskAssignPayload,
  userId?: string,
  signal?: AbortSignal
): Promise<WorkspaceTask> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<WorkspaceTask>(
    `/api/v1/workspaces/${workspaceId}/tasks/${taskId}/assign`,
    { method: "POST", headers, body: JSON.stringify(payload), signal }
  );
}

export async function completeWorkspaceTask(
  workspaceId: string,
  taskId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<WorkspaceTask> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<WorkspaceTask>(
    `/api/v1/workspaces/${workspaceId}/tasks/${taskId}/complete`,
    { method: "POST", headers, signal }
  );
}

export async function reopenWorkspaceTask(
  workspaceId: string,
  taskId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<WorkspaceTask> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<WorkspaceTask>(
    `/api/v1/workspaces/${workspaceId}/tasks/${taskId}/reopen`,
    { method: "POST", headers, signal }
  );
}

export async function deleteWorkspaceTask(
  workspaceId: string,
  taskId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<void> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  await fetch(`${API_URL}/api/v1/workspaces/${workspaceId}/tasks/${taskId}`, {
    method: "DELETE",
    headers,
    signal,
  });
}

export async function getWorkspaceActivity(
  workspaceId: string,
  limit: number = 50,
  offset: number = 0,
  userId?: string,
  signal?: AbortSignal
): Promise<WorkspaceActivityListResponse> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<WorkspaceActivityListResponse>(
    `/api/v1/workspaces/${workspaceId}/activity?limit=${limit}&offset=${offset}`,
    { headers, signal }
  );
}

export async function addWorkspaceComment(
  workspaceId: string,
  payload: WorkspaceCommentCreatePayload,
  userId?: string,
  signal?: AbortSignal
): Promise<WorkspaceActivity> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<WorkspaceActivity>(
    `/api/v1/workspaces/${workspaceId}/comments`,
    { method: "POST", headers, body: JSON.stringify(payload), signal }
  );
}

// ----------------------------------------------------------------------------
// Phase 4.7: Unified Research Intelligence API Methods
// ----------------------------------------------------------------------------

export async function getUnifiedResearchIntelligence(
  researcherId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<UnifiedResearcherContext> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<UnifiedResearcherContext>(
    `/api/v1/researchers/${researcherId}/intelligence/unified`,
    { headers, signal }
  );
}

export async function getUnifiedRecommendations(
  researcherId: string,
  params?: { query?: string; limit?: number; include_evidence?: boolean },
  userId?: string,
  signal?: AbortSignal
): Promise<UnifiedRecommendationResponse> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  const searchParams = new URLSearchParams();
  if (params?.query) searchParams.set("query", params.query);
  if (params?.limit !== undefined) searchParams.set("limit", String(params.limit));
  if (params?.include_evidence !== undefined) searchParams.set("include_evidence", String(params.include_evidence));
  const queryString = searchParams.toString();
  const url = `/api/v1/researchers/${researcherId}/recommendations/unified${queryString ? `?${queryString}` : ""}`;
  return fetchJson<UnifiedRecommendationResponse>(url, { headers, signal });
}

export async function getOpportunityIntelligence(
  researcherId: string,
  opportunityId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<UnifiedOpportunityIntelligence> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<UnifiedOpportunityIntelligence>(
    `/api/v1/researchers/${researcherId}/recommendations/unified/${opportunityId}/intelligence`,
    { headers, signal }
  );
}

// ----------------------------------------------------------------------------
// Phase 5.2: Explicit Preference Interpretation API Methods
// ----------------------------------------------------------------------------

export async function fetchOpportunityPreferenceMatch(
  researcherId: string,
  opportunityId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<PreferencePersonalizationAssessment> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<PreferencePersonalizationAssessment>(
    `/api/v1/researchers/${researcherId}/opportunities/${opportunityId}/preference-match`,
    { headers, signal }
  );
}

export async function fetchBatchOpportunityPreferenceMatches(
  researcherId: string,
  opportunityIds: string[],
  userId?: string,
  signal?: AbortSignal
): Promise<BatchOpportunityPreferenceMatchResponse> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<BatchOpportunityPreferenceMatchResponse>(
    `/api/v1/researchers/${researcherId}/opportunities/preference-matches`,
    {
      method: "POST",
      headers,
      body: JSON.stringify({ opportunity_ids: opportunityIds }),
      signal,
    }
  );
}

// ----------------------------------------------------------------------------
// Phase 5.3: Personalization Scoring & Explainability API Methods
// ----------------------------------------------------------------------------

export async function fetchOpportunityPersonalization(
  researcherId: string,
  opportunityId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<PersonalizationAssessment> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<PersonalizationAssessment>(
    `/api/v1/researchers/${researcherId}/opportunities/${opportunityId}/personalization`,
    { headers, signal }
  );
}

export async function fetchBatchOpportunityPersonalization(
  researcherId: string,
  opportunityIds: string[],
  userId?: string,
  signal?: AbortSignal
): Promise<BatchPersonalizationResponse> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<BatchPersonalizationResponse>(
    `/api/v1/researchers/${researcherId}/opportunities/personalization`,
    {
      method: "POST",
      headers,
      body: JSON.stringify({ opportunity_ids: opportunityIds }),
      signal,
    }
  );
}

// ----------------------------------------------------------------------------
// Phase 5.4: Researcher Feedback & Interaction API Methods
// ----------------------------------------------------------------------------

export async function recordOpportunityInteraction(
  researcherId: string,
  opportunityId: string,
  payload: InteractionCreateRequest,
  userId?: string,
  signal?: AbortSignal
): Promise<InteractionResponse> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<InteractionResponse>(
    `/api/v1/researchers/${researcherId}/opportunities/${opportunityId}/interactions`,
    {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
      signal,
    }
  );
}

export async function fetchOpportunityInteractions(
  researcherId: string,
  opportunityId: string,
  options?: { limit?: number; offset?: number },
  userId?: string,
  signal?: AbortSignal
): Promise<OpportunityInteractionHistoryResponse> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  const params = new URLSearchParams();
  if (options?.limit !== undefined) params.set("limit", String(options.limit));
  if (options?.offset !== undefined) params.set("offset", String(options.offset));
  const query = params.toString();

  return fetchJson<OpportunityInteractionHistoryResponse>(
    `/api/v1/researchers/${researcherId}/opportunities/${opportunityId}/interactions${query ? `?${query}` : ""}`,
    { headers, signal }
  );
}

export async function fetchResearcherInteractionSummary(
  researcherId: string,
  options?: { recentLimit?: number },
  userId?: string,
  signal?: AbortSignal
): Promise<ResearcherInteractionSummaryResponse> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  const params = new URLSearchParams();
  if (options?.recentLimit !== undefined) params.set("recent_limit", String(options.recentLimit));
  const query = params.toString();

  return fetchJson<ResearcherInteractionSummaryResponse>(
    `/api/v1/researchers/${researcherId}/interactions/summary${query ? `?${query}` : ""}`,
    { headers, signal }
  );
}

// ----------------------------------------------------------------------------
// Phase 5.5: Adaptive Preference Signal API Methods
// ----------------------------------------------------------------------------

export async function fetchResearcherAdaptiveSignals(
  researcherId: string,
  filters?: {
    dimension?: AdaptiveSignalDimension;
    state?: AdaptiveEvidenceState;
  },
  userId?: string,
  signal?: AbortSignal
): Promise<AdaptiveSignalsResponse> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  const params = new URLSearchParams();
  if (filters?.dimension) params.set("dimension", filters.dimension);
  if (filters?.state) params.set("state", filters.state);
  const qs = params.toString();

  return fetchJson<AdaptiveSignalsResponse>(
    `/api/v1/researchers/${researcherId}/adaptive-signals${qs ? `?${qs}` : ""}`,
    { headers, signal }
  );
}

export async function fetchAdaptiveSignalById(
  researcherId: string,
  signalId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<AdaptivePreferenceSignal> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<AdaptivePreferenceSignal>(
    `/api/v1/researchers/${researcherId}/adaptive-signals/${signalId}`,
    { headers, signal }
  );
}

export async function fetchAdaptiveSignalsExplanation(
  researcherId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<AdaptiveSignalExplanationResponse> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<AdaptiveSignalExplanationResponse>(
    `/api/v1/researchers/${researcherId}/adaptive-signals/explanation`,
    { headers, signal }
  );
}

export async function recomputeAdaptiveSignals(
  researcherId: string,
  payload?: AdaptiveSignalRecomputeRequest,
  userId?: string,
  signal?: AbortSignal
): Promise<AdaptiveSignalsResponse> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<AdaptiveSignalsResponse>(
    `/api/v1/researchers/${researcherId}/adaptive-signals/recompute`,
    {
      method: "POST",
      headers,
      body: payload ? JSON.stringify(payload) : undefined,
      signal,
    }
  );
}

// ----------------------------------------------------------------------------
// Phase 5.6: Personalization Calibration API Methods
// ----------------------------------------------------------------------------

export async function fetchResearcherCalibrations(
  researcherId: string,
  filters?: {
    dimension?: string;
    state?: CalibrationState;
  },
  userId?: string,
  signal?: AbortSignal
): Promise<PersonalizationCalibrationResponse> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  const params = new URLSearchParams();
  if (filters?.dimension) params.set("dimension", filters.dimension);
  if (filters?.state) params.set("state", filters.state);
  const qs = params.toString();

  return fetchJson<PersonalizationCalibrationResponse>(
    `/api/v1/researchers/${researcherId}/personalization/calibration${qs ? `?${qs}` : ""}`,
    { headers, signal }
  );
}

export async function fetchCalibrationBySignalId(
  researcherId: string,
  signalId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<PersonalizationCalibrationDetailResponse> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<PersonalizationCalibrationDetailResponse>(
    `/api/v1/researchers/${researcherId}/personalization/calibration/${signalId}`,
    { headers, signal }
  );
}

export async function recomputeCalibrations(
  researcherId: string,
  payload?: CalibrationRecomputeRequest,
  userId?: string,
  signal?: AbortSignal
): Promise<PersonalizationCalibrationResponse> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<PersonalizationCalibrationResponse>(
    `/api/v1/researchers/${researcherId}/personalization/calibration/recompute`,
    {
      method: "POST",
      headers,
      body: payload ? JSON.stringify(payload) : undefined,
      signal,
    }
  );
}

// ----------------------------------------------------------------------------
// Phase 5.7: Personalization Quality & Contextual Adaptation API Methods
// ----------------------------------------------------------------------------

export async function fetchPersonalizationQuality(
  researcherId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<PersonalizationQualityResponse> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<PersonalizationQualityResponse>(
    `/api/v1/researchers/${researcherId}/personalization/quality`,
    { headers, signal }
  );
}

export async function fetchContextualAdaptations(
  researcherId: string,
  contextDimension?: string,
  userId?: string,
  signal?: AbortSignal
): Promise<ContextualAdaptationsResponse> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  const params = new URLSearchParams();
  if (contextDimension) params.set("context_dimension", contextDimension);
  const qs = params.toString();

  return fetchJson<ContextualAdaptationsResponse>(
    `/api/v1/researchers/${researcherId}/personalization/quality/contexts${qs ? `?${qs}` : ""}`,
    { headers, signal }
  );
}

export async function fetchSignalQualities(
  researcherId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<SignalQualityResponse> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<SignalQualityResponse>(
    `/api/v1/researchers/${researcherId}/personalization/quality/signals`,
    { headers, signal }
  );
}

export async function recomputePersonalizationQuality(
  researcherId: string,
  payload?: QualityRecomputeRequest,
  userId?: string,
  signal?: AbortSignal
): Promise<PersonalizationQualityResponse> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<PersonalizationQualityResponse>(
    `/api/v1/researchers/${researcherId}/personalization/quality/recompute`,
    {
      method: "POST",
      headers,
      body: payload ? JSON.stringify(payload) : undefined,
      signal,
    }
  );
}

// ----------------------------------------------------------------------------
// Phase 5.8: Personalization Governance, Drift Detection & Safety API Methods
// ----------------------------------------------------------------------------

export async function fetchPersonalizationHealth(
  researcherId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<PersonalizationHealthResponse> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<PersonalizationHealthResponse>(
    `/api/v1/researchers/${researcherId}/personalization/health`,
    { headers, signal }
  );
}

export async function fetchPersonalizationDrift(
  researcherId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<PersonalizationDriftResponse> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<PersonalizationDriftResponse>(
    `/api/v1/researchers/${researcherId}/personalization/drift`,
    { headers, signal }
  );
}

export async function fetchGovernanceEvents(
  researcherId: string,
  limit: number = 20,
  offset: number = 0,
  userId?: string,
  signal?: AbortSignal
): Promise<PersonalizationGovernanceHistoryResponse> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  const params = new URLSearchParams();
  if (limit) params.set("limit", limit.toString());
  if (offset) params.set("offset", offset.toString());
  const qs = params.toString();

  return fetchJson<PersonalizationGovernanceHistoryResponse>(
    `/api/v1/researchers/${researcherId}/personalization/governance${qs ? `?${qs}` : ""}`,
    { headers, signal }
  );
}

export async function recomputePersonalizationHealth(
  researcherId: string,
  payload?: GovernanceRecomputeRequest,
  userId?: string,
  signal?: AbortSignal
): Promise<PersonalizationHealthResponse> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<PersonalizationHealthResponse>(
    `/api/v1/researchers/${researcherId}/personalization/health/recompute`,
    {
      method: "POST",
      headers,
      body: payload ? JSON.stringify(payload) : undefined,
      signal,
    }
  );
}

// =============================================================================
// Phase 5.9 — Personalization Transparency, Researcher Controls & Explanation Layer
// =============================================================================

export async function fetchPersonalizationSettings(
  researcherId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<ResearcherPersonalizationSettings> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<ResearcherPersonalizationSettings>(
    `/api/v1/researchers/${researcherId}/personalization/settings`,
    { headers, signal }
  );
}

export async function updatePersonalizationSettings(
  researcherId: string,
  payload: ResearcherPersonalizationSettingsUpdate,
  userId?: string,
  signal?: AbortSignal
): Promise<ResearcherPersonalizationSettings> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<ResearcherPersonalizationSettings>(
    `/api/v1/researchers/${researcherId}/personalization/settings`,
    {
      method: "PATCH",
      headers,
      body: JSON.stringify(payload),
      signal,
    }
  );
}

export async function resetPersonalization(
  researcherId: string,
  reason?: string,
  userId?: string,
  signal?: AbortSignal
): Promise<PersonalizationResetResponse> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  const params = new URLSearchParams();
  if (reason) params.set("reason", reason);
  const qs = params.toString();

  return fetchJson<PersonalizationResetResponse>(
    `/api/v1/researchers/${researcherId}/personalization/reset${qs ? `?${qs}` : ""}`,
    {
      method: "POST",
      headers,
      signal,
    }
  );
}

export async function fetchPersonalizationControlHistory(
  researcherId: string,
  limit: number = 20,
  offset: number = 0,
  userId?: string,
  signal?: AbortSignal
): Promise<PersonalizationControlHistoryResponse> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  const params = new URLSearchParams();
  if (limit) params.set("limit", limit.toString());
  if (offset) params.set("offset", offset.toString());
  const qs = params.toString();

  return fetchJson<PersonalizationControlHistoryResponse>(
    `/api/v1/researchers/${researcherId}/personalization/control-history${qs ? `?${qs}` : ""}`,
    { headers, signal }
  );
}

export async function fetchRecommendationPersonalizationExplanation(
  researcherId: string,
  recommendationId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<RecommendationPersonalizationExplanation> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<RecommendationPersonalizationExplanation>(
    `/api/v1/researchers/${researcherId}/recommendations/${recommendationId}/personalization`,
    { headers, signal }
  );
}



// ── Phase 5.10 — Faculty Research Postings ────────────────────────────────────
//
// Identity is attached by fetchJson from the stored session (bearer token, or a developer
// X-User-ID), so these helpers do not take a userId parameter. Discovery reads work
// unauthenticated and return only OPEN postings.

export async function fetchPostings(
  filters: PostingFilterParams = {},
  signal?: AbortSignal
): Promise<ResearchPostingListResponse> {
  const params = new URLSearchParams();
  if (filters.posting_type) params.set("posting_type", filters.posting_type);
  if (filters.country) params.set("country", filters.country);
  if (filters.work_mode) params.set("work_mode", filters.work_mode);
  if (filters.topic_id) params.set("topic_id", filters.topic_id);
  if (filters.search) params.set("search", filters.search);
  if (filters.accepting_only) params.set("accepting_only", "true");
  if (filters.sort_by) params.set("sort_by", filters.sort_by);
  if (filters.sort_order) params.set("sort_order", filters.sort_order);
  if (filters.limit !== undefined) params.set("limit", String(filters.limit));
  if (filters.offset !== undefined) params.set("offset", String(filters.offset));

  const qs = params.toString();
  return fetchJson<ResearchPostingListResponse>(
    `/api/v1/postings${qs ? `?${qs}` : ""}`,
    { signal }
  );
}

export async function fetchMyPostings(
  filters: { status?: PostingStatus; posting_type?: PostingType; limit?: number; offset?: number } = {},
  signal?: AbortSignal
): Promise<ResearchPostingListResponse> {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.posting_type) params.set("posting_type", filters.posting_type);
  if (filters.limit !== undefined) params.set("limit", String(filters.limit));
  if (filters.offset !== undefined) params.set("offset", String(filters.offset));

  const qs = params.toString();
  return fetchJson<ResearchPostingListResponse>(
    `/api/v1/postings/mine${qs ? `?${qs}` : ""}`,
    { signal }
  );
}

export async function fetchMyPostingSummary(
  signal?: AbortSignal
): Promise<PostingSummaryResponse> {
  return fetchJson<PostingSummaryResponse>("/api/v1/postings/mine/summary", { signal });
}

export async function fetchPosting(
  postingId: string,
  signal?: AbortSignal
): Promise<ResearchPosting> {
  return fetchJson<ResearchPosting>(`/api/v1/postings/${postingId}`, { signal });
}

export async function createPosting(
  payload: PostingCreatePayload,
  signal?: AbortSignal
): Promise<ResearchPosting> {
  return fetchJson<ResearchPosting>("/api/v1/postings", {
    method: "POST",
    body: JSON.stringify(payload),
    signal,
  });
}

export async function updatePosting(
  postingId: string,
  payload: PostingUpdatePayload,
  signal?: AbortSignal
): Promise<ResearchPosting> {
  return fetchJson<ResearchPosting>(`/api/v1/postings/${postingId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
    signal,
  });
}

export async function transitionPosting(
  postingId: string,
  targetStatus: PostingStatus,
  note?: string,
  signal?: AbortSignal
): Promise<ResearchPosting> {
  return fetchJson<ResearchPosting>(`/api/v1/postings/${postingId}/transition`, {
    method: "POST",
    body: JSON.stringify({ target_status: targetStatus, note: note ?? null }),
    signal,
  });
}

export async function deletePosting(postingId: string, signal?: AbortSignal): Promise<void> {
  return fetchJson<void>(`/api/v1/postings/${postingId}`, { method: "DELETE", signal });
}

// ── Phase 5.11 — Applications to research openings ────────────────────────────

export async function applyToPosting(
  postingId: string,
  payload: ApplicationCreatePayload,
  signal?: AbortSignal
): Promise<PostingApplication> {
  return fetchJson<PostingApplication>(`/api/v1/postings/${postingId}/applications`, {
    method: "POST",
    body: JSON.stringify(payload),
    signal,
  });
}

export async function fetchPostingApplications(
  postingId: string,
  filters: { status?: ApplicationStatus; limit?: number; offset?: number } = {},
  signal?: AbortSignal
): Promise<ApplicationListResponse> {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.limit !== undefined) params.set("limit", String(filters.limit));
  if (filters.offset !== undefined) params.set("offset", String(filters.offset));
  const qs = params.toString();
  return fetchJson<ApplicationListResponse>(
    `/api/v1/postings/${postingId}/applications${qs ? `?${qs}` : ""}`,
    { signal }
  );
}

export async function fetchMyApplications(
  filters: { status?: ApplicationStatus; limit?: number; offset?: number } = {},
  signal?: AbortSignal
): Promise<ApplicationListResponse> {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.limit !== undefined) params.set("limit", String(filters.limit));
  if (filters.offset !== undefined) params.set("offset", String(filters.offset));
  const qs = params.toString();
  return fetchJson<ApplicationListResponse>(
    `/api/v1/postings/applications/mine${qs ? `?${qs}` : ""}`,
    { signal }
  );
}

export async function fetchMyApplicationSummary(
  signal?: AbortSignal
): Promise<ApplicationSummaryResponse> {
  return fetchJson<ApplicationSummaryResponse>("/api/v1/postings/applications/mine/summary", {
    signal,
  });
}

export async function fetchApplication(
  applicationId: string,
  signal?: AbortSignal
): Promise<PostingApplication> {
  return fetchJson<PostingApplication>(`/api/v1/postings/applications/${applicationId}`, { signal });
}

export async function transitionApplication(
  applicationId: string,
  targetStatus: ApplicationStatus,
  options: { decisionReason?: string; reviewerNote?: string } = {},
  signal?: AbortSignal
): Promise<PostingApplication> {
  return fetchJson<PostingApplication>(
    `/api/v1/postings/applications/${applicationId}/transition`,
    {
      method: "POST",
      body: JSON.stringify({
        target_status: targetStatus,
        decision_reason: options.decisionReason ?? null,
        reviewer_note: options.reviewerNote ?? null,
      }),
      signal,
    }
  );
}

// ── Phase 5.12 — Peer & Co-Author Discovery ───────────────────────────────────
//
// `userId` is still accepted for the developer-identity path used by the researcher pages;
// fetchJson prefers a stored bearer token when one exists.

export async function fetchDiscoverySettings(
  researcherId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<DiscoverySettings> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<DiscoverySettings>(
    `/api/v1/researchers/${researcherId}/discovery-settings`,
    { headers, signal }
  );
}

export async function updateDiscoverySettings(
  researcherId: string,
  payload: DiscoverySettingsUpdate,
  userId?: string,
  signal?: AbortSignal
): Promise<DiscoverySettings> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<DiscoverySettings>(
    `/api/v1/researchers/${researcherId}/discovery-settings`,
    { method: "PATCH", headers, body: JSON.stringify(payload), signal }
  );
}

export async function fetchPeerMatches(
  researcherId: string,
  options: {
    limit?: number;
    collaborationInterest?: CollaborationInterest;
    excludeSameInstitution?: boolean;
  } = {},
  userId?: string,
  signal?: AbortSignal
): Promise<PeerMatchResponse> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  const params = new URLSearchParams();
  if (options.limit !== undefined) params.set("limit", String(options.limit));
  if (options.collaborationInterest) {
    params.set("collaboration_interest", options.collaborationInterest);
  }
  if (options.excludeSameInstitution) params.set("exclude_same_institution", "true");
  const qs = params.toString();
  return fetchJson<PeerMatchResponse>(
    `/api/v1/researchers/${researcherId}/peers${qs ? `?${qs}` : ""}`,
    { headers, signal }
  );
}
