/** The literature search with a query, as the header search and the search page put it in the URL. */
export function searchHref(query: string): string {
  return `/?q=${encodeURIComponent(query)}`;
}
