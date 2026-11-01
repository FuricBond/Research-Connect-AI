import type { OpportunityDeadline, OpportunityListResponse, OpportunityRead, RiskExplanation } from "../../types/opportunity";
import { fetchJson } from "./client";

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
