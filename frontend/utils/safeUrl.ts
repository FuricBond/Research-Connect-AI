/**
 * Audit SEC-01 — the one test for an address someone else typed or a source supplied, the same as
 * the API's (backend/app/core/url_safety.py). Only an absolute http(s) address with a host, without
 * credentials or stray characters, ever becomes a link; any other value is shown, if at all, as
 * plain text. The API refuses such values now, but rows stored earlier keep theirs.
 */
const STRAY_CHARACTER = /[\s\u0000-\u001f\u007f\\]/;

/** The address to link to, or null when `value` must not become a link. */
export function safeExternalUrl(value: string | null | undefined): string | null {
  if (!value || STRAY_CHARACTER.test(value)) return null;
  try {
    const url = new URL(value);
    if (url.protocol !== "http:" && url.protocol !== "https:") return null;
    if (!url.hostname || url.username || url.password) return null;
    // `new URL` also accepts "https:example.org" and "http:/x": only the plain form is a web address.
    return /^https?:\/\//i.test(value) ? value : null;
  } catch {
    return null;
  }
}
