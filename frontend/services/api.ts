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
  const response = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
    ...init,
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
  signal?: AbortSignal
): Promise<ResearcherPreferenceItem[]> {
  const params = new URLSearchParams();
  if (category) params.set("category", category);
  if (source) params.set("source", source);
  if (isActive !== undefined) params.set("is_active", String(isActive));
  const query = params.toString();
  return fetchJson<ResearcherPreferenceItem[]>(
    `/api/v1/researchers/${id}/preferences${query ? `?${query}` : ""}`,
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
