import type { ProfileCompleteness, ResearcherIntelligenceResponse, ResearcherInterestItem, ResearcherProfile, ResearcherProfileCreatePayload, ResearcherProfileUpdatePayload, ResearcherWorkSummary } from "../../types/researcher";
import { fetchJson } from "./client";

// ── Researcher Profile API (Phase 3.1) ────────────────────────────────────────





export async function fetchResearcherProfile(
  id: string,
  signal?: AbortSignal
): Promise<ResearcherProfile> {
  return fetchJson<ResearcherProfile>(`/api/v1/researchers/${id}`, { signal });
}

export async function createResearcherProfile(
  payload: ResearcherProfileCreatePayload,
  signal?: AbortSignal
): Promise<ResearcherProfile> {
  return fetchJson<ResearcherProfile>("/api/v1/researchers", {
    method: "POST",
    body: JSON.stringify(payload),
    signal,
  });
}

export async function updateResearcherProfile(
  id: string,
  payload: ResearcherProfileUpdatePayload,
  signal?: AbortSignal
): Promise<ResearcherProfile> {
  return fetchJson<ResearcherProfile>(`/api/v1/researchers/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
    signal,
  });
}

export async function fetchResearcherWorks(
  id: string,
  limit: number = 20,
  offset: number = 0,
  signal?: AbortSignal
): Promise<ResearcherWorkSummary[]> {
  return fetchJson<ResearcherWorkSummary[]>(
    `/api/v1/researchers/${id}/works?limit=${limit}&offset=${offset}`,
    { signal }
  );
}

export async function fetchProfileCompleteness(
  id: string,
  signal?: AbortSignal
): Promise<ProfileCompleteness> {
  return fetchJson<ProfileCompleteness>(
    `/api/v1/researchers/${id}/completeness`,
    { signal }
  );
}

export async function fetchResearcherIntelligence(
  id: string,
  refresh: boolean = false,
  signal?: AbortSignal
): Promise<ResearcherIntelligenceResponse> {
  return fetchJson<ResearcherIntelligenceResponse>(
    `/api/v1/researchers/${id}/research-intelligence?refresh=${refresh}`,
    { signal }
  );
}

export async function fetchResearcherInterests(
  id: string,
  signal?: AbortSignal
): Promise<ResearcherInterestItem[]> {
  return fetchJson<ResearcherInterestItem[]>(
    `/api/v1/researchers/${id}/interests`,
    { signal }
  );
}

export async function fetchResearcherExpertise(
  id: string,
  signal?: AbortSignal
): Promise<ResearcherInterestItem[]> {
  return fetchJson<ResearcherInterestItem[]>(
    `/api/v1/researchers/${id}/expertise`,
    { signal }
  );
}
