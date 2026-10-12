"use client";

/**
 * P4 — every request the dashboard makes, in one place (FRONTEND_REDESIGN_PLAN.md §8).
 *
 * Each hook is a useApiResource with a fixed key, so two modules that read the same source share
 * one request (the student's "Needs attention" and "Upcoming" both read the workspace). All of
 * them start when the page renders; the only ones that wait are the fit scores (they need the
 * open postings' ids), a faculty member's application lists (they need the postings) and the
 * related papers (they need the newest paper), each inside its own module.
 *
 * Student: workspace, application summary, calendar, recommendations, open postings → fit
 * scores, reading list = 7. Faculty: workspace, own postings → up to 3 application lists,
 * newest paper → related papers = at most 7. The shell's session check and unread count are
 * not the dashboard's (every signed-in page makes them).
 */

import { useState } from "react";
import { useApiResource } from "../../hooks/useApiResource";
import {
  fetchMyApplicationSummary,
  fetchMyPostings,
  fetchPostingApplications,
  fetchPostingFits,
  fetchPostings,
  fetchReadingList,
  fetchResearcherCalendar,
  fetchResearcherWorks,
  fetchWorkspaceItems,
  getSimilarResearch,
  getUnifiedRecommendations,
} from "../../services/api";

/** "Needs attention": tracked calls due within this many days (plan §8). */
export const ATTENTION_DAYS = 14;
/** "Upcoming": the timeline's window. */
export const UPCOMING_DAYS = 30;
/** Open postings scored for fit (the fit endpoint takes up to 100). */
export const POSTINGS_SCORED = 50;
/** "Needs your decision": the postings whose applications are fetched (one request each). */
export const DECISION_POSTINGS = 3;

export function useTrackedCalls() {
  return useApiResource("workspace:by-deadline", (signal) =>
    fetchWorkspaceItems({ sort_by: "deadline", sort_order: "asc", limit: 100 }, undefined, signal)
  );
}

export function useApplicationSummary() {
  return useApiResource("applications:mine:summary", (signal) => fetchMyApplicationSummary(signal));
}

/** The calendar from today to UPCOMING_DAYS ahead, the range fixed when the page opens. */
export function useCalendarWindow(profileId: string | null) {
  const [range] = useState(() => {
    const start = new Date();
    start.setHours(0, 0, 0, 0);
    const end = new Date(start.getTime() + (UPCOMING_DAYS + 1) * 86_400_000);
    return { start: start.toISOString(), end: end.toISOString() };
  });
  return useApiResource(profileId ? `calendar:${profileId}:${range.start}:${range.end}` : null, (signal) =>
    fetchResearcherCalendar(profileId!, { start_date: range.start, end_date: range.end }, undefined, signal)
  );
}

export function useRecommendations(profileId: string | null) {
  return useApiResource(profileId ? `recommendations:${profileId}:3` : null, (signal) =>
    getUnifiedRecommendations(profileId!, { limit: 3 }, undefined, signal)
  );
}

export function useOpenPostings() {
  return useApiResource(`postings:accepting:${POSTINGS_SCORED}`, (signal) =>
    fetchPostings({ accepting_only: true, limit: POSTINGS_SCORED }, signal)
  );
}

/** Waits (null) until the open postings are known. */
export function usePostingFits(postingIds: readonly string[] | null) {
  return useApiResource(postingIds && postingIds.length > 0 ? `posting-fits:${postingIds.join(",")}` : null, (signal) =>
    fetchPostingFits([...postingIds!], signal)
  );
}

export function useReadingCounts() {
  return useApiResource("reading-list:counts", (signal) => fetchReadingList({ limit: 1 }, signal));
}

export function useMyPostings() {
  return useApiResource("postings:mine", (signal) => fetchMyPostings({ limit: 100 }, signal));
}

/** One posting's applications (the author's view); waits (null) until the posting is chosen. */
export function usePostingApplications(postingId: string | null) {
  return useApiResource(postingId ? `applications:posting:${postingId}` : null, (signal) =>
    fetchPostingApplications(postingId!, { limit: 100 }, signal)
  );
}

/** The researcher's newest paper (the works come newest first). */
export function useNewestWork(profileId: string | null) {
  return useApiResource(profileId ? `works:${profileId}:newest` : null, (signal) => fetchResearcherWorks(profileId!, 1, 0, signal));
}

/** Papers similar to one paper; waits (null) until the paper is known. */
export function useSimilarPapers(workId: string | null) {
  return useApiResource(workId ? `similar:${workId}:3` : null, (signal) => getSimilarResearch(workId!, { limit: 3 }, signal));
}
