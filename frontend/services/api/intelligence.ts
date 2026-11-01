import type { ApiEvidenceTier, ApiOpportunityIntelligence, ApiUnifiedRecommendationItem, ApiUnifiedRecommendationResponse, ApiWorkspaceContext, EvidenceTierBreakdown, OpportunityWorkspaceContext, UnifiedOpportunityIntelligence, UnifiedRecommendationItem, UnifiedRecommendationResponse, UnifiedResearcherContext } from "../../types/research_intelligence";
import { fetchJson } from "./client";

// ----------------------------------------------------------------------------
// Phase 4.7: Unified Research Intelligence API Methods
// ----------------------------------------------------------------------------

export async function getUnifiedResearchIntelligence(
  researcherId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<UnifiedResearcherContext> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<UnifiedResearcherContext>(
    `/api/v1/researchers/${researcherId}/intelligence/unified`,
    { headers, signal }
  );
}

export async function getUnifiedRecommendations(
  researcherId: string,
  params?: { query?: string; limit?: number; include_evidence?: boolean },
  userId?: string,
  signal?: AbortSignal
): Promise<UnifiedRecommendationResponse> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  const searchParams = new URLSearchParams();
  if (params?.query) searchParams.set("query", params.query);
  if (params?.limit !== undefined) searchParams.set("limit", String(params.limit));
  if (params?.include_evidence !== undefined) searchParams.set("include_evidence", String(params.include_evidence));
  const queryString = searchParams.toString();
  const url = `/api/v1/researchers/${researcherId}/recommendations/unified${queryString ? `?${queryString}` : ""}`;
  const response = await fetchJson<ApiUnifiedRecommendationResponse>(url, { headers, signal });
  return toUnifiedRecommendationResponse(response);
}

export async function getOpportunityIntelligence(
  researcherId: string,
  opportunityId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<UnifiedOpportunityIntelligence> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  const response = await fetchJson<ApiOpportunityIntelligence>(
    `/api/v1/researchers/${researcherId}/recommendations/unified/${opportunityId}/intelligence`,
    { headers, signal }
  );
  return toOpportunityIntelligence(response);
}

// ── Unified intelligence adapters ────────────────────────────────────────────
// The backend schemas (app/schemas/research_intelligence.py) are the contract; these map
// its responses onto the view models the Unified Intelligence components render.

function toEvidenceTier(tier: ApiEvidenceTier): EvidenceTierBreakdown {
  const score = Number(tier.score_or_status);
  const isScore = tier.score_or_status.trim() !== "" && Number.isFinite(score);
  return {
    tier: tier.tier,
    tier_title: tier.title,
    score_contribution: isScore ? score : 0,
    status_label: isScore ? null : tier.score_or_status.replace(/_/g, " "),
    confidence: null,
    summary: tier.summary,
    signals: tier.signals ?? [],
    is_active: tier.is_active,
  };
}

function toWorkspaceContext(context: ApiWorkspaceContext): OpportunityWorkspaceContext {
  return {
    is_saved: context.is_saved,
    saved_id: context.workspace_item_id ?? null,
    saved_status: context.workspace_status ?? null,
    has_active_submission: context.has_active_submission,
    submission_stage: context.submission_status ?? null,
    submission_readiness_score: context.submission_readiness_score ?? null,
    workspace_member_count: 0,
  };
}

function toRecommendationItem(item: ApiUnifiedRecommendationItem): UnifiedRecommendationItem {
  const risk = item.risk_explanation;
  const assessment = item.deadline_intelligence?.primary_view?.canonical_assessment;
  const days = assessment?.days_remaining;
  return {
    opportunity_id: item.opportunity_id,
    title: item.title,
    sponsor: item.organizer ?? item.publisher ?? null,
    opportunity_type: item.opportunity_type ?? null,
    funder_type: null,
    amount_total: null,
    currency: null,
    deadline: item.submission_deadline ?? null,
    composite_score: item.final_score,
    relevance_score: item.base_relevance_score,
    personalization_score: item.personalization_score,
    relevance_dominant_applied: true,
    risk_level: risk?.risk_level ?? null,
    risk_score: risk?.risk_score ?? null,
    is_high_risk: risk ? risk.risk_level === "HIGH_RISK" || risk.is_predatory_flag : false,
    risk_factors: risk?.risk_reasons ?? [],
    deadline_status: assessment?.status ?? null,
    deadline_urgency: assessment?.urgency_tier ?? null,
    deadline_source_authority:
      item.deadline_intelligence?.primary_view?.selected_observation?.authority_tier ?? null,
    days_remaining: typeof days === "number" && days >= 0 ? Math.floor(days) : null,
    workspace_context: toWorkspaceContext(item.workspace_context),
    primary_match_reason:
      item.explanation?.primary_reasons?.[0] ?? item.explanation?.personalization_strength ?? "",
    evidence_tiers: (item.evidence_tiers ?? []).map(toEvidenceTier),
    explanation: item.explanation ?? null,
  };
}

export function toUnifiedRecommendationResponse(
  response: ApiUnifiedRecommendationResponse
): UnifiedRecommendationResponse {
  const context = response.researcher_context;
  const items = response.items ?? [];
  return {
    researcher_id: context.profile_id,
    total_candidates: response.total_count,
    returned_count: items.length,
    identity_status: context.identity_status,
    is_cold_start: context.is_cold_start,
    relevance_dominance_guarantee:
      response.invariants_verified === false
        ? "Relevance dominance could not be verified for this ranking."
        : "Relevance dominance verified: relevance ≥ 85%, personalization ≤ 15%.",
    recommendations: items.map(toRecommendationItem),
    benchmark_stats: null,
    researcher_context: context,
  };
}

export function toOpportunityIntelligence(
  response: ApiOpportunityIntelligence
): UnifiedOpportunityIntelligence {
  return {
    researcher_id: response.profile_id,
    opportunity_id: response.opportunity_id,
    opportunity_title: response.title,
    relevance_score: response.base_relevance_score,
    personalization_score: response.personalization_adjustment,
    composite_score: response.final_score,
    relevance_dominant_applied: true,
    evidence_tiers: (response.evidence_tiers ?? []).map(toEvidenceTier),
    workspace_context: toWorkspaceContext(response.workspace_context),
    identity_status: null,
    evaluated_at: response.deadline_intelligence?.reference_time ?? new Date().toISOString(),
  };
}
