import type { CSSProperties, ReactNode } from "react";
import { CheckCircle2, Inbox, SearchX } from "lucide-react";
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

/* ── Empty state ──────────────────────────────────────────────────────────── */

interface EmptyStateProps {
  /** What is empty, in plain words: "No tracked calls due in the next 30 days". */
  title: ReactNode;
  /** Why it is empty, or what fills it. */
  description?: ReactNode;
  /** The next step: one primary action at most. */
  actions?: ReactNode;
  /** first-use (nothing yet), no-results (filters), done (all caught up). */
  variant?: "first-use" | "no-results" | "done";
  /** Inside another surface: no border of its own. */
  bare?: boolean;
  headingLevel?: 1 | 2 | 3 | 4;
  /** Id of the heading, so a surrounding region can be labelled by it. */
  headingId?: string;
  className?: string;
}

const EMPTY_ICON = { "first-use": Inbox, "no-results": SearchX, done: CheckCircle2 };

/** Answers: what is empty, why, and what to do next. DESIGN_SYSTEM.md §8.4. */
export function EmptyState({ title, description, actions, variant = "first-use", bare, headingLevel = 3, headingId, className }: EmptyStateProps) {
  const Icon = EMPTY_ICON[variant];
  const Heading = `h${headingLevel}` as "h1" | "h2" | "h3" | "h4";
  return (
    <div className={cx(styles.state, bare && styles.bare, className)}>
      <Icon size={20} className={styles.stateIcon} aria-hidden="true" />
      <Heading id={headingId} className={styles.stateTitle}>
        {title}
      </Heading>
      {description && <p className={styles.stateText}>{description}</p>}
      {actions && <div className={styles.stateActions}>{actions}</div>}
    </div>
  );
}
