import type { IngestionRunListResponse, ReadinessResponse } from "../../types/admin";
import type { AdminUserListResponse, AdminUserRead, AdminUserUpdate, PlatformRole } from "../../types/auth";
import { API_URL, ApiError, fetchJson } from "./client";

// ── Phase 6.2 — Platform administration API (ADMIN only) ─────────────────────

export async function fetchAdminUsers(
  params: { role?: PlatformRole; search?: string; isActive?: boolean; isVerified?: boolean; limit?: number; offset?: number } = {},
  signal?: AbortSignal
): Promise<AdminUserListResponse> {
  const query = new URLSearchParams();
  if (params.role) query.set("role", params.role);
  if (params.search) query.set("search", params.search);
  if (params.isActive !== undefined) query.set("is_active", String(params.isActive));
  if (params.isVerified !== undefined) query.set("is_verified", String(params.isVerified));
  query.set("limit", String(params.limit ?? 50));
  query.set("offset", String(params.offset ?? 0));
  return fetchJson<AdminUserListResponse>(`/api/v1/admin/users?${query.toString()}`, { signal });
}

export async function updateAdminUser(
  userId: string,
  payload: AdminUserUpdate,
  signal?: AbortSignal
): Promise<AdminUserRead> {
  return fetchJson<AdminUserRead>(`/api/v1/admin/users/${userId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
    signal,
  });
}

/** Recent ingestion runs and research refresh freshness (research refresh runs by default). */
export async function fetchIngestionRuns(
  params: { limit?: number; researchOnly?: boolean } = {},
  signal?: AbortSignal
): Promise<IngestionRunListResponse> {
  const query = new URLSearchParams();
  query.set("limit", String(params.limit ?? 20));
  query.set("research_only", String(params.researchOnly ?? true));
  return fetchJson<IngestionRunListResponse>(`/api/v1/admin/ingestion-runs?${query.toString()}`, { signal });
}

/**
 * P10 — the backend's readiness (`GET /api/health/ready`, public). A 503 is an answer, not a
 * failure: its body says what is not ready. Any other failure, or a body of another shape, throws.
 */
export async function fetchReadiness(signal?: AbortSignal): Promise<ReadinessResponse> {
  const response = await fetch(`${API_URL}/api/health/ready`, { signal });
  if (response.ok || response.status === 503) {
    let body: unknown = null;
    try {
      body = await response.json();
    } catch {
      // Not the backend's answer (a proxy's error page): reported as the status below.
    }
    const answer = body as Partial<ReadinessResponse> | null;
    if (answer && typeof answer.status === "string" && typeof answer.database === "string" && typeof answer.schema === "string") {
      return answer as ReadinessResponse;
    }
  }
  throw new ApiError(response.status, `Request failed with status ${response.status}`);
}
