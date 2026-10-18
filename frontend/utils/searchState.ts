/**
 * P5 — the literature search's state, as the address bar holds it (FRONTEND_REDESIGN_PLAN.md §9).
 *
 *   /?q=graph%20neural%20networks&type=article&year=2018-2024&oa=1&cites=10&mode=research_similarity&sort=cited&page=2&per=50
 *
 * | Parameter | Meaning | Values (anything else is ignored) |
 * |---|---|---|
 * | `q` | the query | any text; trimmed; none or blank is the start page |
 * | `type` | publication type | article, preprint, book-chapter, dataset |
 * | `year` | publication years | `2020` (that year), `2018-2024`, `2018-` (from), `-2024` (until) |
 * | `oa` | open access only | `1` |
 * | `cites` | at least this many citations | a whole number above 0 |
 * | `mode` | ranking mode (advanced) | research_similarity, research_opportunity (general is the default) |
 * | `sort` | order of the papers on the page | newest, cited (relevance is the default) |
 * | `page` | result page, from 1 | a whole number above 1 |
 * | `per` | papers per page | 10, 50 (20 is the default) |
 *
 * Defaults are left out of the address, so the plainest search stays `/?q=…` (the header search
 * and every link made before P5 keep working). The query is encoded with encodeURIComponent
 * (`%20`, not `+`). The search API has no sort: `sort` reorders the page the API returned and
 * never asks the API again.
 */

import type { RankingMode, ResearchSearchParams } from "../types/discovery";

export const WORK_TYPES = ["article", "preprint", "book-chapter", "dataset"] as const;
export type WorkType = (typeof WORK_TYPES)[number];

export const RANKING_MODES = ["general", "research_similarity", "research_opportunity"] as const;
export const SORTS = ["relevance", "newest", "cited"] as const;
export type SearchSort = (typeof SORTS)[number];
export const PAGE_SIZES = [10, 20, 50] as const;
export const DEFAULT_PAGE_SIZE = 20;

/** Years the filter accepts (the publication years a corpus can hold). */
const MIN_YEAR = 1800;
const MAX_YEAR = 2100;

export interface SearchState {
  q: string;
  type: WorkType | null;
  minYear: number | null;
  maxYear: number | null;
  openAccess: boolean;
  minCitations: number | null;
  mode: RankingMode;
  sort: SearchSort;
  page: number;
  perPage: number;
}

export const EMPTY_SEARCH: SearchState = {
  q: "",
  type: null,
  minYear: null,
  maxYear: null,
  openAccess: false,
  minCitations: null,
  mode: "general",
  sort: "relevance",
  page: 1,
  perPage: DEFAULT_PAGE_SIZE,
};

function wholeNumber(value: string | null): number | null {
  if (value === null || !/^\d{1,9}$/.test(value.trim())) return null;
  return Number(value.trim());
}

function year(value: string | undefined): number | null {
  if (!value || !/^\d{4}$/.test(value)) return null;
  const n = Number(value);
  return n >= MIN_YEAR && n <= MAX_YEAR ? n : null;
}

function parseYears(value: string | null): [number | null, number | null] {
  if (!value) return [null, null];
  const single = /^(\d{4})$/.exec(value.trim());
  if (single) {
    const y = year(single[1]);
    return [y, y];
  }
  const range = /^(\d{4})?-(\d{4})?$/.exec(value.trim());
  if (!range) return [null, null];
  let from = year(range[1]);
  let to = year(range[2]);
  if (from !== null && to !== null && from > to) [from, to] = [to, from];
  return [from, to];
}

function oneOf<T extends string>(values: readonly T[], value: string | null): T | null {
  return value !== null && (values as readonly string[]).includes(value) ? (value as T) : null;
}

/** Reads the search state from a query string; unknown or invalid values fall back to defaults. */
export function parseSearchState(params: URLSearchParams): SearchState {
  const [minYear, maxYear] = parseYears(params.get("year"));
  const cites = wholeNumber(params.get("cites"));
  const page = wholeNumber(params.get("page"));
  const per = wholeNumber(params.get("per"));
  return {
    q: (params.get("q") ?? "").trim(),
    type: oneOf(WORK_TYPES, params.get("type")),
    minYear,
    maxYear,
    openAccess: params.get("oa") === "1",
    minCitations: cites !== null && cites > 0 ? cites : null,
    mode: oneOf(RANKING_MODES, params.get("mode")) ?? "general",
    sort: oneOf(SORTS, params.get("sort")) ?? "relevance",
    page: page !== null && page >= 1 ? page : 1,
    perPage: per !== null && (PAGE_SIZES as readonly number[]).includes(per) ? per : DEFAULT_PAGE_SIZE,
  };
}

function yearsParam(state: SearchState): string | null {
  const { minYear: from, maxYear: to } = state;
  if (from === null && to === null) return null;
  if (from !== null && from === to) return String(from);
  return `${from ?? ""}-${to ?? ""}`;
}

/** The query string for a state (no leading "?"), with defaults left out, in a fixed order. */
export function serializeSearchState(state: SearchState): string {
  const parts: [string, string | null][] = [
    ["q", state.q.trim() || null],
    ["type", state.type],
    ["year", yearsParam(state)],
    ["oa", state.openAccess ? "1" : null],
    ["cites", state.minCitations !== null && state.minCitations > 0 ? String(state.minCitations) : null],
    ["mode", state.mode !== "general" ? state.mode : null],
    ["sort", state.sort !== "relevance" ? state.sort : null],
    ["page", state.page > 1 ? String(state.page) : null],
    ["per", state.perPage !== DEFAULT_PAGE_SIZE ? String(state.perPage) : null],
  ];
  return parts
    .filter((part): part is [string, string] => part[1] !== null)
    .map(([key, value]) => `${key}=${encodeURIComponent(value)}`)
    .join("&");
}

/** The search page's address for a state: "/" or "/?q=…". */
export function searchStateHref(state: SearchState): string {
  const query = serializeSearchState(state);
  return query ? `/?${query}` : "/";
}

/**
 * What the API is asked for. Two states with the same request key show the same answer, so
 * moving between them (a new sort) needs no request.
 */
export function searchRequestKey(state: SearchState): string {
  return serializeSearchState({ ...state, sort: "relevance" });
}

/** The search API's parameters for a state (the explanation and query notes are always asked for). */
export function toSearchParams(state: SearchState): ResearchSearchParams {
  return {
    q: state.q,
    limit: state.perPage,
    offset: (state.page - 1) * state.perPage,
    work_type: state.type ?? undefined,
    min_year: state.minYear ?? undefined,
    max_year: state.maxYear ?? undefined,
    is_oa: state.openAccess ? true : undefined,
    min_citations: state.minCitations ?? undefined,
    ranking_mode: state.mode !== "general" ? state.mode : undefined,
    explain: true,
    include_query_intelligence: true,
  };
}

/** How many filters narrow the results (the query, sort and paging are not filters). */
export function activeFilterCount(state: SearchState): number {
  return [
    state.type !== null,
    state.minYear !== null || state.maxYear !== null,
    state.openAccess,
    state.minCitations !== null,
    state.mode !== "general",
  ].filter(Boolean).length;
}

/** The same search without its filters (query, page size and sort are kept; back to page 1). */
export function withoutFilters(state: SearchState): SearchState {
  return { ...EMPTY_SEARCH, q: state.q, sort: state.sort, perPage: state.perPage };
}

/** The state the address bar shows right now (the router's own notifications can trail it). */
export function currentSearchState(): SearchState | null {
  if (typeof window === "undefined") return null;
  return parseSearchState(new URLSearchParams(window.location.search));
}
