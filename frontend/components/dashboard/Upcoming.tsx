"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import type { ApiResource } from "../../hooks/useApiResource";
import type { ResearcherCalendarViewResponse } from "../../types/calendar";
import type { ResearchPostingListResponse } from "../../types/posting";
import type { WorkspaceListResponse } from "../../types/workspace";
import { describeTimeLeft, formatDeadlineDate, humanizeEnum } from "../../utils/date";
import { upcomingDeadlines, workspaceDeadline } from "../../utils/workspace";
import { EmptyState } from "../ui/State/State";
import { DashboardModule, ModuleError, ModuleLoading } from "./Module";
import { UPCOMING_DAYS } from "./resources";
import styles from "./Dashboard.module.css";

const ENTRIES_SHOWN = 6;
const MS_PER_DAY = 86_400_000;

export interface TimelineEntry {
  id: string;
  /** ISO date or datetime. */
  date: string;
  days: number;
  title: string;
  /** "Submission deadline", "Camera ready", "Applications close"… */
  kind: string;
  /** Deadlines are filled dots; milestones and other events hollow. */
  milestone: boolean;
  href: string;
}

/** Tracked calls with a deadline in the window (shared by both roles). */
export function callDeadlines(data: WorkspaceListResponse): TimelineEntry[] {
  return upcomingDeadlines(data.items, UPCOMING_DAYS).map(({ item, days }) => ({
    id: `call-${item.id}`,
    date: workspaceDeadline(item.opportunity).deadline ?? "",
    days,
    title: item.opportunity.title,
    kind: "Submission deadline",
    milestone: false,
    href: `/workspace/${item.id}`,
  }));
}

/**
 * Calendar events in the window that are still on, leaving out the deadlines of calls already
 * listed from the workspace (the calendar projects them too).
 */
export function calendarEvents(data: ResearcherCalendarViewResponse, trackedOpportunityIds: ReadonlySet<string>, now = Date.now()): TimelineEntry[] {
  const entries: TimelineEntry[] = [];
  for (const event of data.events) {
    if (event.status !== "ACTIVE" && event.status !== "CONFLICT") continue;
    if (event.opportunity_id && trackedOpportunityIds.has(event.opportunity_id)) continue;
    const date = event.start_datetime || event.date_str;
    const time = date ? Date.parse(date) : Number.NaN;
    if (!date || Number.isNaN(time)) continue;
    const days = (time - now) / MS_PER_DAY;
    if (days < 0 || days > UPCOMING_DAYS) continue;
    entries.push({
      id: `event-${event.id}`,
      date,
      days,
      title: event.title,
      kind: event.event_type === "RESEARCH_MILESTONE" || event.event_type === "CUSTOM" ? "Milestone" : humanizeEnum(event.event_type),
      milestone: true,
      href: "/calendar",
    });
  }
  return entries;
}

/** A faculty member's open postings whose applications close in the window. */
export function postingDeadlines(data: ResearchPostingListResponse): TimelineEntry[] {
  return data.postings
    .filter((posting) => posting.status === "OPEN" && posting.application_deadline && posting.days_until_deadline !== null)
    .filter((posting) => posting.days_until_deadline! >= 0 && posting.days_until_deadline! <= UPCOMING_DAYS)
    .map((posting) => ({
      id: `posting-${posting.id}`,
      date: posting.application_deadline!,
      days: posting.days_until_deadline!,
      title: posting.title,
      kind: "Applications close",
      milestone: false,
      href: `/postings/${posting.id}`,
    }));
}

interface Source<T> {
  resource: ApiResource<T>;
  /** "Your tracked calls could not be loaded." */
  failure: string;
}

/**
 * "Upcoming (30 days)" for students and "Upcoming deadlines" for faculty (plan §8): one dot
 * timeline built from two sources. It waits for both (so entries do not jump into place one
 * source at a time), shows what loaded when only one fails, and says which one failed.
 */
export function Upcoming<A, B>({
  title,
  first,
  second,
  build,
  emptyDescription,
}: {
  title: string;
  first: Source<A>;
  second: Source<B>;
  build: (first: A | undefined, second: B | undefined) => TimelineEntry[];
  emptyDescription: ReactNode;
}) {
  // Neither source waits for another, so "idle" can only mean "nothing to ask for" (an account
  // without a researcher profile has no calendar): settled, with no entries.
  const settled = (status: string) => status !== "loading";
  let body: ReactNode;
  if (!settled(first.resource.status) || !settled(second.resource.status)) {
    body = <ModuleLoading label="Loading what is coming up" rows={3} />;
  } else if (first.resource.status === "error" && second.resource.status === "error") {
    body = (
      <ModuleError
        message="What is coming up could not be loaded."
        resource={{
          retries: first.resource.retries,
          retry: () => {
            first.resource.retry();
            second.resource.retry();
          },
        }}
      />
    );
  } else {
    const entries = build(first.resource.data, second.resource.data)
      .sort((a, b) => a.days - b.days)
      .slice(0, ENTRIES_SHOWN);
    body = (
      <>
        {[first, second].map((source) =>
          source.resource.status === "error" ? <ModuleError key={source.failure} message={source.failure} resource={source.resource} /> : null
        )}
        {entries.length === 0 ? (
          <EmptyState bare variant="done" headingLevel={3} title={`Nothing is due in the next ${UPCOMING_DAYS} days.`} description={emptyDescription} />
        ) : (
          <ol className={styles.timeline}>
            {entries.map((entry) => (
              <li key={entry.id} className={entry.milestone ? `${styles.event} ${styles.milestone}` : styles.event}>
                <span className={styles.date}>{formatDeadlineDate(entry.date, undefined, { weekday: "short", year: undefined })}</span>
                <span className={styles.dot} aria-hidden="true" />
                <span className={styles.eventBody}>
                  <Link href={entry.href} className={styles.eventTitle}>
                    {entry.title}
                  </Link>
                  <span className={styles.meta}>
                    {entry.kind} · {describeTimeLeft(entry.days)}
                  </span>
                </span>
              </li>
            ))}
          </ol>
        )}
      </>
    );
  }

  return (
    <DashboardModule id="dashboard-upcoming" title={title} action={<Link href="/calendar">Open the calendar</Link>} reserve="timeline">
      {body}
    </DashboardModule>
  );
}
