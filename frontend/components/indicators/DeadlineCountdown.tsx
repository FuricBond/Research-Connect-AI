import { CalendarX, Clock, History } from "lucide-react";
import { deadlineTone, describeTimeLeft, formatDeadlineDate } from "../../utils/date";

interface DeadlineCountdownProps {
  /** The deadline as the API gives it (ISO datetime or date). */
  deadline?: string | null;
  /** Fractional days left from the deadline intelligence; computed from `deadline` when absent. */
  daysRemaining?: number | null;
  /** DeadlineTemporalStatus and UrgencyTier from the deadline intelligence, when known. */
  status?: string | null;
  urgencyTier?: string | null;
}

const MS_PER_DAY = 86_400_000;

/**
 * P0.5 — a deadline, said in words: "Due 10 Oct 2026 · 3 days left", "Closed 25 Aug 2026",
 * "No deadline listed". Clock icon and time words; styled apart from venue risk.
 */
export function DeadlineCountdown({ deadline, daysRemaining, status, urgencyTier }: DeadlineCountdownProps) {
  let days = daysRemaining ?? null;
  if (days === null && deadline) {
    const time = Date.parse(deadline);
    if (!Number.isNaN(time)) days = (time - Date.now()) / MS_PER_DAY;
  }
  const tone = deadline ? deadlineTone(days, status, urgencyTier) : "unknown";
  const date = deadline ? formatDeadlineDate(deadline) : null;

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
    <span className={`deadline-countdown deadline-${tone}`}>
      <Icon size={14} aria-hidden="true" />
      <span>{text}</span>
    </span>
  );
}
