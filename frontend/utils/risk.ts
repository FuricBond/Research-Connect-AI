/**
 * P0.5 — how a venue's risk assessment is presented.
 *
 * Risk is about trust in a venue; it is never styled like a deadline. Missing or insufficient
 * evidence is not a warning: it reads "Risk not assessed" in neutral styling. The levels come
 * from the backend's risk assessment unchanged; this only decides the words people see.
 */

export type RiskTone = "high" | "caution" | "low" | "unknown";

export interface RiskPresentation {
  tone: RiskTone;
  /** Short label, e.g. "High risk". */
  label: string;
  /** One sentence for a tooltip or an expanded explanation. */
  description: string;
}

const PRESENTATION: Record<RiskTone, RiskPresentation> = {
  high: {
    tone: "high",
    label: "High risk",
    description: "Several warning signs about this venue were found. Check it carefully before submitting.",
  },
  caution: {
    tone: "caution",
    label: "Some risk signs",
    description: "A few warning signs about this venue were found. Review the evidence before submitting.",
  },
  low: {
    tone: "low",
    label: "Low risk",
    description: "No warning signs about this venue were found.",
  },
  unknown: {
    tone: "unknown",
    label: "Risk not assessed",
    description: "There is not enough information about this venue to assess its risk. This is not a warning.",
  },
};

export function riskPresentation(
  level: string | null | undefined,
  options: { isPredatory?: boolean | null } = {}
): RiskPresentation {
  if (options.isPredatory || level === "HIGH_RISK") return PRESENTATION.high;
  if (level === "MODERATE_RISK") return PRESENTATION.caution;
  if (level === "LOW_RISK") return PRESENTATION.low;
  return PRESENTATION.unknown;
}
