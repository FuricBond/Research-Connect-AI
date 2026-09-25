/**
 * Phase 5.10 — Faculty Research Postings.
 *
 * Mirrors backend/app/schemas/research_posting.py. Derived fields such as
 * `is_accepting_applications`, `days_until_deadline` and `allowed_transitions` are computed
 * server-side so every client agrees on them; the UI must render them, never recompute them.
 */

export type PostingType =
  // Phase 5.10 — supervisor-led opportunities
  | "PROJECT"
  | "THESIS_TOPIC"
  | "COLLABORATION"
  | "LAB_ROTATION"
  // Phase 5.11 — structured openings, which carry appointment terms
  | "INTERNSHIP"
  | "RESEARCH_ASSISTANTSHIP"
  | "POSTDOC";

export type CompensationType =
  | "STIPEND"
  | "SALARY"
  | "HOURLY"
  | "SCHOLARSHIP"
  | "GRANT_FUNDED"
  | "UNPAID"
  | "UNSPECIFIED";

export type CommitmentType = "FULL_TIME" | "PART_TIME" | "FLEXIBLE";

export type ApplicationStatus =
  | "SUBMITTED"
  | "UNDER_REVIEW"
  | "SHORTLISTED"
  | "OFFERED"
  | "ACCEPTED"
  | "DECLINED"
  | "REJECTED"
  | "WITHDRAWN";

/**
 * The structured terms of a funded appointment (Phase 5.11).
 *
 * `is_structured_opening` and `accepts_applications` are decided server-side: applications are
 * only handled on-platform for internships, assistantships and post-docs whose author opted in.
 */
export interface OpeningTerms {
  compensation_type: CompensationType;
  compensation_amount: number | null;
  compensation_currency: string | null;
  compensation_period: string | null;
  commitment_type: CommitmentType | null;
  hours_per_week: number | null;
  duration_months: number | null;
  eligibility_requirements: string | null;
  accepts_applications: boolean;
  is_structured_opening: boolean;
}

export interface OpeningTermsUpdate {
  compensation_type?: CompensationType;
  compensation_amount?: number | null;
  compensation_currency?: string | null;
  compensation_period?: string | null;
  commitment_type?: CommitmentType | null;
  hours_per_week?: number | null;
  duration_months?: number | null;
  eligibility_requirements?: string | null;
  accepts_applications?: boolean;
}

export type PostingStatus = "DRAFT" | "OPEN" | "CLOSED" | "FILLED" | "CANCELLED" | "ARCHIVED";

export type PostingWorkMode = "ONSITE" | "REMOTE" | "HYBRID";

export interface ResearchPostingAuthor {
  profile_id: string;
  full_name: string | null;
  institution: string | null;
  department: string | null;
  academic_status: string | null;
}

export interface PostingTopic {
  topic_id: string;
  name: string | null;
  slug: string | null;
  is_primary: boolean;
  confidence_score: number;
}

export interface ResearchPosting {
  id: string;
  author: ResearchPostingAuthor;
  title: string;
  posting_type: PostingType;
  status: PostingStatus;
  summary: string | null;
  description: string;
  required_skills: string[];
  preferred_qualifications: string | null;
  institution: string | null;
  department: string | null;
  location: string | null;
  country: string | null;
  work_mode: PostingWorkMode;
  positions_available: number;
  application_deadline: string | null;
  expected_start_date: string | null;
  expected_end_date: string | null;
  contact_email: string | null;
  external_url: string | null;
  topics: PostingTopic[];
  opening_terms: OpeningTerms;
  application_count: number;
  published_at: string | null;
  closed_at: string | null;
  archived_at: string | null;
  status_note: string | null;
  created_at: string;
  updated_at: string;
  /** OPEN and the application deadline has not passed. */
  is_accepting_applications: boolean;
  /** Whole days until the deadline; negative once it has passed, null when open-ended. */
  days_until_deadline: number | null;
  /** Lifecycle states this posting may move to next, as the server's state machine allows. */
  allowed_transitions: PostingStatus[];
  is_owner: boolean;
  /** The requesting researcher's own application to this posting, if any. */
  viewer_application_id: string | null;
  viewer_application_status: string | null;
}

export interface ApplicantSummary {
  profile_id: string;
  full_name: string | null;
  institution: string | null;
  department: string | null;
  academic_status: string | null;
}

export interface ApplicationStatusEvent {
  from_status: string | null;
  to_status: string;
  actor_role: string;
  reason: string | null;
  at: string;
}

/**
 * An application.
 *
 * `reviewer_note` is populated only when the posting's author is reading; the API omits it for
 * the applicant, so a candid internal assessment cannot leak as feedback.
 */
