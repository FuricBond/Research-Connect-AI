/**
 * P5 — API answers for the search, similar papers, venue matching and calls, shaped like the
 * backend's (backend/app/schemas/discovery.py, opportunity.py, deadline.py). Ids are UUIDs, as the
 * API's are, so the pages accept them.
 */

import type { ExplanationSchema, OpportunityMatchItem, ResearchSearchResultItem, ResearchWorkRead, SimilarResearchItem } from "../types/discovery";
import type { OpportunityDeadline, OpportunityListItem, OpportunityRead, RiskExplanation } from "../types/opportunity";

export const WORK_ID = "0b7a9c1e-1f2d-4e3a-9b8c-7d6e5f4a3b21";
export const OTHER_WORK_ID = "5c4b3a29-1817-4e6d-8c5b-4a3928170615";
export const CALL_ID = "9e8d7c6b-5a49-4382-9170-6f5e4d3c2b1a";

export function makeWork(overrides: Partial<ResearchWorkRead> = {}): ResearchWorkRead {
  return {
    id: WORK_ID,
    title: "Parameterized Explainer for Graph Neural Network",
    abstract:
      "Despite recent progress in Graph Neural Networks (GNNs), explaining predictions made by GNNs remains a challenging open problem. " +
      "The leading method independently addresses the local explanations to interpret each instance, which is time-consuming and lacks a global view.",
    publication_year: 2020,
    work_type: "preprint",
    cited_by_count: 217,
    is_oa: true,
    doi: "https://doi.org/10.48550/arxiv.2011.04573",
    landing_page_url: "https://arxiv.org/abs/2011.04573",
    ...overrides,
  };
}

export function makeExplanation(overrides: Partial<ExplanationSchema> = {}): ExplanationSchema {
  return {
    summary: "Ranked as a relevant research work driven primarily by semantic similarity and topic similarity.",
    strengths: ["The abstract discusses explanation methods for graph neural networks.", "Shares the topic Graph neural networks with the query."],
    limitations: ["Few of the exact query words appear in the title."],
    signal_contributions: {
      semantic_similarity: { signal_name: "semantic_similarity", score: 0.76, weight: 0.5, contribution: 0.38, qualitative_assessment: "Very Strong", is_available: true, is_primary_driver: true, is_active: true },
      topic_compatibility: { signal_name: "topic_compatibility", score: 0.6, weight: 0.2, contribution: 0.12, qualitative_assessment: "Moderate", is_available: true, is_primary_driver: true, is_active: true },
      citation_impact: { signal_name: "citation_impact", score: 0, weight: 0.1, contribution: 0, qualitative_assessment: "Not Available", is_available: false, is_primary_driver: false, is_active: true },
      lexical_relevance: { signal_name: "lexical_relevance", score: 0.09, weight: 0.3, contribution: 0.027, qualitative_assessment: "Minimal", is_available: true, is_primary_driver: false, is_active: true },
      publication_freshness: { signal_name: "publication_freshness", score: 0.4, weight: 0, contribution: 0, qualitative_assessment: "Low", is_available: true, is_primary_driver: false, is_active: false },
    },
    topic_evidence: { shared_topic_ids: ["t1"], shared_topic_names: ["Graph neural networks"], topic_similarity: 0.6, description: "One shared topic." },
    provenance_evidence: { retrieval_sources: ["semantic", "lexical"], description: "Found by meaning and by keywords." },
    primary_factors: ["semantic_similarity", "topic_compatibility"],
    final_score: 0.5634,
    rank: 1,
    score_breakdown: {
      base_score: 0.527,
      relevance_subtotal: 0.4,
      contextual_subtotal: 0.05,
      academic_subtotal: 0.077,
      reranker_adjustment: 0.0364,
      diversity_adjustment: 0,
      final_score: 0.5634,
      reconciliation_gap: 0,
      is_reconciled: true,
    },
    academic_evidence: {
      citation_count: 217,
      citation_impact_score: 0.7,
      author_prominence_score: 0.5,
      author_position_score: 0.5,
      institution_names: ["Pennsylvania State University"],
      institution_prestige_score: 0.4,
      canonical_venue_name: "NeurIPS",
      venue_prestige_score: 0.8,
      is_in_doaj: false,
      oa_status: "green",
      open_access_tier_score: 0.6,
      description: "",
    },
    ...overrides,
  };
}

