import type { BehavioralSignal, FeedbackCreatePayload, FeedbackItem, FeedbackListResponse, FeedbackSummaryResponse } from "../../types/researcher";
import { fetchJson } from "./client";

// ── Phase 3.6 — Feedback & Recommendation Learning API ────────────────────────

export async function recordRecommendationFeedback(
  id: string,
  payload: FeedbackCreatePayload,
  userId?: string,
  signal?: AbortSignal
): Promise<FeedbackItem> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }
  return fetchJson<FeedbackItem>(
    `/api/v1/researchers/${id}/feedback`,
    {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
      signal,
    }
  );
}

export async function fetchRecommendationFeedbackHistory(
  id: string,
  options?: {
    limit?: number;
    offset?: number;
    feedbackType?: string;
    opportunityId?: string;
  },
  userId?: string,
  signal?: AbortSignal
): Promise<FeedbackListResponse> {
  const params = new URLSearchParams();
  if (options?.limit) params.set("limit", String(options.limit));
  if (options?.offset) params.set("offset", String(options.offset));
  if (options?.feedbackType) params.set("feedback_type", options.feedbackType);
  if (options?.opportunityId) params.set("opportunity_id", options.opportunityId);

  const query = params.toString();
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }

  return fetchJson<FeedbackListResponse>(
    `/api/v1/researchers/${id}/feedback${query ? `?${query}` : ""}`,
    {
      headers,
      signal,
    }
  );
}

export async function deleteRecommendationFeedback(
  id: string,
  feedbackId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<{ deleted: boolean; feedback_id: string }> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }
  return fetchJson<{ deleted: boolean; feedback_id: string }>(
    `/api/v1/researchers/${id}/feedback/${feedbackId}`,
    {
      method: "DELETE",
      headers,
      signal,
    }
  );
}

export async function fetchFeedbackSummary(
  id: string,
  userId?: string,
  signal?: AbortSignal
): Promise<FeedbackSummaryResponse> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }
  return fetchJson<FeedbackSummaryResponse>(
    `/api/v1/researchers/${id}/feedback/summary`,
    {
      headers,
      signal,
    }
  );
}

export async function fetchBehavioralSignals(
  id: string,
  userId?: string,
  signal?: AbortSignal
): Promise<{ researcher_id: string; signals: BehavioralSignal[] }> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }
  return fetchJson<{ researcher_id: string; signals: BehavioralSignal[] }>(
    `/api/v1/researchers/${id}/feedback/signals`,
    {
      headers,
      signal,
    }
  );
}
