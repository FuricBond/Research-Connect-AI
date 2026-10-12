"use client";

import React, { useState, type Ref } from "react";
import { ArrowRight, Loader2, Search, X } from "lucide-react";
import type { QueryIntelligenceSchema } from "../../types/discovery";

interface SearchBarProps {
  /** The query on screen: the latest one submitted here or arrived through the URL. */
  initialQuery?: string;
  inputRef?: Ref<HTMLInputElement>;
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
  inputRef,
  onSearch,
  isLoading = false,
  queryIntelligence,
  placeholder = "Search research works by keywords, methods, authors, or topics (e.g., GNN, LLM, Computer Vision)...",
}) => {
  const [inputVal, setInputVal] = useState(initialQuery);
  // A search that arrives from outside (the URL, the header search) shows its query here too.
  // The page changes `initialQuery` only for a submission from this box (whose text it already
  // holds) or an outside navigation, so text typed since the last search is not overwritten.
  const [shownQuery, setShownQuery] = useState(initialQuery);
  if (initialQuery !== shownQuery) {
    setShownQuery(initialQuery);
    setInputVal(initialQuery);
  }

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
            ref={inputRef}
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
          // Not disabled while a search runs: a disabled default button would make Enter do
          // nothing, silently dropping a newer query (P2 audit). A new search replaces the old.
          disabled={!inputVal.trim()}
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

