import type { ApplicationCreatePayload, ApplicationListResponse, ApplicationStatus, ApplicationSummaryResponse, PostingApplication } from "../../types/posting";
import { fetchJson } from "./client";

// ── Phase 5.11 — Applications to research openings ────────────────────────────

export async function applyToPosting(
  postingId: string,
  payload: ApplicationCreatePayload,
  signal?: AbortSignal
): Promise<PostingApplication> {
  return fetchJson<PostingApplication>(`/api/v1/postings/${postingId}/applications`, {
    method: "POST",
    body: JSON.stringify(payload),
    signal,
  });
}

export async function fetchPostingApplications(
  postingId: string,
  filters: { status?: ApplicationStatus; limit?: number; offset?: number } = {},
  signal?: AbortSignal
): Promise<ApplicationListResponse> {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.limit !== undefined) params.set("limit", String(filters.limit));
  if (filters.offset !== undefined) params.set("offset", String(filters.offset));
  const qs = params.toString();
  return fetchJson<ApplicationListResponse>(
    `/api/v1/postings/${postingId}/applications${qs ? `?${qs}` : ""}`,
    { signal }
  );
}

export async function fetchMyApplications(
  filters: { status?: ApplicationStatus; limit?: number; offset?: number } = {},
  signal?: AbortSignal
): Promise<ApplicationListResponse> {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.limit !== undefined) params.set("limit", String(filters.limit));
  if (filters.offset !== undefined) params.set("offset", String(filters.offset));
  const qs = params.toString();
  return fetchJson<ApplicationListResponse>(
    `/api/v1/postings/applications/mine${qs ? `?${qs}` : ""}`,
    { signal }
  );
}

export async function fetchMyApplicationSummary(
  signal?: AbortSignal
): Promise<ApplicationSummaryResponse> {
  return fetchJson<ApplicationSummaryResponse>("/api/v1/postings/applications/mine/summary", {
    signal,
  });
}

export async function fetchApplication(
  applicationId: string,
  signal?: AbortSignal
): Promise<PostingApplication> {
  return fetchJson<PostingApplication>(`/api/v1/postings/applications/${applicationId}`, { signal });
}

export async function transitionApplication(
  applicationId: string,
  targetStatus: ApplicationStatus,
  options: { decisionReason?: string; reviewerNote?: string } = {},
  signal?: AbortSignal
): Promise<PostingApplication> {
  return fetchJson<PostingApplication>(
    `/api/v1/postings/applications/${applicationId}/transition`,
    {
      method: "POST",
      body: JSON.stringify({
        target_status: targetStatus,
        decision_reason: options.decisionReason ?? null,
        reviewer_note: options.reviewerNote ?? null,
      }),
      signal,
    }
  );
}
