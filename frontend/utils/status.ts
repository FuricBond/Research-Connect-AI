/**
 * Domain status → words, tone and icon (DESIGN_SYSTEM.md §3.2, "StatusBadge").
 *
 * Every status shown to a person goes through one of these maps, so the interface never shows
 * an enum value (UNDER_REVIEW, IN_APP) and the same status looks the same everywhere.
 * Unknown values fall back to a sentence-case rendering, never to the raw enum.
 */
import type { LucideIcon } from "lucide-react";
import { Archive, CheckCircle2, Circle, CircleDashed, Clock, Eye, FileCheck2, Gift, Undo2, XCircle } from "lucide-react";
import { humanizeEnum } from "./date";

export type StatusTone = "neutral" | "brand" | "brand-strong" | "info" | "success" | "warning" | "danger" | "muted";

export interface StatusMeta {
  label: string;
  tone: StatusTone;
  icon?: LucideIcon;
}

function lookup(map: Record<string, StatusMeta>, value: string | null | undefined): StatusMeta {
  if (!value) return { label: "Unknown", tone: "muted", icon: CircleDashed };
  return map[value] ?? { label: humanizeEnum(value), tone: "neutral" };
}

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

/** Rejection is not an error and is never red. */
const APPLICATION_STATUS: Record<string, StatusMeta> = {
  SUBMITTED: { label: "Submitted", tone: "neutral", icon: FileCheck2 },
  UNDER_REVIEW: { label: "Under review", tone: "info", icon: Eye },
  SHORTLISTED: { label: "Shortlisted", tone: "brand", icon: CheckCircle2 },
  OFFERED: { label: "Offer made", tone: "brand-strong", icon: Gift },
  ACCEPTED: { label: "Accepted", tone: "success", icon: CheckCircle2 },
  REJECTED: { label: "Not selected", tone: "muted", icon: XCircle },
  DECLINED: { label: "Declined", tone: "muted", icon: XCircle },
  WITHDRAWN: { label: "Withdrawn", tone: "muted", icon: Undo2 },
};

export function applicationStatusMeta(status: string | null | undefined): StatusMeta {
  return lookup(APPLICATION_STATUS, status);
}

const POSTING_STATUS: Record<string, StatusMeta> = {
  DRAFT: { label: "Draft", tone: "neutral", icon: CircleDashed },
  OPEN: { label: "Open", tone: "success", icon: CheckCircle2 },
  CLOSED: { label: "Closed", tone: "muted", icon: XCircle },
  FILLED: { label: "Filled", tone: "muted", icon: CheckCircle2 },
  CANCELLED: { label: "Cancelled", tone: "muted", icon: XCircle },
  ARCHIVED: { label: "Archived", tone: "muted", icon: Archive },
};

export function postingStatusMeta(status: string | null | undefined): StatusMeta {
  return lookup(POSTING_STATUS, status);
}

/** P7: a submission's lifecycle (backend VALID_SUBMISSION_TRANSITIONS). */
const SUBMISSION_STATUS: Record<string, StatusMeta> = {
  DRAFT: { label: "Draft", tone: "neutral", icon: CircleDashed },
  READY: { label: "Ready to submit", tone: "brand", icon: CheckCircle2 },
  SUBMITTED: { label: "Submitted", tone: "brand", icon: FileCheck2 },
  UNDER_REVIEW: { label: "Under review", tone: "info", icon: Eye },
  ACCEPTED: { label: "Accepted", tone: "success", icon: CheckCircle2 },
  REJECTED: { label: "Not accepted", tone: "muted", icon: XCircle },
  WITHDRAWN: { label: "Withdrawn", tone: "muted", icon: Undo2 },
};

export function submissionStatusMeta(status: string | null | undefined): StatusMeta {
  return lookup(SUBMISSION_STATUS, status);
}

const DOCUMENT_STATUS: Record<string, StatusMeta> = {
  REQUIRED: { label: "Needed", tone: "warning", icon: CircleDashed },
  MISSING: { label: "Missing", tone: "warning", icon: CircleDashed },
  DRAFT: { label: "Draft", tone: "neutral", icon: Circle },
  READY: { label: "Ready", tone: "success", icon: CheckCircle2 },
  REJECTED: { label: "Rejected", tone: "muted", icon: XCircle },
  ARCHIVED: { label: "Archived", tone: "muted", icon: Archive },
};

export function documentStatusMeta(status: string | null | undefined): StatusMeta {
  return lookup(DOCUMENT_STATUS, status);
}

const TASK_STATUS: Record<string, StatusMeta> = {
  TODO: { label: "To do", tone: "neutral", icon: Circle },
  IN_PROGRESS: { label: "In progress", tone: "brand", icon: Clock },
  IN_REVIEW: { label: "In review", tone: "info", icon: Eye },
  COMPLETED: { label: "Done", tone: "success", icon: CheckCircle2 },
  CANCELLED: { label: "Cancelled", tone: "muted", icon: XCircle },
};

export function taskStatusMeta(status: string | null | undefined): StatusMeta {
  return lookup(TASK_STATUS, status);
}

const INVITATION_STATUS: Record<string, StatusMeta> = {
  PENDING: { label: "Waiting for an answer", tone: "info", icon: Clock },
  ACCEPTED: { label: "Accepted", tone: "success", icon: CheckCircle2 },
  DECLINED: { label: "Declined", tone: "muted", icon: XCircle },
  EXPIRED: { label: "Expired", tone: "muted", icon: CircleDashed },
  REVOKED: { label: "Withdrawn", tone: "muted", icon: Undo2 },
};

export function invitationStatusMeta(status: string | null | undefined): StatusMeta {
  return lookup(INVITATION_STATUS, status);
}

/** The readiness check (Phase 4.3): blocked is a warning to act on, not an error. */
const READINESS: Record<string, StatusMeta> = {
  READY: { label: "Ready", tone: "success", icon: CheckCircle2 },
  NOT_READY: { label: "Not ready yet", tone: "warning", icon: Clock },
  BLOCKED: { label: "Blocked", tone: "warning", icon: XCircle },
  UNKNOWN: { label: "Not checked", tone: "muted", icon: CircleDashed },
};

export function readinessMeta(status: string | null | undefined): StatusMeta {
  return lookup(READINESS, status);
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

/** Priority is a word (with a level glyph), never a status colour. */
const PRIORITY: Record<string, { label: string; level: 1 | 2 | 3 | 4 }> = {
  LOW: { label: "Low", level: 1 },
  MEDIUM: { label: "Medium", level: 2 },
  HIGH: { label: "High", level: 3 },
  URGENT: { label: "Urgent", level: 4 },
};

export function priorityMeta(priority: string | null | undefined): { label: string; level: 1 | 2 | 3 | 4 } {
  if (!priority) return { label: "No priority", level: 1 };
  return PRIORITY[priority] ?? { label: humanizeEnum(priority), level: 2 };
}
