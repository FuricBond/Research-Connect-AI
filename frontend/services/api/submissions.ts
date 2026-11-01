import type { ResearchSubmission, ResearchSubmissionCreate, ResearchSubmissionListResponse, ResearchSubmissionUpdate, SubmissionStatus, SubmissionStatusTransition, SubmissionSummaryResponse, SubmissionType } from "../../types/submission";
import { fetchJson } from "./client";

// ── Phase 4.2 — Research Submission Management & Tracking API ───────────────

export interface SubmissionFilterParams {
  status?: SubmissionStatus;
  submission_type?: SubmissionType;
  workspace_item_id?: string;
  search?: string;
  sort_by?: string;
  sort_order?: "asc" | "desc";
  limit?: number;
  offset?: number;
}

export async function fetchSubmissions(
  filters: SubmissionFilterParams = {},
  userId?: string,
  signal?: AbortSignal
): Promise<ResearchSubmissionListResponse> {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.submission_type) params.set("submission_type", filters.submission_type);
  if (filters.workspace_item_id) params.set("workspace_item_id", filters.workspace_item_id);
  if (filters.search) params.set("search", filters.search);
  if (filters.sort_by) params.set("sort_by", filters.sort_by);
  if (filters.sort_order) params.set("sort_order", filters.sort_order);
  if (filters.limit) params.set("limit", String(filters.limit));
  if (filters.offset) params.set("offset", String(filters.offset));

  const qs = params.toString();
  const endpoint = qs ? `/api/v1/submissions?${qs}` : "/api/v1/submissions";

  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }

  return fetchJson<ResearchSubmissionListResponse>(endpoint, { headers, signal });
}

export async function fetchSubmissionSummary(
  userId?: string,
  signal?: AbortSignal
): Promise<SubmissionSummaryResponse> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }
  return fetchJson<SubmissionSummaryResponse>("/api/v1/submissions/summary", {
    headers,
    signal,
  });
}

export async function fetchSubmission(
  submissionId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<ResearchSubmission> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }
  return fetchJson<ResearchSubmission>(`/api/v1/submissions/${submissionId}`, {
    headers,
    signal,
  });
}

export async function fetchWorkspaceSubmissions(
  workspaceItemId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<ResearchSubmissionListResponse> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }
  return fetchJson<ResearchSubmissionListResponse>(
    `/api/v1/workspace/${workspaceItemId}/submissions`,
    {
      headers,
      signal,
    }
  );
}

export async function createSubmission(
  payload: ResearchSubmissionCreate,
  userId?: string,
  signal?: AbortSignal
): Promise<ResearchSubmission> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }
  return fetchJson<ResearchSubmission>("/api/v1/submissions", {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
    signal,
  });
}

export async function updateSubmission(
  submissionId: string,
  payload: ResearchSubmissionUpdate,
  userId?: string,
  signal?: AbortSignal
): Promise<ResearchSubmission> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }
  return fetchJson<ResearchSubmission>(`/api/v1/submissions/${submissionId}`, {
    method: "PATCH",
    headers,
    body: JSON.stringify(payload),
    signal,
  });
}

export async function transitionSubmissionStatus(
  submissionId: string,
  payload: SubmissionStatusTransition,
  userId?: string,
  signal?: AbortSignal
): Promise<ResearchSubmission> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }
  return fetchJson<ResearchSubmission>(
    `/api/v1/submissions/${submissionId}/transition`,
    {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
      signal,
    }
  );
}

export async function deleteSubmission(
  submissionId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<void> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }
  await fetchJson<void>(`/api/v1/submissions/${submissionId}`, {
    method: "DELETE",
    headers,
    signal,
  });
}
