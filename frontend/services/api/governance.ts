import type { GovernanceRecomputeRequest, PersonalizationDriftResponse, PersonalizationGovernanceHistoryResponse, PersonalizationHealthResponse } from "../../types/personalization";
import { fetchJson } from "./client";

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
