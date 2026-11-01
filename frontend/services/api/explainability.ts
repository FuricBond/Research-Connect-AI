import type { PersonalizationSummaryResponse, RecommendationExplanation } from "../../types/researcher";
import { fetchJson } from "./client";

// ── Phase 3.8 — Personalization Explainability & Summary API ─────────────────

export async function fetchPersonalizationSummary(
  id: string,
  userId?: string,
  signal?: AbortSignal
): Promise<PersonalizationSummaryResponse> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }

  return fetchJson<PersonalizationSummaryResponse>(
    `/api/v1/researchers/${id}/personalization-summary`,
    {
      headers,
      signal,
    }
  );
}

export async function fetchRecommendationExplanation(
  id: string,
  opportunityId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<RecommendationExplanation> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }

  return fetchJson<RecommendationExplanation>(
    `/api/v1/researchers/${id}/personalized-recommendations/${opportunityId}/explanation`,
    {
      headers,
      signal,
    }
  );
}

export async function fetchHistoricalRecommendationExplanation(
  id: string,
  snapshotId: string,
  opportunityId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<RecommendationExplanation> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }

  return fetchJson<RecommendationExplanation>(
    `/api/v1/researchers/${id}/recommendation-history/${snapshotId}/items/${opportunityId}/explanation`,
    {
      headers,
      signal,
    }
  );
}
