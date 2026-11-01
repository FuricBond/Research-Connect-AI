import type { PersonalizedRankingResponse } from "../../types/researcher";
import { fetchJson } from "./client";

// ── Phase 3.5 — Personalization Ranking API ───────────────────────────────────

export async function fetchPersonalizedRecommendations(
  id: string,
  options?: {
    limit?: number;
    offset?: number;
    includeInferred?: boolean;
    includeExpertise?: boolean;
    includeFallback?: boolean;
    enablePersonalization?: boolean;
    includeAblation?: boolean;
    opportunityType?: string;
    deliveryMode?: string;
  },
  userId?: string,
  signal?: AbortSignal
): Promise<PersonalizedRankingResponse> {
  const params = new URLSearchParams();
  if (options?.limit) params.set("limit", String(options.limit));
  if (options?.offset) params.set("offset", String(options.offset));
  if (options?.includeInferred !== undefined)
    params.set("include_inferred", String(options.includeInferred));
  if (options?.includeExpertise !== undefined)
    params.set("include_expertise", String(options.includeExpertise));
  if (options?.includeFallback !== undefined)
    params.set("include_fallback", String(options.includeFallback));
  if (options?.enablePersonalization !== undefined)
    params.set("enable_personalization", String(options.enablePersonalization));
  if (options?.includeAblation !== undefined)
    params.set("include_ablation", String(options.includeAblation));
  if (options?.opportunityType)
    params.set("opportunity_type", options.opportunityType);
  if (options?.deliveryMode)
    params.set("delivery_mode", options.deliveryMode);

  const query = params.toString();
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }

  return fetchJson<PersonalizedRankingResponse>(
    `/api/v1/researchers/${id}/personalized-recommendations${query ? `?${query}` : ""}`,
    {
      headers,
      signal,
    }
  );
}
 
