import type { CollaborationInterest, DiscoverySettings, DiscoverySettingsUpdate, PeerMatchResponse } from "../../types/peer";
import { fetchJson } from "./client";

// ── Phase 5.12 — Peer & Co-Author Discovery ───────────────────────────────────
//
// `userId` is still accepted for the developer-identity path used by the researcher pages;
// fetchJson prefers a stored bearer token when one exists.

export async function fetchDiscoverySettings(
  researcherId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<DiscoverySettings> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<DiscoverySettings>(
    `/api/v1/researchers/${researcherId}/discovery-settings`,
    { headers, signal }
  );
}

export async function updateDiscoverySettings(
  researcherId: string,
  payload: DiscoverySettingsUpdate,
  userId?: string,
  signal?: AbortSignal
): Promise<DiscoverySettings> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<DiscoverySettings>(
    `/api/v1/researchers/${researcherId}/discovery-settings`,
    { method: "PATCH", headers, body: JSON.stringify(payload), signal }
  );
}

export async function fetchPeerMatches(
  researcherId: string,
  options: {
    limit?: number;
    collaborationInterest?: CollaborationInterest;
    excludeSameInstitution?: boolean;
  } = {},
  userId?: string,
  signal?: AbortSignal
): Promise<PeerMatchResponse> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  const params = new URLSearchParams();
  if (options.limit !== undefined) params.set("limit", String(options.limit));
  if (options.collaborationInterest) {
    params.set("collaboration_interest", options.collaborationInterest);
  }
  if (options.excludeSameInstitution) params.set("exclude_same_institution", "true");
  const qs = params.toString();
  return fetchJson<PeerMatchResponse>(
    `/api/v1/researchers/${researcherId}/peers${qs ? `?${qs}` : ""}`,
    { headers, signal }
  );
}
