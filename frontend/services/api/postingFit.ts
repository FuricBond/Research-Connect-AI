import type { PostingFit, PostingFitBatchResponse } from "../../types/posting";
import { fetchJson } from "./client";

// ── Phase 5.15 — Posting fit for students ─────────────────────────────────────

/** How well one posting fits the signed-in student. 403 for other roles and for the author. */
export async function fetchPostingFit(postingId: string, signal?: AbortSignal): Promise<PostingFit> {
  return fetchJson<PostingFit>(`/api/v1/postings/${postingId}/fit`, { signal });
}

/** Fits for up to 100 postings in one call; postings that are not OPEN are left out. */
export async function fetchPostingFits(
  postingIds: string[],
  signal?: AbortSignal
): Promise<PostingFitBatchResponse> {
  if (postingIds.length === 0) return { fits: [] };
  return fetchJson<PostingFitBatchResponse>("/api/v1/postings/fit-scores", {
    method: "POST",
    body: JSON.stringify({ posting_ids: postingIds.slice(0, 100) }),
    signal,
  });
}
