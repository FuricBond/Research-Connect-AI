export type AcademicStatus =
  | "UNDERGRADUATE"
  | "POSTGRADUATE"
  | "PHD"
  | "POSTDOC"
  | "FACULTY"
  | "RESEARCHER"
  | "OTHER"
  | "UNKNOWN";

export type CompletenessLevel = "INCOMPLETE" | "BASIC" | "INTERMEDIATE" | "COMPLETE";

export interface ExternalIdentifiers {
  orcid?: string | null;
  openalex_id?: string | null;
  google_scholar_id?: string | null;
  scopus_id?: string | null;
  semantic_scholar_id?: string | null;
  [key: string]: unknown;
}

export interface InstitutionSummary {
  id: string;
  display_name: string;
  ror?: string | null;
  country_code?: string | null;
  institution_type?: string | null;
  homepage_url?: string | null;
}

export interface ResearcherWorkSummary {
  id: string;
  title: string;
  doi?: string | null;
  publication_year?: number | null;
  work_type?: string | null;
  author_position?: string | null;
  is_corresponding: boolean;
  cited_by_count: number;
}

export interface ProfileCompleteness {
  score: number;
  percentage: number;
  level: CompletenessLevel;
  is_complete: boolean;
  missing_fields: string[];
  field_breakdown: Record<string, boolean>;
}

export interface ResearcherProfile {
  id: string;
  user_id: string;
  full_name: string;
  email?: string | null;
  academic_status: AcademicStatus;
  academic_level?: string | null;
  department?: string | null;
  bio?: string | null;
  institution_id?: string | null;
  institution_name?: string | null;
  institution?: InstitutionSummary | null;
  canonical_researcher_id?: string | null;
  orcid?: string | null;
  openalex_id?: string | null;
  external_identifiers: ExternalIdentifiers;
  keywords: string[];
  target_opportunity_types: string[];
  completeness: ProfileCompleteness;
  works_count: number;
  created_at: string;
  updated_at: string;
}

export interface ResearcherProfileCreatePayload {
  full_name: string;
  email: string;
  institution_name?: string | null;
  institution_id?: string | null;
  department?: string | null;
  academic_status?: AcademicStatus;
  academic_level?: string | null;
  bio?: string | null;
  orcid?: string | null;
  openalex_id?: string | null;
  external_identifiers?: ExternalIdentifiers;
  keywords?: string[];
  target_opportunity_types?: string[];
}

export interface ResearcherProfileUpdatePayload {
  full_name?: string | null;
  institution_name?: string | null;
  institution_id?: string | null;
  department?: string | null;
  academic_status?: AcademicStatus | null;
  academic_level?: string | null;
  bio?: string | null;
  orcid?: string | null;
  openalex_id?: string | null;
  external_identifiers?: ExternalIdentifiers | null;
  keywords?: string[] | null;
  target_opportunity_types?: string[] | null;
}

// ── Phase 3.2 — Researcher Interest & Expertise Intelligence Types ──────────

export type ExpertiseClassification =
  | "PRIMARY_EXPERTISE"
  | "SECONDARY_EXPERTISE"
  | "EMERGING_INTEREST"
  | "WEAK_INTEREST"
  | "INSUFFICIENT_EVIDENCE";

export interface SupportingWorkReference {
  id: string;
  title: string;
  doi?: string | null;
  publication_year?: number | null;
  work_type?: string | null;
  author_position?: string | null;
  is_corresponding: boolean;
  cited_by_count: number;
  topic_confidence?: number | null;
}

export interface ResearcherInterestItem {
  topic_id?: string | null;
  topic_name: string;
  topic_slug: string;
  topic_category?: string | null;
  strength: number;
  confidence: number;
  evidence_count: number;
  recency_score: number;
  classification: ExpertiseClassification;
  is_primary_expertise: boolean;
  first_observed_year?: number | null;
  last_observed_year?: number | null;
  source: string;
  provenance_reasons: string[];
  supporting_works: SupportingWorkReference[];
}

export interface ResearcherIntelligenceSummary {
  total_topics_analyzed: number;
  primary_expertise_count: number;
  secondary_expertise_count: number;
  emerging_interest_count: number;
  total_works_analyzed: number;
  active_years_span?: string | null;
  has_profile_keywords: boolean;
}

