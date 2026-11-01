"use client";

import type { FormEvent, RefObject } from "react";
import { Button } from "../ui/Button/Button";
import { Dialog } from "../ui/Dialog/Dialog";
import { SearchInput } from "../ui/Field/SearchInput";
import styles from "./GlobalSearch.module.css";

/** The search on narrow screens: a sheet with the field and a Search button. Loaded when opened. */
export function SearchSheet({
  query,
  setQuery,
  onClose,
  onSubmit,
  fieldRef,
}: {
  query: string;
  setQuery: (value: string) => void;
  onClose: () => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  fieldRef: RefObject<HTMLInputElement | null>;
}) {
  return (
    <Dialog
      open
      onClose={onClose}
      title="Search papers"
      initialFocusRef={fieldRef}
      // The sheet holds only a field and a button: no extra Tab stop for its body.
      focusableBody={false}
      className={styles.sheet}
    >
      <form role="search" aria-label="Papers" className={styles.sheetForm} onSubmit={onSubmit}>
        <SearchInput
          ref={fieldRef}
          label="Search papers"
          hideLabel
          name="q"
          placeholder="Topic, method or author"
          autoComplete="off"
          enterKeyHint="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onClear={() => {
            setQuery("");
            fieldRef.current?.focus();
          }}
        />
        <Button type="submit" variant="primary" fullWidth>
          Search
        </Button>
      </form>
    </Dialog>
  );
}
