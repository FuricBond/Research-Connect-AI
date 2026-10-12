"use client";

import { Suspense, useCallback, useEffect, useState, useRef } from "react";
import { useSearchParams } from "next/navigation";
import { AlertCircle, BookOpen, Loader2, Search } from "lucide-react";
import { SearchBar } from "../discovery/SearchBar";
import { SearchFilters } from "../discovery/SearchFilters";
import { ResearchResultCard } from "../discovery/ResearchResultCard";
import { PaginationControls } from "../discovery/PaginationControls";
import { ExplainabilityDrawer } from "../discovery/ExplainabilityDrawer";
import { searchResearchWorks, lookupReadingList, ApiError } from "../../services/api";
import { useSession } from "../auth/SessionProvider";
import { VisitorIntro } from "../auth/VisitorIntro";
import { currentUrlQuery, searchHref, takeSearchFocusRequest } from "../../utils/search";
import { PageHeader } from "../ui/PageHeader/PageHeader";
import type {
  ExplanationSchema,
  QueryIntelligenceSchema,
  ResearchSearchParams,
  ResearchSearchResultItem,
} from "../../types/discovery";

/**
 * Reports the URL's `q` whenever it changes (on arrival, from the header search, back and
 * forward). Isolated in its own Suspense boundary: reading search params on the client keeps
 * the rest of the page prerendered.
 */
function UrlQuery({ onChange }: { onChange: (query: string | null) => void }) {
  const query = useSearchParams().get("q");
  useEffect(() => onChange(query), [query, onChange]);
  return null;
}

/**
 * Literature search. The query lives in the URL (`/?q=…`), so a search can be bookmarked,
 * shared, reloaded and reached from the header's global search. Filters and pagination stay in
 * the page.
 *
 * The latest submission always wins (P2 audit): a search typed here runs at once and the address
 * bar is updated with the browser's own history (Next.js keeps `useSearchParams` in step with
 * native `pushState` without fetching the page again), so no page navigation is ever pending
 * behind the person's back. The URL itself starts a search only when it changes from outside
 * this box — a direct link, back/forward, or the header search — and only for the address the
 * bar actually shows, so a late notification for an older address can neither search again nor
 * overwrite what is being typed.
 */
