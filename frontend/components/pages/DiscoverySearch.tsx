"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { SlidersHorizontal } from "lucide-react";
import { SearchBar } from "../discovery/SearchBar";
import { SearchFilters } from "../discovery/SearchFilters";
import { searchResearchWorks, lookupReadingList, ApiError } from "../../services/api";
import { useSession } from "../auth/SessionProvider";
import { VisitorIntro } from "../auth/VisitorIntro";
import { setSelectedWork } from "../../hooks/useSelectedWork";
import { takeSearchFocusRequest } from "../../utils/search";
import {
  EMPTY_SEARCH,
  PAGE_SIZES,
  activeFilterCount,
  currentSearchState,
  parseSearchState,
  searchRequestKey,
  searchStateHref,
  serializeSearchState,
  toSearchParams,
  withoutFilters,
  type SearchSort,
  type SearchState,
} from "../../utils/searchState";
import { PaperCard } from "../research/PaperCard";
import { EvidencePanel, PaperPanel } from "../research/lazyPanels";
import { fromSearchResult, type PaperItem } from "../research/paper";
import { Button } from "../ui/Button/Button";
import { Drawer } from "../ui/Dialog/Dialog";
import { Select } from "../ui/Field/Field";
import { PageHeader } from "../ui/PageHeader/PageHeader";
import { Pagination } from "../ui/Pagination/Pagination";
import { EmptyState, ErrorState, SkeletonList } from "../ui/State/State";
import type { ResearchSearchResponse, ResearchWorkRead } from "../../types/discovery";
import styles from "../discovery/Search.module.css";

/** After this long a search says it is still working (plan §9: slow-query notice after 3 s). */
const SLOW_AFTER_MS = 3000;

type SearchFailure = "network" | "server" | "invalid";

const SORT_LABELS: Record<SearchSort, string> = {
  relevance: "Relevance",
  newest: "Newest first (this page)",
  cited: "Most cited (this page)",
};

/**
 * Reports the URL's query string whenever it changes (on arrival, from the header search, back
 * and forward). Isolated in its own Suspense boundary: reading search params on the client keeps
 * the rest of the page prerendered.
 */
function UrlState({ onChange }: { onChange: (query: string) => void }) {
  const query = useSearchParams().toString();
  useEffect(() => onChange(query), [query, onChange]);
  return null;
}

function sortItems(items: PaperItem[], sort: SearchSort): PaperItem[] {
  if (sort === "relevance") return items;
  const sorted = [...items];
  if (sort === "newest") sorted.sort((a, b) => (b.work.publication_year ?? -Infinity) - (a.work.publication_year ?? -Infinity) || a.rank - b.rank);
  if (sort === "cited") sorted.sort((a, b) => (b.work.cited_by_count ?? -1) - (a.work.cited_by_count ?? -1) || a.rank - b.rank);
  return sorted;
}

/** Records `state` in the address bar; a state the bar already shows adds no history entry. */
function record(state: SearchState, mode: "push" | "replace" = "push") {
  const shown = currentSearchState();
  if (shown && serializeSearchState(shown) === serializeSearchState(state)) return;
  const href = searchStateHref(state);
  if (mode === "replace") window.history.replaceState(null, "", href);
  else window.history.pushState(null, "", href);
}

/**
 * Literature search (FRONTEND_REDESIGN_PLAN.md §9). The whole search lives in the URL
 * (`/?q=…&type=…&year=…&oa=1&cites=…&mode=…&sort=…&page=…&per=…`, utils/searchState.ts), so a
 * search can be bookmarked, shared, reloaded and reached from the header's global search.
 *
 * The latest submission always wins (P2 audit): a search started here runs at once and the
 * address bar is updated with the browser's own history (Next.js keeps `useSearchParams` in step
 * with native `pushState` without fetching the page again), so no page navigation is ever pending
 * behind the person's back. The URL itself starts a search only when it changes from outside this
 * page — a direct link, back/forward, or the header search — and only for the address the bar
 * actually shows, so a late notification for an older address can neither search again nor
 * overwrite what is being typed. A newer search aborts the older one, and an older answer is never
 * shown. Sorting reorders the page in hand and asks the API nothing.
 */
