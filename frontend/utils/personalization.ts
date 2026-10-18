/**
 * P6 — personalization in words (DESIGN_SYSTEM.md §7, §18).
 *
 * Names for what the backend already decided: preference categories, how strong an inferred
 * preference is, how much personalization moved a recommendation, which kind of reason a factor
 * is. Nothing here scores or ranks; every number shown next to these words is the API's.
 */

import type { ExplanationReasonCategory, PreferenceCategory, ResearcherPreferenceItem, SignalImpact } from "../types/researcher";
import type { PersonalizationImpact } from "../types/personalization";
import { humanizeEnum } from "./date";

const CATEGORY_LABELS: Record<PreferenceCategory, string> = {
  OPPORTUNITY_TYPE: "Kind of call",
  DELIVERY_MODE: "Attendance",
  TOPIC: "Topic",
  LOCATION: "Location",
  DEADLINE_WINDOW: "Deadline window",
  OPEN_ACCESS: "Open access",
  VENUE: "Venue",
  KEYWORD: "Keyword",
  RESEARCH_DOMAIN: "Research area",
  COUNTRY: "Country",
  REGION: "Region",
  INSTITUTION: "Institution",
  FUNDING: "Funding",
  ACADEMIC_LEVEL: "Academic level",
  CAREER_STAGE: "Career stage",
};

export function preferenceCategoryLabel(category: string): string {
  return CATEGORY_LABELS[category as PreferenceCategory] ?? humanizeEnum(category);
}

/** The categories that name research topics (the profile lists them as declared topics). */
export const TOPIC_CATEGORIES: readonly string[] = ["TOPIC", "KEYWORD", "RESEARCH_DOMAIN"];

/** What a preference says, in words: "Conference", "Online"… (the API's own label first). */
export function preferenceLabel(item: Pick<ResearcherPreferenceItem, "display_label" | "preference_value">): string {
  return item.display_label?.trim() || humanizeEnum(item.preference_value);
}

/**
 * How strong an inferred preference is, in words. A presentation of the API's 0–1 strength
 * (≥ 0.7 strong, ≥ 0.4 moderate, below that light); the evidence sentence beside it is the API's.
 */
export function strengthWord(strength: number | null | undefined): string {
  if (strength === null || strength === undefined || Number.isNaN(strength)) return "Not known";
  if (strength >= 0.7) return "Strong";
  if (strength >= 0.4) return "Moderate";
  return "Light";
}

const IMPACT_LABELS: Record<PersonalizationImpact, string> = {
  STRONG_PERSONALIZATION: "Your preferences moved it a lot",
  MODERATE_PERSONALIZATION: "Your preferences moved it somewhat",
  LOW_PERSONALIZATION: "Your preferences moved it a little",
  NO_PERSONALIZATION: "Your preferences did not move it",
  PERSONALIZATION_SUPPRESSED: "Personalization was held back for this one",
};

export function personalizationImpactLabel(impact: string | null | undefined): string {
  return (impact && IMPACT_LABELS[impact as PersonalizationImpact]) || humanizeEnum(impact);
}

const FACTOR_CATEGORY: Record<ExplanationReasonCategory, string> = {
  EXPLICIT_PREFERENCE: "Your preferences",
  EXPERTISE_MATCH: "Your publications",
  BEHAVIORAL_SIGNAL: "Your activity",
  PROFILE_MATCH: "Your profile",
  DOMAIN_RELEVANCE: "Relevance to your research",
  DEADLINE_URGENCY: "Deadline",
  TRUST_SAFETY: "Venue trust",
  NEGATIVE_SIGNAL: "Against it",
};

export function factorCategoryLabel(category: string): string {
  return FACTOR_CATEGORY[category as ExplanationReasonCategory] ?? humanizeEnum(category);
}

/** "Counted for it", "Counted against it", "A caution", "Neutral": what a factor did, in words, never a colour alone. */
export function impactWord(impact: SignalImpact | string | null | undefined): string {
  if (impact === "POSITIVE") return "Counted for it";
  if (impact === "NEGATIVE") return "Counted against it";
  if (impact === "WARNING") return "A caution";
  return "Neutral";
}

/** The four kinds of Phase 5.9 factor, in the order the backend applies them, with their words. */
export const PERSONALIZATION_FACTOR_GROUPS = [
  { key: "explicit_preference_factors", label: "Your stated preferences" },
  { key: "adaptive_signal_factors", label: "What you saved and marked" },
  { key: "calibration_factors", label: "How your feedback was weighed" },
  { key: "contextual_factors", label: "The kind of call it is" },
] as const;

/** "79% confidence" from the explanation's 0–1 confidence; null when it did not say. */
export function confidenceLabel(confidence: number | null | undefined): string | null {
  if (typeof confidence !== "number" || !Number.isFinite(confidence)) return null;
  return `${Math.round(confidence * 100)}% confidence`;
}

/** The backend's leading marks ("✓ ", "✕ ", "⚠️ ") are dropped: the words carry the meaning. */
export function withoutMark(text: string): string {
  // ✓ ✔ ✕ ✗ ○ ● • ⚠, with or without the emoji variation selector.
  return text.replace(/^(?:[\u2713\u2714\u2715\u2717\u25CB\u25CF\u2022\u26A0]\uFE0F?\s*)+/u, "");
}

/** "(PRIMARY_EXPERTISE)", "(POSITIVE)" at the end of an API label, in words: "(primary expertise)". */
export function wordedSuffix(text: string): string {
  return text.replace(/\(([A-Z][A-Z_]+)\)\s*$/, (_, code: string) => `(${code.replace(/_+/g, " ").toLowerCase()})`);
}

/** Unique ignoring case and spacing, keeping the first spelling. */
export function uniqueWords(values: readonly string[]): string[] {
  const seen = new Set<string>();
  return values.filter((value) => {
    const key = value.trim().toLowerCase().replace(/\s+/g, " ");
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

const MATCH_STATE: Record<string, string> = {
  PREFERRED_MATCH: "Matches your preferences",
  EXCLUDED_MATCH: "Excluded by your preferences",
  CONFLICT: "Your preferences disagree about it",
  PARTIAL_MATCH: "Partly matches your preferences",
  NEUTRAL: "No preference applies",
  INSUFFICIENT_EVIDENCE: "Not enough information to compare",
};

/** A Phase 5.2 preference match state, in words. */
export function preferenceMatchLabel(state: string | null | undefined): string {
  return (state && MATCH_STATE[state]) || humanizeEnum(state);
}

const ACADEMIC_STATUS: Record<string, string> = {
  UNDERGRADUATE: "Undergraduate",
  POSTGRADUATE: "Postgraduate",
  PHD: "PhD",
  POSTDOC: "Postdoctoral researcher",
  FACULTY: "Faculty",
  RESEARCHER: "Researcher",
  OTHER: "Other",
};

/** A career stage in words ("PhD", not "Phd"); an unset stage is null, never shown as "Unknown". */
export function academicStatusLabel(status: string | null | undefined): string | null {
  if (!status || status === "UNKNOWN") return null;
  return ACADEMIC_STATUS[status] ?? humanizeEnum(status);
}
