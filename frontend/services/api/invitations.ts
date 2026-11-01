import type { MyWorkspaceInvitationsResponse, WorkspaceMember } from "../../types/collaboration";
import { fetchJson } from "./client";

/** Audit FUNC-01: what the signed-in account was invited to, and the workspaces it joined. */
export async function fetchMyWorkspaceInvitations(signal?: AbortSignal): Promise<MyWorkspaceInvitationsResponse> {
  return fetchJson<MyWorkspaceInvitationsResponse>("/api/v1/workspace-invitations/mine", { signal });
}

export async function acceptMyWorkspaceInvitation(invitationId: string, signal?: AbortSignal): Promise<WorkspaceMember> {
  return fetchJson<WorkspaceMember>(`/api/v1/workspace-invitations/${encodeURIComponent(invitationId)}/accept`, { method: "POST", signal });
}

export async function declineMyWorkspaceInvitation(invitationId: string, signal?: AbortSignal): Promise<void> {
  await fetchJson<void>(`/api/v1/workspace-invitations/${encodeURIComponent(invitationId)}/decline`, { method: "POST", signal });
}
