import React, { useEffect, useState, useRef } from "react";
import { AlertCircle, BookOpen, Loader2, Sparkles } from "lucide-react";
import { SearchBar } from "../components/discovery/SearchBar";
import { SearchFilters } from "../components/discovery/SearchFilters";
import { ResearchResultCard } from "../components/discovery/ResearchResultCard";
import { PaginationControls } from "../components/discovery/PaginationControls";
import { ExplainabilityDrawer } from "../components/discovery/ExplainabilityDrawer";
import { searchResearchWorks, ApiError } from "../services/api";
import type {
  ExplanationSchema,
  QueryIntelligenceSchema,
  ResearchSearchParams,
  ResearchSearchResultItem,
  ResearchWorkRead,
} from "../types/discovery";

interface DiscoverySearchProps {
  onFindSimilar: (work: ResearchWorkRead) => void;
  onMatchOpportunities: (work: ResearchWorkRead) => void;
}

export const DiscoverySearch: React.FC<DiscoverySearchProps> = ({
  onFindSimilar,
  onMatchOpportunities,
}) => {
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

      setItems(response.items);
      setTotal(response.total);
      setQueryIntelligence(response.query_intelligence || null);
    } catch (err: unknown) {
      if (err instanceof Error && err.name === "AbortError") {
        return; // Request was aborted by newer search
      }
      if (err instanceof ApiError) {
        setError(err.detail || err.message);
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("An unexpected error occurred while searching.");
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleQuerySubmit = (newQuery: string) => {
    setQuery(newQuery);
    const updatedFilters = { ...filters, offset: 0 };
    setFilters(updatedFilters);
    executeSearch(newQuery, updatedFilters);
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
      <div className="page-intro">
        <span className="eyebrow">Academic Literature Search</span>
        <h2>Discover peer-reviewed papers with multi-channel hybrid intelligence.</h2>
        <p className="page-desc">
          Combines dense 384-dimensional semantic embeddings with PostgreSQL full-text cover density ranking and canonical taxonomy DAG proximity.
        </p>
      </div>

      <SearchBar
        initialQuery={query}
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

      {/* Initial Landing Prompt */}
      {!hasSearched && !isLoading && (
        <div className="state-container prompt-state">
          <Sparkles size={28} className="prompt-icon" />
          <h4>Begin your literature search</h4>
          <p>Type a topic, methodology, or academic acronym to discover relevant literature and match venues.</p>
        </div>
      )}

      {/* Result Cards List */}
      {!isLoading && items.length > 0 && (
        <div className="results-container">
          <div className="results-header">
            <h3>Matching Research Works</h3>
            <span className="results-count-text">
              {total} total results found
            </span>
          </div>

          <div className="results-grid">
            {items.map((item) => (
              <ResearchResultCard
                key={item.work.id}
                item={item}
                onFindSimilar={onFindSimilar}
                onMatchOpportunities={onMatchOpportunities}
                onExplain={handleOpenExplain}
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
};
