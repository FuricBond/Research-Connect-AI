import type { WorkspaceMemberListResponse } from "../../types/collaboration";
import { fetchJson } from "./client";

/** On its own: an item's page reads its members, whichever tab is open. */
export async function getWorkspaceMembers(
  workspaceId: string,
  status?: string,
  userId?: string,
  signal?: AbortSignal
): Promise<WorkspaceMemberListResponse> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  return fetchJson<WorkspaceMemberListResponse>(
    `/api/v1/workspaces/${workspaceId}/members${query}`,
    { headers, signal }
  );
}
