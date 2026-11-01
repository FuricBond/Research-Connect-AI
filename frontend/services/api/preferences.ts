import type { BulkPreferencesUpdatePayload, ResearcherPreferenceCreatePayload, ResearcherPreferenceIntelligenceResponse, ResearcherPreferenceItem, ResearcherPreferenceUpdatePayload, StructuredPreferencesResponse } from "../../types/researcher";
import { fetchJson } from "./client";

// ── Phase 3.3 — Personal Preference Intelligence API ────────────────────────

export async function fetchResearcherPreferenceIntelligence(
  id: string,
  signal?: AbortSignal
): Promise<ResearcherPreferenceIntelligenceResponse> {
  return fetchJson<ResearcherPreferenceIntelligenceResponse>(
    `/api/v1/researchers/${id}/preference-intelligence`,
    { signal }
  );
}

export async function fetchResearcherPreferences(
  id: string,
  category?: string,
  source?: string,
  isActive?: boolean,
  preferenceType?: string,
  signal?: AbortSignal
): Promise<ResearcherPreferenceItem[]> {
  const params = new URLSearchParams();
  if (category) params.set("category", category);
  if (source) params.set("source", source);
  if (isActive !== undefined) params.set("is_active", String(isActive));
  if (preferenceType) params.set("preference_type", preferenceType);
  const query = params.toString();
  return fetchJson<ResearcherPreferenceItem[]>(
    `/api/v1/researchers/${id}/preferences${query ? `?${query}` : ""}`,
    { signal }
  );
}

export async function fetchStructuredResearcherPreferences(
  id: string,
  signal?: AbortSignal
): Promise<StructuredPreferencesResponse> {
  return fetchJson<StructuredPreferencesResponse>(
    `/api/v1/researchers/${id}/preferences/structured`,
    { signal }
  );
}

export async function createResearcherPreference(
  id: string,
  payload: ResearcherPreferenceCreatePayload,
  userId?: string,
  signal?: AbortSignal
): Promise<ResearcherPreferenceItem> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }
  return fetchJson<ResearcherPreferenceItem>(
    `/api/v1/researchers/${id}/preferences`,
    {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
      signal,
    }
  );
}

export async function bulkUpdateResearcherPreferences(
  id: string,
  payload: BulkPreferencesUpdatePayload,
  userId?: string,
  signal?: AbortSignal
): Promise<ResearcherPreferenceItem[]> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }
  return fetchJson<ResearcherPreferenceItem[]>(
    `/api/v1/researchers/${id}/preferences`,
    {
      method: "PUT",
      headers,
      body: JSON.stringify(payload),
      signal,
    }
  );
}

export async function updateResearcherPreference(
  id: string,
  preferenceId: string,
  payload: ResearcherPreferenceUpdatePayload,
  userId?: string,
  signal?: AbortSignal
): Promise<ResearcherPreferenceItem> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }
  return fetchJson<ResearcherPreferenceItem>(
    `/api/v1/researchers/${id}/preferences/${preferenceId}`,
    {
      method: "PATCH",
      headers,
      body: JSON.stringify(payload),
      signal,
    }
  );
}

export async function deleteResearcherPreference(
  id: string,
  preferenceId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<{ deleted: boolean; preference_id: string }> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }
  return fetchJson<{ deleted: boolean; preference_id: string }>(
    `/api/v1/researchers/${id}/preferences/${preferenceId}`,
    {
      method: "DELETE",
      headers,
      signal,
    }
  );
}
