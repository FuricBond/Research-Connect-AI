/**
 * TypeScript definitions for Phase 2.4 Discovery & Explainability APIs.
 *
 * Fully aligned with backend Pydantic models in `backend/app/schemas/discovery.py`.
 */
import type { OpportunityDeadline, OpportunityRead, RiskExplanation } from "./opportunity";

export type RankingMode = "general" | "research_similarity" | "research_opportunity";

export interface ResearchWorkRead {
  id: string;
  openalex_id?: string | null;
  doi?: string | null;
  title: string;
  abstract?: string | null;
  publication_year?: number | null;
  publication_date?: string | null;
  work_type?: string | null;
  language?: string | null;
  cited_by_count?: number | null;
  is_oa?: boolean | null;
  oa_status?: string | null;
  landing_page_url?: string | null;
  volume?: string | null;
  issue?: string | null;
  page?: string | null;
  article_number?: string | null;
  license_url?: string | null;
  primary_source_id?: string | null;
  ingestion_source_id?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface SignalContributionSchema {
  signal_name: string;
  score: number;
  weight: number;
  contribution: number;
  qualitative_assessment: string;
  is_available: boolean;
  is_primary_driver: boolean;
  raw_value?: any | null;
  is_active?: boolean;
}

export interface TopicEvidenceSchema {
  shared_topic_ids: string[];
  shared_topic_names: string[];
  topic_similarity: number;
  description: string;
}

export interface ProvenanceEvidenceSchema {
  retrieval_sources: string[];
  description: string;
}

export interface ScoreBreakdownSchema {
  base_score: number;
  relevance_subtotal: number;
  contextual_subtotal: number;
  academic_subtotal: number;
  reranker_adjustment: number;
  diversity_adjustment: number;
  final_score: number;
  reconciliation_gap: number;
  is_reconciled: boolean;
}

export interface AcademicEvidenceSchema {
  citation_count?: number | null;
  citation_impact_score: number;
  author_prominence_score: number;
  lead_author_citations?: number | null;
  author_position?: string | null;
  author_position_score: number;
  institution_names: string[];
  institution_prestige_score: number;
  canonical_venue_name?: string | null;
  venue_prestige_score: number;
  is_in_doaj: boolean;
  oa_status?: string | null;
  open_access_tier_score: number;
  description: string;
}

export interface RerankerExplanationSchema {
  enabled: boolean;
  applied: boolean;
  weight: number;
  pre_rerank_score?: number | null;
  post_rerank_score?: number | null;
  adjustment: number;
  raw_score?: number | null;
  fallback: boolean;
  description: string;
}

export interface DiversityExplanationSchema {
  enabled: boolean;
  applied: boolean;
  adjustment: number;
  redundancy_score?: number | null;
  novelty_score?: number | null;
  redundancy_reasons: string[];
  novelty_reasons: string[];
  description: string;
}

export interface RankingComparisonResponse {
  winner_id: string;
  loser_id: string;
  score_difference: number;
  relevance_difference: number;
  academic_difference: number;
  contextual_difference: number;
  reranker_difference: number;
  diversity_difference: number;
  dominant_factors: string[];
  summary: string;
}

export interface RankingComparisonRequest {
  candidate_a_id: string;
  candidate_b_id: string;
  candidate_type?: string;
  ranking_mode?: string;
}

export interface ExplanationSchema {
  summary: string;
  strengths: string[];
  limitations: string[];
  signal_contributions: Record<string, SignalContributionSchema>;
  topic_evidence: TopicEvidenceSchema;
  provenance_evidence: ProvenanceEvidenceSchema;
  primary_factors: string[];
  final_score: number;
  rank: number;
  base_score?: number | null;
  score_breakdown?: ScoreBreakdownSchema | null;
  academic_evidence?: AcademicEvidenceSchema | null;
  reranker_explanation?: RerankerExplanationSchema | null;
  diversity_explanation?: DiversityExplanationSchema | null;
}

export interface QueryIntelligenceSchema {
  original_query: string;
  normalized_query: string;
  expanded_query: string;
  was_expanded: boolean;
  detected_acronyms: string[];
  detected_terms: string[];
  transformations: string[];
}

export interface ResearchSearchResultItem {
  work: ResearchWorkRead;
  rank: number;
  final_score: number;
  semantic_score?: number | null;
  lexical_score?: number | null;
  topic_score?: number | null;
  freshness_score?: number | null;
  quality_score?: number | null;
  retrieval_sources: string[];
  explanation?: ExplanationSchema | null;
}

export interface ResearchSearchResponse {
  query: string;
  items: ResearchSearchResultItem[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
  ranking_mode: string;
  query_intelligence?: QueryIntelligenceSchema | null;
}

export interface SimilarResearchItem {
  work: ResearchWorkRead;
  rank: number;
  combined_similarity: number;
  semantic_similarity: number;
  lexical_similarity: number;
  topic_similarity: number;
  freshness?: number | null;
  shared_topic_ids: string[];
  shared_topic_names: string[];
  retrieval_sources: string[];
  explanation?: ExplanationSchema | null;
}

export interface SimilarResearchResponse {
  source_work_id: string;
  items: SimilarResearchItem[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
  ranking_mode: string;
}

export interface OpportunityMatchItem {
  opportunity: OpportunityRead;
  rank: number;
  match_score: number;
  semantic_similarity: number;
  lexical_similarity: number;
  topic_similarity: number;
  type_compatibility: number;
  urgency?: number | null;
  quality_score?: number | null;
  shared_topic_ids: string[];
  shared_topic_names: string[];
  retrieval_sources: string[];
  explanation?: ExplanationSchema | null;
  risk_explanation?: RiskExplanation | null;
  deadline_explanation?: OpportunityDeadline | null;
}

export interface OpportunityMatchResponse {
  research_work_id: string;
  items: OpportunityMatchItem[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
  ranking_mode: string;
}

export interface ResearchSearchParams {
  q: string;
  limit?: number;
  offset?: number;
  publication_year?: number;
  min_year?: number;
  max_year?: number;
  work_type?: string;
  language?: string;
  primary_source_id?: string;
  is_oa?: boolean;
  min_citations?: number;
  ranking_mode?: RankingMode;
  explain?: boolean;
  include_query_intelligence?: boolean;
}

export interface SimilarResearchParams {
  limit?: number;
  offset?: number;
  publication_year?: number;
  min_year?: number;
  max_year?: number;
  work_type?: string;
  language?: string;
  primary_source_id?: string;
  is_oa?: boolean;
  min_citations?: number;
  ranking_mode?: RankingMode;
  explain?: boolean;
  require_embedding?: boolean;
}

export interface OpportunityMatchParams {
  limit?: number;
  offset?: number;
  opportunity_type?: string;
  status?: string;
  delivery_mode?: string;
  source_id?: string;
  upcoming_only?: boolean;
  submission_deadline_after?: string;
  max_apc_usd?: number;
  require_known_apc?: boolean;
  location?: string;
  ranking_mode?: RankingMode;
  explain?: boolean;
  require_embedding?: boolean;
}

