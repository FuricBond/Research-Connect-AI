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

// =============================================================================
// Phase 5.3 — Personalization Scoring & Explainability Types
// =============================================================================

export interface PersonalizationContribution {
  dimension: PreferenceDimension;
  match_type: PreferenceMatchType;
  polarity: SignalPolarity;
  weight: number;
  raw_contribution: number;
  normalized_contribution: number;
  preference_value: string;
  opportunity_value: string | null;
  evidence: string;
  explanation: string;
}

export interface PersonalizationDimensionScore {
  dimension: PreferenceDimension;
  score: number;
  weight: number;
  weighted_score: number;
  status: PreferenceMatchType;
  explanation: string;
}

export interface PersonalizationScoreBreakdown {
  dimension_scores: Record<PreferenceDimension, PersonalizationDimensionScore>;
  positive_contributions: PersonalizationContribution[];
  negative_contributions: PersonalizationContribution[];
  neutral_contributions: PersonalizationContribution[];
  unresolved_contributions: PersonalizationContribution[];
  total_positive_weight: number;
  total_negative_weight: number;
  active_dimensions_count: number;
}

export interface PersonalizationExplanation {
  summary: string;
  positive_reasons: string[];
  negative_reasons: string[];
  unresolved_reasons: string[];
  insufficient_evidence_reasons: string[];
  neutral_reasons: string[];
}

export interface PersonalizationScore {
  bounded_score: number;
  normalized_score: number;
  absolute_score: number;
  raw_score: number;
  positive_contribution: number;
  negative_penalty: number;
  confidence: number;
  match_state: PreferenceMatchType;
}

export interface PersonalizationAssessment {
  profile_id: string;
  opportunity_id: string;
  personalization_score: number;
  score: PersonalizationScore;
  breakdown: PersonalizationScoreBreakdown;
  explanation: PersonalizationExplanation;
  preference_assessment: PreferencePersonalizationAssessment;
  evaluated_at: string;
}

export interface BatchPersonalizationRequest {
  opportunity_ids: string[];
}

export interface BatchPersonalizationResponse {
  profile_id: string;
  assessments: PersonalizationAssessment[];
  evaluated_count: number;
}