export function DiscoverySearch() {
  const [query, setQuery] = useState("");
  const [filters, setFilters] = useState<Partial<ResearchSearchParams>>({
    limit: 20,
    offset: 0,
    explain: true,
    include_query_intelligence: true,
  });

  const [items, setItems] = useState<ResearchSearchResultItem[]>([]);
  const [total, setTotal] = useState(0);
  const [queryIntelligence, setQueryIntelligence] = useState<QueryIntelligenceSchema | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasSearched, setHasSearched] = useState(false);

  // Explainability Drawer State
  const [selectedExplanation, setSelectedExplanation] = useState<ExplanationSchema | null>(null);
  const [drawerTitle, setDrawerTitle] = useState("");
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);

  const abortControllerRef = useRef<AbortController | null>(null);
  // The latest filters, for a search started by the URL rather than by a filter change.
  const filtersRef = useRef(filters);
  filtersRef.current = filters;
  // The query whose results are shown or loading (null: the landing state).
  const searchedQueryRef = useRef<string | null>(null);
  // The query of the request in flight, if any.
  const loadingQueryRef = useRef<string | null>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  // Reading list: which visible works the signed-in user has already saved (work id -> item id).
  const { status: sessionStatus } = useSession();
  const [savedWorks, setSavedWorks] = useState<Record<string, string>>({});

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

  const executeSearch = async (
    searchQuery: string,
    currentFilters: Partial<ResearchSearchParams>
  ) => {
    if (!searchQuery.trim()) return;

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const abortController = new AbortController();
    abortControllerRef.current = abortController;
    loadingQueryRef.current = searchQuery;

    setIsLoading(true);
    setError(null);
    setHasSearched(true);

    try {
      const response = await searchResearchWorks(
        {
          q: searchQuery,
          ...currentFilters,
          explain: true,
          include_query_intelligence: true,
        },
        abortController.signal
      );
      // A newer search replaced this one: its answer must not replace the newer results.
      if (abortController.signal.aborted) return;

      setItems(response.items);
      setTotal(response.total);
      setQueryIntelligence(response.query_intelligence || null);
    } catch (err: unknown) {
      if (abortController.signal.aborted || (err instanceof Error && err.name === "AbortError")) {
        return;
      }
      if (err instanceof ApiError) {
        setError(err.detail || err.message);
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("An unexpected error occurred while searching.");
      }
    } finally {
      // Only the latest search ends the loading state.
      if (abortControllerRef.current === abortController) {
        loadingQueryRef.current = null;
        setIsLoading(false);
      }
    }
  };

  const searchFromStart = (newQuery: string) => {
    searchedQueryRef.current = newQuery;
    setQuery(newQuery);
    const updatedFilters = { ...filtersRef.current, offset: 0 };
    setFilters(updatedFilters);
    executeSearch(newQuery, updatedFilters);
  };
  // executeSearch only uses state setters and refs, so the latest one is always equivalent.
  const searchFromStartRef = useRef(searchFromStart);
  searchFromStartRef.current = searchFromStart;

  const handleUrlQuery = useCallback((urlQuery: string | null) => {
    // The router applies address changes in a transition; if the bar has already moved on, a
    // newer notification follows and this one is stale.
    if (urlQuery !== currentUrlQuery()) return;
    const trimmed = urlQuery?.trim() ?? "";
    if (trimmed) {
      // Already shown (this box submitted it): nothing to do, and nothing to overwrite.
      if (trimmed !== searchedQueryRef.current) searchFromStartRef.current(trimmed);
      // Arrived from the header search: keyboard focus goes to the box that now holds the query.
      if (takeSearchFocusRequest(trimmed)) searchInputRef.current?.focus();
      return;
    }
    // No query in the URL (the navigation's "Literature search", or back to the start): the
    // landing state, with nothing still loading.
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
    loadingQueryRef.current = null;
    searchedQueryRef.current = null;
    setQuery("");
    setItems([]);
    setTotal(0);
    setQueryIntelligence(null);
    setError(null);
    setIsLoading(false);
    setHasSearched(false);
  }, []);

  const handleQuerySubmit = (newQuery: string) => {
    // The same query is already being fetched (a double press): one request is enough.
    if (newQuery === loadingQueryRef.current) return;
    searchFromStart(newQuery);
    // Record it in the address bar; an unchanged query adds no history entry.
    if (currentUrlQuery() !== newQuery) window.history.pushState(null, "", searchHref(newQuery));
  };

  const handleFilterChange = (updated: Partial<ResearchSearchParams>) => {
    const updatedFilters = { ...filters, ...updated, offset: 0 };
    setFilters(updatedFilters);
    if (query) {
      executeSearch(query, updatedFilters);
    }
  };

  const handleResetFilters = () => {
    const reset = {
      limit: 20,
      offset: 0,
      explain: true,
      include_query_intelligence: true,
    };
    setFilters(reset);
    if (query) {
      executeSearch(query, reset);
    }
  };

  const handlePageChange = (newOffset: number) => {
    const updated = { ...filters, offset: newOffset };
    setFilters(updated);
    executeSearch(query, updated);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const handleLimitChange = (newLimit: number) => {
    const updated = { ...filters, limit: newLimit, offset: 0 };
    setFilters(updated);
    executeSearch(query, updated);
  };

  const handleOpenExplain = (item: ResearchSearchResultItem) => {
    setSelectedExplanation(item.explanation || null);
    setDrawerTitle(item.work.title);
    setIsDrawerOpen(true);
  };

  return (
    <section className="discovery-search-page" aria-label="Research Literature Discovery">
      <Suspense fallback={null}>
        <UrlQuery onChange={handleUrlQuery} />
      </Suspense>
      <PageHeader
        title="Literature search"
        description="Find papers by topic, method or author. Every result shows why it ranks where it does."
      />

      <SearchBar
        initialQuery={query}
        inputRef={searchInputRef}
        onSearch={handleQuerySubmit}
        isLoading={isLoading}
        queryIntelligence={queryIntelligence}
      />

      <SearchFilters
        filters={filters}
        onFilterChange={handleFilterChange}
        onReset={handleResetFilters}
      />

      {/* Loading State */}
      {isLoading && (
        <div className="state-container loading-state" role="status">
          <Loader2 size={24} className="spin" />
          <p>Retrieving and ranking research works across vector and lexical channels...</p>
        </div>
      )}

      {/* Error State */}
      {error && !isLoading && (
        <div className="state-container error-state" role="alert">
          <AlertCircle size={24} className="status-error" />
          <div>
            <h4>Search Error</h4>
            <p>{error}</p>
            <button
              type="button"
              className="retry-btn"
              onClick={() => executeSearch(query, filters)}
            >
              Retry Search
            </button>
          </div>
        </div>
      )}

      {/* Empty State */}
      {!isLoading && !error && hasSearched && items.length === 0 && (
        <div className="state-container empty-state">
          <BookOpen size={28} className="empty-icon" />
          <h4>No research works matched your query</h4>
          <p>Try searching broader terms, checking for spelling variations, or clearing active filters.</p>
        </div>
      )}

      {/* Initial Landing Prompt; a visitor also reads what an account adds (P3). */}
      {!hasSearched && !isLoading && (
        <div className="state-container prompt-state">
          <Search size={28} className="prompt-icon" aria-hidden="true" />
          <h4>Begin your literature search</h4>
          <p>Type a topic, methodology, or academic acronym to discover relevant literature and match venues.</p>
          {sessionStatus === "unauthenticated" && <VisitorIntro />}
        </div>
      )}

      {/* Result Cards List */}
      {!isLoading && items.length > 0 && (
        <div className="results-container">
          <div className="results-header">
            <h2>Matching papers</h2>
            <span className="results-count-text">
              {total} total results found
            </span>
          </div>

          <div className="results-grid">
            {items.map((item) => (
              <ResearchResultCard
                key={item.work.id}
                item={item}
                onExplain={handleOpenExplain}
                isSaved={item.work.id in savedWorks}
                onSaved={handleSaved}
              />
            ))}
          </div>

          <PaginationControls
            total={total}
            limit={filters.limit || 20}
            offset={filters.offset || 0}
            onPageChange={handlePageChange}
            onLimitChange={handleLimitChange}
            isLoading={isLoading}
          />
        </div>
      )}

      {/* Slide-over Explainability Drawer */}
      <ExplainabilityDrawer
        isOpen={isDrawerOpen}
        onClose={() => setIsDrawerOpen(false)}
        explanation={selectedExplanation}
        entityTitle={drawerTitle}
        entityType="research_work"
      />
    </section>
  );
}
