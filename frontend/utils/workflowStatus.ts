/** A submission's, document's, task's and invitation's status, and readiness (DESIGN_SYSTEM.md §3.2). */
import { Archive, CheckCircle2, Circle, CircleDashed, Clock, Eye, FileCheck2, Undo2, XCircle } from "lucide-react";
import { lookup, type StatusMeta } from "./statusMeta";

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
  REVIEW: { label: "In review", tone: "info", icon: Eye },
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
