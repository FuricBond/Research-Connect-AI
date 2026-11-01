import { getAuthHeaders } from "../auth";
import type { ReadingListItem, ReadingListItemUpdate, ReadingListLookupResponse, ReadingListResponse, ReadingStatus } from "../../types/reading_list";
import { API_URL, ApiError, extractErrorDetail, fetchJson, notifyUnauthorized } from "./client";

// ── Phase 5.14 — Personal reading list ────────────────────────────────────────

export async function fetchReadingList(
  options: { status?: ReadingStatus; limit?: number; offset?: number } = {},
  signal?: AbortSignal
): Promise<ReadingListResponse> {
  const params = new URLSearchParams();
  if (options.status) params.set("status", options.status);
  if (options.limit !== undefined) params.set("limit", String(options.limit));
  if (options.offset !== undefined) params.set("offset", String(options.offset));
  const qs = params.toString();
  return fetchJson<ReadingListResponse>(`/api/v1/reading-list${qs ? `?${qs}` : ""}`, { signal });
}

/** Saves a work; saving one already on the list returns the existing item unchanged. */
export async function addToReadingList(
  workId: string,
  options: { status?: ReadingStatus; notes?: string } = {},
  signal?: AbortSignal
): Promise<ReadingListItem> {
  return fetchJson<ReadingListItem>("/api/v1/reading-list", {
    method: "POST",
    body: JSON.stringify({ work_id: workId, ...options }),
    signal,
  });
}

export async function updateReadingListItem(
  itemId: string,
  payload: ReadingListItemUpdate,
  signal?: AbortSignal
): Promise<ReadingListItem> {
  return fetchJson<ReadingListItem>(`/api/v1/reading-list/${itemId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
    signal,
  });
}

export async function removeReadingListItem(itemId: string, signal?: AbortSignal): Promise<void> {
  await fetchJson<void>(`/api/v1/reading-list/${itemId}`, { method: "DELETE", signal });
}

/** Which of the given works are saved; at most 100 ids per call, as the API allows. */
export async function lookupReadingList(
  workIds: string[],
  signal?: AbortSignal
): Promise<ReadingListLookupResponse> {
  if (workIds.length === 0) return { saved: {} };
  const params = new URLSearchParams();
  for (const workId of workIds.slice(0, 100)) params.append("work_ids", workId);
  return fetchJson<ReadingListLookupResponse>(`/api/v1/reading-list/lookup?${params.toString()}`, {
    signal,
  });
}

/**
 * Downloads the reading list (or the chosen items, or one status) as `reading-list.bib`.
 *
 * The export needs the caller's credentials, so it is fetched with the auth headers and saved
 * from a Blob; a plain link would send no Bearer token.
 */
export async function downloadReadingListBibtex(
  options: { itemIds?: string[]; status?: ReadingStatus } = {},
  signal?: AbortSignal
): Promise<void> {
  const params = new URLSearchParams();
  for (const itemId of options.itemIds ?? []) params.append("item_ids", itemId);
  if (options.status) params.set("status", options.status);
  const qs = params.toString();
  const path = `/api/v1/reading-list/export.bib${qs ? `?${qs}` : ""}`;
  const headers = getAuthHeaders();

  const response = await fetch(`${API_URL}${path}`, { headers, signal });
  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`;
    try {
      detail = extractErrorDetail(await response.json(), detail);
    } catch {
      // Non-JSON error body fallback
    }
    if (response.status === 401) {
      notifyUnauthorized(path, headers["Authorization"] !== undefined);
    }
    throw new ApiError(response.status, detail, detail);
  }

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  try {
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "reading-list.bib";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
  } finally {
    URL.revokeObjectURL(url);
  }
}
