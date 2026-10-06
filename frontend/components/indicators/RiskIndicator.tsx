import { ShieldAlert, ShieldCheck, ShieldQuestion, ShieldX } from "lucide-react";
import { riskPresentation, type RiskTone } from "../../utils/risk";

const ICONS: Record<RiskTone, typeof ShieldX> = {
  high: ShieldX,
  caution: ShieldAlert,
  low: ShieldCheck,
  unknown: ShieldQuestion,
};

/**
 * P0.5 — a venue's risk in words with a shield icon: "High risk", "Some risk signs",
 * "Low risk", or a neutral "Risk not assessed" when the evidence is missing. Never styled like
 * a deadline.
 */
export function RiskIndicator({ level, isPredatory }: { level?: string | null; isPredatory?: boolean | null }) {
  const risk = riskPresentation(level, { isPredatory });
  const Icon = ICONS[risk.tone];
  return (
    <span className={`risk-indicator risk-${risk.tone}`} title={risk.description}>
      <Icon size={14} aria-hidden="true" />
      <span>{risk.label}</span>
    </span>
  );
}
