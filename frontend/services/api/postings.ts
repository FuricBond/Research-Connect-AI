import type { PostingCreatePayload, PostingFilterParams, PostingStatus, PostingSummaryResponse, PostingType, PostingUpdatePayload, ResearchPosting, ResearchPostingListResponse } from "../../types/posting";
import { fetchJson } from "./client";

// ── Phase 5.10 — Faculty Research Postings ────────────────────────────────────
//
// Identity is attached by fetchJson from the stored session (bearer token, or a developer
// X-User-ID), so these helpers do not take a userId parameter. Discovery reads work
// unauthenticated and return only OPEN postings.

export async function fetchPostings(
  filters: PostingFilterParams = {},
  signal?: AbortSignal
): Promise<ResearchPostingListResponse> {
  const params = new URLSearchParams();
  if (filters.posting_type) params.set("posting_type", filters.posting_type);
  if (filters.country) params.set("country", filters.country);
  if (filters.work_mode) params.set("work_mode", filters.work_mode);
  if (filters.topic_id) params.set("topic_id", filters.topic_id);
  if (filters.search) params.set("search", filters.search);
  if (filters.accepting_only) params.set("accepting_only", "true");
  if (filters.sort_by) params.set("sort_by", filters.sort_by);
  if (filters.sort_order) params.set("sort_order", filters.sort_order);
  if (filters.limit !== undefined) params.set("limit", String(filters.limit));
  if (filters.offset !== undefined) params.set("offset", String(filters.offset));

  const qs = params.toString();
  return fetchJson<ResearchPostingListResponse>(
    `/api/v1/postings${qs ? `?${qs}` : ""}`,
    { signal }
  );
}

export async function fetchMyPostings(
  filters: { status?: PostingStatus; posting_type?: PostingType; limit?: number; offset?: number } = {},
  signal?: AbortSignal
): Promise<ResearchPostingListResponse> {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.posting_type) params.set("posting_type", filters.posting_type);
  if (filters.limit !== undefined) params.set("limit", String(filters.limit));
  if (filters.offset !== undefined) params.set("offset", String(filters.offset));

  const qs = params.toString();
  return fetchJson<ResearchPostingListResponse>(
    `/api/v1/postings/mine${qs ? `?${qs}` : ""}`,
    { signal }
  );
}

export async function fetchMyPostingSummary(
  signal?: AbortSignal
): Promise<PostingSummaryResponse> {
  return fetchJson<PostingSummaryResponse>("/api/v1/postings/mine/summary", { signal });
}

export async function fetchPosting(
  postingId: string,
  signal?: AbortSignal
): Promise<ResearchPosting> {
  return fetchJson<ResearchPosting>(`/api/v1/postings/${postingId}`, { signal });
}

export async function createPosting(
  payload: PostingCreatePayload,
  signal?: AbortSignal
): Promise<ResearchPosting> {
  return fetchJson<ResearchPosting>("/api/v1/postings", {
    method: "POST",
    body: JSON.stringify(payload),
    signal,
  });
}

export async function updatePosting(
  postingId: string,
  payload: PostingUpdatePayload,
  signal?: AbortSignal
): Promise<ResearchPosting> {
  return fetchJson<ResearchPosting>(`/api/v1/postings/${postingId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
    signal,
  });
}

export async function transitionPosting(
  postingId: string,
  targetStatus: PostingStatus,
  note?: string,
  signal?: AbortSignal
): Promise<ResearchPosting> {
  return fetchJson<ResearchPosting>(`/api/v1/postings/${postingId}/transition`, {
    method: "POST",
    body: JSON.stringify({ target_status: targetStatus, note: note ?? null }),
    signal,
  });
}

export async function deletePosting(postingId: string, signal?: AbortSignal): Promise<void> {
  return fetchJson<void>(`/api/v1/postings/${postingId}`, { method: "DELETE", signal });
}