export function DiscoverySearch() {
  // The state on screen; the results, when shown, answer its request key.
  const [state, setState] = useState<SearchState>(EMPTY_SEARCH);
  // "pending" until the address has been read: the page is prerendered without knowing the URL,
  // so its first paint is only the title and the search box. The start page or the results are
  // then added below them, which moves nothing (P5: showing the start page first and replacing it
  // with results moved the layout by 104–179px, CLS 0.07–0.11).
  const [phase, setPhase] = useState<"pending" | "start" | "loading" | "done" | "error">("pending");
  const [response, setResponse] = useState<ResearchSearchResponse | null>(null);
  const [failure, setFailure] = useState<SearchFailure | null>(null);
  const [slow, setSlow] = useState(false);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [paper, setPaper] = useState<PaperItem | null>(null);
  const [evidence, setEvidence] = useState<PaperItem | null>(null);

  const stateRef = useRef(state);
  stateRef.current = state;
  const abortControllerRef = useRef<AbortController | null>(null);
  // The request key whose results are shown or loading (null: the start page).
  const shownKeyRef = useRef<string | null>(null);
  // The request key of the request in flight, if any.
  const loadingKeyRef = useRef<string | null>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const resultsHeading = useRef<HTMLHeadingElement>(null);

  // Reading list: which visible works the signed-in user has already saved (work id -> item id).
  const { status: sessionStatus } = useSession();
  const [savedWorks, setSavedWorks] = useState<Record<string, string>>({});
  const items = useMemo(() => (response?.items ?? []).map(fromSearchResult), [response]);

  useEffect(() => {
    if (sessionStatus !== "authenticated" || items.length === 0) {
      setSavedWorks({});
      return;
    }
    const controller = new AbortController();
    lookupReadingList(
      items.map((item) => item.work.id),
      controller.signal
    )
      .then((result) => setSavedWorks(result.saved))
      .catch(() => {
        // Saving still works without the lookup; the buttons just start unmarked.
      });
    return () => controller.abort();
  }, [items, sessionStatus]);

  const handleSaved = (workId: string, itemId: string) => {
    setSavedWorks((previous) => ({ ...previous, [workId]: itemId }));
  };

  // The slow-search notice: only while the same search is still loading.
  useEffect(() => {
    if (phase !== "loading") return;
    const timer = window.setTimeout(() => setSlow(true), SLOW_AFTER_MS);
    return () => window.clearTimeout(timer);
  }, [phase, state]);

  const executeSearch = async (next: SearchState) => {
    if (!next.q.trim()) return;
    abortControllerRef.current?.abort();
    const abortController = new AbortController();
    abortControllerRef.current = abortController;
    const key = searchRequestKey(next);
    loadingKeyRef.current = key;
    shownKeyRef.current = key;

    setState(next);
    setPhase("loading");
    setFailure(null);
    setSlow(false);
    setPaper(null);
    setEvidence(null);

    try {
      const answer = await searchResearchWorks(toSearchParams(next), abortController.signal);
      // A newer search replaced this one: its answer must not replace the newer results.
      if (abortController.signal.aborted) return;
      setResponse(answer);
      setPhase("done");
    } catch (err: unknown) {
      if (abortController.signal.aborted || (err instanceof Error && err.name === "AbortError")) return;
      // Words chosen here, never the server's text.
      setFailure(err instanceof ApiError ? (err.status >= 500 ? "server" : "invalid") : "network");
      setResponse(null);
      setPhase("error");
    } finally {
      // Only the latest search ends the loading state.
      if (abortControllerRef.current === abortController) loadingKeyRef.current = null;
    }
  };
  // executeSearch only uses state setters and refs, so the latest one is always equivalent.
  const executeRef = useRef(executeSearch);
  executeRef.current = executeSearch;

  const handleUrlState = useCallback((query: string) => {
    const fromUrl = parseSearchState(new URLSearchParams(query));
    // The router applies address changes in a transition; if the bar has already moved on, a
    // newer notification follows and this one is stale.
    const bar = currentSearchState();
    if (!bar || serializeSearchState(fromUrl) !== serializeSearchState(bar)) return;

    if (fromUrl.q) {
      // Already shown or loading (this page asked for it): nothing to ask again, nothing to overwrite.
      if (searchRequestKey(fromUrl) !== shownKeyRef.current) executeRef.current(fromUrl);
      else if (fromUrl.sort !== stateRef.current.sort) setState(fromUrl);
      // Arrived from the header search: keyboard focus goes to the box that now holds the query.
      if (takeSearchFocusRequest(fromUrl.q)) searchInputRef.current?.focus();
      return;
    }
    // No query in the URL (the navigation's "Literature search", or back to the start): the
    // start page, with nothing still loading.
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
    loadingKeyRef.current = null;
    shownKeyRef.current = null;
    setState(fromUrl);
    setResponse(null);
    setFailure(null);
    setPhase("start");
    setPaper(null);
    setEvidence(null);
  }, []);

  const handleQuerySubmit = (q: string) => {
    // A new query keeps the filters, sort and page size, from the first page.
    const next = { ...stateRef.current, q, page: 1 };
    // The same search is already being fetched (a double press): one request is enough.
    if (searchRequestKey(next) === loadingKeyRef.current) return;
    record(next);
    executeSearch(next);
  };

  const changeFilters = (change: Partial<SearchState>) => {
    const next = { ...stateRef.current, ...change, page: 1 };
    if (!next.q) {
      record(next, "replace");
      setState(next);
      return;
    }
    record(next);
    executeSearch(next);
  };

  const changeSort = (sort: SearchSort) => {
    const next = { ...stateRef.current, sort };
    record(next, next.q ? "push" : "replace");
    setState(next);
  };

  const changePage = (page: number) => {
    const next = { ...stateRef.current, page };
    record(next);
    executeSearch(next);
    resultsHeading.current?.focus();
  };

  const changePageSize = (perPage: number) => {
    const next = { ...stateRef.current, perPage, page: 1 };
    record(next);
    executeSearch(next);
  };

  const chooseWork = (work: ResearchWorkRead) => setSelectedWork(work, searchStateHref(stateRef.current));

  const filterCount = activeFilterCount(state);
  const shownItems = sortItems(items, state.sort);
  const total = response?.total ?? 0;
  const announcement =
    phase === "loading"
      ? slow
        ? "Still searching. Large searches can take a few seconds."
        : "Searching papers…"
      : phase === "done"
        ? total === 0
          ? "No papers matched your search."
          : `${total.toLocaleString("en")} result${total === 1 ? "" : "s"}`
        : "";

  const filters = <SearchFilters state={state} onChange={changeFilters} onClear={() => changeFilters(withoutFilters(stateRef.current))} />;

  return (
    <section className="discovery-search-page" aria-label="Research Literature Discovery">
      <Suspense fallback={null}>
        <UrlState onChange={handleUrlState} />
      </Suspense>
      <PageHeader
        title="Literature search"
        description="Find papers by topic, method or author. Results combine meaning and keyword matching, and every result says why it is there."
      />

      <SearchBar
        initialQuery={state.q}
        inputRef={searchInputRef}
        onSearch={handleQuerySubmit}
        isLoading={phase === "loading"}
        queryIntelligence={phase === "done" ? (response?.query_intelligence ?? null) : null}
        showSuggestions={phase === "start"}
      />

      <p role="status" className="rc-visually-hidden">
        {announcement}
      </p>

      {phase === "pending" ? null : phase === "start" ? (
        <div className={styles.start}>
          <EmptyState
            headingLevel={2}
            title="Begin your literature search"
            description="Type a topic, method or acronym to find papers, then open one to see why it matches, find similar papers or find venues for it."
          />
          {/* A visitor also reads what an account adds (P3). */}
          {sessionStatus === "unauthenticated" && <VisitorIntro />}
        </div>
      ) : (
        <div className={styles.layout}>
          <aside className={styles.rail} aria-labelledby="search-filters-heading">
            <h2 id="search-filters-heading" className={styles.railTitle}>
              Filters
            </h2>
            {filters}
          </aside>

          <section className={styles.results} aria-labelledby="search-results-heading" aria-busy={phase === "loading" || undefined}>
            <div className={styles.resultsHeader}>
              <h2 id="search-results-heading" ref={resultsHeading} tabIndex={-1} className={styles.resultsTitle}>
                {phase === "done" ? `${total.toLocaleString("en")} result${total === 1 ? "" : "s"}` : "Results"}
              </h2>
              <div className={styles.resultsTools}>
                <Button
                  className={styles.filtersButton}
                  size="sm"
                  aria-haspopup="dialog"
                  leadingIcon={<SlidersHorizontal size={16} aria-hidden="true" />}
                  onClick={() => setFiltersOpen(true)}
                >
                  Filters{filterCount > 0 ? ` (${filterCount})` : ""}
                </Button>
                <Select
                  label="Sort"
                  value={state.sort}
                  onChange={(event) => changeSort(event.target.value as SearchSort)}
                  className={styles.sort}
                  hint={state.sort !== "relevance" ? "Reorders the papers on this page; pages follow relevance." : undefined}
                >
                  {(Object.keys(SORT_LABELS) as SearchSort[]).map((sort) => (
                    <option key={sort} value={sort}>
                      {SORT_LABELS[sort]}
                    </option>
                  ))}
                </Select>
              </div>
            </div>

            {phase === "loading" && (
              <>
                {slow && <p className={styles.slow}>This search is taking longer than usual. Results will appear here.</p>}
                <SkeletonList rows={4} lines={3} label="Searching papers" announce={false} />
              </>
            )}

            {phase === "error" && (
              <ErrorState
                kind={failure === "network" ? "offline" : "failed"}
                title="The search could not be completed"
                description={
                  failure === "network"
                    ? "The server could not be reached. Check your connection and try again."
                    : failure === "server"
                      ? "Something went wrong on our side. Try again in a moment."
                      : "This search could not be run. Try different words or fewer filters."
                }
                onRetry={() => executeSearch(stateRef.current)}
                announce
              />
            )}

            {phase === "done" && items.length === 0 && (
              <EmptyState
                variant="no-results"
                title={total > 0 ? "This page is past the last one" : "No papers matched your search"}
                description={
                  total > 0
                    ? "Go back to the first page of results."
                    : filterCount > 0
                      ? "Check the spelling, try broader terms, or clear the filters."
                      : "Check the spelling, or try broader or different terms."
                }
                actions={
                  total > 0 ? (
                    <Button onClick={() => changePage(1)}>Go to the first page</Button>
                  ) : filterCount > 0 ? (
                    <Button onClick={() => changeFilters(withoutFilters(stateRef.current))}>Clear filters</Button>
                  ) : undefined
                }
              />
            )}

            {phase === "done" && items.length > 0 && (
              <>
                <ul className={styles.list}>
                  {shownItems.map((item) => (
                    <li key={item.work.id}>
                      <PaperCard
                        item={item}
                        onOpen={setPaper}
                        onExplain={setEvidence}
                        onChoose={chooseWork}
                        saved={item.work.id in savedWorks}
                        onSaved={handleSaved}
                      />
                    </li>
                  ))}
                </ul>
                <Pagination
                  page={state.page}
                  total={total}
                  pageSize={state.perPage}
                  onPage={changePage}
                  pageSizes={PAGE_SIZES}
                  onPageSize={changePageSize}
                  label="Search results pages"
                />
              </>
            )}
          </section>
        </div>
      )}

      <Drawer
        open={filtersOpen}
        onClose={() => setFiltersOpen(false)}
        title="Filters"
        description="Results update as you change a filter."
        footer={
          <Button variant="primary" onClick={() => setFiltersOpen(false)}>
            Show results
          </Button>
        }
      >
        {filters}
      </Drawer>

      {paper && (
        <PaperPanel item={paper} onClose={() => setPaper(null)} savedItemId={savedWorks[paper.work.id] ?? null} onSaved={handleSaved} onChoose={chooseWork} />
      )}
      {evidence && (
        <EvidencePanel
          subject={{
            title: evidence.work.title,
            context: "search",
            rank: evidence.rank,
            score: evidence.score,
            scoreKind: "relevance",
            explanation: evidence.explanation,
            sharedTopics: evidence.sharedTopics,
          }}
          onClose={() => setEvidence(null)}
          rankingMode={response?.ranking_mode}
        />
      )}
    </section>
  );
}
