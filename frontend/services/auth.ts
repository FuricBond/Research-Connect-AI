/**
 * Phase 6 — Client Authentication & Identity Management.
 *
 * Manages the current active identity in localStorage:
 * - researchconnect_active_user_id
 * - researchconnect_active_profile_id
 * - researchconnect_access_token
 * - researchconnect_user_email
 * - researchconnect_user_name
 * - researchconnect_user_role
 */

const STORAGE_KEYS = {
  USER_ID: "researchconnect_active_user_id",
  PROFILE_ID: "researchconnect_active_profile_id",
  ACCESS_TOKEN: "researchconnect_access_token",
  USER_EMAIL: "researchconnect_user_email",
  USER_NAME: "researchconnect_user_name",
  USER_ROLE: "researchconnect_user_role",
} as const;

export interface StoredIdentity {
  userId: string | null;
  profileId: string | null;
  token: string | null;
  email: string | null;
  name: string | null;
  role: string | null;
}

export function getActiveUserId(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(STORAGE_KEYS.USER_ID);
}

export function getActiveProfileId(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(STORAGE_KEYS.PROFILE_ID);
}

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(STORAGE_KEYS.ACCESS_TOKEN);
}

export function getStoredIdentity(): StoredIdentity {
  if (typeof window === "undefined") {
    return { userId: null, profileId: null, token: null, email: null, name: null, role: null };
  }
  return {
    userId: localStorage.getItem(STORAGE_KEYS.USER_ID),
    profileId: localStorage.getItem(STORAGE_KEYS.PROFILE_ID),
    token: localStorage.getItem(STORAGE_KEYS.ACCESS_TOKEN),
    email: localStorage.getItem(STORAGE_KEYS.USER_EMAIL),
    name: localStorage.getItem(STORAGE_KEYS.USER_NAME),
    role: localStorage.getItem(STORAGE_KEYS.USER_ROLE),
  };
}

export function setActiveIdentity(identity: {
  userId?: string | null;
  profileId?: string | null;
  token?: string | null;
  email?: string | null;
  name?: string | null;
  role?: string | null;
}): void {
  if (typeof window === "undefined") return;
  if (identity.userId) localStorage.setItem(STORAGE_KEYS.USER_ID, identity.userId);
  if (identity.profileId) localStorage.setItem(STORAGE_KEYS.PROFILE_ID, identity.profileId);
  if (identity.token) localStorage.setItem(STORAGE_KEYS.ACCESS_TOKEN, identity.token);
  if (identity.email) localStorage.setItem(STORAGE_KEYS.USER_EMAIL, identity.email);
  if (identity.name) localStorage.setItem(STORAGE_KEYS.USER_NAME, identity.name);
  if (identity.role) localStorage.setItem(STORAGE_KEYS.USER_ROLE, identity.role);
}

export function clearActiveIdentity(): void {
  if (typeof window === "undefined") return;
  Object.values(STORAGE_KEYS).forEach((key) => localStorage.removeItem(key));
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
