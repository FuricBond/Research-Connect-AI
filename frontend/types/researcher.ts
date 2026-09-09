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


