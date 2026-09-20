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
  adaptive_score?: number;
  adaptive_contributions?: AdaptivePersonalizationContribution[];
  calibration_score?: number;
  contextual_score?: number;
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

// =============================================================================
// Phase 5.4 — Researcher Feedback & Interaction Signal Types
// =============================================================================

export type InteractionType =
  | "VIEWED"
  | "OPENED"
  | "SAVED"
  | "DISMISSED"
  | "HIDDEN"
  | "INTERESTED"
  | "NOT_INTERESTED"
  | "APPLIED"
  | "SHARED";

export interface InteractionCreateRequest {
  interaction_type: InteractionType;
  source?: string;
  client_event_id?: string;
  metadata_payload?: Record<string, unknown>;
}

export interface InteractionResponse {
  id: string;
  profile_id: string;
  opportunity_id: string;
  interaction_type: InteractionType;
  is_explicit_feedback: boolean;
  source: string;
  client_event_id?: string | null;
  metadata_payload: Record<string, unknown>;
  created_at: string;
}

export interface OpportunityInteractionHistoryResponse {
  opportunity_id: string;
  profile_id: string;
  interactions: InteractionResponse[];
  total_count: number;
  limit: number;
  offset: number;
}

export interface ResearcherInteractionSummaryResponse {
  profile_id: string;
  total_interactions: number;
  positive_explicit_count: number;
  negative_explicit_count: number;
  saved_count: number;
  dismissed_count: number;
  hidden_count: number;
  interested_count: number;
  not_interested_count: number;
  viewed_count: number;
  opened_count: number;
  applied_count: number;
  shared_count: number;
  counts_by_type: Record<string, number>;
  most_recent_interaction?: InteractionResponse | null;
  recent_interactions: InteractionResponse[];
  interaction_strength_signal?: number | null;
}

// =============================================================================
// Phase 5.5 — Adaptive Preference Signal Aggregation & Personalization Bridge Types
// =============================================================================

export type AdaptiveSignalDimension =
  | "OPPORTUNITY_TYPE"
  | "DELIVERY_MODE"
  | "LOCATION"
  | "PUBLISHER"
  | "RESEARCH_TOPIC";

export type AdaptiveEvidenceState =
  | "INSUFFICIENT_EVIDENCE"
  | "EMERGING"
  | "ESTABLISHED"
  | "STRONG"
  | "CONFLICT";

export interface AdaptivePreferenceSignal {
  id: string;
  profile_id: string;
  dimension: AdaptiveSignalDimension;
  signal_value: string;
  positive_evidence_count: number;
  negative_evidence_count: number;
  total_evidence_count: number;
  decay_adjusted_positive_weight: number;
  decay_adjusted_negative_weight: number;
  weighted_signal_strength: number;
  confidence: number;
  evidence_state: AdaptiveEvidenceState;
  evidence_window_days: number;
  latest_evidence_timestamp?: string | null;
  algorithm_version: string;
  deterministic_explanation: string;
  created_at: string;
  updated_at: string;
}

export interface AdaptivePersonalizationContribution {
  dimension: AdaptiveSignalDimension;
  signal_value: string;
  signal_strength: number;
  confidence: number;
  evidence_state: AdaptiveEvidenceState;
  weight: number;
  raw_contribution: number;
  bounded_contribution: number;
  calibration_modifier?: number;
  contextual_modifier?: number;
  explanation: string;
}

export interface AdaptiveSignalsResponse {
  profile_id: string;
  items: AdaptivePreferenceSignal[];
  total_count: number;
}

export interface AdaptiveSignalExplanationResponse {
  profile_id: string;
  established_signals_count: number;
  emerging_signals_count: number;
  insufficient_signals_count: number;
  conflict_signals_count: number;
  summary_explanation: string;
  dimension_explanations: Record<string, string[]>;
}

export interface AdaptiveSignalRecomputeRequest {
  force?: boolean;
}

// =============================================================================
// Phase 5.6 — Personalization Calibration & Feedback Loop Types
// =============================================================================

export type CalibrationState =
  | "INSUFFICIENT_DATA"
  | "EARLY_SIGNAL"
  | "CALIBRATING"
  | "STABLE"
  | "CONFLICTED";

export type AttributionConfidence =
  | "DIRECT"
  | "LIKELY"
  | "WEAK"
  | "UNATTRIBUTED";

export type FeedbackOutcomeType =
  | "STRONG_POSITIVE"
  | "MODERATE_POSITIVE"
  | "WEAK_POSITIVE"
  | "NEGATIVE"
  | "NEUTRAL";

