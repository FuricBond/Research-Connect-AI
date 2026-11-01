import type { BatchPersonalizationResponse, PersonalizationAssessment } from "../../types/personalization";
import { fetchJson } from "./client";

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
