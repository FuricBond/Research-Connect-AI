/**
 * A workspace item's status and a member's role (DESIGN_SYSTEM.md §3.2). The other domains' maps are in
 * utils/postingStatus.ts and utils/workflowStatus.ts, a priority in utils/priority.ts, so a page loads
 * only the words and icons it shows (P12); the shape and fallback are in utils/statusMeta.ts.
 */
import { Archive, CheckCircle2, Circle, Clock, Eye, FileCheck2, XCircle } from "lucide-react";
import { humanizeEnum } from "./date";
import { lookup, type StatusMeta } from "./statusMeta";

export type { StatusMeta, StatusTone } from "./statusMeta";

/** Saved and Considering are neutral; Planning and Applied brand-tinted; outcomes success/muted. */
const WORKSPACE_STATUS: Record<string, StatusMeta> = {
  SAVED: { label: "Saved", tone: "neutral", icon: Circle },
  CONSIDERING: { label: "Considering", tone: "neutral", icon: Eye },
  PLANNING: { label: "Planning", tone: "brand", icon: Clock },
  APPLIED: { label: "Applied", tone: "brand", icon: FileCheck2 },
  ACCEPTED: { label: "Accepted", tone: "success", icon: CheckCircle2 },
  REJECTED: { label: "Not accepted", tone: "muted", icon: XCircle },
  ARCHIVED: { label: "Archived", tone: "muted", icon: Archive },
};

export function workspaceStatusMeta(status: string | null | undefined): StatusMeta {
  return lookup(WORKSPACE_STATUS, status);
}

const ROLE: Record<string, { label: string; description: string }> = {
  OWNER: { label: "Owner", description: "Manages members and everything else" },
  EDITOR: { label: "Editor", description: "Edits the item, its submissions and documents" },
  CONTRIBUTOR: { label: "Contributor", description: "Adds tasks, documents and notes" },
  VIEWER: { label: "Viewer", description: "Reads everything, changes nothing" },
};

export function workspaceRoleMeta(role: string | null | undefined): { label: string; description: string } {
  if (!role) return { label: "Unknown role", description: "" };
  return ROLE[role] ?? { label: humanizeEnum(role), description: "" };
}
