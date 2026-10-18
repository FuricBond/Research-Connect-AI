/**
 * P5 — research data in words (DESIGN_SYSTEM.md §7, §9).
 *
 * The ranking signals, publication types and call facts the API returns, named for people. These
 * are labels for what the backend already decided; nothing here scores, ranks or judges.
 */

import type { ExplanationSchema, SignalContributionSchema } from "../types/discovery";
import { humanizeEnum } from "./date";

/** Where an explanation comes from: the search names its keyword signal after the query. */
export type ExplanationContext = "search" | "similar" | "venue" | "recommendation";

interface SignalWords {
  /** The short reason on a card's evidence line ("Similar meaning · Shared topics"); a noun phrase, so it also reads in a sentence. */
  reason: string;
  /** The meter's name in the Evidence panel. */
  meter: string;
  /** One sentence on what the signal measures. */
  about: string;
}

const SIGNALS: Record<string, SignalWords> = {
  semantic_similarity: { reason: "Similar meaning", meter: "Meaning", about: "How close the meaning of the text is, beyond the exact words." },
  lexical_similarity: { reason: "Matching terms", meter: "Shared terms", about: "How many of the same words and phrases appear." },
  topic_similarity: { reason: "Shared topics", meter: "Topics", about: "How many research topics they have in common." },
  type_compatibility: { reason: "Paper type fit", meter: "Paper type fit", about: "Whether this kind of venue publishes this kind of paper." },
  opportunity_quality: { reason: "Venue indexing", meter: "Venue indexing", about: "Whether the venue is listed in recognised indexes." },
  urgency: { reason: "Deadline timing", meter: "Deadline timing", about: "How soon the submission deadline is." },
  freshness: { reason: "Recency", meter: "Recency", about: "How recently the paper was published." },
  citation_impact: { reason: "Citation count", meter: "Citations", about: "How often other papers cite it." },
  author_prominence: { reason: "Author track record", meter: "Author track record", about: "How widely cited the authors' work is." },
  author_position: { reason: "Author position", meter: "Author position", about: "Where the lead author sits in the author list." },
  institution_prestige: { reason: "Institution record", meter: "Institution", about: "The track record of the authors' institutions." },
  venue_prestige: { reason: "Venue record", meter: "Venue", about: "The track record of the venue it was published in." },
  open_access_tier: { reason: "Open access", meter: "Open access", about: "Whether anyone can read it without a subscription." },
};
// The names the backend's explainer uses (app/explainability/result_explainer.py); the ones above
// are the older labels the previous drawer knew, kept so either spelling reads the same.
SIGNALS.lexical_relevance = SIGNALS.lexical_similarity;
SIGNALS.topic_compatibility = SIGNALS.topic_similarity;
SIGNALS.deadline_urgency = SIGNALS.urgency;
SIGNALS.publication_freshness = SIGNALS.freshness;

const LEXICAL = new Set(["lexical_similarity", "lexical_relevance"]);

function words(signal: string): SignalWords {
  return SIGNALS[signal] ?? { reason: humanizeEnum(signal), meter: humanizeEnum(signal), about: "" };
}

/** The meter name; the search calls its keyword signal "Search terms". */
export function signalName(signal: string, context: ExplanationContext = "search"): string {
  if (LEXICAL.has(signal) && context === "search") return "Search terms";
  return words(signal).meter;
}

export function signalDescription(signal: string, context: ExplanationContext = "search"): string {
  if (LEXICAL.has(signal) && context === "search") return "How many of your search words appear in the title and abstract.";
  if (signal === "semantic_similarity" && context === "search") return "How close the meaning is to your query, beyond the exact words.";
  return words(signal).about;
}

/**
 * The strongest reasons, in words: the backend's own primary factors, in its order. An item
 * without an explanation, or whose factors are all weak, has no reasons (never made up).
 */
export function topReasons(explanation: ExplanationSchema | null | undefined, count = 2): string[] {
  const factors = explanation?.primary_factors ?? [];
  const seen = new Set<string>();
  const reasons: string[] = [];
  for (const factor of factors) {
    const reason = words(factor).reason;
    if (seen.has(reason)) continue;
    seen.add(reason);
    reasons.push(reason);
    if (reasons.length === count) break;
  }
  return reasons;
}

/** "Ranked #1 mainly for similar meaning and shared topics." — the primary factors as a sentence. */
export function plainSummary(explanation: ExplanationSchema, rank?: number | null): string | null {
  const reasons = topReasons(explanation, 3).map((reason) => reason.toLowerCase());
  if (reasons.length === 0) return null;
  const list = reasons.length === 1 ? reasons[0] : `${reasons.slice(0, -1).join(", ")} and ${reasons[reasons.length - 1]}`;
  return rank ? `Ranked #${rank} mainly for ${list}.` : `Mainly for ${list}.`;
}

