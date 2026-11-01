import type { SimilarResearchParams, SimilarResearchResponse } from "../../types/discovery";
import { fetchJson } from "./client";

/**
 * Retrieve research works similar to a specified source work based on semantic embeddings and topic proximity.
 */
export async function getSimilarResearch(
  workId: string,
  params: SimilarResearchParams = {},
  signal?: AbortSignal
): Promise<SimilarResearchResponse> {
  const searchParams = new URLSearchParams();
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
  if (params.require_embedding !== undefined) searchParams.set("require_embedding", String(params.require_embedding));

  const query = searchParams.toString();
  return fetchJson<SimilarResearchResponse>(
    `/api/v1/discovery/research/${workId}/similar${query ? `?${query}` : ""}`,
    { signal }
  );
}