export interface RecommendationFeedbackAttribution {
  id: string;
  profile_id: string;
  opportunity_id: string;
  interaction_id?: string | null;
  dimension: string;
  signal_value: string;
  personalization_contribution: number;
  interaction_type: string;
  outcome_type: FeedbackOutcomeType;
  attribution_confidence: AttributionConfidence;
  attribution_weight: number;
  decay_adjusted_weight: number;
  recommendation_timestamp: string;
  interaction_timestamp: string;
  algorithm_version: string;
  created_at: string;
}

export interface PersonalizationCalibration {
  id: string;
  profile_id: string;
  signal_id?: string | null;
  dimension: string;
  signal_value: string;
  recommendations_influenced_count: number;
  positive_outcome_count: number;
  negative_outcome_count: number;
  neutral_outcome_count: number;
  accumulated_positive_weight: number;
  accumulated_negative_weight: number;
  net_calibration_modifier: number;
  calibration_confidence: number;
  calibration_state: CalibrationState;
  algorithm_version: string;
  deterministic_explanation: string;
  latest_feedback_timestamp?: string | null;
  created_at: string;
  updated_at: string;
}

export interface PersonalizationCalibrationResponse {
  profile_id: string;
  items: PersonalizationCalibration[];
  total_count: number;
  state_counts: Record<string, number>;
  average_confidence: number;
  calibrated_signals_count: number;
}

export interface PersonalizationCalibrationDetailResponse {
  calibration: PersonalizationCalibration;
  attributions: RecommendationFeedbackAttribution[];
  total_attributions: number;
}

export interface CalibrationRecomputeRequest {
  attribution_window_days?: number;
}

// =============================================================================
// Phase 5.7 — Personalization Quality Evaluation & Contextual Adaptation Types
// =============================================================================

export type QualityEvaluationState =
  | "INSUFFICIENT_DATA"
  | "EARLY_SIGNAL"
  | "EVALUATING"
  | "STABLE"
  | "POSITIVE"
  | "NEGATIVE"
  | "MIXED";

export type ContextualFallbackLevel =
  | "RESEARCHER_EXACT_CONTEXT"
  | "RESEARCHER_BROAD_CONTEXT"
  | "GLOBAL_SIGNAL_CALIBRATION"
  | "NEUTRAL";

export interface PersonalizationQualityEvaluation {
  id: string;
  profile_id: string;
  evaluation_period_days: number;
  recommendations_evaluated_count: number;
  attributed_interactions_count: number;
  positive_outcomes_count: number;
  negative_outcomes_count: number;
  neutral_outcomes_count: number;
  observed_engagement_rate: number;
  observed_positive_rate: number;
  observed_negative_rate: number;
  baseline_engagement_rate: number;
  baseline_positive_rate: number;
  observed_personalization_lift: number;
  confidence: number;
  evaluation_state: QualityEvaluationState;
  diversity_score: number;
  novelty_rate: number;
  contextual_breakdown: Record<string, unknown>;
  deterministic_explanation: string;
  algorithm_version: string;
  created_at: string;
  updated_at: string;
}

export interface PersonalizationContextualAdaptation {
  id: string;
  profile_id: string;
  dimension: string;
  signal_value: string;
  context_dimension: string;
  context_value: string;
  sample_size: number;
  positive_count: number;
  negative_count: number;
  observed_lift: number;
  confidence: number;
  fallback_level: ContextualFallbackLevel;
  contextual_modifier: number;
  hysteresis_state: string;
  evaluation_state: QualityEvaluationState;
  deterministic_explanation: string;
  algorithm_version: string;
  created_at: string;
  updated_at: string;
}

export interface ContextualSummaryItem {
  context_dimension: string;
  context_value: string;
  sample_size: number;
  positive_rate: number;
  observed_lift: number;
  evaluation_state: QualityEvaluationState;
  explanation: string;
}

export interface SignalQualitySummaryItem {
  dimension: string;
  signal_value: string;
  sample_size: number;
  positive_count: number;
  negative_count: number;
  observed_lift: number;
  confidence: number;
  evaluation_state: QualityEvaluationState;
  contexts_count: number;
  explanation: string;
}

export interface PersonalizationQualityResponse {
  profile_id: string;
  evaluation: PersonalizationQualityEvaluation;
  context_summaries: ContextualSummaryItem[];
  deterministic_explanation: string;
}

export interface ContextualAdaptationsResponse {
  profile_id: string;
  items: PersonalizationContextualAdaptation[];
  total_count: number;
}

export interface SignalQualityResponse {
  profile_id: string;
  items: SignalQualitySummaryItem[];
  total_count: number;
}

export interface QualityRecomputeRequest {
  reference_time?: string;
  evaluation_period_days?: number;
  force_recompute?: boolean;
}


