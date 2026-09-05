"use client";

import React, { useState } from "react";
import { ArrowRight, Loader2, Search, X } from "lucide-react";
import type { QueryIntelligenceSchema } from "../../types/discovery";

interface SearchBarProps {
  initialQuery?: string;
  onSearch: (query: string) => void;
  isLoading?: boolean;
  queryIntelligence?: QueryIntelligenceSchema | null;
  placeholder?: string;
}

const SUGGESTED_QUERIES = [
  "Graph Neural Networks for molecular prediction",
  "Attention mechanisms in transformer architectures",
  "Medical image segmentation using deep learning",
  "RAG retrieval augmented generation with knowledge graphs",
];

export const SearchBar: React.FC<SearchBarProps> = ({
  initialQuery = "",
  onSearch,
  isLoading = false,
  queryIntelligence,
  placeholder = "Search research works by keywords, methods, authors, or topics (e.g., GNN, LLM, Computer Vision)...",
}) => {
  const [inputVal, setInputVal] = useState(initialQuery);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (inputVal.trim()) {
      onSearch(inputVal.trim());
    }
  };

  const handleSuggestionClick = (suggestion: string) => {
    setInputVal(suggestion);
    onSearch(suggestion);
  };

  return (
    <div className="search-bar-container">
      <form onSubmit={handleSubmit} className="search-form" role="search">
        <div className="search-input-wrapper">
          <Search size={18} className="search-icon" />
          <input
            type="search"
            value={inputVal}
            onChange={(e) => setInputVal(e.target.value)}
            placeholder={placeholder}
            aria-label="Search research literature"
            className="search-input"
          />
          {inputVal && (
            <button
              type="button"
              className="clear-button"
              onClick={() => setInputVal("")}
              aria-label="Clear search input"
            >
              <X size={16} />
            </button>
          )}
        </div>

        <button
          type="submit"
          className="search-submit-btn"
          disabled={isLoading || !inputVal.trim()}
          aria-label="Submit search"
        >
          {isLoading ? (
            <>
              <Loader2 size={16} className="spin" />
              <span>Searching...</span>
            </>
          ) : (
            <>
              <span>Search</span>
              <ArrowRight size={16} />
            </>
          )}
        </button>
      </form>

      {/* Query Intelligence Acronym Expansion Banner */}
      {queryIntelligence && queryIntelligence.was_expanded && (
        <div className="query-intelligence-banner" role="status">
          <span className="qi-badge">Acronym Intelligence</span>
          <span className="qi-text">
            Expanded <strong>{queryIntelligence.detected_acronyms.join(", ")}</strong> to{" "}
            <em>{queryIntelligence.detected_terms.join(", ")}</em>
          </span>
        </div>
      )}

      {/* Quick Search Suggestions */}
      {!queryIntelligence && (
        <div className="suggestions-row">
          <span className="suggestions-label">Try:</span>
          {SUGGESTED_QUERIES.map((query) => (
            <button
              key={query}
              type="button"
              className="suggestion-chip"
              onClick={() => handleSuggestionClick(query)}
            >
              {query}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};

