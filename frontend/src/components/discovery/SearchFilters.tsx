import React, { useState } from "react";
import { ChevronDown, ChevronUp, Filter, RotateCcw } from "lucide-react";
import type { RankingMode, ResearchSearchParams } from "../../types/discovery";

interface SearchFiltersProps {
  filters: Partial<ResearchSearchParams>;
  onFilterChange: (updated: Partial<ResearchSearchParams>) => void;
  onReset: () => void;
}

export const SearchFilters: React.FC<SearchFiltersProps> = ({
  filters,
  onFilterChange,
  onReset,
}) => {
  const [isExpanded, setIsExpanded] = useState(false);

  const activeFilterCount = [
    filters.min_year,
    filters.max_year,
    filters.work_type,
    filters.is_oa,
    filters.min_citations,
    filters.ranking_mode && filters.ranking_mode !== "general",
  ].filter(Boolean).length;

  return (
    <aside className="filters-panel" aria-label="Search filter controls">
      <div className="filters-header">
        <button
          type="button"
          className="filters-toggle-btn"
          onClick={() => setIsExpanded(!isExpanded)}
          aria-expanded={isExpanded}
        >
          <Filter size={16} />
          <span>Filters & Ranking Mode</span>
          {activeFilterCount > 0 && (
            <span className="filters-count-badge">{activeFilterCount} active</span>
          )}
          {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </button>

        {activeFilterCount > 0 && (
          <button
            type="button"
            className="filters-reset-btn"
            onClick={onReset}
            title="Reset all filters to defaults"
          >
            <RotateCcw size={14} />
            <span>Reset</span>
          </button>
        )}
      </div>

      {isExpanded && (
        <div className="filters-body">
          <div className="filter-group">
            <label htmlFor="ranking-mode-select">Ranking Mode</label>
            <select
              id="ranking-mode-select"
              value={filters.ranking_mode || "general"}
              onChange={(e) =>
                onFilterChange({ ranking_mode: e.target.value as RankingMode })
              }
            >
              <option value="general">General Discovery (Balanced)</option>
              <option value="research_similarity">Similar Research (Freshness-weighted)</option>
              <option value="research_opportunity">Opportunity Matching (Type & Quality)</option>
            </select>
          </div>

          <div className="filter-group">
            <label htmlFor="work-type-select">Publication Type</label>
            <select
              id="work-type-select"
              value={filters.work_type || ""}
              onChange={(e) =>
                onFilterChange({ work_type: e.target.value || undefined })
              }
            >
              <option value="">All Types</option>
              <option value="article">Journal Article</option>
              <option value="preprint">Preprint</option>
              <option value="book-chapter">Book Chapter</option>
              <option value="dataset">Dataset</option>
            </select>
          </div>

          <div className="filter-group filter-group-row">
            <div>
              <label htmlFor="min-year-input">From Year</label>
              <input
                id="min-year-input"
                type="number"
                min="1950"
                max="2030"
                placeholder="e.g. 2018"
                value={filters.min_year || ""}
                onChange={(e) =>
                  onFilterChange({
                    min_year: e.target.value ? parseInt(e.target.value, 10) : undefined,
                  })
                }
              />
            </div>
            <div>
              <label htmlFor="max-year-input">To Year</label>
              <input
                id="max-year-input"
                type="number"
                min="1950"
                max="2030"
                placeholder="e.g. 2026"
                value={filters.max_year || ""}
                onChange={(e) =>
                  onFilterChange({
                    max_year: e.target.value ? parseInt(e.target.value, 10) : undefined,
                  })
                }
              />
            </div>
          </div>

          <div className="filter-group">
            <label htmlFor="min-citations-input">Min Citations</label>
            <input
              id="min-citations-input"
              type="number"
              min="0"
              placeholder="0"
              value={filters.min_citations || ""}
              onChange={(e) =>
                onFilterChange({
                  min_citations: e.target.value ? parseInt(e.target.value, 10) : undefined,
                })
              }
            />
          </div>

          <div className="filter-group filter-checkbox">
            <label>
              <input
                type="checkbox"
                checked={Boolean(filters.is_oa)}
                onChange={(e) =>
                  onFilterChange({ is_oa: e.target.checked ? true : undefined })
                }
              />
              <span>Open Access Only</span>
            </label>
          </div>
        </div>
      )}
    </aside>
  );
};
