import type { WorkspaceItem, WorkspaceOpportunitySummary } from "../types/workspace";

/** The deadline facts a tracked call carries, read the same way wherever it is shown. */
export interface WorkspaceDeadline {
  /** The submission deadline (ISO datetime or date), or null when none is known. */
  deadline: string | null;
  /** Fractional days left, from the deadline intelligence when it has an assessment. */
  daysRemaining: number | null;
  status: string | null;
  urgencyTier: string | null;
}

export function workspaceDeadline(opportunity: WorkspaceOpportunitySummary | null | undefined): WorkspaceDeadline {
  const intelligence = opportunity?.deadline_intelligence;
  const view = intelligence?.primary_view;
  return {
    deadline:
      opportunity?.submission_deadline ||
      view?.canonical_deadline?.utc_deadline ||
      view?.canonical_deadline?.local_date ||
      null,
    daysRemaining: view?.canonical_assessment?.days_remaining ?? null,
    status: view?.canonical_assessment?.status ?? null,
    urgencyTier: intelligence?.overall_urgency_tier ?? null,
  };
}

const CLOSED_STATUSES = new Set(["ACCEPTED", "REJECTED", "ARCHIVED"]);
const MS_PER_DAY = 86_400_000;

export interface UpcomingDeadline {
  item: WorkspaceItem;
  /** Fractional days left. */
  days: number;
}

/**
 * Tracked calls that are still open and due within `windowDays`, soonest first. A call with no
 * deadline intelligence falls back to its raw submission deadline; past deadlines are left out.
 */
export function upcomingDeadlines(
  items: readonly WorkspaceItem[],
  windowDays: number,
  now: number = Date.now()
): UpcomingDeadline[] {
  const upcoming: UpcomingDeadline[] = [];
  for (const item of items) {
    if (CLOSED_STATUSES.has(item.status)) continue;
    const { deadline, daysRemaining } = workspaceDeadline(item.opportunity);
    let days = daysRemaining;
    if (days === null && deadline) {
      const time = Date.parse(deadline);
      days = Number.isNaN(time) ? null : (time - now) / MS_PER_DAY;
    }
    if (days !== null && days >= 0 && days <= windowDays) upcoming.push({ item, days });
  }
  return upcoming.sort((a, b) => a.days - b.days);
}
