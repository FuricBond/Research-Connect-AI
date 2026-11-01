import type { RecommendationEvaluationResponse, RecommendationHistoryResponse, RecommendationSnapshotDetail } from "../../types/researcher";
import { fetchJson } from "./client";

// ── Phase 3.7 — Recommendation History & Evaluation API ───────────────────────

export async function fetchRecommendationHistory(
  id: string,
  options?: {
    limit?: number;
    offset?: number;
    rankingVersion?: string;
    fromDate?: string;
    toDate?: string;
  },
  userId?: string,
  signal?: AbortSignal
): Promise<RecommendationHistoryResponse> {
  const params = new URLSearchParams();
  if (options?.limit) params.set("limit", String(options.limit));
  if (options?.offset) params.set("offset", String(options.offset));
  if (options?.rankingVersion) params.set("ranking_version", options.rankingVersion);
  if (options?.fromDate) params.set("from_date", options.fromDate);
  if (options?.toDate) params.set("to_date", options.toDate);

  const query = params.toString();
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }

  return fetchJson<RecommendationHistoryResponse>(
    `/api/v1/researchers/${id}/recommendation-history${query ? `?${query}` : ""}`,
    {
      headers,
      signal,
    }
  );
}

export async function fetchRecommendationSnapshotDetail(
  id: string,
  snapshotId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<RecommendationSnapshotDetail> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }

  return fetchJson<RecommendationSnapshotDetail>(
    `/api/v1/researchers/${id}/recommendation-history/${snapshotId}`,
    {
      headers,
      signal,
    }
  );
}

export async function fetchRecommendationEvaluation(
  id: string,
  options?: {
    rankingVersion?: string;
    fromDate?: string;
    toDate?: string;
    includeComparison?: boolean;
  },
  userId?: string,
  signal?: AbortSignal
): Promise<RecommendationEvaluationResponse> {
  const params = new URLSearchParams();
  if (options?.rankingVersion) params.set("ranking_version", options.rankingVersion);
  if (options?.fromDate) params.set("from_date", options.fromDate);
  if (options?.toDate) params.set("to_date", options.toDate);
  if (options?.includeComparison !== undefined)
    params.set("include_comparison", String(options.includeComparison));

  const query = params.toString();
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }

  return fetchJson<RecommendationEvaluationResponse>(
    `/api/v1/researchers/${id}/recommendation-evaluation${query ? `?${query}` : ""}`,
    {
      headers,
      signal,
    }
  );
}
