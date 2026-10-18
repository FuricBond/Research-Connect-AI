/**
 * P5 — the literature search's state in the address (FRONTEND_REDESIGN_PLAN.md §9): every
 * supported value round-trips; defaults stay out of the address; anything unsupported is ignored
 * rather than sent to the API; sorting is not part of what the API is asked.
 */

import { describe, expect, it } from "vitest";
import {
  EMPTY_SEARCH,
  activeFilterCount,
  parseSearchState,
  searchRequestKey,
  searchStateHref,
  serializeSearchState,
  toSearchParams,
  withoutFilters,
  type SearchState,
} from "../utils/searchState";
import { callsHref, parseCallsState, serializeCallsState, toOpportunityFilters } from "../utils/callsState";

const parse = (query: string) => parseSearchState(new URLSearchParams(query));

describe("search state ↔ address", () => {
  it("keeps the plainest search as /?q=… (the header search and older links)", () => {
    expect(searchStateHref({ ...EMPTY_SEARCH, q: "graph neural networks" })).toBe("/?q=graph%20neural%20networks");
    expect(searchStateHref(EMPTY_SEARCH)).toBe("/");
  });

  it("round-trips every supported value, in a fixed order", () => {
    const state: SearchState = {
      q: "retrieval",
      type: "preprint",
      minYear: 2018,
      maxYear: 2024,
      openAccess: true,
      minCitations: 10,
      mode: "research_similarity",
      sort: "cited",
      page: 3,
      perPage: 50,
    };
    const query = serializeSearchState(state);
    expect(query).toBe("q=retrieval&type=preprint&year=2018-2024&oa=1&cites=10&mode=research_similarity&sort=cited&page=3&per=50");
    expect(parse(query)).toEqual(state);
  });

  it("writes one year, an open start and an open end", () => {
    expect(serializeSearchState({ ...EMPTY_SEARCH, q: "x", minYear: 2020, maxYear: 2020 })).toBe("q=x&year=2020");
    expect(serializeSearchState({ ...EMPTY_SEARCH, q: "x", minYear: 2018 })).toBe("q=x&year=2018-");
    expect(serializeSearchState({ ...EMPTY_SEARCH, q: "x", maxYear: 2024 })).toBe("q=x&year=-2024");
    expect(parse("q=x&year=2020")).toMatchObject({ minYear: 2020, maxYear: 2020 });
    expect(parse("q=x&year=2018-")).toMatchObject({ minYear: 2018, maxYear: null });
    expect(parse("q=x&year=-2024")).toMatchObject({ minYear: null, maxYear: 2024 });
    // Given the wrong way round, the range is read the right way round.
    expect(parse("q=x&year=2024-2018")).toMatchObject({ minYear: 2018, maxYear: 2024 });
  });

  it("encodes and decodes spaces, Unicode and reserved characters", () => {
    for (const q of ["Müller & Sørensen: über-graphs?", "C++ #compilers 50% faster", "量子 计算", "a+b=c / d"]) {
      const href = searchStateHref({ ...EMPTY_SEARCH, q });
      expect(parseSearchState(new URL(href, "http://localhost").searchParams).q).toBe(q);
    }
    expect(searchStateHref({ ...EMPTY_SEARCH, q: "a b" })).not.toContain("+");
  });

  it("ignores what it does not support instead of sending it to the API", () => {
    expect(parse("q=x&type=novel&year=19-ish&oa=yes&cites=-5&mode=fast&sort=random&page=0&per=7&utm=1")).toEqual({ ...EMPTY_SEARCH, q: "x" });
    expect(parse("q=x&page=abc&cites=1.5&year=0999")).toEqual({ ...EMPTY_SEARCH, q: "x" });
    expect(parse("")).toEqual(EMPTY_SEARCH);
    // A blank query is the start page.
    expect(parse("q=%20%20").q).toBe("");
  });

  it("asks the API the same thing whatever the sort, so sorting needs no request", () => {
    const state = { ...EMPTY_SEARCH, q: "x" };
    expect(searchRequestKey({ ...state, sort: "newest" })).toBe(searchRequestKey(state));
    expect(searchRequestKey({ ...state, page: 2 })).not.toBe(searchRequestKey(state));
  });

  it("maps the state to the search API's parameters", () => {
    expect(toSearchParams(parse("q=retrieval&type=article&year=2018-2024&oa=1&cites=10&mode=research_opportunity&page=3&per=10"))).toEqual({
      q: "retrieval",
      limit: 10,
      offset: 20,
      work_type: "article",
      min_year: 2018,
      max_year: 2024,
      is_oa: true,
      min_citations: 10,
      ranking_mode: "research_opportunity",
      explain: true,
      include_query_intelligence: true,
    });
    expect(toSearchParams(parse("q=x"))).toMatchObject({ limit: 20, offset: 0, work_type: undefined, is_oa: undefined, ranking_mode: undefined });
  });

  it("counts filters, and clears them while keeping the query, sort and page size", () => {
    const state = parse("q=x&type=article&year=2018-&oa=1&cites=3&mode=research_similarity&sort=newest&page=4&per=50");
    expect(activeFilterCount(state)).toBe(5);
    expect(withoutFilters(state)).toEqual({ ...EMPTY_SEARCH, q: "x", sort: "newest", perPage: 50 });
  });
});

describe("calls-for-papers list ↔ address", () => {
  it("round-trips the API's own filters, with defaults left out", () => {
    const state = parseCallsState(new URLSearchParams("q=neural%20retrieval&type=WORKSHOP&mode=ONLINE&upcoming=1&sort=deadline&page=2"));
    expect(state).toEqual({ q: "neural retrieval", type: "WORKSHOP", mode: "ONLINE", upcoming: true, sort: "deadline", page: 2 });
    expect(serializeCallsState(state)).toBe("q=neural%20retrieval&type=WORKSHOP&mode=ONLINE&upcoming=1&sort=deadline&page=2");
    expect(callsHref(parseCallsState(new URLSearchParams("")))).toBe("/browse");
  });

  it("ignores unsupported values and keeps 'upcoming' off unless asked", () => {
    expect(parseCallsState(new URLSearchParams("type=PODCAST&mode=VR&upcoming=true&sort=random&page=-1"))).toEqual({
      q: "",
      type: null,
      mode: null,
      upcoming: false,
      sort: "newest",
      page: 1,
    });
  });

  it("asks the API for 20 calls a page with exactly the chosen filters", () => {
    expect(toOpportunityFilters(parseCallsState(new URLSearchParams("type=JOURNAL&page=3")))).toEqual({
      search: undefined,
      opportunity_type: "JOURNAL",
      delivery_mode: undefined,
      upcoming: undefined,
      sort: "newest",
      page: 3,
      page_size: 20,
    });
  });
});
