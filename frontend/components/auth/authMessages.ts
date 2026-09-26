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

/** Where a signed-in account lands when no usable destination was requested. */
const DEFAULT_REDIRECT = "/researcher";

/** Destinations that would only bounce a signed-in person back to a sign-in form. */
const EXCLUDED_REDIRECTS = new Set(["/login", "/register"]);

/**
 * Parse base for environments with no browser origin (server prerender). It is a
 * reserved, unresolvable name, so it can never coincide with a real host.
 */
const FALLBACK_ORIGIN = "http://researchconnect.invalid";

/**
 * Backslashes, ASCII control characters and whitespace. No in-app path contains them, and
 * browsers reinterpret them rather than keep them: a backslash is read as "/", and tabs
 * and newlines are silently dropped, so "/\evil.example" and "/<TAB>/evil.example" both
 * become the protocol-relative "//evil.example".
 */
const PARSER_AMBIGUOUS = /[\u005c\s\u0000-\u001f\u007f]/;

function currentOrigin(): string {
  if (typeof window === "undefined") return FALLBACK_ORIGIN;
  const { origin } = window.location;
  // An opaque origin ("null": file://, sandboxed frames) is same-origin with nothing.
  return origin && origin !== "null" ? origin : FALLBACK_ORIGIN;
}

/** True when `value`, resolved exactly as a browser resolves it, stays on `origin`. */
function staysOnOrigin(value: string, origin: string): boolean {
  if (PARSER_AMBIGUOUS.test(value)) return false;
  try {
    return new URL(value, origin).origin === origin;
  } catch {
    return false;
  }
}

/**
 * Where a freshly signed-in account should land, given the `?next=` it arrived with.
 *
 * The browser's URL parser decides, not string prefixes: a prefix check cannot anticipate
 * every spelling a parser treats as another host. Only an internal path is ever returned
 * (pathname, query and fragment), never an absolute URL.
 */
export function resolveRedirectTarget(
  next: string | null,
  origin: string = currentOrigin()
): string {
  // A root-relative path is the only destination this app produces. An absolute URL is
  // refused even when it names this origin, as it always has been.
  if (next === null || !next.startsWith("/") || !staysOnOrigin(next, origin)) {
    return DEFAULT_REDIRECT;
  }

  const parsed = new URL(next, origin);
  let decodedPath: string;
  try {
    decodedPath = decodeURIComponent(parsed.pathname);
  } catch {
    return DEFAULT_REDIRECT;
  }

  // Check the path exactly as it will be handed to the router, and once more decoded.
  // Dot-segment removal can leave a path that begins "//" ("/..//evil.example" parses to
  // the pathname "//evil.example", another host once navigated to), and an encoded
  // separator ("/%2F%2Fevil.example", "/%5Cevil.example") is one decode away from one.
  if (!staysOnOrigin(parsed.pathname, origin) || !staysOnOrigin(decodedPath, origin)) {
    return DEFAULT_REDIRECT;
  }

  if (EXCLUDED_REDIRECTS.has(parsed.pathname)) return DEFAULT_REDIRECT;
  return parsed.pathname + parsed.search + parsed.hash;
}
