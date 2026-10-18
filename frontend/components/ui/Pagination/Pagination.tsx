"use client";

import { useId } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "../Button/Button";
import styles from "./Pagination.module.css";

interface PaginationProps {
  /** The current page, from 1. */
  page: number;
  /** Every item across all pages. */
  total: number;
  pageSize: number;
  onPage: (page: number) => void;
  /** What the items are, plural: "results", "calls". */
  noun?: string;
  /** Offer these page sizes (a native select) when given. */
  pageSizes?: readonly number[];
  onPageSize?: (size: number) => void;
  /** Names the navigation landmark when a page has more than one list ("Search results pages"). */
  label?: string;
}

/**
 * "Showing 21–40 of 312 results", Previous page / Next page and "Page 2 of 16". DESIGN_SYSTEM.md
 * §8.3. Stable positions (no infinite scroll), so results can be compared. The buttons are never
 * disabled while a page loads: a newer page replaces the request for the older one.
 */
export function Pagination({ page, total, pageSize, onPage, noun = "results", pageSizes, onPageSize, label = "Pages" }: PaginationProps) {
  const sizeId = useId();
  if (total <= 0) return null;
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  const current = Math.min(Math.max(1, page), pageCount);
  const first = (current - 1) * pageSize + 1;
  const last = Math.min(current * pageSize, total);

  return (
    <nav className={styles.pagination} aria-label={label}>
      <p className={styles.summary}>
        Showing {first.toLocaleString("en")}–{last.toLocaleString("en")} of {total.toLocaleString("en")} {noun}
      </p>
      <div className={styles.controls}>
        <Button
          size="sm"
          onClick={() => onPage(current - 1)}
          disabled={current <= 1}
          leadingIcon={<ChevronLeft size={16} aria-hidden="true" />}
          aria-label="Previous page"
        >
          Previous
        </Button>
        <span className={styles.position}>
          Page {current} of {pageCount}
        </span>
        <Button
          size="sm"
          onClick={() => onPage(current + 1)}
          disabled={current >= pageCount}
          trailingIcon={<ChevronRight size={16} aria-hidden="true" />}
          aria-label="Next page"
        >
          Next
        </Button>
      </div>
      {pageSizes && onPageSize && (
        <div className={styles.size}>
          <label htmlFor={sizeId} className={styles.sizeLabel}>
            Per page
          </label>
          <select id={sizeId} className={styles.select} value={pageSize} onChange={(event) => onPageSize(Number(event.target.value))}>
            {pageSizes.map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
        </div>
      )}
    </nav>
  );
}
