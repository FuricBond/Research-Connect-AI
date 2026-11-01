import type { AuthenticatedUser, LoginPayload, RegisterPayload, TokenResponse } from "../../types/auth";
import { fetchJson } from "./client";

// ── Phase 6.2 — Authentication API ───────────────────────────────────────────
//
// Contracts come from backend/app/api/v1/auth.py and are mounted at /api/v1 only
// (unlike the discovery routers, which are also mounted at /api).

/**
 * Exchanges credentials for a signed bearer token. Throws `ApiError` with status 401
 * for bad credentials and 429 when the login rate limit is hit.
 */
export async function login(
  payload: LoginPayload,
  signal?: AbortSignal
): Promise<TokenResponse> {
  return fetchJson<TokenResponse>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify(payload),
    signal,
  });
}

/**
 * Creates an account and its researcher profile, and returns a token: registration
 * authenticates, so no second sign-in round trip is needed. 409 means the email is taken.
 */
export async function register(
  payload: RegisterPayload,
  signal?: AbortSignal
): Promise<TokenResponse> {
  return fetchJson<TokenResponse>("/api/v1/auth/register", {
    method: "POST",
    body: JSON.stringify(payload),
    signal,
  });
}

/** Verifies the stored credentials against the backend and returns the live account. */
export async function getCurrentUser(signal?: AbortSignal): Promise<AuthenticatedUser> {
  return fetchJson<AuthenticatedUser>("/api/v1/auth/me", { signal });
}

/**
 * Phase 6.7: revokes every token issued to the signed-in account (204). The caller clears the
 * stored session whatever the outcome.
 */
export async function logout(signal?: AbortSignal): Promise<void> {
  await fetchJson<void>("/api/v1/auth/logout", { method: "POST", signal });
}

/**
 * Phase 6.7: replaces the password and returns a fresh token; every earlier token, this
 * browser's included, stops working. 400 means the current password was wrong.
 */
export async function changePassword(
  payload: { current_password: string; new_password: string },
  signal?: AbortSignal
): Promise<TokenResponse> {
  return fetchJson<TokenResponse>("/api/v1/auth/change-password", {
    method: "POST",
    body: JSON.stringify(payload),
    signal,
  });
}
