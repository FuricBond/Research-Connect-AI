import type { InteractionCreateRequest, InteractionResponse, OpportunityInteractionHistoryResponse, ResearcherInteractionSummaryResponse } from "../../types/personalization";
import { fetchJson } from "./client";

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
