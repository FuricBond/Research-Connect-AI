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