export interface PostingApplication {
  id: string;
  posting_id: string;
  posting_title: string | null;
  applicant: ApplicantSummary;
  status: ApplicationStatus;
  cover_note: string | null;
  contact_email: string | null;
  portfolio_url: string | null;
  decision_reason: string | null;
  reviewer_note: string | null;
  status_history: ApplicationStatusEvent[];
  submitted_at: string;
  decided_at: string | null;
  withdrawn_at: string | null;
  created_at: string;
  updated_at: string;
  /** Transitions available to the researcher making the request, given their role. */
  allowed_transitions: ApplicationStatus[];
  is_applicant: boolean;
  is_posting_author: boolean;
}

export interface ApplicationListResponse {
  applications: PostingApplication[];
  total: number;
  limit: number;
  offset: number;
}

export interface ApplicationSummaryResponse {
  total: number;
  by_status: Record<string, number>;
  /** Still in play: not withdrawn, rejected or declined. */
  active: number;
}

export interface ApplicationCreatePayload {
  cover_note?: string | null;
  contact_email?: string | null;
  portfolio_url?: string | null;
}

export interface ResearchPostingListResponse {
  postings: ResearchPosting[];
  total: number;
  limit: number;
  offset: number;
}

export interface PostingSummaryResponse {
  author_profile_id: string;
  total: number;
  by_status: Record<string, number>;
  by_type: Record<string, number>;
  total_applications: number;
  open_accepting_applications: number;
}

export interface PostingCreatePayload {
  title: string;
  posting_type: PostingType;
  description: string;
  summary?: string | null;
  required_skills?: string[];
  preferred_qualifications?: string | null;
  institution?: string | null;
  department?: string | null;
  location?: string | null;
  country?: string | null;
  work_mode?: PostingWorkMode;
  positions_available?: number;
  application_deadline?: string | null;
  expected_start_date?: string | null;
  expected_end_date?: string | null;
  contact_email?: string | null;
  external_url?: string | null;
  topic_ids?: string[];
  /** Phase 5.11 appointment terms; ignored for supervisor-led categories. */
  opening_terms?: OpeningTermsUpdate;
}

export type PostingUpdatePayload = Partial<PostingCreatePayload>;

export interface PostingFilterParams {
  posting_type?: PostingType;
  country?: string;
  work_mode?: PostingWorkMode;
  topic_id?: string;
  search?: string;
  accepting_only?: boolean;
  sort_by?: string;
  sort_order?: "asc" | "desc";
  limit?: number;
  offset?: number;
}

export const POSTING_TYPE_LABELS: Record<PostingType, string> = {
  PROJECT: "Research Project",
  THESIS_TOPIC: "Thesis Topic",
  COLLABORATION: "Collaboration",
  LAB_ROTATION: "Lab Rotation",
  INTERNSHIP: "Internship",
  RESEARCH_ASSISTANTSHIP: "Research Assistantship",
  POSTDOC: "Post-doctoral Position",
};

export const COMPENSATION_TYPE_LABELS: Record<CompensationType, string> = {
  STIPEND: "Stipend",
  SALARY: "Salary",
  HOURLY: "Hourly",
  SCHOLARSHIP: "Scholarship",
  GRANT_FUNDED: "Grant funded",
  UNPAID: "Unpaid",
  UNSPECIFIED: "Not specified",
};

export const COMMITMENT_TYPE_LABELS: Record<CommitmentType, string> = {
  FULL_TIME: "Full time",
  PART_TIME: "Part time",
  FLEXIBLE: "Flexible",
};

export const APPLICATION_STATUS_LABELS: Record<ApplicationStatus, string> = {
  SUBMITTED: "Submitted",
  UNDER_REVIEW: "Under review",
  SHORTLISTED: "Shortlisted",
  OFFERED: "Offer extended",
  ACCEPTED: "Accepted",
  DECLINED: "Declined by applicant",
  REJECTED: "Not selected",
  WITHDRAWN: "Withdrawn",
};

/** Categories for which the platform can handle applications. */
export const STRUCTURED_OPENING_TYPES: PostingType[] = [
  "INTERNSHIP",
  "RESEARCH_ASSISTANTSHIP",
  "POSTDOC",
];

export const POSTING_STATUS_LABELS: Record<PostingStatus, string> = {
  DRAFT: "Draft",
  OPEN: "Open",
  CLOSED: "Closed",
  FILLED: "Filled",
  CANCELLED: "Cancelled",
  ARCHIVED: "Archived",
};

export const WORK_MODE_LABELS: Record<PostingWorkMode, string> = {
  ONSITE: "On site",
  REMOTE: "Remote",
  HYBRID: "Hybrid",
};
