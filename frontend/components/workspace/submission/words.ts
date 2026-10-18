import type { DocumentStatus, DocumentType, SubmissionEventType, SubmissionStatus, SubmissionType } from "../../../types/submission";
import { humanizeEnum } from "../../../utils/date";

export const SUBMISSION_TYPES: { value: SubmissionType; label: string }[] = [
  { value: "FULL_PAPER", label: "Full paper" },
  { value: "SHORT_PAPER", label: "Short paper" },
  { value: "EXTENDED_ABSTRACT", label: "Extended abstract" },
  { value: "POSTER", label: "Poster" },
  { value: "WORKSHOP_PAPER", label: "Workshop paper" },
  { value: "GRANT_PROPOSAL", label: "Grant proposal" },
  { value: "OTHER", label: "Other" },
];

export const DOCUMENT_TYPES: { value: DocumentType; label: string }[] = [
  { value: "FULL_PAPER", label: "Full paper" },
  { value: "ABSTRACT", label: "Abstract" },
  { value: "COVER_LETTER", label: "Cover letter" },
  { value: "AUTHOR_BIO", label: "Author biography" },
  { value: "CV", label: "CV" },
  { value: "SUPPLEMENTARY", label: "Supplementary material" },
  { value: "FIGURES", label: "Figures and tables" },
  { value: "DATASET", label: "Dataset or artifact" },
  { value: "CODE", label: "Source code or notebooks" },
  { value: "DISCLOSURE", label: "Conflict or disclosure statement" },
  { value: "OTHER", label: "Other document" },
];

/** Statuses a person may give a document when adding it, and when recording a new version. */
export const NEW_DOCUMENT_STATUSES: DocumentStatus[] = ["DRAFT", "REQUIRED", "READY"];
export const VERSION_STATUSES: DocumentStatus[] = ["READY", "DRAFT", "REQUIRED", "REJECTED", "ARCHIVED"];

export function submissionTypeLabel(type: string | null | undefined): string {
  return SUBMISSION_TYPES.find((entry) => entry.value === type)?.label ?? humanizeEnum(type);
}

export function documentTypeLabel(type: string | null | undefined): string {
  return DOCUMENT_TYPES.find((entry) => entry.value === type)?.label ?? humanizeEnum(type);
}

/** The lifecycle as steps; the last step is the decision (accepted or not). */
export const LIFECYCLE: { status: SubmissionStatus; label: string }[] = [
  { status: "DRAFT", label: "Draft" },
  { status: "READY", label: "Ready" },
  { status: "SUBMITTED", label: "Submitted" },
  { status: "UNDER_REVIEW", label: "Under review" },
  { status: "ACCEPTED", label: "Decision" },
];

const ORDER: Record<SubmissionStatus, number> = { DRAFT: 0, READY: 1, SUBMITTED: 2, UNDER_REVIEW: 3, ACCEPTED: 4, REJECTED: 4, WITHDRAWN: -1 };

export type StepState = "done" | "current" | "upcoming";

/** Where a step stands for a submission in `status` (a withdrawn submission has no current step). */
export function stepState(step: SubmissionStatus, status: SubmissionStatus): StepState {
  const at = ORDER[status] ?? 0;
  const index = ORDER[step] ?? 0;
  if (at < 0) return "upcoming";
  if (index < at) return "done";
  if (index === at) return "current";
  return "upcoming";
}

/**
 * The words on a status change, by the target (and where it comes from). Only targets the server
 * lists in `allowed_transitions` are ever offered.
 */
export function transitionLabel(target: SubmissionStatus, from: SubmissionStatus): string {
  switch (target) {
    case "READY":
      return "Mark ready to submit";
    case "SUBMITTED":
      return "Mark as submitted";
    case "UNDER_REVIEW":
      return "Mark as under review";
    case "ACCEPTED":
      return "Record acceptance";
    case "REJECTED":
      return "Record rejection";
    case "WITHDRAWN":
      return "Withdraw";
    case "DRAFT":
      return from === "READY" ? "Back to draft" : "Reopen as a draft";
    default:
      return `Move to ${humanizeEnum(target).toLowerCase()}`;
  }
}

/** The forward step is the primary action; withdrawing and recording a rejection are secondary. */
export function isForward(target: SubmissionStatus, from: SubmissionStatus): boolean {
  if (target === "WITHDRAWN" || target === "REJECTED") return false;
  if (target === "DRAFT") return from !== "READY";
  return true;
}

const EVENTS: Record<string, string> = {
  SUBMISSION_CREATED: "Submission created",
  METADATA_UPDATED: "Details changed",
  STATUS_TRANSITIONED: "Status changed",
  DOCUMENT_ADDED: "Document added",
  DOCUMENT_UPDATED: "Document changed",
  DOCUMENT_VERSION_CREATED: "New document version",
  DOCUMENT_STATUS_CHANGED: "Document status changed",
  DOCUMENT_ARCHIVED: "Document archived",
  DOCUMENT_DELETED: "Document deleted",
  READINESS_EVALUATED: "Readiness checked",
};

export function eventLabel(type: SubmissionEventType | string): string {
  return EVENTS[type] ?? humanizeEnum(type);
}
