import type { PersonalizedCandidateSetResponse } from "../../types/researcher";
import { fetchJson } from "./client";

// ── Phase 3.4 — Personalized Candidate Generation API ────────────────────────

export async function fetchPersonalizedCandidates(
  id: string,
  options?: {
    limit?: number;
    includeInferred?: boolean;
    includeExpertise?: boolean;
    includeFallback?: boolean;
  },
  userId?: string,
  signal?: AbortSignal
): Promise<PersonalizedCandidateSetResponse> {
  const params = new URLSearchParams();
  if (options?.limit) params.set("limit", String(options.limit));
  if (options?.includeInferred !== undefined)
    params.set("include_inferred", String(options.includeInferred));
  if (options?.includeExpertise !== undefined)
    params.set("include_expertise", String(options.includeExpertise));
  if (options?.includeFallback !== undefined)
    params.set("include_fallback", String(options.includeFallback));

  const query = params.toString();
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }

  return fetchJson<PersonalizedCandidateSetResponse>(
    `/api/v1/researchers/${id}/personalized-candidates${query ? `?${query}` : ""}`,
    {
      headers,
      signal,
    }
  );
}
