"use client";

import React from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";

interface PaginationControlsProps {
  total: number;
  limit: number;
  offset: number;
  onPageChange: (newOffset: number) => void;
  onLimitChange?: (newLimit: number) => void;
  isLoading?: boolean;
}

export const PaginationControls: React.FC<PaginationControlsProps> = ({
  total,
  limit,
  offset,
  onPageChange,
  onLimitChange,
  isLoading = false,
}) => {
  if (total <= 0) return null;

  const currentPage = Math.floor(offset / limit) + 1;
  const totalPages = Math.ceil(total / limit);
  const startItem = offset + 1;
  const endItem = Math.min(offset + limit, total);

  const handlePrev = () => {
    if (currentPage > 1) {
      onPageChange(Math.max(0, offset - limit));
    }
  };

  const handleNext = () => {
    if (currentPage < totalPages) {
      onPageChange(offset + limit);
    }
  };

  return (
    <div className="pagination-wrapper" aria-label="Pagination controls">
      <div className="pagination-summary">
        Showing <strong>{startItem}–{endItem}</strong> of <strong>{total}</strong> results
      </div>

      <div className="pagination-actions">
        <button
          type="button"
          className="pagination-nav-btn"
          onClick={handlePrev}
          disabled={currentPage <= 1 || isLoading}
          aria-label="Previous page"
        >
          <ChevronLeft size={16} />
          <span>Previous</span>
        </button>

        <span className="pagination-current-indicator">
          Page <strong>{currentPage}</strong> of <strong>{totalPages}</strong>
        </span>

        <button
          type="button"
          className="pagination-nav-btn"
          onClick={handleNext}
          disabled={currentPage >= totalPages || isLoading}
          aria-label="Next page"
        >
          <span>Next</span>
          <ChevronRight size={16} />
        </button>
      </div>

      {onLimitChange && (
        <div className="pagination-limit-select">
          <label htmlFor="limit-select">Per page:</label>
          <select
            id="limit-select"
            value={limit}
            onChange={(e) => onLimitChange(parseInt(e.target.value, 10))}
            disabled={isLoading}
          >
            <option value={10}>10</option>
            <option value={20}>20</option>
            <option value={50}>50</option>
          </select>
        </div>
      )}
    </div>
  );
};