export function makeSearchItem(overrides: Partial<ResearchSearchResultItem> = {}): ResearchSearchResultItem {
  return { work: makeWork(), rank: 1, final_score: 0.5634, retrieval_sources: ["semantic"], explanation: makeExplanation(), ...overrides };
}

export function searchAnswer(items: ResearchSearchResultItem[], total = items.length, extra: Record<string, unknown> = {}) {
  return { query: "q", items, total, limit: 20, offset: 0, has_more: total > items.length, ranking_mode: "general", query_intelligence: null, ...extra };
}

export function makeSimilarItem(overrides: Partial<SimilarResearchItem> = {}): SimilarResearchItem {
  return {
    work: makeWork({ id: OTHER_WORK_ID, title: "GNNExplainer: Generating Explanations for Graph Neural Networks", publication_year: 2019 }),
    rank: 1,
    combined_similarity: 0.72,
    semantic_similarity: 0.8,
    lexical_similarity: 0.3,
    topic_similarity: 0.6,
    shared_topic_ids: ["t1"],
    shared_topic_names: ["Graph neural networks", "Explainable AI"],
    retrieval_sources: ["semantic"],
    explanation: makeExplanation({ rank: 1 }),
    ...overrides,
  };
}

export function similarAnswer(items: SimilarResearchItem[], total = items.length, sourceId = WORK_ID) {
  return { source_work_id: sourceId, items, total, limit: 20, offset: 0, has_more: total > items.length, ranking_mode: "research_similarity" };
}

export function makeDeadline(days: number, overrides: Partial<{ status: string; tier: string }> = {}): OpportunityDeadline {
  const view = (type: string, date: string, d: number) => ({
    deadline_type: type,
    canonical_deadline: { deadline_type: type, local_date: date, local_time: "23:59:00", timezone_name: "AoE", utc_deadline: `${date}T11:59:59+00:00` },
    canonical_assessment: { deadline_type: type, reference_time: "2026-10-06T00:00:00Z", status: d < 0 ? "EXPIRED" : "UPCOMING", urgency_tier: d < 0 ? "EXPIRED" : "DISTANT", urgency_score: 0.2, days_remaining: d, confidence: 1, explanation: "" },
    selected_source: "WikiCFP",
    all_observations: [],
    revision_history: [],
    conflict_state: "NO_CONFLICT",
    confidence: 0.9,
    explanation: "",
    unresolved_alternatives: [],
    deterministic_explanation: "",
  });
  const submission = view("SUBMISSION", "2026-10-20", days);
  if (overrides.status) submission.canonical_assessment.status = overrides.status;
  if (overrides.tier) submission.canonical_assessment.urgency_tier = overrides.tier;
  return {
    reference_time: "2026-10-06T00:00:00Z",
    primary_milestone: "SUBMISSION",
    primary_view: submission,
    milestone_views: {
      CAMERA_READY: view("CAMERA_READY", "2026-12-11", days + 52),
      SUBMISSION: submission,
      ABSTRACT: view("ABSTRACT", "2026-10-13", days - 7),
      NOTIFICATION: view("NOTIFICATION", "2026-11-19", days + 30),
    },
    summary: "",
    overall_urgency_tier: overrides.tier ?? "DISTANT",
    has_extension: false,
    has_conflict: false,
    primary_reason: "",
  } as unknown as OpportunityDeadline;
}

