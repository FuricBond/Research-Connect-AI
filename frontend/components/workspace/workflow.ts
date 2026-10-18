import { ApiError } from "../../services/api";
import type { WorkspaceRole } from "../../types/collaboration";
import type { WorkspaceItem } from "../../types/workspace";

/** "12 Oct 2026", in the reader's time zone; null when there is no date. */
export function shortDate(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

/** "12 Oct 2026, 14:05". */
export function dateTime(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleString(undefined, { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

/**
 * What to say when a change fails. The server's own words are used where they explain a refusal
 * (a 400/409/422 such as "Cannot transition submission to 'READY': 2 blocking readiness issues"),
 * never for a server error, and never a status code.
 */
export function actionError(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    if (error.status === 403) return `${fallback} Your role on this item does not allow it.`;
    if (error.status === 404) return `${fallback} It no longer exists; reload the page.`;
    if ((error.status === 400 || error.status === 409 || error.status === 422) && error.detail && !error.detail.startsWith("Request failed")) {
      return `${fallback} ${error.detail}`;
    }
    if (error.status === 429) return `${fallback} Too many requests; wait a moment and try again.`;
    return `${fallback} Try again.`;
  }
  return `${fallback} Check your connection and try again.`;
}

/** What a role may do on a shared item (backend WorkspaceAuthorizationService). */
export interface Abilities {
  role: WorkspaceRole | null;
  /** VIEWER and up: read everything. */
  view: boolean;
  /** CONTRIBUTOR and up: tasks, documents, notes. */
  contribute: boolean;
  /** EDITOR and up: status, item details, submissions, deleting documents and others' tasks. */
  edit: boolean;
  /** OWNER: members, invitations, deleting submissions, removing the item. */
  manage: boolean;
}

export function abilities(role: WorkspaceRole | null): Abilities {
  return {
    role,
    view: role !== null,
    contribute: role === "OWNER" || role === "EDITOR" || role === "CONTRIBUTOR",
    edit: role === "OWNER" || role === "EDITOR",
    manage: role === "OWNER",
  };
}

/**
 * The viewer's role on an item: its owner is OWNER without asking; anyone else's role comes from
 * the member list (null until it has loaded, so nothing is offered before it is known).
 */
export function roleOn(item: WorkspaceItem | undefined, userId: string | null | undefined, members: { user_id: string; role: WorkspaceRole; status: string }[] | undefined): WorkspaceRole | null {
  if (!item || !userId) return null;
  if (item.user_id === userId) return "OWNER";
  const member = members?.find((entry) => entry.user_id === userId && entry.status === "ACTIVE");
  return member?.role ?? null;
}
