"use client";

import { useEffect, useState, useRef } from "react";
import { AlertCircle, ArrowLeft, BookOpen, Compass, Loader2, Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";
import { SimilarResearchCard } from "../discovery/SimilarResearchCard";
import { PaginationControls } from "../discovery/PaginationControls";
import { ExplainabilityDrawer } from "../discovery/ExplainabilityDrawer";
import { getSimilarResearch, ApiError } from "../../services/api";
import { getSelectedWork, setSelectedWork } from "../../hooks/useSelectedWork";
import type {
  ExplanationSchema,
  ResearchWorkRead,
  SimilarResearchItem,
  SimilarResearchParams,
} from "../../types/discovery";

export function SimilarResearchPage() {
  const router = useRouter();
  const [selectedWork, setSelectedWork] = useState<ResearchWorkRead | null>(null);

  const [items, setItems] = useState<SimilarResearchItem[]>([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [filters, setFilters] = useState<SimilarResearchParams>({
    limit: 20,
    offset: 0,
    explain: true,
  });

  // Explainability Drawer State
  const [selectedExplanation, setSelectedExplanation] = useState<ExplanationSchema | null>(null);
  const [drawerTitle, setDrawerTitle] = useState("");
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);

  const abortControllerRef = useRef<AbortController | null>(null);

  // Hydrate selectedWork from sessionStorage on mount
  useEffect(() => {
    const work = getSelectedWork();
    setSelectedWork(work);
    if (work) {
      fetchSimilar(work.id, filters);
    }
  }, []);

  const fetchSimilar = async (workId: string, currentFilters: SimilarResearchParams) => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    setIsLoading(true);
    setError(null);

    try {
      const response = await getSimilarResearch(
        workId,
        { ...currentFilters, explain: true },
        abortController.signal
      );
      setItems(response.items);
      setTotal(response.total);
    } catch (err: unknown) {
      if (err instanceof Error && err.name === "AbortError") {
        return;
      }
      if (err instanceof ApiError) {
        setError(err.detail || err.message);
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("An unexpected error occurred while fetching similar research.");
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handlePageChange = (newOffset: number) => {
    const updated = { ...filters, offset: newOffset };
    setFilters(updated);
    if (selectedWork) {
      fetchSimilar(selectedWork.id, updated);
    }
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const handleOpenExplain = (item: SimilarResearchItem) => {
    setSelectedExplanation(item.explanation || null);
    setDrawerTitle(item.work.title);
    setIsDrawerOpen(true);
  };

  const handleBackToSearch = () => {
    router.push("/");
  };

  if (!selectedWork) {
    return (
      <section className="similar-research-page empty-selection">
        <div className="state-container prompt-state">
          <Compass size={32} className="prompt-icon" />
          <h3>No Research Paper Selected</h3>
          <p>
            Please search for an academic paper in the <strong>Literature Search</strong> tab and click{" "}
            <em>&quot;Find Similar Research&quot;</em> to explore nearest semantic neighbors and topic proximity.
          </p>
          <button type="button" className="action-btn primary-btn" onClick={handleBackToSearch}>
            <ArrowLeft size={16} />
            <span>Go to Literature Search</span>
          </button>
        </div>
      </section>
    );
  }

  return (
    <section className="similar-research-page" aria-label="Similar Research Explorer">
      {/* Back to search link */}
      <button type="button" className="back-link-btn" onClick={handleBackToSearch}>
        <ArrowLeft size={16} />
        <span>Back to Literature Search</span>
      </button>

      {/* Source Paper Banner */}
      <div className="source-paper-hero">
        <div className="source-hero-eyebrow">
          <BookOpen size={14} />
          <span>Source Reference Work</span>
        </div>
        <h2 className="source-hero-title">{selectedWork.title}</h2>
        {selectedWork.abstract && (
          <p className="source-hero-abstract">{selectedWork.abstract}</p>
        )}
        <div className="source-hero-actions">
          <button
            type="button"
            className="action-btn primary-btn"
            onClick={() => {
              setSelectedWork(selectedWork);
              router.push("/opportunities");
            }}
          >
            <Sparkles size={15} />
            <span>Match Calls for This Paper</span>
          </button>
        </div>
      </div>

      {/* Loading State */}
      {isLoading && (
        <div className="state-container loading-state" role="status">
          <Loader2 size={24} className="spin" />
          <p>Analyzing semantic vectors and canonical taxonomy DAG proximity...</p>
        </div>
      )}

      {/* Error State */}
      {error && !isLoading && (
        <div className="state-container error-state" role="alert">
          <AlertCircle size={24} className="status-error" />
          <div>
            <h4>Retrieval Error</h4>
            <p>{error}</p>
            <button
              type="button"
              className="retry-btn"
              onClick={() => fetchSimilar(selectedWork.id, filters)}
            >
              Retry
            </button>
          </div>
        </div>
      )}

      {/* Empty State */}
      {!isLoading && !error && items.length === 0 && (
        <div className="state-container empty-state">
          <Compass size={28} className="empty-icon" />
          <h4>No similar research works found</h4>
          <p>No other works in the repository met the similarity criteria for this reference paper.</p>
        </div>
      )}

      {/* Results Grid */}
      {!isLoading && items.length > 0 && (
        <div className="results-container">
          <div className="results-header">
            <h3>Similar Research Works</h3>
            <span className="results-count-text">{total} similar works discovered</span>
          </div>

          <div className="results-grid">
            {items.map((item) => (
              <SimilarResearchCard
                key={item.work.id}
                item={item}
                onExplain={handleOpenExplain}
              />
            ))}
          </div>

          <PaginationControls
            total={total}
            limit={filters.limit || 20}
            offset={filters.offset || 0}
            onPageChange={handlePageChange}
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
