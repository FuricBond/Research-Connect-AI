import { cx } from "../../utils/cx";
import styles from "./Indicators.module.css";

export type MatchBand = "strong" | "good" | "partial" | "weak";

/**
 * Bands are a presentation of the backend's score; ranking is unchanged. Thresholds from
 * DESIGN_SYSTEM.md §3.2 (open question Q3: validate against real score distributions).
 */
export function matchBand(percent: number): MatchBand {
  if (percent >= 70) return "strong";
  if (percent >= 45) return "good";
  if (percent >= 25) return "partial";
  return "weak";
}

const NOUN = { match: "match", fit: "fit", relevance: "relevance" } as const;
const BAND_WORD: Record<MatchBand, string> = { strong: "Strong", good: "Good", partial: "Partial", weak: "Weak" };
const BAND_CLASS: Record<MatchBand, string> = {
  strong: styles.matchStrong,
  good: styles.matchGood,
  partial: styles.matchPartial,
  weak: styles.matchWeak,
};

interface MatchScoreProps {
  /** 0–1 or 0–100; values ≤ 1 are read as a fraction. */
  score: number | null | undefined;
  kind?: keyof typeof NOUN;
  /** Show the exact percentage after the band (default true). */
  showValue?: boolean;
  className?: string;
}

/**
 * "Good match · 62%": the band word is the signal, the number is secondary and always in the
 * text (and so in the accessible name). One petrol scale: a low score is neutral, never red.
 * Pair it with the reason ("Why this match?") wherever it appears.
 */
export function MatchScore({ score, kind = "match", showValue = true, className }: MatchScoreProps) {
  if (score === null || score === undefined || Number.isNaN(score)) {
    return <span className={cx(styles.indicator, styles.match, styles.matchWeak, className)}>Not scored</span>;
  }
  const percent = Math.round(score <= 1 ? score * 100 : score);
  const band = matchBand(percent);
  return (
    <span className={cx(styles.indicator, styles.match, BAND_CLASS[band], className)}>
      {BAND_WORD[band]} {NOUN[kind]}
      {showValue && <span className={styles.matchValue}> · {percent}%</span>}
    </span>
  );
}
