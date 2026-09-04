import type {
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

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

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
