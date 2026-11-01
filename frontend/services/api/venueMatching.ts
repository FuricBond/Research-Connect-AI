import type { OpportunityMatchParams, OpportunityMatchResponse } from "../../types/discovery";
import { fetchJson } from "./client";

/**
 * Match and rank relevant academic opportunities for a given research work.
 */
export async function matchOpportunitiesForResearch(
  workId: string,
  params: OpportunityMatchParams = {},
  signal?: AbortSignal
): Promise<OpportunityMatchResponse> {
  const searchParams = new URLSearchParams();
  if (params.limit !== undefined) searchParams.set("limit", String(params.limit));
  if (params.offset !== undefined) searchParams.set("offset", String(params.offset));
  if (params.opportunity_type) searchParams.set("opportunity_type", params.opportunity_type);
  if (params.status) searchParams.set("status", params.status);
  if (params.delivery_mode) searchParams.set("delivery_mode", params.delivery_mode);
  if (params.source_id) searchParams.set("source_id", params.source_id);
  if (params.upcoming_only !== undefined) searchParams.set("upcoming_only", String(params.upcoming_only));
  if (params.submission_deadline_after) searchParams.set("submission_deadline_after", params.submission_deadline_after);
  if (params.max_apc_usd !== undefined) searchParams.set("max_apc_usd", String(params.max_apc_usd));
  if (params.require_known_apc !== undefined) searchParams.set("require_known_apc", String(params.require_known_apc));
  if (params.location) searchParams.set("location", params.location);
  if (params.ranking_mode) searchParams.set("ranking_mode", params.ranking_mode);
  if (params.explain !== undefined) searchParams.set("explain", String(params.explain));
  if (params.require_embedding !== undefined) searchParams.set("require_embedding", String(params.require_embedding));

  const query = searchParams.toString();
  return fetchJson<OpportunityMatchResponse>(
    `/api/v1/discovery/research/${workId}/opportunities${query ? `?${query}` : ""}`,
    { signal }
  );
}
