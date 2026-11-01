import type { CalibrationRecomputeRequest, CalibrationState, PersonalizationCalibrationDetailResponse, PersonalizationCalibrationResponse } from "../../types/personalization";
import { fetchJson } from "./client";

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
