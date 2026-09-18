/**
 * Phase 4.2 — Research Submission Management & Tracking Types.
 */

export type SubmissionStatus =
  | "DRAFT"
  | "READY"
  | "SUBMITTED"
  | "UNDER_REVIEW"
  | "ACCEPTED"
  | "REJECTED"
  | "WITHDRAWN";

export type SubmissionType =
  | "FULL_PAPER"
  | "SHORT_PAPER"
  | "EXTENDED_ABSTRACT"
  | "POSTER"
  | "WORKSHOP_PAPER"
  | "GRANT_PROPOSAL"
  | "OTHER";

export interface SubmissionDeadlineContext {
  submission_deadline?: string | null;
  days_remaining?: number | null;
  urgency_tier?: string | null;
  is_aoe: boolean;
  has_extension: boolean;
  has_conflict: boolean;
  summary?: string | null;
}

export interface ResearchSubmission {
  id: string;
  workspace_item_id: string;
  title: string;
  abstract?: string | null;
  submission_type: SubmissionType;
  status: SubmissionStatus;
  external_submission_id?: string | null;
  venue?: string | null;
  submission_url?: string | null;
  notes?: string | null;
  submitted_at?: string | null;
  decision_at?: string | null;
  status_updated_at: string;
  created_at: string;
  updated_at: string;
  allowed_transitions: SubmissionStatus[];
  workspace_status: string;
  opportunity_id: string;
  opportunity_title: string;
  venue_name?: string | null;
  deadline_context?: SubmissionDeadlineContext | null;
}

export interface ResearchSubmissionCreate {
  workspace_item_id: string;
  title: string;
  abstract?: string | null;
  submission_type?: SubmissionType;
  external_submission_id?: string | null;
  venue?: string | null;
  submission_url?: string | null;
  notes?: string | null;
}

export interface ResearchSubmissionUpdate {
  title?: string | null;
  abstract?: string | null;
  submission_type?: SubmissionType | null;
  external_submission_id?: string | null;
  venue?: string | null;
  submission_url?: string | null;
  notes?: string | null;
}

export interface SubmissionStatusTransition {
  target_status: SubmissionStatus;
  notes?: string | null;
}

export interface ResearchSubmissionListResponse {
  items: ResearchSubmission[];
  total_count: number;
  counts_by_status: Record<string, number>;
  counts_by_type: Record<string, number>;
}

export interface SubmissionSummaryResponse {
  total_submissions: number;
  active_submissions: number;
  accepted_submissions: number;
  rejected_submissions: number;
  withdrawn_submissions: number;
  counts_by_status: Record<string, number>;
  counts_by_type: Record<string, number>;
}