export function makeCall(overrides: Partial<OpportunityRead> = {}): OpportunityRead {
  return {
    id: CALL_ID,
    title: "Workshop on Neural Retrieval Methods",
    opportunity_type: "WORKSHOP",
    publisher: "ACM",
    organizer: "ACM",
    summary: "Workshop hosted by ACM.",
    description: "Workshop on Neural Retrieval Methods invites full papers, short papers and posters.",
    delivery_mode: "ONLINE",
    location: "Online",
    submission_deadline: "2026-10-20T11:59:59+00:00",
    event_start_date: "2027-01-18",
    event_end_date: "2027-01-21",
    indexing: ["DBLP"],
    website_url: "https://example.org/neural-retrieval",
    submission_url: null,
    is_predatory_flag: false,
    risk_score: null,
    risk_level: "INSUFFICIENT_EVIDENCE",
    risk_confidence: null,
    deadline_intelligence: null,
    status: "ACTIVE",
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
    slug: null,
    series_name: null,
    edition: null,
    notification_date: "2026-11-19T00:00:00+00:00",
    camera_ready_deadline: "2026-12-11T00:00:00+00:00",
    apc_or_fee: null,
    risk_reasons: null,
    source_id: null,
    last_verified_at: null,
    ...overrides,
  };
}

export function asListItem(call: OpportunityRead): OpportunityListItem {
  return call;
}

export function listAnswer(items: OpportunityListItem[], total = items.length, page = 1) {
  return { items, page, page_size: 20, total };
}

export function makeRisk(overrides: Partial<RiskExplanation> = {}): RiskExplanation {
  return {
    risk_score: 0.12,
    risk_level: "LOW_RISK",
    risk_confidence: 0.8,
    evidence_sufficiency: "SUFFICIENT",
    is_predatory_flag: false,
    summary: "Indexed in DBLP and organised by an established society.",
    positive_trust_signals: [
      { signal: "indexed", category: "POSITIVE_TRUST", strength: "STRONG", confidence: "HIGH", provenance: "DBLP", source_field: "indexing", explanation: "Listed in DBLP.", is_present: true, contribution: 0.2, severity: "TRUST", evidence_type: "DIRECT_METADATA" },
    ],
    suspicious_signals: [],
    neutral_signals: [
      { signal: "fee", category: "NEUTRAL_UNKNOWN", strength: "NONE", confidence: "LOW", provenance: "metadata", source_field: "apc_or_fee", explanation: "No fee information was found.", is_present: false, contribution: 0, severity: "NEUTRAL", evidence_type: "DIRECT_METADATA" },
    ],
    graph_signals: [],
    venue_signals: [],
    publisher_signals: [],
    evidence_items: [],
    risk_reasons: [],
    provenance_summary: { DBLP: 1 },
    limitations: ["Based on public metadata only."],
    gross_negative_score: 0,
    trust_mitigation_score: 0.2,
    resolved_entity: null,
    ...overrides,
  };
}

export function makeMatchItem(overrides: Partial<OpportunityMatchItem> = {}): OpportunityMatchItem {
  return {
    opportunity: makeCall({ deadline_intelligence: makeDeadline(14) }),
    rank: 1,
    match_score: 0.61,
    semantic_similarity: 0.6,
    lexical_similarity: 0.2,
    topic_similarity: 0.5,
    type_compatibility: 0.9,
    urgency: 0.3,
    shared_topic_ids: [],
    shared_topic_names: ["Information retrieval"],
    retrieval_sources: ["semantic"],
    explanation: makeExplanation({ primary_factors: ["type_compatibility", "semantic_similarity"] }),
    risk_explanation: makeRisk({ risk_level: "INSUFFICIENT_EVIDENCE", summary: "Not enough evidence to assess this venue." }),
    deadline_explanation: makeDeadline(14),
    ...overrides,
  };
}

export function matchAnswer(items: OpportunityMatchItem[], total = items.length) {
  return { research_work_id: WORK_ID, items, total, limit: 20, offset: 0, has_more: false, ranking_mode: "research_opportunity" };
}
