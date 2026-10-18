import Link from "next/link";
import type { PeerMatchTier } from "../../types/peer";
import { PEER_TIER_LABELS } from "../../types/peer";
import { cx } from "../../utils/cx";
import styles from "./Indicators.module.css";

/** The band words the fit APIs return (postings: Strong/Good/Partial/Low). */
export type FitBand = "Strong" | "Good" | "Partial" | "Low" | "Weak";

const BAND_CLASS: Record<FitBand, string> = {
  Strong: styles.matchStrong,
  Good: styles.matchGood,
  Partial: styles.matchPartial,
  Low: styles.matchWeak,
  Weak: styles.matchWeak,
};

/** Supervisor and peer matching name their tiers themselves; the badge uses those words. */
const TIER_CLASS: Record<PeerMatchTier, string> = {
  STRONG: styles.matchStrong,
  MODERATE: styles.matchGood,
  EXPLORATORY: styles.matchPartial,
  INSUFFICIENT_EVIDENCE: styles.matchWeak,
};

function bandOf(value: string | null | undefined): FitBand | null {
  if (!value) return null;
  const word = value.charAt(0).toUpperCase() + value.slice(1).toLowerCase();
  return (Object.keys(BAND_CLASS) as FitBand[]).includes(word as FitBand) ? (word as FitBand) : null;
}

interface FitScoreProps {
  /** 0–100 as the API returns it, or null when nothing could be compared. */
  score: number | null | undefined;
  /** The API's own band word; the badge never re-bands the score. */
  band?: string | null;
  /** Or a supervisor/peer match tier, shown in that API's words ("Strong match"). */
  tier?: PeerMatchTier | null;
  /** The strongest reason, in the API's words. */
  reason?: string | null;
  /** What would raise a partial or low fit (the API's gaps), shown as an action. */
  gaps?: readonly string[];
  className?: string;
}

/**
 * "Good fit · 62%" (DESIGN_SYSTEM.md §9 FitScore): the API's band word first, the exact value
 * second, then the strongest reason. A partial or low fit reads as something to act on —
 * "Partial fit — add your skills to improve it" — with the skills the API says are missing and a
 * link to the research preferences, never as a judgement. No score is "Fit not scored".
 */
export function FitScore({ score, band, tier, reason, gaps = [], className }: FitScoreProps) {
  if (tier) {
    if (score === null || score === undefined || Number.isNaN(score)) {
      return <span className={cx(styles.indicator, styles.match, styles.matchWeak, className)}>Fit not scored</span>;
    }
    const thin = tier === "EXPLORATORY" || tier === "INSUFFICIENT_EVIDENCE";
    return (
      <span className={cx(styles.fit, className)}>
        <span className={cx(styles.indicator, styles.match, TIER_CLASS[tier])}>
          {PEER_TIER_LABELS[tier]}
          <span className={styles.matchValue}> · {Math.round(score)}%</span>
        </span>
        {reason && <span className={styles.fitReason}>{reason}</span>}
        {thin && (
          <span className={styles.fitAction}>
            Matches rest on your research topics. <Link href="/researcher/preferences">Add research topics</Link> to sharpen them.
          </span>
        )}
      </span>
    );
  }
  const word = bandOf(band);
  if (score === null || score === undefined || Number.isNaN(score) || !word) {
    return <span className={cx(styles.indicator, styles.match, styles.matchWeak, className)}>Fit not scored</span>;
  }
  const actionable = word === "Partial" || word === "Low" || word === "Weak";
  return (
    <span className={cx(styles.fit, className)}>
      <span className={cx(styles.indicator, styles.match, BAND_CLASS[word])}>
        {word} fit<span className={styles.matchValue}> · {Math.round(score)}%</span>
      </span>
      {reason && <span className={styles.fitReason}>{reason}</span>}
      {actionable && (
        <span className={styles.fitAction}>
          {gaps.length > 0 ? `To improve it: ${gaps.slice(0, 3).join(", ")}. ` : "Add your skills to improve it. "}
          <Link href="/researcher/preferences">Update your research preferences</Link>
        </span>
      )}
    </span>
  );
}
