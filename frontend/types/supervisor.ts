/**
 * Phase 5.13 — Find a Supervisor.
 *
 * Mirrors backend/app/schemas/supervisor_discovery.py.
 *
 * The supervisor is the same disclosure-filtered profile peer discovery returns, so it reuses
 * `PeerProfile`: an `institution` or `contact_email` arriving as null means the faculty member
 * chose not to show it. Scores, signals and matching papers are computed server-side and are only
 * rendered here, never recomputed.
 */

import type { PeerMatchTier, PeerProfile } from "./peer";
import type { PostingType } from "./posting";

export type SupervisorSignalType =
  | "TOPIC_FIT"
  | "SEMANTIC_FIT"
  | "RECENT_PAPER_EVIDENCE"
  | "TAXONOMY_PROXIMITY"
  | "SUPERVISION_AVAILABILITY"
  | "EXCLUDED_TOPIC_PENALTY";

export interface MatchingPaper {
  work_id: string;
  title: string;
  publication_year: number | null;
  /** Closeness in meaning, or the share of the paper's topics you hold when no embedding exists. */
  similarity: number;
  shared_topics: string[];
  doi: string | null;
  landing_page_url: string | null;
}

export interface OpenPostingRef {
  posting_id: string;
  title: string;
  posting_type: PostingType;
  application_deadline: string | null;
}

export interface SupervisorMatchSignal {
  signal_type: SupervisorSignalType;
  raw_score: number;
  weight: number;
  weighted_contribution: number;
  evidence: string[];
  explanation: string;
}

export interface SupervisorMatch {
  supervisor: PeerProfile;
  match_score: number;
  tier: PeerMatchTier;
  confidence: number;
  shared_topics: string[];
  matching_papers: MatchingPaper[];
  open_postings: OpenPostingRef[];
  signals: SupervisorMatchSignal[];
  explanation_reasons: string[];
}

export interface SupervisorMatchResponse {
  researcher_id: string;
  matches: SupervisorMatch[];
  total_candidates_evaluated: number;
  returned_count: number;
  algorithm_version: string;
  /** False when your interests could not be embedded; matches are then scored on topics only. */
  semantic_available: boolean;
  data_sufficiency: "SUFFICIENT" | "INSUFFICIENT_PROFILE" | "NO_CANDIDATES";
  /** Present when no matches could be produced, explaining which problem applies. */
  guidance: string | null;
}

export const SUPERVISOR_SIGNAL_LABELS: Record<SupervisorSignalType, string> = {
  TOPIC_FIT: "Shared topics",
  SEMANTIC_FIT: "Closeness in meaning",
  RECENT_PAPER_EVIDENCE: "Recent papers",
  TAXONOMY_PROXIMITY: "Related fields",
  SUPERVISION_AVAILABILITY: "Supervision availability",
  EXCLUDED_TOPIC_PENALTY: "Excluded topics",
};
