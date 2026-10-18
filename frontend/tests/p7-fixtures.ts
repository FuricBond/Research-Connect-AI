/**
 * P7 — API answers for the workspace, its collaboration and submission endpoints, shaped like the
 * backend's (backend/app/schemas/workspace.py, workspace_collaboration.py, research_submission.py).
 * Ids are UUIDs, as the API's are, so the item page accepts them.
 */

import type { WorkspaceMember } from "../types/collaboration";
import type { ResearchSubmission, SubmissionReadinessResponse } from "../types/submission";
import type { WorkspaceItem, WorkspaceListResponse, WorkspaceStatus } from "../types/workspace";
import { USER_ID, jsonResponse } from "./factories";

export const ITEM_ID = "a1b2c3d4-0000-4000-8000-000000000001";
export const OTHER_ITEM_ID = "a1b2c3d4-0000-4000-8000-000000000002";
export const CALL_ID = "c1a2b3c4-0000-4000-8000-000000000001";
export const OWNER_ID = "0aaaaaaa-0000-4000-8000-000000000009";
export const SUBMISSION_ID = "5b000000-0000-4000-8000-000000000001";

/** The backend's VALID_TRANSITIONS (app/services/workspace_service.py). */
export const TRANSITIONS: Record<WorkspaceStatus, WorkspaceStatus[]> = {
  SAVED: ["CONSIDERING", "PLANNING", "ARCHIVED"],
  CONSIDERING: ["PLANNING", "SAVED", "ARCHIVED"],
  PLANNING: ["APPLIED", "CONSIDERING", "SAVED", "ARCHIVED"],
  APPLIED: ["ACCEPTED", "REJECTED", "PLANNING", "ARCHIVED"],
  ACCEPTED: ["ARCHIVED", "APPLIED"],
  REJECTED: ["ARCHIVED", "PLANNING"],
  ARCHIVED: ["SAVED", "CONSIDERING", "PLANNING", "APPLIED"],
};

export function makeItem(overrides: Partial<WorkspaceItem> = {}): WorkspaceItem {
  const status = overrides.status ?? "PLANNING";
  return {
    id: ITEM_ID,
    user_id: USER_ID,
    opportunity_id: CALL_ID,
    status,
    priority: "HIGH",
    tags: [],
    notes: null,
    created_at: "2026-09-20T10:00:00+00:00",
    updated_at: "2026-09-21T10:00:00+00:00",
    status_updated_at: "2026-09-21T10:00:00+00:00",
    archived_at: null,
    allowed_transitions: TRANSITIONS[status],
    opportunity: {
      id: CALL_ID,
      title: "International Conference on Information Retrieval Systems",
      opportunity_type: "CONFERENCE",
      delivery_mode: "IN_PERSON",
      status: "ACTIVE",
      is_predatory_flag: false,
      submission_deadline: "2026-11-18T23:59:00+00:00",
    },
    ...overrides,
  };
}

export function listOf(items: WorkspaceItem[]): WorkspaceListResponse {
  const counts: Record<string, number> = {};
  for (const item of items) counts[item.status] = (counts[item.status] ?? 0) + 1;
  return { items, total_count: items.length, active_count: items.length, archived_count: 0, counts_by_status: counts, counts_by_priority: {} };
}

export function makeMember(overrides: Partial<WorkspaceMember> = {}): WorkspaceMember {
  return {
    id: "3e000000-0000-4000-8000-000000000001",
    workspace_id: ITEM_ID,
    user_id: USER_ID,
    role: "VIEWER",
    status: "ACTIVE",
    joined_at: "2026-09-22T10:00:00+00:00",
    created_at: "2026-09-22T10:00:00+00:00",
    updated_at: "2026-09-22T10:00:00+00:00",
    user: { id: USER_ID, full_name: "Ada Lovelace", email: "ada@university.edu", role: "STUDENT" },
    ...overrides,
  };
}

export function makeSubmission(overrides: Partial<ResearchSubmission> = {}): ResearchSubmission {
  return {
    id: SUBMISSION_ID,
    workspace_item_id: ITEM_ID,
    title: "Query understanding for low-resource languages",
    submission_type: "FULL_PAPER",
    status: "DRAFT",
    status_updated_at: "2026-09-20T10:00:00+00:00",
    created_at: "2026-09-20T10:00:00+00:00",
    updated_at: "2026-09-21T10:00:00+00:00",
    allowed_transitions: ["READY", "WITHDRAWN"],
    workspace_status: "PLANNING",
    opportunity_id: CALL_ID,
    opportunity_title: "International Conference on Information Retrieval Systems",
    ...overrides,
  };
}

export function makeReadiness(overrides: Partial<SubmissionReadinessResponse> = {}): SubmissionReadinessResponse {
  return {
    submission_id: SUBMISSION_ID,
    overall_readiness: "BLOCKED",
    can_mark_submission_ready: false,
    readiness_percentage: 40,
    total_document_count: 1,
    required_document_count: 2,
    completed_document_count: 1,
    missing_document_count: 1,
    draft_document_count: 0,
    rejected_document_count: 0,
    archived_document_count: 0,
    metadata_completeness: 0.5,
    blocking_issues: [{ code: "MISSING_REQUIRED_DOCUMENT", message: "The full paper is still missing.", is_blocking: true }],
    warnings: [],
    readiness_explanation: "One required document is missing.",
    ...overrides,
  };
}

/** A promise the test resolves or rejects when it chooses, to hold a request in flight. */
export function deferred<T = Response>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}

export const ok = (body: unknown) => Promise.resolve(jsonResponse(body));
export const refuse = (status: number, detail: string) => Promise.resolve(jsonResponse({ detail }, status));
