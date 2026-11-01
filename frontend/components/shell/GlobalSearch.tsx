"use client";

import { lazy, Suspense, useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { useRouter } from "next/navigation";
import { Search } from "lucide-react";
import { IconButton } from "../ui/Button/Button";
import { SearchInput } from "../ui/Field/SearchInput";
import { requestSearchFocus, searchHref } from "../../utils/search";
import styles from "./GlobalSearch.module.css";

const loadSheet = () => import("./SearchSheet");
const SearchSheet = lazy(() => loadSheet().then((module) => ({ default: module.SearchSheet })));

/**
 * The global paper search. It searches nothing itself: it opens the literature search page with
 * the query in the URL (`/?q=…`), so the search runs once, there, and can be bookmarked,
 * shared and reloaded.
 *
 * When the header has room (768px at the default text size) it is a field (Enter submits,
 * Escape clears then leaves, `/` focuses it from anywhere outside a text field); otherwise a
 * button that opens a search sheet with the field and a Search button. After a search, focus
 * goes to the search page's own box, which then holds the query.
 */
export function GlobalSearch() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [sheetOpen, setSheetOpen] = useState(false);
  const inlineField = useRef<HTMLInputElement>(null);
  const sheetField = useRef<HTMLInputElement>(null);

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) {
      (sheetOpen ? sheetField : inlineField).current?.focus();
      return;
    }
    setQuery("");
    setSheetOpen(false);
    inlineField.current?.blur();
    requestSearchFocus(trimmed);
    router.push(searchHref(trimmed));
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key !== "Escape") return;
    if (query) setQuery("");
    else event.currentTarget.blur();
  };

  // "/" focuses the header field (DESIGN_SYSTEM.md §8.2), unless the person is typing.
  useEffect(() => {
    const onSlash = (event: globalThis.KeyboardEvent) => {
      if (event.key !== "/" || event.ctrlKey || event.metaKey || event.altKey || event.defaultPrevented) return;
      const target = event.target instanceof Element ? event.target : null;
      if (target?.closest("input, textarea, select, [contenteditable=''], [contenteditable='true']")) return;
      const field = inlineField.current;
      const form = field?.closest("form");
      // Not displayed below 768px (the sheet button stands in for it there).
      if (!field || !form || window.getComputedStyle(form).display === "none") return;
      event.preventDefault();
      field.focus();
    };
    document.addEventListener("keydown", onSlash);
    return () => document.removeEventListener("keydown", onSlash);
  }, []);

  return (
    <>
      <form role="search" aria-label="Papers" className={styles.inline} onSubmit={submit}>
        <SearchInput
          ref={inlineField}
          label="Search papers"
          hideLabel
          name="q"
          placeholder="Search papers"
          autoComplete="off"
          enterKeyHint="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={onKeyDown}
          onClear={() => {
            setQuery("");
            inlineField.current?.focus();
          }}
          className={styles.field}
        />
      </form>

      <IconButton
        className={styles.sheetButton}
        label="Search papers"
        icon={<Search size={20} aria-hidden="true" />}
        aria-haspopup="dialog"
        aria-expanded={sheetOpen}
        // The sheet's code loads as soon as the button is about to be used.
        onPointerEnter={loadSheet}
        onFocus={loadSheet}
        onClick={() => setSheetOpen(true)}
      />
      {sheetOpen && (
        <Suspense fallback={null}>
          <SearchSheet query={query} setQuery={setQuery} onClose={() => setSheetOpen(false)} onSubmit={submit} fieldRef={sheetField} />
        </Suspense>
      )}
    </>
  );
}
