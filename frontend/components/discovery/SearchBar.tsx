"use client";

import { useId, useState, type FormEvent, type Ref } from "react";
import { ArrowRight } from "lucide-react";
import type { QueryIntelligenceSchema } from "../../types/discovery";
import { Button } from "../ui/Button/Button";
import { SearchInput } from "../ui/Field/Field";
import styles from "./Search.module.css";

interface SearchBarProps {
  /** The query on screen: the latest one submitted here or arrived through the URL. */
  initialQuery?: string;
  inputRef?: Ref<HTMLInputElement>;
  onSearch: (query: string) => void;
  isLoading?: boolean;
  queryIntelligence?: QueryIntelligenceSchema | null;
  /** The first view shows a few example searches. */
  showSuggestions?: boolean;
}

const SUGGESTED_QUERIES = [
  "Graph neural networks for molecular prediction",
  "Attention mechanisms in transformer architectures",
  "Medical image segmentation using deep learning",
  "Retrieval-augmented generation with knowledge graphs",
];

/**
 * The literature search box (DESIGN_SYSTEM.md §8.2 SearchInput). Its name stays "Search research
 * literature" (plan §23). The submit button is never disabled — not while a search runs (Enter
 * must always start the newer search, P2 audit) and not while empty (a hint says what to type).
 */
export function SearchBar({ initialQuery = "", inputRef, onSearch, isLoading = false, queryIntelligence, showSuggestions = false }: SearchBarProps) {
  const hintId = useId();
  const [inputVal, setInputVal] = useState(initialQuery);
  const [emptyHint, setEmptyHint] = useState(false);
  // A search that arrives from outside (the URL, the header search) shows its query here too.
  // The page changes `initialQuery` only for a submission from this box (whose text it already
  // holds) or an outside navigation, so text typed since the last search is not overwritten.
  const [shownQuery, setShownQuery] = useState(initialQuery);
  if (initialQuery !== shownQuery) {
    setShownQuery(initialQuery);
    setInputVal(initialQuery);
  }

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    const query = inputVal.trim();
    if (!query) {
      setEmptyHint(true);
      return;
    }
    setEmptyHint(false);
    onSearch(query);
  };

  const expanded = queryIntelligence?.was_expanded ? queryIntelligence : null;

  return (
    <div className={styles.bar}>
      <form onSubmit={handleSubmit} className={styles.form} role="search" aria-label="Literature">
        <SearchInput
          ref={inputRef}
          label="Search research literature"
          hideLabel
          value={inputVal}
          onChange={(event) => {
            setInputVal(event.target.value);
            if (emptyHint) setEmptyHint(false);
          }}
          onClear={() => setInputVal("")}
          placeholder="Topic, method or author — for example GNN, LLM, computer vision"
          aria-describedby={emptyHint ? hintId : undefined}
          className={styles.input}
        />
        <Button type="submit" variant="primary" loading={isLoading} aria-label="Submit search" trailingIcon={isLoading ? undefined : <ArrowRight size={16} aria-hidden="true" />}>
          Search
        </Button>
      </form>
      {emptyHint && (
        <p id={hintId} className={styles.hint}>
          Type a topic, method or author to search.
        </p>
      )}

      {expanded && (
        <p className={styles.expansion}>
          Also searched for <strong>{expanded.detected_terms.join(", ")}</strong>
          {expanded.detected_acronyms.length > 0 && <> (from {expanded.detected_acronyms.join(", ")})</>}.
        </p>
      )}

      {showSuggestions && (
        <div className={styles.suggestions}>
          <span className={styles.suggestionsLabel} id={`${hintId}-try`}>
            Try:
          </span>
          <ul className={styles.suggestionList} aria-labelledby={`${hintId}-try`}>
            {SUGGESTED_QUERIES.map((query) => (
              <li key={query}>
                <button
                  type="button"
                  className={styles.suggestion}
                  onClick={() => {
                    setInputVal(query);
                    onSearch(query);
                  }}
                >
                  {query}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
