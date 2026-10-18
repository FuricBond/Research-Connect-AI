"use client";

import { useState, type KeyboardEvent } from "react";
import type { RankingMode } from "../../types/discovery";
import { WORK_TYPES, activeFilterCount, type SearchState } from "../../utils/searchState";
import { workTypeLabel } from "../../utils/research";
import { Button } from "../ui/Button/Button";
import { Checkbox, Select, TextInput } from "../ui/Field/Field";
import styles from "./Search.module.css";

interface SearchFiltersProps {
  state: SearchState;
  /** A filter changed: the page records it in the address and searches again (from page 1). */
  onChange: (change: Partial<SearchState>) => void;
  onClear: () => void;
}

const RANKING_LABELS: Record<RankingMode, string> = {
  general: "Balanced (default)",
  research_similarity: "Similar research — favours recent work",
  research_opportunity: "Venue matching — favours publication type and quality",
};

/**
 * A number filter that applies when the person is done typing it — on Enter or on leaving the
 * field — so typing "2018" runs one search, not four. An emptied field removes the filter.
 */
function NumberFilter({ label, value, onCommit, min, max, placeholder }: { label: string; value: number | null; onCommit: (value: number | null) => void; min: number; max: number; placeholder: string }) {
  const [text, setText] = useState(value === null ? "" : String(value));
  const [shown, setShown] = useState(value);
  if (value !== shown) {
    setShown(value);
    setText(value === null ? "" : String(value));
  }
  const commit = () => {
    const trimmed = text.trim();
    if (!trimmed) {
      if (value !== null) onCommit(null);
      return;
    }
    const parsed = Number(trimmed);
    if (!Number.isInteger(parsed) || parsed < min || parsed > max) {
      setText(value === null ? "" : String(value));
      return;
    }
    if (parsed !== value) onCommit(parsed);
  };
  return (
    <TextInput
      label={label}
      type="number"
      inputMode="numeric"
      min={min}
      max={max}
      placeholder={placeholder}
      value={text}
      onChange={(event) => setText(event.target.value)}
      onBlur={commit}
      onKeyDown={(event: KeyboardEvent<HTMLInputElement>) => {
        if (event.key === "Enter") {
          event.preventDefault();
          commit();
        }
      }}
    />
  );
}

/**
 * The search filters (FRONTEND_REDESIGN_PLAN.md §9): publication type, years, citations, open
 * access, and the ranking mode as an advanced control. Shown as a rail beside the results from
 * 1280px and in a sheet below. Every filter is part of the address (utils/searchState.ts).
 */
export function SearchFilters({ state, onChange, onClear }: SearchFiltersProps) {
  const count = activeFilterCount(state);
  return (
    <div className={styles.filters}>
      <Select label="Publication type" value={state.type ?? ""} onChange={(event) => onChange({ type: (event.target.value || null) as SearchState["type"] })}>
        <option value="">All types</option>
        {WORK_TYPES.map((type) => (
          <option key={type} value={type}>
            {workTypeLabel(type)}
          </option>
        ))}
      </Select>
      <fieldset className={styles.years}>
        <legend className={styles.legend}>Published</legend>
        <NumberFilter label="From year" value={state.minYear} min={1800} max={2100} placeholder="e.g. 2018" onCommit={(minYear) => onChange({ minYear })} />
        <NumberFilter label="To year" value={state.maxYear} min={1800} max={2100} placeholder="e.g. 2026" onCommit={(maxYear) => onChange({ maxYear })} />
      </fieldset>
      <NumberFilter label="At least this many citations" value={state.minCitations} min={1} max={1_000_000_000} placeholder="e.g. 10" onCommit={(minCitations) => onChange({ minCitations })} />
      <Checkbox label="Open access only" checked={state.openAccess} onChange={(event) => onChange({ openAccess: event.target.checked })} />
      <details className={styles.advanced} open={state.mode !== "general" || undefined}>
        <summary>Advanced</summary>
        <Select
          label="Ranking"
          hint="Changes how the results are weighted and ordered."
          value={state.mode}
          onChange={(event) => onChange({ mode: event.target.value as RankingMode })}
        >
          {(Object.keys(RANKING_LABELS) as RankingMode[]).map((mode) => (
            <option key={mode} value={mode}>
              {RANKING_LABELS[mode]}
            </option>
          ))}
        </Select>
      </details>
      {count > 0 && (
        <Button variant="ghost" size="sm" onClick={onClear}>
          Clear filters ({count})
        </Button>
      )}
    </div>
  );
}
