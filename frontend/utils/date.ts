/**
 * Date and deadline formatting utilities for ResearchConnect AI.
 *
 * Prevents browser-side date-shift anomalies where UTC midnight or Anywhere on Earth (AoE)
 * timestamps roll backward or forward across calendar days due to local browser timezone offsets.
 */

export function formatDeadlineDate(
  iso: string | null | undefined,
  locale?: string,
  options?: Intl.DateTimeFormatOptions
): string {
  if (!iso) return "No deadline specified";

  const defaultOptions: Intl.DateTimeFormatOptions = {
    year: "numeric",
    month: "short",
    day: "numeric",
    ...options,
  };

  // Case 1: AoE deadline normalized to 11:59:59 UTC on the subsequent calendar day
  // e.g. "2026-08-23T11:59:59..." represents 23:59:59 AoE on calendar date 2026-08-22
  const aoeMatch = /^(\d{4})-(\d{2})-(\d{2})T1[12]:(?:59|00)/.exec(iso);
  if (aoeMatch) {
    const [, y, m, d] = aoeMatch;
    const utcInstant = new Date(Date.UTC(Number(y), Number(m) - 1, Number(d)));
    utcInstant.setUTCDate(utcInstant.getUTCDate() - 1);
    return utcInstant.toLocaleDateString(locale, { ...defaultOptions, timeZone: "UTC" });
  }

  // Case 2: Date-only ISO ("2026-08-22") or legacy UTC midnight ("2026-08-22T00:00:00...")
  const dateMatch = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (dateMatch && (iso.length === 10 || iso.includes("T00:00:00"))) {
    const [, y, m, d] = dateMatch;
    const utcDate = new Date(Date.UTC(Number(y), Number(m) - 1, Number(d), 12, 0, 0));
    return utcDate.toLocaleDateString(locale, { ...defaultOptions, timeZone: "UTC" });
  }

  // Case 3: Standard datetime with explicit non-midnight time
  const parsed = new Date(iso);
  if (isNaN(parsed.getTime())) {
    return iso;
  }
  return parsed.toLocaleDateString(locale, defaultOptions);
}

export function calculateRemainingDays(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const deadlineDate = new Date(iso);
  if (isNaN(deadlineDate.getTime())) return null;
  const now = new Date();
  const diffMs = deadlineDate.getTime() - now.getTime();
  return Math.ceil(diffMs / (1000 * 60 * 60 * 24));
}

/**
 * P0.5 — how much time is left before a deadline, in words.
 *
 * `daysRemaining` is the fractional day count the deadline intelligence returns (for example
 * 3.7978). It is shown as whole units — "3 days left", "18 hours left" — never as the raw float.
 * Returns null when there is nothing to say.
 */
export function describeTimeLeft(daysRemaining: number | null | undefined): string | null {
  if (daysRemaining === null || daysRemaining === undefined || Number.isNaN(daysRemaining)) return null;
  if (daysRemaining < 0) return "Closed";
  if (daysRemaining < 1) {
    const hours = Math.floor(daysRemaining * 24);
    if (hours < 1) return "Due within the hour";
    return `${hours} hour${hours === 1 ? "" : "s"} left`;
  }
  const days = Math.floor(daysRemaining);
  return `${days} day${days === 1 ? "" : "s"} left`;
}

/**
 * How pressing a deadline is, as a presentation tone. Deadline urgency is about time only; it
 * is styled apart from venue risk (see components/indicators).
 *   passed  — the deadline is over
 *   urgent  — two days or less (or the intelligence says CRITICAL / DUE_TODAY)
 *   soon    — a week or less (or URGENT)
 *   open    — further away
 *   unknown — no usable deadline
 */
export type DeadlineTone = "passed" | "urgent" | "soon" | "open" | "unknown";

export function deadlineTone(
  daysRemaining: number | null | undefined,
  status?: string | null,
  urgencyTier?: string | null
): DeadlineTone {
  if (status === "EXPIRED" || urgencyTier === "EXPIRED") return "passed";
  if (status === "DUE_TODAY" || urgencyTier === "DUE_TODAY" || urgencyTier === "CRITICAL") return "urgent";
  if (daysRemaining === null || daysRemaining === undefined || Number.isNaN(daysRemaining)) {
    if (urgencyTier === "URGENT") return "soon";
    if (status === "MISSING" || status === "INVALID" || !status) return "unknown";
    return "open";
  }
  if (daysRemaining < 0) return "passed";
  if (daysRemaining <= 2) return "urgent";
  if (daysRemaining <= 7 || urgencyTier === "URGENT") return "soon";
  return "open";
}

/** "CAMERA_READY" -> "Camera ready": enum values shown to people in sentence case. */
export function humanizeEnum(value: string | null | undefined): string {
  if (!value) return "";
  const words = value.replace(/[_-]+/g, " ").trim().toLowerCase();
  return words.charAt(0).toUpperCase() + words.slice(1);
}
