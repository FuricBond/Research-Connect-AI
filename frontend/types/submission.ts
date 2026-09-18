/**
 * Phase 4.2 & 4.3 — Research Submission & Document Management Types.
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

export type DocumentType =
  | "ABSTRACT"
  | "FULL_PAPER"
  | "COVER_LETTER"
  | "AUTHOR_BIO"
  | "CV"
  | "SUPPLEMENTARY"
  | "FIGURES"
  | "DATASET"
  | "CODE"
  | "DISCLOSURE"
  | "OTHER";

export type DocumentStatus =
  | "REQUIRED"
  | "MISSING"
  | "DRAFT"
  | "READY"
  | "REJECTED"
  | "ARCHIVED";

export type SubmissionEventType =
  | "SUBMISSION_CREATED"
  | "METADATA_UPDATED"
  | "STATUS_TRANSITIONED"
  | "DOCUMENT_ADDED"
  | "DOCUMENT_UPDATED"
  | "DOCUMENT_VERSION_CREATED"
  | "DOCUMENT_STATUS_CHANGED"
  | "DOCUMENT_ARCHIVED"
  | "DOCUMENT_DELETED"
  | "READINESS_EVALUATED";

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

// ── Phase 4.3: Submission Document & Version Types ───────────────────────────

export interface SubmissionDocumentVersion {
  id: string;
  document_id: string;
  version_number: number;
  title: string;
  file_metadata: Record<string, any>;
  storage_reference?: string | null;
  checksum?: string | null;
  status: string;
  created_at: string;
  created_by_id?: string | null;
}

export interface SubmissionDocument {
  id: string;
  submission_id: string;
  document_type: DocumentType;
  title: string;
  description?: string | null;
  status: DocumentStatus;
  is_required: boolean;
  current_version: number;
  file_metadata: Record<string, any>;
  storage_reference?: string | null;
  completed_at?: string | null;
  created_at: string;
  updated_at: string;
  versions_count: number;
  latest_versions?: SubmissionDocumentVersion[];
}

export type ResearchSubmissionDocument = SubmissionDocument;

export interface DocumentFilterParams {
  document_type?: DocumentType;
  status?: DocumentStatus;
  is_required?: boolean;
  limit?: number;
  offset?: number;
}


export interface SubmissionDocumentCreate {
  document_type: DocumentType;
  title: string;
  description?: string | null;
  is_required?: boolean;
  status?: DocumentStatus;
  file_metadata?: Record<string, any>;
  storage_reference?: string | null;
}

export interface SubmissionDocumentUpdate {
  title?: string | null;
  description?: string | null;
  document_type?: DocumentType | null;
  status?: DocumentStatus | null;
  is_required?: boolean | null;
  file_metadata?: Record<string, any> | null;
  storage_reference?: string | null;
  create_new_version?: boolean;
}

export interface SubmissionDocumentListResponse {
  items: SubmissionDocument[];
  total_count: number;
  submission_id: string;
  counts_by_status: Record<string, number>;
  counts_by_type: Record<string, number>;
}

// ── Phase 4.3: Readiness Assessment Types ───────────────────────────────────

export interface SubmissionReadinessIssue {
  code: string;
  message: string;
  is_blocking: boolean;
  document_id?: string | null;
  field?: string | null;
}

export interface SubmissionReadinessResponse {
  submission_id: string;
  overall_readiness: "READY" | "NOT_READY" | "BLOCKED" | "UNKNOWN" | string;
  can_mark_submission_ready: boolean;
  readiness_percentage: number;
  total_document_count: number;
  required_document_count: number;
  completed_document_count: number;
  missing_document_count: number;
  draft_document_count: number;
  rejected_document_count: number;
  archived_document_count: number;
  metadata_completeness: number;
  blocking_issues: SubmissionReadinessIssue[];
  warnings: SubmissionReadinessIssue[];
  readiness_explanation: string;
  deadline_context?: SubmissionDeadlineContext | null;
}

// ── Phase 4.3: Audit Trail History Types ─────────────────────────────────────

export interface SubmissionHistoryEvent {
  id: string;
  submission_id: string;
  event_type: SubmissionEventType;
  document_id?: string | null;
  description: string;
  old_state?: Record<string, any> | null;
  new_state?: Record<string, any> | null;
  created_at: string;
  created_by_id?: string | null;
}

export interface SubmissionHistoryResponse {
  items: SubmissionHistoryEvent[];
  total_count: number;
  submission_id: string;
}
