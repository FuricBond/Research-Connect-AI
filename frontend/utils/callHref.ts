/**
 * The address of a call's page. On its own so a page that only links to a call (the calendar, a
 * workspace item) does not load the call card with it (P12).
 */
export function callHref(id: string): string {
  return `/calls/${encodeURIComponent(id)}`;
}
