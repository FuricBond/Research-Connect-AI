import type { CSSProperties } from "react";
import { cx } from "../../../utils/cx";
import styles from "./State.module.css";

/* ── Skeleton ─────────────────────────────────────────────────────────────── */

/** One placeholder block. Size it like the content it stands for. */
export function Skeleton({ width, height, className, style }: { width?: string; height?: string; className?: string; style?: CSSProperties }) {
  return <span className={cx(styles.skeleton, className)} style={{ width, height, ...style }} aria-hidden="true" />;
}

/** Placeholder lines for a title and text; `lines` text lines of decreasing width. */
export function SkeletonText({ lines = 2, title = false }: { lines?: number; title?: boolean }) {
  return (
    <span className={styles.skeletonGroup} aria-hidden="true">
      {title && <span className={cx(styles.skeleton, styles.skeletonTitle)} />}
      {Array.from({ length: lines }, (_, i) => (
        <span key={i} className={cx(styles.skeleton, styles.skeletonText)} style={{ width: i === lines - 1 ? "60%" : "100%" }} />
      ))}
    </span>
  );
}

/**
 * Loading placeholder for a list of rows. The region is busy and one visually hidden status
 * says what is loading, so screen readers hear one message, not a list of shapes.
 */
export function SkeletonList({ rows = 3, label, lines = 1 }: { rows?: number; label: string; lines?: number }) {
  return (
    <div aria-busy="true">
      <p role="status" className="rc-visually-hidden">
        {label}
      </p>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className={styles.skeletonRow}>
          <SkeletonText title lines={lines} />
        </div>
      ))}
    </div>
  );
}
