/**
 * P5 — one shape for a paper in a list, whether it came from the search or from "similar papers",
 * so the card, the paper panel and the Evidence panel render it the same way.
 */

import type { ExplanationSchema, ResearchSearchResultItem, ResearchWorkRead, SimilarResearchItem } from "../../types/discovery";
import type { ExplanationContext } from "../../utils/research";

export type PaperScoreKind = "relevance" | "similarity";

export interface PaperItem {
  work: ResearchWorkRead;
  rank: number;
  /** The API's score for this list (0–1): search relevance, or similarity to the chosen paper. */
  score: number | null;
  scoreKind: PaperScoreKind;
  context: ExplanationContext;
  explanation: ExplanationSchema | null;
  /** Topics shared with the query or the chosen paper, as the API names them. */
  sharedTopics: string[];
  /** The publication venue, when the explanation names it (the paper record has no venue field). */
  venue: string | null;
}

export function fromSearchResult(item: ResearchSearchResultItem): PaperItem {
  return {
    work: item.work,
    rank: item.rank,
    score: item.final_score,
    scoreKind: "relevance",
    context: "search",
    explanation: item.explanation ?? null,
    sharedTopics: item.explanation?.topic_evidence?.shared_topic_names ?? [],
    venue: item.explanation?.academic_evidence?.canonical_venue_name ?? null,
  };
}

export function fromSimilarItem(item: SimilarResearchItem): PaperItem {
  return {
    work: item.work,
    rank: item.rank,
    score: item.combined_similarity,
    scoreKind: "similarity",
    context: "similar",
    explanation: item.explanation ?? null,
    sharedTopics: item.shared_topic_names?.length ? item.shared_topic_names : (item.explanation?.topic_evidence?.shared_topic_names ?? []),
    venue: item.explanation?.academic_evidence?.canonical_venue_name ?? null,
  };
}

/** The paper-based tools, with the paper in the address. */
export function similarHref(workId: string): string {
  return `/similar?paper=${encodeURIComponent(workId)}`;
}

export function venuesHref(workId: string): string {
  return `/opportunities?paper=${encodeURIComponent(workId)}`;
}

/** What "Why …?" says on this list's cards. */
export function explainLabel(context: ExplanationContext): string {
  if (context === "similar") return "Why similar?";
  if (context === "venue") return "Why this venue?";
  return "Why this result?";
}
