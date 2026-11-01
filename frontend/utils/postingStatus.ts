/** An application's and a posting's status in words, tone and icon (DESIGN_SYSTEM.md §3.2). */
import { Archive, CheckCircle2, CircleDashed, Eye, FileCheck2, Gift, Undo2, XCircle } from "lucide-react";
import { lookup, type StatusMeta } from "./statusMeta";

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
