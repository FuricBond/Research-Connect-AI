"use client";

/**
 * P10 — the administration pages' requests (FRONTEND_REDESIGN_PLAN.md §15), each a useApiResource:
 * one request per key however many modules read it, answers belonging to the signed-in account
 * only, nothing kept once the page is left. Every endpoint but readiness is ADMIN only on the
 * server, whatever the page shows.
 *
 *   Overview       GET /api/health/ready · GET /admin/ingestion-runs?limit=100 (the monitor and the
 *                  failed runs share it) · GET /admin/users?role=…&limit=1 per role (the counts) ·
 *                  GET /admin/users?limit=200 (deactivated accounts): 6 requests, all at once
 *   Research data  GET /admin/ingestion-runs?limit=100
 *   Users          GET /admin/users?limit=25&offset=…[&role][&search] · PATCH /admin/users/{id}
 */

import { useRef } from "react";
import { useApiResource, type ApiResource } from "../../hooks/useApiResource";
import { fetchAdminUsers, fetchIngestionRuns, fetchReadiness } from "../../services/api";
import type { PlatformRole } from "../../types/auth";
import { ACCOUNT_SCAN_LIMIT, RUNS_LIMIT, USERS_PAGE_SIZE, type UsersQuery } from "../../utils/admin";

export function useIngestionRuns() {
  return useApiResource(`admin:ingestion-runs:${RUNS_LIMIT}`, (signal) => fetchIngestionRuns({ limit: RUNS_LIMIT }, signal));
}

export function useReadiness() {
  return useApiResource("admin:readiness", (signal) => fetchReadiness(signal));
}

/** How many accounts have the role: the answer's total (one row asked for). */
export function useRoleCount(role: PlatformRole) {
  return useApiResource(`admin:users:count:${role}`, (signal) => fetchAdminUsers({ role, limit: 1, offset: 0 }, signal));
}

/** The first ACCOUNT_SCAN_LIMIT accounts, for the deactivated ones (the API has no such filter). */
export function useAccountScan() {
  return useApiResource(`admin:users:scan:${ACCOUNT_SCAN_LIMIT}`, (signal) => fetchAdminUsers({ limit: ACCOUNT_SCAN_LIMIT, offset: 0 }, signal));
}

export function usersKey(query: UsersQuery): string {
  return `admin:users:${query.role ?? "all"}:${(query.page - 1) * USERS_PAGE_SIZE}:${query.q}`;
}

export function useUsersPage(query: UsersQuery) {
  return useApiResource(usersKey(query), (signal) =>
    fetchAdminUsers({ role: query.role ?? undefined, search: query.q || undefined, limit: USERS_PAGE_SIZE, offset: (query.page - 1) * USERS_PAGE_SIZE }, signal)
  );
}

/**
 * The last answer while the same key is asked again (Try again), so the table does not blank out;
 * another key (another page, filter or search) never shows this one's rows.
 */
export function useKeptFor<T>(key: string, resource: ApiResource<T>): T | undefined {
  const kept = useRef<{ key: string; data: T } | null>(null);
  if (resource.data !== undefined) kept.current = { key, data: resource.data };
  if (resource.data !== undefined) return resource.data;
  return resource.status === "loading" && kept.current?.key === key ? kept.current.data : undefined;
}
