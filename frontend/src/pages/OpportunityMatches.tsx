import React, { useEffect, useState, useRef } from "react";
import {
  AlertCircle,
  ArrowLeft,
  BookOpen,
  Calendar,
  Filter,
  Loader2,
  Sparkles,
} from "lucide-react";
import { OpportunityCard } from "../components/discovery/OpportunityCard";
import { PaginationControls } from "../components/discovery/PaginationControls";
import { ExplainabilityDrawer } from "../components/discovery/ExplainabilityDrawer";
import { matchOpportunitiesForResearch, ApiError } from "../services/api";
import type {
  ExplanationSchema,
  OpportunityMatchItem,
  OpportunityMatchParams,
  ResearchWorkRead,
} from "../types/discovery";
import type { OpportunityDeadline, RiskExplanation } from "../types/opportunity";

interface OpportunityMatchesProps {
  selectedWork: ResearchWorkRead | null;
  onBackToSearch: () => void;
}

export const OpportunityMatches: React.FC<OpportunityMatchesProps> = ({
  selectedWork,
  onBackToSearch,
}) => {
  const [items, setItems] = useState<OpportunityMatchItem[]>([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [filters, setFilters] = useState<OpportunityMatchParams>({
    limit: 20,
    offset: 0,
    explain: true,
  });

  const [opportunityType, setOpportunityType] = useState<string>("");
  const [upcomingOnly, setUpcomingOnly] = useState<boolean>(false);
  const [deliveryMode, setDeliveryMode] = useState<string>("");
  const [maxApcUsd, setMaxApcUsd] = useState<string>("");
  const [requireKnownApc, setRequireKnownApc] = useState<boolean>(false);
  const [locationFilter, setLocationFilter] = useState<string>("");

  // Explainability Drawer State (Phases 2.5F, 2.6F, 2.7F)
  const [selectedExplanation, setSelectedExplanation] = useState<ExplanationSchema | null>(null);
  const [selectedRiskExplanation, setSelectedRiskExplanation] = useState<RiskExplanation | null>(null);
  const [selectedDeadlineExplanation, setSelectedDeadlineExplanation] = useState<OpportunityDeadline | null>(null);
  const [drawerTitle, setDrawerTitle] = useState("");
  const [drawerInitialTab, setDrawerInitialTab] = useState<"match" | "risk" | "deadline">("match");
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);

  const abortControllerRef = useRef<AbortController | null>(null);

  const fetchMatches = async (workId: string, currentFilters: OpportunityMatchParams) => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    setIsLoading(true);
    setError(null);

    try {
      const parsedMaxApc = maxApcUsd ? parseFloat(maxApcUsd) : undefined;
      const response = await matchOpportunitiesForResearch(
        workId,
        {
          ...currentFilters,
          opportunity_type: opportunityType || undefined,
          upcoming_only: upcomingOnly || undefined,
          delivery_mode: deliveryMode || undefined,
          max_apc_usd: !isNaN(parsedMaxApc as number) ? parsedMaxApc : undefined,
          require_known_apc: requireKnownApc || undefined,
          location: locationFilter.trim() || undefined,
          explain: true,
        },
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
        setError("An unexpected error occurred while matching opportunities.");
      }
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (selectedWork && selectedWork.id) {
      fetchMatches(selectedWork.id, filters);
    }
  }, [selectedWork?.id, opportunityType, upcomingOnly, deliveryMode, maxApcUsd, requireKnownApc, locationFilter]);

  const handlePageChange = (newOffset: number) => {
    const updated = { ...filters, offset: newOffset };
    setFilters(updated);
    if (selectedWork) {
      fetchMatches(selectedWork.id, updated);
    }
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const handleOpenExplain = (
    item: OpportunityMatchItem,
    initialTab: "match" | "risk" | "deadline" = "match"
  ) => {
    setSelectedExplanation(item.explanation || null);
    setSelectedRiskExplanation(item.risk_explanation || item.opportunity.risk_explanation || null);
    setSelectedDeadlineExplanation(item.deadline_explanation || item.opportunity.deadline_intelligence || null);
    setDrawerTitle(item.opportunity.title);
    setDrawerInitialTab(initialTab);
    setIsDrawerOpen(true);
  };

  if (!selectedWork) {
    return (
      <section className="opportunity-matches-page empty-selection">
        <div className="state-container prompt-state">
          <Sparkles size={32} className="prompt-icon" />
          <h3>No Research Paper Selected</h3>
          <p>
            Please search for an academic paper in the <strong>Literature Search</strong> tab and click{" "}
            <em>"Match Calls & Venues"</em> to evaluate venue quality, publication type compatibility, and upcoming deadlines.
          </p>
          <button type="button" className="action-btn primary-btn" onClick={onBackToSearch}>
            <ArrowLeft size={16} />
            <span>Go to Literature Search</span>
          </button>
        </div>
      </section>
    );
  }

  return (
    <section className="opportunity-matches-page" aria-label="Research Opportunity Matcher">
      {/* Back button */}
      <button type="button" className="back-link-btn" onClick={onBackToSearch}>
        <ArrowLeft size={16} />
        <span>Back to Literature Search</span>
      </button>

      {/* Target Paper Banner */}
      <div className="source-paper-hero">
        <div className="source-hero-eyebrow">
          <BookOpen size={14} />
          <span>Manuscript / Target Research Work</span>
        </div>
        <h2 className="source-hero-title">{selectedWork.title}</h2>
        {selectedWork.abstract && (
          <p className="source-hero-abstract">{selectedWork.abstract}</p>
        )}
      </div>

      {/* Opportunity Filters Strip */}
      <div className="opportunity-filters-strip">
        <div className="filter-select-wrap">
          <label htmlFor="opp-type-filter">Category:</label>
          <select
            id="opp-type-filter"
            value={opportunityType}
            onChange={(e) => setOpportunityType(e.target.value)}
          >
            <option value="">All Categories</option>
            <option value="CONFERENCE">Conferences</option>
            <option value="JOURNAL">Journals</option>
            <option value="WORKSHOP">Workshops</option>
            <option value="CALL_FOR_PAPERS">Calls for Papers</option>
            <option value="SPECIAL_ISSUE">Special Issues</option>
          </select>
        </div>

        <div className="filter-select-wrap">
          <label htmlFor="delivery-mode-filter">Attendance:</label>
          <select
            id="delivery-mode-filter"
            value={deliveryMode}
            onChange={(e) => setDeliveryMode(e.target.value)}
          >
            <option value="">All Modes</option>
            <option value="ONLINE">Online / Virtual</option>
            <option value="HYBRID">Hybrid</option>
            <option value="OFFLINE">In-Person (Offline)</option>
          </select>
        </div>

        <div className="filter-input-wrap">
          <label htmlFor="max-apc-filter">Max APC ($):</label>
          <input
            id="max-apc-filter"
            type="number"
            min="0"
            step="100"
            placeholder="e.g. 1000"
            value={maxApcUsd}
            onChange={(e) => setMaxApcUsd(e.target.value)}
          />
        </div>

        <div className="filter-input-wrap">
          <label htmlFor="location-filter">Location:</label>
          <input
            id="location-filter"
            type="text"
            placeholder="e.g. London, USA"
            value={locationFilter}
            onChange={(e) => setLocationFilter(e.target.value)}
          />
        </div>

        <div className="filter-checkbox-wrap">
          <label>
            <input
              type="checkbox"
              checked={requireKnownApc}
              onChange={(e) => setRequireKnownApc(e.target.checked)}
            />
            <span>Require Stated Fee</span>
          </label>
        </div>

        <div className="filter-checkbox-wrap">
          <label>
            <input
              type="checkbox"
              checked={upcomingOnly}
              onChange={(e) => setUpcomingOnly(e.target.checked)}
            />
            <span>Upcoming Only</span>
          </label>
        </div>
      </div>

      {/* Loading State */}
      {isLoading && (
        <div className="state-container loading-state" role="status">
          <Loader2 size={24} className="spin" />
          <p>Evaluating venue quality, predatory risk, topic compatibility, and submission deadlines...</p>
        </div>
      )}

      {/* Error State */}
      {error && !isLoading && (
        <div className="state-container error-state" role="alert">
          <AlertCircle size={24} className="status-error" />
          <div>
            <h4>Matching Error</h4>
            <p>{error}</p>
            <button
              type="button"
              className="retry-btn"
              onClick={() => fetchMatches(selectedWork.id, filters)}
            >
              Retry
            </button>
          </div>
        </div>
      )}

      {/* Empty State */}
      {!isLoading && !error && items.length === 0 && (
        <div className="state-container empty-state">
          <Calendar size={28} className="empty-icon" />
          <h4>No academic opportunities matched this paper</h4>
          <p>Try broadening your filters or unchecking "Upcoming Deadlines Only".</p>
        </div>
      )}

      {/* Results Grid */}
      {!isLoading && items.length > 0 && (
        <div className="results-container">
          <div className="results-header">
            <h3>Ranked Target Venues & Calls</h3>
            <span className="results-count-text">{total} relevant venues identified</span>
          </div>

          <div className="results-grid">
            {items.map((item) => (
              <OpportunityCard
                key={item.opportunity.id}
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

      {/* Slide-over Explainability Drawer (Phase 2.5F + 2.6F + 2.7F) */}
      <ExplainabilityDrawer
        isOpen={isDrawerOpen}
        onClose={() => setIsDrawerOpen(false)}
        explanation={selectedExplanation}
        entityTitle={drawerTitle}
        entityType="opportunity"
        riskExplanation={selectedRiskExplanation}
        deadlineExplanation={selectedDeadlineExplanation}
        initialTab={drawerInitialTab}
      />
    </section>
  );
};
