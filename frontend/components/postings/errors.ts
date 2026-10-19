import { ApiError } from "../../services/api";

/**
 * What to say when a posting or application change fails. The server's refusals here name enum
 * values ("cannot move an application from SUBMITTED to OFFERED"), so they are worded instead,
 * never shown; a refusal of a move the page offered means the object changed meanwhile.
 */
export function changeError(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    if (error.status === 400 || error.status === 409) return `${fallback} It may have changed since this page loaded; reload to see where it stands.`;
    if (error.status === 403) return `${fallback} Only its author can change it.`;
    if (error.status === 404) return `${fallback} It no longer exists, or it is no longer visible to you.`;
    if (error.status === 422) return `${fallback} Some of what was sent was not accepted.`;
    if (error.status === 429) return `${fallback} Too many requests; wait a moment and try again.`;
    return `${fallback} Try again.`;
  }
  return `${fallback} Check your connection and try again.`;
}
