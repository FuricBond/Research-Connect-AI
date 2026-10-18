import { AlertTriangle, ArrowUpRight } from "lucide-react";
import type { CanonicalDeadlineView, OpportunityDeadline } from "../../types/opportunity";
import { cx } from "../../utils/cx";
import { formatDeadlineDate, humanizeEnum } from "../../utils/date";
import { TimeLeft } from "./DeadlineCountdown";
import styles from "./Details.module.css";

/** The academic order of a call's dates (DESIGN_SYSTEM.md §9 DeadlineIndicator). */
const ORDER: [type: string, label: string][] = [
  ["ABSTRACT", "Abstract"],
  ["SUBMISSION", "Paper submission"],
  ["NOTIFICATION", "Notification"],
  ["CAMERA_READY", "Camera-ready"],
  ["REGISTRATION", "Registration"],
  ["EVENT_START", "Event starts"],
  ["EVENT_END", "Event ends"],
];

interface Milestone {
  type: string;
  label: string;
  /** The date as the call states it, in its own time zone ("10 Oct 2026, 23:59 AoE"). */
  date: string;
  /** What DeadlineCountdown needs to say how much time is left. */
  instant: string | null;
  daysRemaining: number | null;
  status: string | null;
  urgencyTier: string | null;
  source: string | null;
  extendedByDays: number | null;
  disputed: string | null;
}

function fromView(type: string, label: string, view: CanonicalDeadlineView): Milestone | null {
  const deadline = view.canonical_deadline;
  if (!deadline?.local_date) return null;
  const time = deadline.local_time ? `, ${deadline.local_time.slice(0, 5)}` : "";
  const zone = deadline.timezone_name ? ` ${deadline.timezone_name}` : "";
  const assessment = view.canonical_assessment;
  const extended = view.latest_revision?.classification === "EXTENDED" ? (view.latest_revision.days_diff ?? null) : null;
  return {
    type,
    label,
    date: `${formatDeadlineDate(deadline.local_date)}${time}${zone}`,
    instant: deadline.utc_deadline ?? deadline.normalized_utc ?? deadline.local_date,
    daysRemaining: assessment?.days_remaining ?? null,
    status: assessment?.status ?? null,
    urgencyTier: assessment?.urgency_tier ?? null,
    source: view.selected_source ?? null,
    extendedByDays: extended !== null ? Math.round(extended) : null,
    disputed: view.conflict_state === "SOURCE_CONFLICT" ? (view.conflict_reason || "Sources give different dates.") : null,
  };
}

function plainMilestone(type: string, label: string, value: string | null | undefined): Milestone | null {
  if (!value) return null;
  return { type, label, date: formatDeadlineDate(value), instant: value, daysRemaining: null, status: null, urgencyTier: null, source: null, extendedByDays: null, disputed: null };
}

export interface CallDates {
  submission_deadline?: string | null;
  notification_date?: string | null;
  camera_ready_deadline?: string | null;
  event_start_date?: string | null;
  event_end_date?: string | null;
}

/** The milestones to show: the deadline intelligence's views, or else the call's own date fields. */
export function callMilestones(intelligence: OpportunityDeadline | null | undefined, dates: CallDates): Milestone[] {
  const views = intelligence?.milestone_views ?? {};
  const fromIntelligence: Milestone[] = [];
  for (const [type, label] of ORDER) {
    const view = views[type];
    const milestone = view ? fromView(type, label, view) : null;
    if (milestone) fromIntelligence.push(milestone);
  }
  for (const [type, view] of Object.entries(views)) {
    if (ORDER.some(([known]) => known === type)) continue;
    const milestone = fromView(type, humanizeEnum(type), view);
    if (milestone) fromIntelligence.push(milestone);
  }
  if (fromIntelligence.length > 0) return fromIntelligence;
  return [
    plainMilestone("SUBMISSION", "Paper submission", dates.submission_deadline),
    plainMilestone("NOTIFICATION", "Notification", dates.notification_date),
    plainMilestone("CAMERA_READY", "Camera-ready", dates.camera_ready_deadline),
    plainMilestone("EVENT_START", "Event starts", dates.event_start_date),
    plainMilestone("EVENT_END", "Event ends", dates.event_end_date),
  ].filter((milestone): milestone is Milestone => milestone !== null);
}

/**
 * A call's dates in order, each with its own time zone and the time left in words; the main
 * deadline is marked, an extension or a disagreement between sources is said in words. Only
 * dates the API holds are shown.
 */
export function DeadlineMilestones({ intelligence, dates }: { intelligence: OpportunityDeadline | null | undefined; dates: CallDates }) {
  const milestones = callMilestones(intelligence, dates);
  const primary = intelligence?.primary_milestone ?? "SUBMISSION";
  if (milestones.length === 0) return <p className={styles.text}>This call lists no dates.</p>;

  return (
    <ol className={styles.timeline}>
      {milestones.map((milestone) => {
        const isPrimary = milestone.type === primary;
        return (
          <li key={milestone.type} className={cx(styles.milestone, isPrimary && styles.milestonePrimary)}>
            <span className={styles.milestoneDot} aria-hidden="true" />
            <div className={styles.milestoneBody}>
              <p className={styles.milestoneTitle}>
                {milestone.label}
                {isPrimary && <span className={styles.milestoneTag}>Main deadline</span>}
              </p>
              <p className={styles.milestoneDate}>{milestone.date}</p>
              {milestone.type !== "EVENT_START" && milestone.type !== "EVENT_END" && (
                <TimeLeft deadline={milestone.instant} daysRemaining={milestone.daysRemaining} status={milestone.status} urgencyTier={milestone.urgencyTier} />
              )}
              {milestone.extendedByDays !== null && milestone.extendedByDays > 0 && (
                <p className={styles.note}>
                  <ArrowUpRight size={14} aria-hidden="true" />
                  Extended by {milestone.extendedByDays} day{milestone.extendedByDays === 1 ? "" : "s"}
                </p>
              )}
              {milestone.disputed && (
                <p className={styles.note}>
                  <AlertTriangle size={14} aria-hidden="true" />
                  {milestone.disputed}
                </p>
              )}
              {milestone.source && <p className={styles.source}>Source: {milestone.source}</p>}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
