import type { PersonalizationControlHistoryResponse, PersonalizationResetResponse, RecommendationPersonalizationExplanation, ResearcherPersonalizationSettings, ResearcherPersonalizationSettingsUpdate } from "../../types/personalization";
import { fetchJson } from "./client";

// =============================================================================
// Phase 5.9 — Personalization Transparency, Researcher Controls & Explanation Layer
// =============================================================================

export async function fetchPersonalizationSettings(
  researcherId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<ResearcherPersonalizationSettings> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<ResearcherPersonalizationSettings>(
    `/api/v1/researchers/${researcherId}/personalization/settings`,
    { headers, signal }
  );
}

export async function updatePersonalizationSettings(
  researcherId: string,
  payload: ResearcherPersonalizationSettingsUpdate,
  userId?: string,
  signal?: AbortSignal
): Promise<ResearcherPersonalizationSettings> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<ResearcherPersonalizationSettings>(
    `/api/v1/researchers/${researcherId}/personalization/settings`,
    {
      method: "PATCH",
      headers,
      body: JSON.stringify(payload),
      signal,
    }
  );
}

export async function resetPersonalization(
  researcherId: string,
  reason?: string,
  userId?: string,
  signal?: AbortSignal
): Promise<PersonalizationResetResponse> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  const params = new URLSearchParams();
  if (reason) params.set("reason", reason);
  const qs = params.toString();

  return fetchJson<PersonalizationResetResponse>(
    `/api/v1/researchers/${researcherId}/personalization/reset${qs ? `?${qs}` : ""}`,
    {
      method: "POST",
      headers,
      signal,
    }
  );
}

export async function fetchPersonalizationControlHistory(
  researcherId: string,
  limit: number = 20,
  offset: number = 0,
  userId?: string,
  signal?: AbortSignal
): Promise<PersonalizationControlHistoryResponse> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  const params = new URLSearchParams();
  if (limit) params.set("limit", limit.toString());
  if (offset) params.set("offset", offset.toString());
  const qs = params.toString();

  return fetchJson<PersonalizationControlHistoryResponse>(
    `/api/v1/researchers/${researcherId}/personalization/control-history${qs ? `?${qs}` : ""}`,
    { headers, signal }
  );
}

export async function fetchRecommendationPersonalizationExplanation(
  researcherId: string,
  recommendationId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<RecommendationPersonalizationExplanation> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<RecommendationPersonalizationExplanation>(
    `/api/v1/researchers/${researcherId}/recommendations/${recommendationId}/personalization`,
    { headers, signal }
  );
}
