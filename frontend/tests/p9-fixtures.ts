/**
 * P9 — API answers for the faculty pages, shaped like the backend's
 * (backend/app/schemas/research_posting.py, research_posting_application.py). Allowed transitions
 * come as the backend sends them: sorted by their enum names, which is not the review order.
 */

import type { ApplicationStatus, PostingApplication, PostingStatus, ResearchPosting } from "../types/posting";
import { jsonResponse, PROFILE_ID } from "./factories";

/** backend AUTHOR_TRANSITIONS, sorted as allowed_transitions_for() returns them. */
export const AUTHOR_MOVES: Record<ApplicationStatus, ApplicationStatus[]> = {
  SUBMITTED: ["REJECTED", "SHORTLISTED", "UNDER_REVIEW"],
  UNDER_REVIEW: ["OFFERED", "REJECTED", "SHORTLISTED"],
  SHORTLISTED: ["OFFERED", "REJECTED"],
  OFFERED: ["REJECTED"],
  ACCEPTED: [],
  DECLINED: [],
  REJECTED: [],
  WITHDRAWN: [],
};

/** backend VALID_TRANSITIONS, sorted. */
export const POSTING_MOVES: Record<PostingStatus, PostingStatus[]> = {
  DRAFT: ["ARCHIVED", "CANCELLED", "OPEN"],
  OPEN: ["CANCELLED", "CLOSED", "DRAFT", "FILLED"],
  CLOSED: ["ARCHIVED", "FILLED", "OPEN"],
  FILLED: ["ARCHIVED"],
  CANCELLED: ["ARCHIVED"],
  ARCHIVED: [],
};

export const postingId = (n: number) => `9a000000-0000-4000-8000-${String(n).padStart(12, "0")}`;
export const applicationId = (n: number) => `8b000000-0000-4000-8000-${String(n).padStart(12, "0")}`;

export function makePosting(n: number, overrides: Partial<ResearchPosting> = {}): ResearchPosting {
  const status = overrides.status ?? "OPEN";
  return {
    id: postingId(n),
    author: { profile_id: PROFILE_ID, full_name: "Dr. Amara Okafor", institution: "Test University", department: "Computer Science", academic_status: "FACULTY" },
    title: `Posting ${n}`,
    posting_type: "RESEARCH_ASSISTANTSHIP",
    status,
    summary: null,
    description: "We are seeking a research assistant to build retrieval benchmarks.",
    required_skills: ["Python"],
    preferred_qualifications: null,
    institution: "Test University",
    department: "Computer Science",
    location: "Boston, US",
    country: "US",
    work_mode: "ONSITE",
    positions_available: 1,
    application_deadline: null,
    expected_start_date: null,
    expected_end_date: null,
    contact_email: null,
    external_url: null,
    topics: [],
    opening_terms: {
      compensation_type: "STIPEND",
      compensation_amount: 2000,
      compensation_currency: "USD",
      compensation_period: "MONTH",
      commitment_type: "PART_TIME",
      hours_per_week: 20,
      duration_months: 6,
      eligibility_requirements: null,
      accepts_applications: true,
      is_structured_opening: true,
    },
    application_count: 0,
    // Published one day apart: a higher n is newer.
    published_at: status === "DRAFT" ? null : `2026-09-${String(Math.min(28, n)).padStart(2, "0")}T10:00:00+00:00`,
    closed_at: null,
    archived_at: null,
    status_note: null,
    created_at: "2026-09-01T10:00:00+00:00",
    updated_at: "2026-10-01T10:00:00+00:00",
    is_accepting_applications: status === "OPEN",
    days_until_deadline: null,
    allowed_transitions: POSTING_MOVES[status],
    is_owner: true,
    viewer_application_id: null,
    viewer_application_status: null,
    ...overrides,
  };
}

export function makeApplication(n: number, posting: ResearchPosting, overrides: Partial<PostingApplication> = {}): PostingApplication {
  const status = overrides.status ?? "SUBMITTED";
  return {
    id: applicationId(n),
    posting_id: posting.id,
    posting_title: posting.title,
    applicant: { profile_id: `7c000000-0000-4000-8000-${String(n).padStart(12, "0")}`, full_name: `Applicant ${n}`, institution: "Fairview University", department: null, academic_status: "PHD" },
    status,
    cover_note: "I build retrieval evaluation pipelines.",
    contact_email: `applicant${n}@fairview.edu`,
    portfolio_url: null,
    decision_reason: null,
    reviewer_note: null,
    status_history: [{ from_status: null, to_status: "SUBMITTED", actor_role: "APPLICANT", reason: null, at: "2026-10-02T09:00:00+00:00" }],
    submitted_at: "2026-10-02T09:00:00+00:00",
    decided_at: null,
    withdrawn_at: null,
    created_at: "2026-10-02T09:00:00+00:00",
    updated_at: "2026-10-02T09:00:00+00:00",
    allowed_transitions: AUTHOR_MOVES[status],
    is_applicant: false,
    is_posting_author: true,
    ...overrides,
  };
}

export const listOf = (postings: ResearchPosting[]) => ({ postings, total: postings.length, limit: 100, offset: 0 });
export const applicationsOf = (applications: PostingApplication[]) => ({ applications, total: applications.length, limit: 200, offset: 0 });
export const ok = (body: unknown) => Promise.resolve(jsonResponse(body));
export const refuse = (status: number, detail = "Refused") => Promise.resolve(jsonResponse({ detail }, status));

export function summaryOf(postings: ResearchPosting[]) {
  const by_status: Record<string, number> = {};
  for (const posting of postings) by_status[posting.status] = (by_status[posting.status] ?? 0) + 1;
  return { author_profile_id: PROFILE_ID, total: postings.length, by_status, by_type: {}, total_applications: 0, open_accepting_applications: 0 };
}

export function deferred<T = Response>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((yes) => {
    resolve = yes;
  });
  return { promise, resolve };
}
