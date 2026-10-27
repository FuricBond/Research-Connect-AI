import { ApiError } from "../../services/api";

/**
 * Why an account change did not happen, in plain words (never the server's text). The backend
 * refuses to demote or deactivate the last active administrator with 409.
 */
export function accountChangeError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 409) return "Every platform needs an active administrator: make another account an administrator before changing this one.";
    if (error.status === 404) return "This account no longer exists.";
    if (error.status === 401 || error.status === 403) return "Only administrators can change accounts.";
    if (error.status === 422) return "The server could not apply this change.";
    if (error.status >= 500) return "The server could not make the change. Try again in a moment.";
    return "The change was refused.";
  }
  return "The change could not be sent. Check your connection and try again.";
}
