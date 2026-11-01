import type { ContextualAdaptationsResponse, PersonalizationQualityResponse, QualityRecomputeRequest, SignalQualityResponse } from "../../types/personalization";
import { fetchJson } from "./client";

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
