import type { AdaptiveEvidenceState, AdaptivePreferenceSignal, AdaptiveSignalDimension, AdaptiveSignalExplanationResponse, AdaptiveSignalRecomputeRequest, AdaptiveSignalsResponse } from "../../types/personalization";
import { fetchJson } from "./client";

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
