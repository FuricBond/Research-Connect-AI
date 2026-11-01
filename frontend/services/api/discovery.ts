import type { ResearchSearchParams, ResearchSearchResponse } from "../../types/discovery";
import { fetchJson } from "./client";

// ── Phase 2.4 Discovery APIs ──────────────────────────────────────────────────

/**
 * Execute multi-channel hybrid search (semantic + lexical + topic) over research works.
 */
export async function searchResearchWorks(
  params: ResearchSearchParams,
  signal?: AbortSignal
): Promise<ResearchSearchResponse> {
  const searchParams = new URLSearchParams();
  searchParams.set("q", params.q);

  if (params.limit !== undefined) searchParams.set("limit", String(params.limit));
  if (params.offset !== undefined) searchParams.set("offset", String(params.offset));
  if (params.publication_year !== undefined) searchParams.set("publication_year", String(params.publication_year));
  if (params.min_year !== undefined) searchParams.set("min_year", String(params.min_year));
  if (params.max_year !== undefined) searchParams.set("max_year", String(params.max_year));
  if (params.work_type) searchParams.set("work_type", params.work_type);
  if (params.language) searchParams.set("language", params.language);
  if (params.primary_source_id) searchParams.set("primary_source_id", params.primary_source_id);
  if (params.is_oa !== undefined) searchParams.set("is_oa", String(params.is_oa));
  if (params.min_citations !== undefined) searchParams.set("min_citations", String(params.min_citations));
  if (params.ranking_mode) searchParams.set("ranking_mode", params.ranking_mode);
  if (params.explain !== undefined) searchParams.set("explain", String(params.explain));
  if (params.include_query_intelligence !== undefined) {
    searchParams.set("include_query_intelligence", String(params.include_query_intelligence));
  }

  const query = searchParams.toString();
  return fetchJson<ResearchSearchResponse>(
    `/api/v1/discovery/research/search${query ? `?${query}` : ""}`,
    { signal }
  );
}
