/**
 * Phase 6.2 — Authentication contract types.
 *
 * These mirror `backend/app/schemas/auth.py` exactly. The backend is the authority on
 * roles and validation; anything here that drifts from it is a bug in this file.
 */

/** Every role the platform recognises (`PlatformRole` in the backend). */
export type PlatformRole = "STUDENT" | "FACULTY" | "ADMIN";

/**
 * Roles a person may claim when registering themselves (`SelfServiceRole`).
 * ADMIN is deliberately absent: only an existing administrator can grant it, so the
 * registration form must never offer it.
 */
export type SelfServiceRole = "STUDENT" | "FACULTY";

export const SELF_SERVICE_ROLES: readonly SelfServiceRole[] = ["STUDENT", "FACULTY"];

/** Backend password and name constraints, duplicated so forms can fail fast. */
export const MIN_PASSWORD_LENGTH = 8;
export const MAX_PASSWORD_BYTES = 72;
export const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

/** The caller's own account, from `/auth/me` and from a login or registration response. */
export interface AuthenticatedUser {
  id: string;
  email: string;
  full_name: string;
  role: PlatformRole;
  is_active: boolean;
  is_verified: boolean;
  /** The researcher profile created alongside the account; null only for legacy accounts. */
  profile_id: string | null;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_at: string;
  user: AuthenticatedUser;
}

export interface LoginPayload {
  email: string;
  password: string;
}

export interface RegisterPayload {
  email: string;
  password: string;
  full_name: string;
  role: SelfServiceRole;
  institution_name?: string;
  department?: string;
}

/** Administration views (`/admin/users`), available to ADMIN accounts only. */
export interface AdminUserRead {
  id: string;
  email: string;
  full_name: string;
  role: PlatformRole;
  is_active: boolean;
  is_verified: boolean;
  created_at: string;
  updated_at: string;
}

export interface AdminUserListResponse {
  users: AdminUserRead[];
  total: number;
}

/** Omitted fields are left unchanged by the backend. */
export interface AdminUserUpdate {
  role?: PlatformRole;
  is_active?: boolean;
  is_verified?: boolean;
}

export const ROLE_LABELS: Record<PlatformRole, string> = {
  STUDENT: "Student researcher",
  FACULTY: "Faculty",
  ADMIN: "Administrator",
};
