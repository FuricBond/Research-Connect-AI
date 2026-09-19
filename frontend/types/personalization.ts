/**
 * TypeScript definitions for Phase 5.2 — Explicit Preference Interpretation & Personalization Signals.
 * Strict 1-to-1 parity with backend Pydantic schemas.
 */

export type PreferenceMatchType =
  | "PREFERRED_MATCH"
  | "EXCLUDED_MATCH"
  | "NEUTRAL"
  | "PARTIAL_MATCH"
  | "CONFLICT"
  | "INSUFFICIENT_EVIDENCE";

export type PreferenceDimension =
  | "KEYWORD"
  | "RESEARCH_DOMAIN"
  | "COUNTRY"
  | "REGION"
  | "INSTITUTION"
  | "FUNDING"
  | "ACADEMIC_LEVEL"
  | "CAREER_STAGE"
  | "OPPORTUNITY_TYPE";

export type SignalPolarity =
  | "POSITIVE"
  | "NEGATIVE"
  | "NEUTRAL"
  | "UNRESOLVED";

export interface PreferenceMatchSignal {
  signal_id: string;
  profile_id: string;
  opportunity_id: string;
  dimension: PreferenceDimension;
  preference_value: string;
  preference_type: string;
  opportunity_value: string | null;
  match_type: PreferenceMatchType;
  polarity: SignalPolarity;
  evidence: string;
  explanation: string;
  confidence: number;
  is_explicit: boolean;
  metadata_payload?: Record<string, unknown>;
}

export interface PreferencePersonalizationAssessment {
  profile_id: string;
  opportunity_id: string;
  overall_match_state: PreferenceMatchType;
  positive_matches_count: number;
  excluded_matches_count: number;
  conflict_count: number;
  neutral_dimensions_count: number;
  insufficient_evidence_count: number;
  total_evaluated_preferences: number;
  evidence_coverage: number;
  deterministic_explanation: string;
  dimension_signals: PreferenceMatchSignal[];
  positive_matches: PreferenceMatchSignal[];
  excluded_matches: PreferenceMatchSignal[];
  conflicts: PreferenceMatchSignal[];
  insufficient_evidence_dimensions: PreferenceDimension[];
  neutral_dimensions: PreferenceDimension[];
  computed_at: string;
}

export interface BatchOpportunityPreferenceMatchRequest {
  opportunity_ids: string[];
}

export interface BatchOpportunityPreferenceMatchResponse {
  profile_id: string;
  assessments: PreferencePersonalizationAssessment[];
  evaluated_count: number;
}
