import { CalendarX, Clock, History } from "lucide-react";
import { cx } from "../../utils/cx";
import { deadlineTone, describeTimeLeft, formatDeadlineDate, isAoeDeadline, type DeadlineTone } from "../../utils/date";
import styles from "./Indicators.module.css";

interface DeadlineCountdownProps {
  /** The deadline as the API gives it (ISO datetime or date). */
  deadline?: string | null;
  /** Fractional days left from the deadline intelligence; computed from `deadline` when absent. */
  daysRemaining?: number | null;
  /** DeadlineTemporalStatus and UrgencyTier from the deadline intelligence, when known. */
  status?: string | null;
  urgencyTier?: string | null;
  className?: string;
}

const MS_PER_DAY = 86_400_000;

const TONE_CLASS: Record<DeadlineTone, string> = {
  open: styles.deadlineOpen,
  soon: styles.deadlineSoon,
  urgent: styles.deadlineUrgent,
  passed: styles.deadlinePassed,
  unknown: styles.deadlineUnknown,
};

/**
 * The canonical deadline indicator (DESIGN_SYSTEM.md §3.2 "DeadlineBadge"): a clock and words —
 * "Due 9 Oct 2026 AoE · 3 days left", "Closed 25 Aug 2026", "No deadline listed". Orange only
 * within 7 days, tinted within 48 hours; never styled like venue risk.
 * `deadline-countdown deadline-<tone>` stay on the element as stable hooks for tests.
 */
export function DeadlineCountdown({ deadline, daysRemaining, status, urgencyTier, className }: DeadlineCountdownProps) {
  let days = daysRemaining ?? null;
  if (days === null && deadline) {
    const time = Date.parse(deadline);
    if (!Number.isNaN(time)) days = (time - Date.now()) / MS_PER_DAY;
  }
  const tone = deadline ? deadlineTone(days, status, urgencyTier) : "unknown";
  // An AoE date is a day behind the UTC instant the countdown measures to, so it says "AoE"
  // (as the call badges say "UTC" or "AoE"): "Due 7 Oct 2026 AoE · 1 day left".
  const date = deadline ? `${formatDeadlineDate(deadline)}${isAoeDeadline(deadline) ? " AoE" : ""}` : null;

  let text: string;
  if (tone === "unknown" || !date) {
    text = "No deadline listed";
  } else if (tone === "passed") {
    text = `Closed ${date}`;
  } else {
    const left = describeTimeLeft(days);
    text = left ? `Due ${date} · ${left}` : `Due ${date}`;
  }

  const Icon = tone === "passed" ? History : tone === "unknown" ? CalendarX : Clock;
  return (
    <span className={cx(styles.indicator, TONE_CLASS[tone], "deadline-countdown", `deadline-${tone}`, className)}>
      <Icon size={14} aria-hidden="true" />
      <span className={styles.text}>{text}</span>
    </span>
  );
}
