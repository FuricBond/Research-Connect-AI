import type { TaskFilterParams, WorkspaceActivity, WorkspaceActivityListResponse, WorkspaceCommentCreatePayload, WorkspaceInvitationCreatePayload, WorkspaceInvitationCreateResponse, WorkspaceInvitationListResponse, WorkspaceMember, WorkspaceMemberAddPayload, WorkspaceMemberListResponse, WorkspaceMemberRoleUpdatePayload, WorkspaceTask, WorkspaceTaskAssignPayload, WorkspaceTaskCreatePayload, WorkspaceTaskListResponse, WorkspaceTaskUpdatePayload } from "../../types/collaboration";
import { fetchJson } from "./client";

// ── Phase 4.6 Workspace Collaboration API Methods ──

export async function addWorkspaceMember(
  workspaceId: string,
  payload: WorkspaceMemberAddPayload,
  userId?: string,
  signal?: AbortSignal
): Promise<WorkspaceMember> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<WorkspaceMember>(
    `/api/v1/workspaces/${workspaceId}/members`,
    { method: "POST", headers, body: JSON.stringify(payload), signal }
  );
}

export async function updateWorkspaceMemberRole(
  workspaceId: string,
  memberId: string,
  payload: WorkspaceMemberRoleUpdatePayload,
  userId?: string,
  signal?: AbortSignal
): Promise<WorkspaceMember> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<WorkspaceMember>(
    `/api/v1/workspaces/${workspaceId}/members/${memberId}/role`,
    { method: "PATCH", headers, body: JSON.stringify(payload), signal }
  );
}

export async function removeWorkspaceMember(
  workspaceId: string,
  memberId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<void> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  await fetchJson<void>(`/api/v1/workspaces/${workspaceId}/members/${memberId}`, {
    method: "DELETE",
    headers,
    signal,
  });
}

export async function getWorkspaceInvitations(
  workspaceId: string,
  status?: string,
  userId?: string,
  signal?: AbortSignal
): Promise<WorkspaceInvitationListResponse> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  return fetchJson<WorkspaceInvitationListResponse>(
    `/api/v1/workspaces/${workspaceId}/invitations${query}`,
    { headers, signal }
  );
}

export async function createWorkspaceInvitation(
  workspaceId: string,
  payload: WorkspaceInvitationCreatePayload,
  userId?: string,
  signal?: AbortSignal
): Promise<WorkspaceInvitationCreateResponse> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<WorkspaceInvitationCreateResponse>(
    `/api/v1/workspaces/${workspaceId}/invitations`,
    { method: "POST", headers, body: JSON.stringify(payload), signal }
  );
}

export async function acceptWorkspaceInvitation(
  token: string,
  userId?: string,
  signal?: AbortSignal
): Promise<WorkspaceMember> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<WorkspaceMember>(
    `/api/v1/workspaces/invitations/${encodeURIComponent(token)}/accept`,
    { method: "POST", headers, signal }
  );
}

export async function declineWorkspaceInvitation(
  token: string,
  userId?: string,
  signal?: AbortSignal
): Promise<void> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<void>(
    `/api/v1/workspaces/invitations/${encodeURIComponent(token)}/decline`,
    { method: "POST", headers, signal }
  );
}

export async function revokeWorkspaceInvitation(
  workspaceId: string,
  invitationId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<void> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<void>(
    `/api/v1/workspaces/${workspaceId}/invitations/${invitationId}`,
    { method: "DELETE", headers, signal }
  );
}

export async function getWorkspaceTasks(
  workspaceId: string,
  params?: TaskFilterParams,
  userId?: string,
  signal?: AbortSignal
): Promise<WorkspaceTaskListResponse> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;

  const q = new URLSearchParams();
  if (params?.assignee_id) q.set("assignee_id", params.assignee_id);
  if (params?.status) q.set("status", params.status);
  if (params?.priority) q.set("priority", params.priority);
  if (params?.due_before) q.set("due_before", params.due_before);
  if (params?.limit) q.set("limit", String(params.limit));
  if (params?.offset) q.set("offset", String(params.offset));

  const qs = q.toString() ? `?${q.toString()}` : "";
  return fetchJson<WorkspaceTaskListResponse>(
    `/api/v1/workspaces/${workspaceId}/tasks${qs}`,
    { headers, signal }
  );
}

export async function createWorkspaceTask(
  workspaceId: string,
  payload: WorkspaceTaskCreatePayload,
  userId?: string,
  signal?: AbortSignal
): Promise<WorkspaceTask> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<WorkspaceTask>(
    `/api/v1/workspaces/${workspaceId}/tasks`,
    { method: "POST", headers, body: JSON.stringify(payload), signal }
  );
}

export async function updateWorkspaceTask(
  workspaceId: string,
  taskId: string,
  payload: WorkspaceTaskUpdatePayload,
  userId?: string,
  signal?: AbortSignal
): Promise<WorkspaceTask> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<WorkspaceTask>(
    `/api/v1/workspaces/${workspaceId}/tasks/${taskId}`,
    { method: "PATCH", headers, body: JSON.stringify(payload), signal }
  );
}

export async function assignWorkspaceTask(
  workspaceId: string,
  taskId: string,
  payload: WorkspaceTaskAssignPayload,
  userId?: string,
  signal?: AbortSignal
): Promise<WorkspaceTask> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<WorkspaceTask>(
    `/api/v1/workspaces/${workspaceId}/tasks/${taskId}/assign`,
    { method: "POST", headers, body: JSON.stringify(payload), signal }
  );
}

export async function completeWorkspaceTask(
  workspaceId: string,
  taskId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<WorkspaceTask> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<WorkspaceTask>(
    `/api/v1/workspaces/${workspaceId}/tasks/${taskId}/complete`,
    { method: "POST", headers, signal }
  );
}

export async function reopenWorkspaceTask(
  workspaceId: string,
  taskId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<WorkspaceTask> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<WorkspaceTask>(
    `/api/v1/workspaces/${workspaceId}/tasks/${taskId}/reopen`,
    { method: "POST", headers, signal }
  );
}

export async function deleteWorkspaceTask(
  workspaceId: string,
  taskId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<void> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  await fetchJson<void>(`/api/v1/workspaces/${workspaceId}/tasks/${taskId}`, {
    method: "DELETE",
    headers,
    signal,
  });
}

export async function getWorkspaceActivity(
  workspaceId: string,
  limit: number = 50,
  offset: number = 0,
  userId?: string,
  signal?: AbortSignal
): Promise<WorkspaceActivityListResponse> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<WorkspaceActivityListResponse>(
    `/api/v1/workspaces/${workspaceId}/activity?limit=${limit}&offset=${offset}`,
    { headers, signal }
  );
}

export async function addWorkspaceComment(
  workspaceId: string,
  payload: WorkspaceCommentCreatePayload,
  userId?: string,
  signal?: AbortSignal
): Promise<WorkspaceActivity> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<WorkspaceActivity>(
    `/api/v1/workspaces/${workspaceId}/comments`,
    { method: "POST", headers, body: JSON.stringify(payload), signal }
  );
}
