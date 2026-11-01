import { getAccessToken } from "../services/auth";

/**
 * A page only an account can see does not belong in what a visitor downloads (audit PERF-04). For
 * someone with a stored session its code starts loading with the page, next to the session check,
 * so nobody waits for one and then the other.
 */
export function preloadForSession(load: () => Promise<unknown>): void {
  if (typeof window !== "undefined" && getAccessToken()) void load();
}
