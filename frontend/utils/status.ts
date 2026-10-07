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
