import { getAuthHeaders } from "../auth";

// NEXT_PUBLIC_API_URL replaces former VITE_API_URL
export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ── Phase 6.2 — Session expiry notification ──────────────────────────────────
//
// `fetchJson` cannot decide what an expired session means: it does not know which
// route the person is on, and redirecting from here would fight the router. It only
// reports, and the session provider (the single owner of auth state) reacts.

type UnauthorizedHandler = () => void;

let unauthorizedHandler: UnauthorizedHandler | null = null;

/** Registers the single listener notified when an authenticated request is rejected. */
export function setUnauthorizedHandler(handler: UnauthorizedHandler | null): void {
  unauthorizedHandler = handler;
}

// Sign-in and registration answer 401 and 409 as ordinary form errors. Reporting those
// as a lost session would clear the credentials the caller is in the middle of
// establishing, so they are excluded.
const SESSION_EXEMPT_PATHS = ["/api/v1/auth/login", "/api/v1/auth/register"];

export function notifyUnauthorized(path: string, sentBearerToken: boolean): void {
  if (!sentBearerToken) return;
  if (SESSION_EXEMPT_PATHS.some((exempt) => path.startsWith(exempt))) return;
  unauthorizedHandler?.();
}

/**
 * Pulls a human-readable message out of an error body. FastAPI sends a string `detail`
 * for raised HTTPExceptions but a list of per-field objects for request validation, and
 * showing "[object Object]" to someone mistyping their email is not acceptable.
 */
export function extractErrorDetail(body: unknown, fallback: string): string {
  if (body === null || typeof body !== "object") return fallback;
  const detail = (body as { detail?: unknown }).detail;
  if (typeof detail === "string" && detail.trim() !== "") return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((entry) =>
        entry !== null && typeof entry === "object" && typeof (entry as { msg?: unknown }).msg === "string"
          ? ((entry as { msg: string }).msg)
          : null
      )
      .filter((msg): msg is string => msg !== null);
    if (messages.length > 0) return messages.join(" ");
  }
  return fallback;
}

export class ApiError extends Error {
  public status: number;
  public detail?: string;

  constructor(status: number, message: string, detail?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_URL}${path}`;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (init?.headers) {
    if (init.headers instanceof Headers) {
      init.headers.forEach((value, key) => {
        headers[key] = value;
      });
    } else if (Array.isArray(init.headers)) {
      init.headers.forEach(([key, value]) => {
        headers[key] = value;
      });
    } else {
      Object.assign(headers, init.headers);
    }
  }

  const authHeaders = getAuthHeaders();
  if (headers["Authorization"] || authHeaders["Authorization"]) {
    // A Bearer token is authoritative in production.  Several legacy wrapper
    // methods still accept a developer user ID, so remove that fallback header
    // whenever either an explicit or stored Bearer token is available.
    delete headers["X-User-ID"];
    if (!headers["Authorization"]) {
      headers["Authorization"] = authHeaders["Authorization"];
    }
  } else if (!headers["X-User-ID"]) {
    Object.assign(headers, authHeaders);
  }

  const response = await fetch(url, {
    ...init,
    headers,
  });

  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`;
    try {
      detail = extractErrorDetail(await response.json(), detail);
    } catch {
      // Non-JSON error body fallback
    }

    if (response.status === 429) {
      // The discovery endpoints and the authentication endpoints have separate limits,
      // so the message must not name one while describing the other.
      detail = detail.trim() !== "" && !detail.startsWith("Request failed")
        ? detail
        : "Rate limit exceeded. Please slow down and try again shortly.";
    }

    if (response.status === 401) {
      notifyUnauthorized(path, headers["Authorization"] !== undefined);
    }

    throw new ApiError(response.status, detail, detail);
  }

  if (response.status === 204) {
    return undefined as unknown as T;
  }

  return response.json() as Promise<T>;
}
