/**
 * Phase 6.2 — Turning backend failures into something a person can act on.
 *
 * Only messages the backend wrote for a human are passed through. Anything else becomes
 * a generic line, so a stack trace, a driver error or a token can never reach the screen.
 */

import { ApiError } from "../../services/api";

const GENERIC_SIGN_IN = "Sign-in is unavailable right now. Please try again in a moment.";
const GENERIC_REGISTER = "We could not create the account right now. Please try again in a moment.";

/** A 4xx `detail` is written for the caller; a 5xx body may carry internals, so it is not shown. */
function safeDetail(error: ApiError, fallback: string): string {
  if (error.status >= 500) return fallback;
  const detail = error.detail ?? error.message;
  return typeof detail === "string" && detail.trim() !== "" ? detail : fallback;
}

export function describeLoginError(error: unknown): string {
  if (!(error instanceof ApiError)) {
    // A network failure or a backend that is not running never reaches an HTTP status.
    return "Could not reach the server. Check that the backend is running and try again.";
  }
  switch (error.status) {
    case 401:
      // Deliberately identical whether the email is unknown or the password is wrong:
      // the backend equalises its timing for the same reason.
      return "Email or password is incorrect.";
    case 422:
    case 400:
      return safeDetail(error, "Please check the email and password you entered.");
    case 429:
      return safeDetail(error, "Too many attempts. Please wait a moment and try again.");
    default:
      return safeDetail(error, GENERIC_SIGN_IN);
  }
}

export function describeRegisterError(error: unknown): string {
  if (!(error instanceof ApiError)) {
    return "Could not reach the server. Check that the backend is running and try again.";
  }
  switch (error.status) {
    case 409:
      return "An account with this email already exists. Try signing in instead.";
    case 422:
    case 400:
      return safeDetail(error, "Please check the details you entered.");
    case 429:
      return safeDetail(error, "Too many attempts. Please wait a moment and try again.");
    default:
      return safeDetail(error, GENERIC_REGISTER);
  }
}

/** Where a freshly signed-in account should land, given an optional requested path. */
export function resolveRedirectTarget(next: string | null): string {
  // Only same-origin absolute paths are honoured, so `?next=` cannot send somebody to
  // another site, and `//evil.example` (a protocol-relative URL) is rejected too.
  if (next === null || !next.startsWith("/") || next.startsWith("//")) return "/researcher";
  if (next === "/login" || next === "/register") return "/researcher";
  return next;
}
