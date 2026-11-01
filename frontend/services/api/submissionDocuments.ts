import type { DocumentFilterParams, ResearchSubmissionDocument, SubmissionDocumentCreate, SubmissionDocumentListResponse, SubmissionDocumentUpdate, SubmissionDocumentVersion, SubmissionHistoryResponse, SubmissionReadinessResponse } from "../../types/submission";
import { fetchJson } from "./client";

// ── Phase 4.3 — Submission Documents, Versions, Readiness & History API ─────

export async function fetchSubmissionDocuments(
  submissionId: string,
  filters: DocumentFilterParams = {},
  userId?: string,
  signal?: AbortSignal
): Promise<SubmissionDocumentListResponse> {
  const params = new URLSearchParams();
  if (filters.document_type) params.set("document_type", filters.document_type);
  if (filters.status) params.set("status", filters.status);
  if (filters.is_required !== undefined) params.set("is_required", String(filters.is_required));
  if (filters.limit) params.set("limit", String(filters.limit));
  if (filters.offset) params.set("offset", String(filters.offset));

  const qs = params.toString();
  const endpoint = qs
    ? `/api/v1/submissions/${submissionId}/documents?${qs}`
    : `/api/v1/submissions/${submissionId}/documents`;

  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }

  return fetchJson<SubmissionDocumentListResponse>(endpoint, { headers, signal });
}

export async function fetchSubmissionDocument(
  submissionId: string,
  documentId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<ResearchSubmissionDocument> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }
  return fetchJson<ResearchSubmissionDocument>(
    `/api/v1/submissions/${submissionId}/documents/${documentId}`,
    { headers, signal }
  );
}

export async function createSubmissionDocument(
  submissionId: string,
  payload: SubmissionDocumentCreate,
  userId?: string,
  signal?: AbortSignal
): Promise<ResearchSubmissionDocument> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }
  return fetchJson<ResearchSubmissionDocument>(
    `/api/v1/submissions/${submissionId}/documents`,
    {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
      signal,
    }
  );
}

export async function updateSubmissionDocument(
  submissionId: string,
  documentId: string,
  payload: SubmissionDocumentUpdate,
  userId?: string,
  signal?: AbortSignal
): Promise<ResearchSubmissionDocument> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }
  return fetchJson<ResearchSubmissionDocument>(
    `/api/v1/submissions/${submissionId}/documents/${documentId}`,
    {
      method: "PATCH",
      headers,
      body: JSON.stringify(payload),
      signal,
    }
  );
}

export async function deleteSubmissionDocument(
  submissionId: string,
  documentId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<void> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }
  await fetchJson<void>(`/api/v1/submissions/${submissionId}/documents/${documentId}`, {
    method: "DELETE",
    headers,
    signal,
  });
}

export async function fetchDocumentVersions(
  submissionId: string,
  documentId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<SubmissionDocumentVersion[]> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }
  return fetchJson<SubmissionDocumentVersion[]>(
    `/api/v1/submissions/${submissionId}/documents/${documentId}/versions`,
    { headers, signal }
  );
}

export async function fetchSubmissionReadiness(
  submissionId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<SubmissionReadinessResponse> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }
  return fetchJson<SubmissionReadinessResponse>(
    `/api/v1/submissions/${submissionId}/readiness`,
    { headers, signal }
  );
}

export async function fetchSubmissionHistory(
  submissionId: string,
  options: { limit?: number; offset?: number } = {},
  userId?: string,
  signal?: AbortSignal
): Promise<SubmissionHistoryResponse> {
  const params = new URLSearchParams();
  if (options.limit) params.set("limit", String(options.limit));
  if (options.offset) params.set("offset", String(options.offset));

  const qs = params.toString();
  const endpoint = qs
    ? `/api/v1/submissions/${submissionId}/history?${qs}`
    : `/api/v1/submissions/${submissionId}/history`;

  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }

  return fetchJson<SubmissionHistoryResponse>(endpoint, { headers, signal });
}
