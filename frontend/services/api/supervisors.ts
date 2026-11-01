import type { SupervisorMatchResponse } from "../../types/supervisor";
import { fetchJson } from "./client";

// ── Phase 5.13 — Find a Supervisor ────────────────────────────────────────────

export async function fetchSupervisorMatches(
  researcherId: string,
  options: {
    limit?: number;
    excludeSameInstitution?: boolean;
    openPostingsOnly?: boolean;
  } = {},
  signal?: AbortSignal
): Promise<SupervisorMatchResponse> {
  const params = new URLSearchParams();
  if (options.limit !== undefined) params.set("limit", String(options.limit));
  if (options.excludeSameInstitution) params.set("exclude_same_institution", "true");
  if (options.openPostingsOnly) params.set("open_postings_only", "true");
  const qs = params.toString();
  return fetchJson<SupervisorMatchResponse>(
    `/api/v1/researchers/${researcherId}/supervisor-matches${qs ? `?${qs}` : ""}`,
    { signal }
  );
}
