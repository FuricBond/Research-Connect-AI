/**
 * P5 — the calls-for-papers list's state, as the address bar holds it (FRONTEND_REDESIGN_PLAN.md §11):
 *
 *   /browse?q=retrieval&type=CONFERENCE&mode=ONLINE&upcoming=1&sort=deadline&page=2
 *
 * | Parameter | Meaning | Values (anything else is ignored) |
 * |---|---|---|
 * | `q` | words in the title, summary or description | any text, trimmed |
 * | `type` | kind of call | CONFERENCE, JOURNAL, WORKSHOP, CALL_FOR_PAPERS, SPECIAL_ISSUE |
 * | `mode` | attendance | OFFLINE (in person), ONLINE, HYBRID |
 * | `upcoming` | only calls whose submission deadline is still ahead | `1` (off by default) |
 * | `sort` | order | deadline, title (newest is the default) |
 * | `page` | page of 20, from 1 | a whole number above 1 |
 *
 * These are the filters `GET /api/opportunities` already has; the page adds none of its own. The
 * API leaves out calls marked expired, archived or draft unless asked; "upcoming" also leaves out
 * calls with no deadline (the API's rule), so it stays off unless the person turns it on (P5
 * decision on plan Q10).
 */

import type { OpportunityFilters } from "../services/api";
import { CALL_TYPES, DELIVERY_MODES } from "./research";

export const CALLS_PAGE_SIZE = 20;
export const CALL_SORTS = ["newest", "deadline", "title"] as const;
export type CallSort = (typeof CALL_SORTS)[number];

export interface CallsState {
  q: string;
  type: string | null;
  mode: string | null;
  upcoming: boolean;
  sort: CallSort;
  page: number;
}

export const EMPTY_CALLS: CallsState = { q: "", type: null, mode: null, upcoming: false, sort: "newest", page: 1 };

function oneOf(values: readonly string[], value: string | null): string | null {
  return value !== null && values.includes(value) ? value : null;
}

export function parseCallsState(params: URLSearchParams): CallsState {
  const page = Number(params.get("page"));
  const sort = oneOf(CALL_SORTS, params.get("sort")) as CallSort | null;
  return {
    q: (params.get("q") ?? "").trim(),
    type: oneOf(CALL_TYPES, params.get("type")),
    mode: oneOf(DELIVERY_MODES, params.get("mode")),
    upcoming: params.get("upcoming") === "1",
    sort: sort ?? "newest",
    page: Number.isInteger(page) && page >= 1 && page <= 100_000 ? page : 1,
  };
}

/** The query string (no "?"), defaults left out, in a fixed order. */
export function serializeCallsState(state: CallsState): string {
  const parts: [string, string | null][] = [
    ["q", state.q.trim() || null],
    ["type", state.type],
    ["mode", state.mode],
    ["upcoming", state.upcoming ? "1" : null],
    ["sort", state.sort !== "newest" ? state.sort : null],
    ["page", state.page > 1 ? String(state.page) : null],
  ];
  return parts
    .filter((part): part is [string, string] => part[1] !== null)
    .map(([key, value]) => `${key}=${encodeURIComponent(value)}`)
    .join("&");
}

export function callsHref(state: CallsState): string {
  const query = serializeCallsState(state);
  return query ? `/browse?${query}` : "/browse";
}

export function toOpportunityFilters(state: CallsState): OpportunityFilters {
  return {
    search: state.q || undefined,
    opportunity_type: state.type ?? undefined,
    delivery_mode: state.mode ?? undefined,
    upcoming: state.upcoming || undefined,
    sort: state.sort,
    page: state.page,
    page_size: CALLS_PAGE_SIZE,
  };
}

export function hasCallFilters(state: CallsState): boolean {
  return Boolean(state.q || state.type || state.mode || state.upcoming);
}

/* The list a call's page was opened from, so its breadcrumb leads back to the same filters. */
const ORIGIN_KEY = "rc_calls_origin";

export function rememberCallsOrigin(href: string): void {
  try {
    window.sessionStorage.setItem(ORIGIN_KEY, href);
  } catch {
    // Without storage the breadcrumb leads to the unfiltered list.
  }
}

export function callsOrigin(): string {
  try {
    const href = window.sessionStorage.getItem(ORIGIN_KEY);
    return href && href.startsWith("/browse") ? href : "/browse";
  } catch {
    return "/browse";
  }
}
