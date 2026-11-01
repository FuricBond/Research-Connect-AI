import type { BatchOpportunityPreferenceMatchResponse, PreferencePersonalizationAssessment } from "../../types/personalization";
import { fetchJson } from "./client";

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
