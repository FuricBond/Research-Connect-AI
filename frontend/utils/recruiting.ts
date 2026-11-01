import type { AuthenticatedUser } from "../types/auth";

/**
 * Decision 1 (audit SEC-03): anyone can register as faculty, so recruiting waits for an
 * administrator's verification. A convenience for what to offer: the API enforces the same rule.
 */
export function canRecruit(user: Pick<AuthenticatedUser, "role" | "is_verified"> | null): boolean {
  if (user === null) return false;
  return user.role === "ADMIN" || (user.role === "FACULTY" && user.is_verified);
}

/** A faculty account an administrator has not verified yet. */
export function awaitingVerification(user: Pick<AuthenticatedUser, "role" | "is_verified"> | null): boolean {
  return user?.role === "FACULTY" && !user.is_verified;
}