export interface ResearcherIntelligenceResponse {
  researcher_id: string;
  profile_id?: string | null;
  canonical_researcher_id?: string | null;
  display_name: string;
  interests: ResearcherInterestItem[];
  expertise: ResearcherInterestItem[];
  emerging: ResearcherInterestItem[];
  summary: ResearcherIntelligenceSummary;
  generated_at: string;
}

// ── Phase 3.3 — Personal Preference Intelligence Types ──────────────────────

export type PreferenceCategory =
  | "OPPORTUNITY_TYPE"
  | "DELIVERY_MODE"
  | "TOPIC"
  | "LOCATION"
  | "DEADLINE_WINDOW"
  | "OPEN_ACCESS"
  | "VENUE";

export type PreferenceSource = "EXPLICIT" | "INFERRED" | "DERIVED_FROM_EXPERTISE";

export interface PreferenceConflict {
  category: string;
  conflicting_values: string[];
  reason: string;
  is_critical: boolean;
}

export interface PreferenceCompleteness {
  score: number;
  percentage: number;
  is_complete: boolean;
  missing_dimensions: string[];
  dimension_breakdown: Record<string, boolean>;
}

export interface ResearcherPreferenceItem {
  id: string;
  profile_id: string;
  category: PreferenceCategory;
  preference_key: string;
  preference_value: string;
  display_label: string;
  canonical_id?: string | null;
  strength: number;
  confidence: number;
  source: PreferenceSource;
  is_active: boolean;
  recency_score: number;
  provenance?: Record<string, unknown> | null;
  provenance_reasons: string[];
  last_observed_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ResearcherPreferenceCreatePayload {
  category: PreferenceCategory;
  preference_key?: string | null;
  preference_value: string;
  display_label?: string | null;
  canonical_id?: string | null;
  strength?: number;
  is_active?: boolean;
}

export interface ResearcherPreferenceUpdatePayload {
  preference_value?: string | null;
  display_label?: string | null;
  strength?: number | null;
  is_active?: boolean | null;
}

export interface PreferenceIntelligenceSummary {
  total_preferences: number;
  explicit_count: number;
  inferred_count: number;
  derived_count: number;
  has_conflicts: boolean;
  confidence_level: "HIGH" | "MEDIUM" | "LOW" | string;
  completeness_percentage: number;
}

export interface ResearcherPreferenceIntelligenceResponse {
  profile_id: string;
  user_id: string;
  display_name: string;
  explicit_preferences: ResearcherPreferenceItem[];
  inferred_preferences: ResearcherPreferenceItem[];
  derived_candidates: ResearcherPreferenceItem[];
  conflicts: PreferenceConflict[];
  completeness: PreferenceCompleteness;
  summary: PreferenceIntelligenceSummary;
  generated_at: string;
}

// ── Phase 3.4 — Personalized Candidate Generation Types ──────────────────────

export type CandidateSourceType =
  | "EXPLICIT_PREFERENCE"
  | "INFERRED_PREFERENCE"
  | "RESEARCH_EXPERTISE"
  | "RESEARCH_INTEREST"
  | "PROFILE_KEYWORD"
  | "COLD_START_FALLBACK";

export interface CandidateProvenance {
  candidate_id: string;
  opportunity_id: string;
  sources: CandidateSourceType[];
  matched_topics: string[];
  matched_preferences: string[];
  matched_expertise: string[];
  reasons: string[];
  retrieval_channels: string[];
}

export interface PersonalizedCandidateOpportunity {
  id: string;
  title: string;
  opportunity_type: string;
  delivery_mode: string;
  location?: string | null;
  organizer?: string | null;
  submission_deadline?: string | null;
  website_url?: string | null;
  topics: string[];
  status: string;
  is_predatory_flag: boolean;
  risk_level?: string | null;
  risk_score?: number | null;
  risk_reasons: string[];
  deadline_status?: string | null;
  days_remaining?: number | null;
  urgency_tier?: string | null;
  deadline_explanation?: string | null;
}

export interface PersonalizedCandidateItem {
  candidate_id: string;
  opportunity: PersonalizedCandidateOpportunity;
  provenance: CandidateProvenance;
  eligibility_passed: boolean;
  eligibility_reasons: string[];
}

export interface CandidateSourceCoverage {
  explicit_preference_count: number;
  inferred_preference_count: number;
  expertise_count: number;
  profile_count: number;
  fallback_count: number;
  unique_candidate_count: number;
  deduplication_ratio: number;
}

export interface PersonalizedCandidateSetResponse {
  researcher_id: string;
  candidate_count: number;
  is_cold_start: boolean;
  coverage: CandidateSourceCoverage;
  candidates: PersonalizedCandidateItem[];
  metadata: Record<string, unknown>;
}

// ── Phase 3.5 — Personalization Ranking Layer Types ──────────────────────────

export interface PersonalizationScoreBreakdown {
  explicit_preference_score: number;
  inferred_preference_score: number;
  expertise_match_score: number;
  profile_match_score: number;
  provenance_score: number;
  raw_personalization_score: number;
  relevance_damping: number;
  behavioral_score?: number;
  behavioral_confidence?: number;
  behavioral_adjustment?: number;
}

export interface MatchedPersonalizationSignals {
  matched_preferences: string[];
  matched_expertise: string[];
  matched_topics: string[];
  matched_types: string[];
}

export interface PersonalizedRankedCandidate {
  opportunity_id: string;
  rank: number;
  base_rank: number;
  rank_delta: number;
  final_score: number;
  base_relevance_score: number;
  personalization_score: number;
  personalization_adjustment: number;
  score_breakdown: PersonalizationScoreBreakdown;
  matched_signals: MatchedPersonalizationSignals;
  provenance: CandidateProvenance;
  opportunity: PersonalizedCandidateOpportunity;
  explanation?: RecommendationExplanation | null;
}

export interface AblationSummary {
  total_candidates: number;
  reordered_candidates_count: number;
  max_rank_promotion: number;
  max_rank_demotion: number;
  average_personalization_adjustment: number;
  invariants_verified: boolean;
}

export interface PersonalizedRankingResponse {
  researcher_id: string;
  total_candidates: number;
  ranked_count: number;
  is_cold_start: boolean;
  personalization_enabled: boolean;
  max_personalization_contribution: number;
  recommendations: PersonalizedRankedCandidate[];
  ablation_summary?: AblationSummary | null;
  metadata: Record<string, unknown>;
}

// ── Phase 3.6 — Feedback & Recommendation Learning Types ─────────────────────

export type FeedbackType =
  | "VIEW"
  | "SAVE"
  | "DISMISS"
  | "INTERESTED"
  | "NOT_INTERESTED"
  | "APPLY";

export type FeedbackSource =
  | "RECOMMENDATION_FEED"
  | "SEARCH_RESULT"
  | "OPPORTUNITY_DETAIL"
  | "SAVED_LIST"
  | "MANUAL_ACTION";

export interface FeedbackCreatePayload {
  opportunity_id: string;
  feedback_type: FeedbackType;
  source?: FeedbackSource;
  notes?: string;
  rank_position?: number;
  recommendation_session_id?: string;
  metadata_snapshot?: Record<string, unknown>;
}

export interface FeedbackItem {
  id: string;
  researcher_id: string;
  opportunity_id: string;
  feedback_type: FeedbackType;
  source: FeedbackSource;
  notes?: string | null;
  rank_position?: number | null;
  recommendation_session_id?: string | null;
  metadata_snapshot?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
  opportunity_title?: string | null;
  opportunity_type?: string | null;
  delivery_mode?: string | null;
  location?: string | null;
}

export interface FeedbackListResponse {
  items: FeedbackItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface BehavioralSignal {
  category: string;
  preference_key: string;
  preference_value: string;
  display_label: string;
  raw_score: number;
  normalized_score: number;
  confidence: number;
  sample_size: number;
  direction: "POSITIVE" | "NEGATIVE";
  recency_score: number;
  last_interacted_at?: string | null;
}

export interface FeedbackSummaryResponse {
  total_feedback_count: number;
  counts_by_type: Record<string, number>;
  top_positive_topics: string[];
  top_negative_topics: string[];
  overall_confidence: number;
  suppressed_count: number;
  is_cold_start: boolean;
}

// ── Phase 3.7 — Recommendation History & Evaluation Types ─────────────────────

export interface RecommendationOpportunityBrief {
  id: string;
  title: string;
  opportunity_type?: string | null;
  delivery_mode?: string | null;
  organizer?: string | null;
  submission_deadline?: string | null;
}

export interface RecommendationItemSnapshot {
  id: string;
  snapshot_id: string;
  opportunity_id: string;
  rank: number;
  base_relevance_score: number;
  personalization_score: number;
  behavioral_adjustment: number;
  final_score: number;
  risk_level?: string | null;
  deadline_status?: string | null;
  created_at: string;
  opportunity?: RecommendationOpportunityBrief | null;
  user_feedback: string[];
}

export interface RecommendationSnapshotSummary {
  id: string;
  researcher_id: string;
  ranking_version: string;
  candidate_count: number;
  returned_count: number;
  request_context: Record<string, unknown>;
  created_at: string;
  top_opportunity_titles: string[];
}

export interface RecommendationSnapshotDetail {
  id: string;
  researcher_id: string;
  ranking_version: string;
  candidate_count: number;
  returned_count: number;
  request_context: Record<string, unknown>;
  created_at: string;
  items: RecommendationItemSnapshot[];
}

export interface RecommendationHistoryResponse {
  researcher_id: string;
  items: RecommendationSnapshotSummary[];
  total: number;
  limit: number;
  offset: number;
}

export type DataSufficiencyStatus =
  | "SUFFICIENT_DATA"
  | "INSUFFICIENT_DATA"
  | "NO_FEEDBACK"
  | "NO_HISTORY";

export interface EvaluationMetrics {
  precision_at_5?: number | null;
  precision_at_10?: number | null;
  recall_at_10?: number | null;
  hit_rate_at_5?: number | null;
  hit_rate_at_10?: number | null;
  ndcg_at_5?: number | null;
  ndcg_at_10?: number | null;
  save_rate?: number | null;
  engagement_rate?: number | null;
  dismissal_rate?: number | null;
  data_status: DataSufficiencyStatus;
  sample_size: number;
  feedback_count: number;
  notes?: string | null;
}

export interface VersionComparisonSummary {
  ranking_version: string;
  display_name: string;
  sample_size: number;
  data_status: DataSufficiencyStatus;
  metrics: EvaluationMetrics;
}

export interface RecommendationEvaluationResponse {
  researcher_id: string;
  ranking_version?: string | null;
  total_snapshots: number;
  total_recommendations: number;
  total_feedback_events: number;
  data_status: DataSufficiencyStatus;
  metrics: EvaluationMetrics;
  ranking_comparison?: Record<string, VersionComparisonSummary> | null;
  evaluated_at: string;
}

// ── Phase 3.8 — Personalization Explainability Types ─────────────────────────

export type ExplanationReasonCategory =
  | "EXPLICIT_PREFERENCE"
  | "RESEARCH_EXPERTISE"
  | "RESEARCH_INTEREST"
  | "BEHAVIORAL_FEEDBACK"
  | "PROFILE_KEYWORD"
  | "DOMAIN_RELEVANCE"
  | "DEADLINE_URGENCY"
  | "TRUST_AND_SAFETY";

export type SignalImpact = "POSITIVE" | "NEGATIVE" | "NEUTRAL";

export interface ExplanationFactor {
  category: ExplanationReasonCategory;
  summary: string;
  detail?: string | null;
  impact: SignalImpact;
  weight_or_score?: number | null;
  is_primary: boolean;
}

export interface RecommendationExplanation {
  opportunity_id: string;
  researcher_id: string;
  rank: number;
  final_score: number;
  base_relevance_score: number;
  personalization_contribution: number;
  personalization_strength: string;
  primary_reasons: string[];
  supporting_reasons: string[];
  behavioral_reasons: string[];
  preference_reasons: string[];
  expertise_reasons: string[];
  negative_reasons: string[];
  factors: ExplanationFactor[];
  risk_summary?: string | null;
  trust_status?: string | null;
  deadline_summary?: string | null;
  confidence: string;
  confidence_score: number;
  is_historical: boolean;
  ranking_version: string;
  generated_at: string;
}

export interface LearnedSignalItem {
  category: string;
  display_label: string;
  strength: string;
  direction: string;
  normalized_score: number;
  confidence: number;
  supporting_event_count: number;
}

export interface PersonalizationSummaryResponse {
  researcher_id: string;
  active_interests_count: number;
  strong_expertise_count: number;
  explicit_preferences_count: number;
  behavioral_signals_count: number;
  personalization_confidence: string;
  confidence_score: number;
  is_cold_start: boolean;
  has_feedback: boolean;
  total_feedback_count: number;
  learned_topics: LearnedSignalItem[];
  learned_opportunity_types: LearnedSignalItem[];
  learned_delivery_modes: LearnedSignalItem[];
  top_positive_signals: string[];
  top_negative_signals: string[];
}
