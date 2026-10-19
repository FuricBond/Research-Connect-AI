"use client";

/**
 * P9 — the faculty pages' requests (FRONTEND_REDESIGN_PLAN.md §14), each a useApiResource so a
 * page never asks twice for the same thing and answers belong to the signed-in account only.
 *
 *   My postings   GET /postings/mine?limit=25[&status][&offset] + GET /postings/mine/summary (the
 *                 filter counts) + the applications of up to INBOX_POSTINGS open postings ("New")
 *   Applicants    GET /postings/mine?limit=100 + GET /postings/{id}/applications?limit=200 for
 *                 each of up to INBOX_POSTINGS postings (inboxPostings), all at once
 *   A posting     GET /postings/{id} (+ its applications, for its author, when it takes them)
 */

import { useRef } from "react";
import { useApiResource, type ApiResource } from "../../hooks/useApiResource";
import { fetchMyPostingSummary, fetchMyPostings, fetchPosting, fetchPostingApplications } from "../../services/api";
import type { PostingStatus } from "../../types/posting";
import { INBOX_POSTINGS, MINE_PAGE_SIZE } from "../../utils/postings";

/**
 * The last answer while the same key is asked again (a retry), so a list does not blank out; as
 * P7's useKept, kept here so the postings pages do not load the workspace item's code.
 */
export function useKept<T>(resource: ApiResource<T>): T | undefined {
  const kept = useRef<T | undefined>(undefined);
  if (resource.data !== undefined) kept.current = resource.data;
  return resource.data ?? (resource.status === "loading" ? kept.current : undefined);
}

/** The most a posting's applications list returns in one answer (backend MAX_LIMIT). */
export const APPLICATIONS_LIMIT = 200;
/** The most of one's postings one answer holds (backend MAX_LIMIT): the inbox reads one page. */
export const ALL_MINE_LIMIT = 100;

export function useMyPostingsPage(status: PostingStatus | null, page: number) {
  const offset = (page - 1) * MINE_PAGE_SIZE;
  return useApiResource(`postings:mine:${status ?? "all"}:${offset}`, (signal) =>
    fetchMyPostings({ status: status ?? undefined, limit: MINE_PAGE_SIZE, offset: offset || undefined }, signal)
  );
}

export function useMyPostingSummary() {
  return useApiResource("postings:mine:summary", (signal) => fetchMyPostingSummary(signal));
}

/** Every posting of one's (one page of ALL_MINE_LIMIT), for the inbox to choose from. */
export function useAllMyPostings() {
  return useApiResource(`postings:mine:all:${ALL_MINE_LIMIT}`, (signal) => fetchMyPostings({ limit: ALL_MINE_LIMIT }, signal));
}

/** One posting's applications, the author's view; waits (null) until the posting is known. */
export function usePostingApplications(postingId: string | null) {
  return useApiResource(postingId ? `applications:posting:${postingId}:${APPLICATIONS_LIMIT}` : null, (signal) =>
    fetchPostingApplications(postingId!, { limit: APPLICATIONS_LIMIT }, signal)
  );
}

/**
 * The applications of up to INBOX_POSTINGS postings: a fixed number of hooks (React needs the
 * same hooks on every render), each slot without a posting waiting and asking nothing.
 */
export function useApplicationsOf(postingIds: readonly string[]) {
  const ids = postingIds.slice(0, INBOX_POSTINGS);
  const slots = [
    usePostingApplications(ids[0] ?? null),
    usePostingApplications(ids[1] ?? null),
    usePostingApplications(ids[2] ?? null),
    usePostingApplications(ids[3] ?? null),
    usePostingApplications(ids[4] ?? null),
    usePostingApplications(ids[5] ?? null),
    usePostingApplications(ids[6] ?? null),
    usePostingApplications(ids[7] ?? null),
    usePostingApplications(ids[8] ?? null),
    usePostingApplications(ids[9] ?? null),
  ];
  return ids.map((id, index) => ({ postingId: id, applications: slots[index] }));
}

export function usePosting(postingId: string | null) {
  return useApiResource(postingId ? `posting:${postingId}` : null, (signal) => fetchPosting(postingId!, signal));
}
