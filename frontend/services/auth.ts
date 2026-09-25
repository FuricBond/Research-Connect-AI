/**
 * Phase 6 — Client Authentication & Identity Management.
 *
 * Manages the current active identity in localStorage:
 * - researchconnect_active_user_id
 * - researchconnect_active_profile_id
 * - researchconnect_access_token
 * - researchconnect_token_expires_at
 * - researchconnect_user_email
 * - researchconnect_user_name
 * - researchconnect_user_role
 *
 * Every read and write goes through the helpers below, which swallow the exceptions
 * localStorage throws when site data is blocked. A caller therefore sees a missing
 * identity rather than a crash, and stored values that no longer parse are treated as
 * absent instead of being trusted.
 */

import type { AuthenticatedUser, PlatformRole, TokenResponse } from "../types/auth";

const STORAGE_KEYS = {
  USER_ID: "researchconnect_active_user_id",
  PROFILE_ID: "researchconnect_active_profile_id",
  ACCESS_TOKEN: "researchconnect_access_token",
  TOKEN_EXPIRES_AT: "researchconnect_token_expires_at",
  USER_EMAIL: "researchconnect_user_email",
  USER_NAME: "researchconnect_user_name",
  USER_ROLE: "researchconnect_user_role",
} as const;

const PLATFORM_ROLES: readonly string[] = ["STUDENT", "FACULTY", "ADMIN"];

function readItem(key: string): string | null {
  if (typeof window === "undefined") return null;
  try {
    const value = window.localStorage.getItem(key);
    // An empty string is indistinguishable from "not set" for every value we store.
    return value === null || value === "" ? null : value;
  } catch {
    return null;
  }
}

function writeItem(key: string, value: string): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Site data blocked (private browsing, storage disabled): the session stays
    // in memory for this page only, which is better than failing the sign-in.
  }
}

function removeItem(key: string): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(key);
  } catch {
    // ignore
  }
}

export interface StoredIdentity {
  userId: string | null;
  profileId: string | null;
  token: string | null;
  email: string | null;
  name: string | null;
  role: string | null;
}

export function getActiveUserId(): string | null {
  return readItem(STORAGE_KEYS.USER_ID);
}

export function getActiveProfileId(): string | null {
  return readItem(STORAGE_KEYS.PROFILE_ID);
}

export function getAccessToken(): string | null {
  return readItem(STORAGE_KEYS.ACCESS_TOKEN);
}

export function getStoredIdentity(): StoredIdentity {
  return {
    userId: readItem(STORAGE_KEYS.USER_ID),
    profileId: readItem(STORAGE_KEYS.PROFILE_ID),
    token: readItem(STORAGE_KEYS.ACCESS_TOKEN),
    email: readItem(STORAGE_KEYS.USER_EMAIL),
    name: readItem(STORAGE_KEYS.USER_NAME),
    role: readItem(STORAGE_KEYS.USER_ROLE),
  };
}

/** The stored role, or null when nothing recognisable is stored. */
export function getStoredRole(): PlatformRole | null {
  const raw = readItem(STORAGE_KEYS.USER_ROLE);
  return raw !== null && PLATFORM_ROLES.includes(raw) ? (raw as PlatformRole) : null;
}

export function setActiveIdentity(identity: {
  userId?: string | null;
  profileId?: string | null;
  token?: string | null;
  email?: string | null;
  name?: string | null;
  role?: string | null;
}): void {
  if (identity.userId) writeItem(STORAGE_KEYS.USER_ID, identity.userId);
  if (identity.profileId) writeItem(STORAGE_KEYS.PROFILE_ID, identity.profileId);
  if (identity.token) writeItem(STORAGE_KEYS.ACCESS_TOKEN, identity.token);
  if (identity.email) writeItem(STORAGE_KEYS.USER_EMAIL, identity.email);
  if (identity.name) writeItem(STORAGE_KEYS.USER_NAME, identity.name);
  if (identity.role) writeItem(STORAGE_KEYS.USER_ROLE, identity.role);
}

/**
 * Records a freshly issued session. Unlike `setActiveIdentity`, this *replaces* the
 * identity: a field the new account does not have (an account with no researcher
 * profile, say) clears the previous account's value rather than leaving it behind.
 */
export function storeSession(response: TokenResponse): void {
  writeItem(STORAGE_KEYS.ACCESS_TOKEN, response.access_token);
  writeItem(STORAGE_KEYS.TOKEN_EXPIRES_AT, response.expires_at);
  storeAuthenticatedUser(response.user);
}

/** Syncs the cached account details after a login or a `/auth/me` verification. */
export function storeAuthenticatedUser(user: AuthenticatedUser): void {
  writeItem(STORAGE_KEYS.USER_ID, user.id);
  writeItem(STORAGE_KEYS.USER_EMAIL, user.email);
  writeItem(STORAGE_KEYS.USER_NAME, user.full_name);
  writeItem(STORAGE_KEYS.USER_ROLE, user.role);
  if (user.profile_id) {
    writeItem(STORAGE_KEYS.PROFILE_ID, user.profile_id);
  } else {
    removeItem(STORAGE_KEYS.PROFILE_ID);
  }
}

/** The access token's expiry, or null when none is stored or it does not parse. */
export function getTokenExpiry(): Date | null {
  const raw = readItem(STORAGE_KEYS.TOKEN_EXPIRES_AT);
  if (raw === null) return null;
  const parsed = new Date(raw);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

/**
 * True when a token is stored and its recorded expiry has passed. An unparseable or
 * missing expiry is *not* treated as expired: the backend, not the clock on this
 * machine, decides whether a token is still good.
 */
export function isStoredSessionExpired(now: Date = new Date()): boolean {
  if (getAccessToken() === null) return false;
  const expiry = getTokenExpiry();
  return expiry !== null && expiry.getTime() <= now.getTime();
}

export function clearActiveIdentity(): void {
  Object.values(STORAGE_KEYS).forEach((key) => removeItem(key));
}

export function getAuthHeaders(): Record<string, string> {
  const headers: Record<string, string> = {};
  const token = getAccessToken();
  const userId = getActiveUserId();
  const profileId = getActiveProfileId();

  if (token) {
    // JWT Bearer token is the production authentication mechanism.
    // When a token is present, do NOT also send X-User-ID to avoid ambiguity.
    headers["Authorization"] = `Bearer ${token}`;
  } else if (userId) {
    // Fallback: developer-mode only (AUTH_DEV_IDENTITY_ENABLED=true on backend).
    // Only used when no JWT is available (e.g., pre-login dev sessions).
    headers["X-User-ID"] = userId;
  } else if (profileId) {
    headers["X-User-ID"] = profileId;
  }
  return headers;
}