/** The signals that counted (weight above zero), strongest contribution first. */
export function countedSignals(explanation: ExplanationSchema | null | undefined): SignalContributionSchema[] {
  return Object.values(explanation?.signal_contributions ?? {})
    .filter((signal) => signal.weight > 0 && signal.is_active !== false)
    .sort((a, b) => b.contribution - a.contribution);
}

/** "Very Strong" -> "Very strong"; the backend's verbal tier for a signal, in sentence case. */
export function assessmentWord(value: string | null | undefined): string {
  return humanizeEnum(value?.replace(/\s+/g, "_"));
}

/* ── Papers ─────────────────────────────────────────────────────────────────────────────── */

const WORK_TYPE_LABELS: Record<string, string> = {
  article: "Journal article",
  "journal-article": "Journal article",
  preprint: "Preprint",
  "posted-content": "Preprint",
  "book-chapter": "Book chapter",
  book: "Book",
  dataset: "Dataset",
  "proceedings-article": "Conference paper",
  review: "Review",
  dissertation: "Thesis",
  report: "Report",
};

/** The publication type in words; an unknown type is shown in sentence case, never as a code. */
export function workTypeLabel(type: string | null | undefined): string | null {
  if (!type) return null;
  return WORK_TYPE_LABELS[type.toLowerCase()] ?? humanizeEnum(type);
}

/** A DOI as the API gives it, without a resolver prefix ("10.1109/…"). */
export function bareDoi(doi: string | null | undefined): string | null {
  if (!doi) return null;
  const bare = doi.trim().replace(/^https?:\/\/(dx\.)?doi\.org\//i, "").replace(/^doi:/i, "");
  return bare || null;
}

export function doiHref(doi: string): string {
  return `https://doi.org/${bareDoi(doi) ?? doi}`;
}

/** "217 citations", "1 citation"; null when the count is unknown. */
export function citationsLabel(count: number | null | undefined): string | null {
  if (count === null || count === undefined || Number.isNaN(count)) return null;
  return `${count.toLocaleString("en")} citation${count === 1 ? "" : "s"}`;
}

/* ── Calls for papers ───────────────────────────────────────────────────────────────────── */

const CALL_TYPE_LABELS: Record<string, string> = {
  CONFERENCE: "Conference",
  JOURNAL: "Journal",
  WORKSHOP: "Workshop",
  CALL_FOR_PAPERS: "Call for papers",
  SPECIAL_ISSUE: "Special issue",
};

export const CALL_TYPES = Object.keys(CALL_TYPE_LABELS);

export function callTypeLabel(type: string | null | undefined): string {
  if (!type) return "Call";
  return CALL_TYPE_LABELS[type] ?? humanizeEnum(type);
}

const DELIVERY_MODE_LABELS: Record<string, string> = {
  OFFLINE: "In person",
  ONLINE: "Online",
  HYBRID: "Hybrid",
};

export const DELIVERY_MODES = Object.keys(DELIVERY_MODE_LABELS);

export function deliveryModeLabel(mode: string | null | undefined): string | null {
  if (!mode) return null;
  return DELIVERY_MODE_LABELS[mode] ?? humanizeEnum(mode);
}

/**
 * A call's fee as the API records it (`apc_or_fee`), in words: "No fee", "USD 1,200",
 * "Fee charged (amount not stated)", or null when nothing is recorded.
 */
export function feeLabel(fee: Record<string, unknown> | null | undefined): string | null {
  if (!fee) return null;
  if (fee.has_fee === false || fee.amount === 0) return "No fee";
  if (typeof fee.amount === "number") {
    const currency = typeof fee.currency === "string" && fee.currency ? fee.currency : "USD";
    return `${currency} ${fee.amount.toLocaleString("en")}`;
  }
  if (fee.has_fee === true) return "Fee charged (amount not stated)";
  return null;
}

const CALL_STATUS_LABELS: Record<string, string> = {
  ACTIVE: "Open",
  EXPIRED: "Closed",
  UNVERIFIED: "Not yet verified",
  ARCHIVED: "Archived",
  DRAFT: "Draft",
};

/** A call's lifecycle status as the API records it, in words. */
export function callStatusLabel(status: string | null | undefined): string | null {
  if (!status) return null;
  return CALL_STATUS_LABELS[status] ?? humanizeEnum(status);
}
