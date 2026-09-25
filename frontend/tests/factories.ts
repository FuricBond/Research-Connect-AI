/**
 * Shared fixtures for the Phase 6.2 authentication tests.
 *
 * The shapes here mirror the backend responses exactly; if one drifts, the tests that
 * depend on it should fail rather than quietly agreeing with a wrong assumption.
 */

import type { AuthenticatedUser, PlatformRole, TokenResponse } from "../types/auth";

export const PROFILE_ID = "6f1d0e2a-6b6c-4a1f-9d2c-5b6a7c8d9e01";
export const USER_ID = "11111111-2222-3333-4444-555555555555";

export function makeUser(overrides: Partial<AuthenticatedUser> = {}): AuthenticatedUser {
  return {
    id: USER_ID,
    email: "ada@university.edu",
    full_name: "Ada Lovelace",
    role: "STUDENT" as PlatformRole,
    is_active: true,
    is_verified: false,
    profile_id: PROFILE_ID,
    created_at: "2026-01-01T00:00:00+00:00",
    ...overrides,
  };
}

export function makeTokenResponse(overrides: Partial<TokenResponse> = {}): TokenResponse {
  return {
    access_token: "header.payload.signature",
    token_type: "bearer",
    // Comfortably in the future so the expiry short-circuit never fires by accident.
    expires_at: "2099-01-01T00:00:00+00:00",
    user: makeUser(),
    ...overrides,
  };
}

/** A `fetch` stand-in returning one JSON response, recording what it was called with. */
export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Reads the headers off a recorded `fetch` call, whatever form they were passed in. */
export function headersOf(call: unknown[]): Record<string, string> {
  const init = call[1] as RequestInit | undefined;
  const raw = init?.headers;
  if (raw === undefined) return {};
  if (raw instanceof Headers) return Object.fromEntries(raw.entries());
  if (Array.isArray(raw)) return Object.fromEntries(raw);
  return { ...(raw as Record<string, string>) };
}
