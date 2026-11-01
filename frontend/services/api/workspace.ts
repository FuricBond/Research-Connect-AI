import type { WorkspaceFilterParams, WorkspaceItem, WorkspaceItemCreatePayload, WorkspaceItemUpdatePayload, WorkspaceListResponse, WorkspaceStatus, WorkspaceSummaryResponse } from "../../types/workspace";
import { fetchJson } from "./client";

// ── Phase 4.1 Opportunity Workspace API ──────────────────────────────────────

export async function fetchWorkspaceItems(
  filters: WorkspaceFilterParams = {},
  userId?: string,
  signal?: AbortSignal
): Promise<WorkspaceListResponse> {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.priority) params.set("priority", filters.priority);
  if (filters.tag) params.set("tag", filters.tag);
  if (filters.search) params.set("search", filters.search);
  if (filters.include_archived) params.set("include_archived", "true");
  if (filters.sort_by) params.set("sort_by", filters.sort_by);
  if (filters.sort_order) params.set("sort_order", filters.sort_order);
  if (filters.limit) params.set("limit", String(filters.limit));
  if (filters.offset) params.set("offset", String(filters.offset));

  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }

  const query = params.toString();
  return fetchJson<WorkspaceListResponse>(
    `/api/v1/workspace${query ? `?${query}` : ""}`,
    {
      headers,
      signal,
    }
  );
}

export async function fetchWorkspaceSummary(
  userId?: string,
  signal?: AbortSignal
): Promise<WorkspaceSummaryResponse> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }

  return fetchJson<WorkspaceSummaryResponse>("/api/v1/workspace/summary", {
    headers,
    signal,
  });
}

export async function fetchWorkspaceItem(
  itemId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<WorkspaceItem> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }

  return fetchJson<WorkspaceItem>(`/api/v1/workspace/${itemId}`, {
    headers,
    signal,
  });
}

export async function addOpportunityToWorkspace(
  payload: WorkspaceItemCreatePayload,
  userId?: string,
  signal?: AbortSignal
): Promise<WorkspaceItem> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }

  return fetchJson<WorkspaceItem>("/api/v1/workspace", {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
    signal,
  });
}

export async function updateWorkspaceItem(
  itemId: string,
  payload: WorkspaceItemUpdatePayload,
  userId?: string,
  signal?: AbortSignal
): Promise<WorkspaceItem> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }

  return fetchJson<WorkspaceItem>(`/api/v1/workspace/${itemId}`, {
    method: "PATCH",
    headers,
    body: JSON.stringify(payload),
    signal,
  });
}

export async function transitionWorkspaceStatus(
  itemId: string,
  targetStatus: WorkspaceStatus,
  notes?: string,
  userId?: string,
  signal?: AbortSignal
): Promise<WorkspaceItem> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }

  return fetchJson<WorkspaceItem>(`/api/v1/workspace/${itemId}/transition`, {
    method: "POST",
    headers,
    body: JSON.stringify({ target_status: targetStatus, notes }),
    signal,
  });
}

export async function archiveWorkspaceItem(
  itemId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<WorkspaceItem> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }

  return fetchJson<WorkspaceItem>(`/api/v1/workspace/${itemId}/archive`, {
    method: "POST",
    headers,
    signal,
  });
}

export async function unarchiveWorkspaceItem(
  itemId: string,
  targetStatus: WorkspaceStatus = "SAVED",
  userId?: string,
  signal?: AbortSignal
): Promise<WorkspaceItem> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }

  return fetchJson<WorkspaceItem>(
    `/api/v1/workspace/${itemId}/unarchive?target_status=${targetStatus}`,
    {
      method: "POST",
      headers,
      signal,
    }
  );
}

export async function removeWorkspaceItem(
  itemId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<void> {
  const headers: Record<string, string> = {};
  if (userId) {
    headers["X-User-ID"] = userId;
  }

  await fetchJson<void>(`/api/v1/workspace/${itemId}`, {
    method: "DELETE",
    headers,
    signal,
  });
}
