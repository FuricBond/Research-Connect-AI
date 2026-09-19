/**
 * Phase 4.7: Unified Research Intelligence Types
 *
 * Strict TypeScript types for unified research-intelligence context,
 * bounded recommendations, signal provenance, and 6-tier explainability.
 * Matches backend app.schemas.research_intelligence schemas 1-to-1.
 */

export type SignalProvenanceType =
  | "EXPLICIT_PREFERENCE"
  | "INFERRED_PREFERENCE"
  | "SCHOLARLY_EXPERTISE"
  | "EMERGING_INTEREST"
  | "HISTORICAL_INTERACTION"
  | "WORKSPACE_COLLABORATION"
  | "OPPORTUNITY_METRIC"
  | "PROFILE_ATTRIBUTE";

export type SignalSource =
  | "USER_DECLARED"
  | "RESEARCH_PROFILE"
  | "OPENALEX_KNOWLEDGE"
  | "BEHAVIORAL_FEEDBACK"
  | "WORKSPACE_SERVICE"
  | "SUBMISSION_ENGINE"
  | "HYBRID_SEARCH"
  | "DEADLINE_ENGINE"
  | "RISK_ENGINE"
  | "COLLABORATION_SERVICE";

export type EvidenceTierType =
  | "OPPORTUNITY_RELEVANCE"
  | "RESEARCHER_EVIDENCE"
  | "RESEARCH_INTEREST_EVIDENCE"
  | "PREFERENCE_EVIDENCE"
  | "DEADLINE_EVIDENCE"
  | "RISK_EVIDENCE"
  | "WORKSPACE_CONTEXT";

export type IdentityResolutionStatus =
  | "RESOLVED"
  | "UNRESOLVED"
  | "AMBIGUOUS"
  | "SELF_DECLARED_ONLY";

export interface ResearchIntelligenceSignal {
  signal_id: string;
  signal_type: SignalProvenanceType;
  source: SignalSource;
  confidence: number;
  strength: number;
  evidence: string;
  contributing_entity_id?: string | null;
  contributing_entity_type?: string | null;
  is_explicit: boolean;
  observed_at: string;
  metadata_payload?: Record<string, unknown>;
}

export interface UnifiedResearcherContext {
  profile_id: string;
  user_id: string;
  full_name: string;
  academic_status: string;
  institution_name?: string | null;
  department?: string | null;
  identity_status: IdentityResolutionStatus;
  canonical_researcher_id?: string | null;
  orcid?: string | null;
  openalex_id?: string | null;
  is_identity_ambiguous: boolean;
  completeness_score: number;
  is_cold_start: boolean;
  is_partial_profile: boolean;
  signals: ResearchIntelligenceSignal[];
  active_interests_count: number;
  explicit_preferences_count: number;
  inferred_preferences_count: number;
  saved_opportunities_count: number;
  active_submissions_count: number;
  upcoming_tasks_count: number;
  calendar_events_count: number;
}

export interface OpportunityWorkspaceContext {
  is_saved: boolean;
  saved_id?: string | null;
  saved_status?: string | null;
  has_active_submission: boolean;
  submission_stage?: string | null;
  submission_readiness_score?: number | null;
  workspace_member_count: number;
}

export interface EvidenceTierBreakdown {
  tier: EvidenceTierType;
  tier_title: string;
  score_contribution: number;
  confidence: number;
  summary: string;
  signals: ResearchIntelligenceSignal[];
  is_active: boolean;
}

export interface UnifiedRecommendationItem {
  opportunity_id: string;
  title: string;
  sponsor?: string | null;
  opportunity_type?: string | null;
  funder_type?: string | null;
  amount_total?: number | null;
  currency?: string | null;
  deadline?: string | null;
  composite_score: number;
  relevance_score: number;
  personalization_score: number;
  relevance_dominant_applied: boolean;
  risk_level?: string | null;
  risk_score?: number | null;
  is_high_risk: boolean;
  risk_factors: string[];
  deadline_status?: string | null;
  deadline_urgency?: string | null;
  deadline_source_authority?: string | null;
  days_remaining?: number | null;
  workspace_context: OpportunityWorkspaceContext;
  primary_match_reason: string;
  evidence_tiers: EvidenceTierBreakdown[];
}

export interface UnifiedRecommendationResponse {
  researcher_id: string;
  total_candidates: number;
  returned_count: number;
  identity_status: IdentityResolutionStatus;
  is_cold_start: boolean;
  relevance_dominance_guarantee: string;
  recommendations: UnifiedRecommendationItem[];
  benchmark_stats?: Record<string, unknown> | null;
}

export interface UnifiedOpportunityIntelligence {
  researcher_id: string;
  opportunity_id: string;
  opportunity_title: string;
  relevance_score: number;
  personalization_score: number;
  composite_score: number;
  relevance_dominant_applied: boolean;
  evidence_tiers: EvidenceTierBreakdown[];
  workspace_context: OpportunityWorkspaceContext;
  identity_status: IdentityResolutionStatus;
  evaluated_at: string;
}
