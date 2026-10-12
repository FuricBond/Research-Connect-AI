/** The literature search with a query, as the header search and the search page put it in the URL. */
export function searchHref(query: string): string {
  return `/?q=${encodeURIComponent(query)}`;
}

/** The query in the address bar right now (the router's own notifications can trail it). */
export function currentUrlQuery(): string | null {
  if (typeof window === "undefined") return null;
  return new URLSearchParams(window.location.search).get("q");
}

// A header search leaves its page; the search page then shows the query. The request below is
// how the header asks that page to put keyboard focus in its search box once it does.
let focusRequest: string | null = null;

/** Called by the header search just before it opens the search page with `query`. */
export function requestSearchFocus(query: string): void {
  focusRequest = query;
}

/** True once, when the search page shows the query a header search asked to be focused. */
export function takeSearchFocusRequest(query: string): boolean {
  if (focusRequest === null || focusRequest !== query) return false;
  focusRequest = null;
  return true;
}
