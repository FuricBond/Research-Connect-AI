/**
 * Phase 5.10 — Faculty Research Postings.
 *
 * Mirrors backend/app/schemas/research_posting.py. Derived fields such as
 * `is_accepting_applications`, `days_until_deadline` and `allowed_transitions` are computed
 * server-side so every client agrees on them; the UI must render them, never recompute them.
 */

export type PostingType = "PROJECT" | "THESIS_TOPIC" | "COLLABORATION" | "LAB_ROTATION";

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
};

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
