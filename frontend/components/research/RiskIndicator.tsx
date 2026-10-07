import { ShieldAlert, ShieldCheck, ShieldQuestion, ShieldX } from "lucide-react";
import { cx } from "../../utils/cx";
import { riskPresentation, type RiskTone } from "../../utils/risk";
import styles from "./Indicators.module.css";

const ICONS: Record<RiskTone, typeof ShieldX> = {
  high: ShieldX,
  caution: ShieldAlert,
  low: ShieldCheck,
  unknown: ShieldQuestion,
};

const TONE_CLASS: Record<RiskTone, string> = {
  high: styles.riskHigh,
  caution: styles.riskCaution,
  low: styles.riskLow,
  unknown: styles.riskUnknown,
};

/**
 * The canonical venue-risk indicator (DESIGN_SYSTEM.md §3.2 "RiskBadge"): a shield and a word —
 * "High risk", "Some risk signs", "Low risk", or a neutral "Risk not assessed" when the evidence
 * is missing. Red is kept for high risk; never styled like a deadline.
 * `risk-indicator risk-<tone>` stay on the element as stable hooks for tests.
 */
export function RiskIndicator({ level, isPredatory, className }: { level?: string | null; isPredatory?: boolean | null; className?: string }) {
  const risk = riskPresentation(level, { isPredatory });
  const Icon = ICONS[risk.tone];
  return (
    <span className={cx(styles.indicator, styles.risk, TONE_CLASS[risk.tone], "risk-indicator", `risk-${risk.tone}`, className)} title={risk.description}>
      <Icon size={14} aria-hidden="true" />
      <span>{risk.label}</span>
    </span>
  );
}
