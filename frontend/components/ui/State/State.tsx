import type { CSSProperties, ReactNode } from "react";
import { AlertCircle, AlertTriangle, CheckCircle2, CloudOff, FileQuestion, Info, Inbox, Lock, SearchX, ServerCrash } from "lucide-react";
import { cx } from "../../../utils/cx";
import { Button } from "../Button/Button";
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
 * says what is loading, so screen readers hear one message, not a list of shapes. Where several
 * load at once (the dashboard's modules), `announce={false}` keeps the label but not the live
 * region, so the page is not read out once per module.
 */
export function SkeletonList({ rows = 3, label, lines = 1, announce = true }: { rows?: number; label: string; lines?: number; announce?: boolean }) {
  return (
    <div aria-busy="true">
      <p role={announce ? "status" : undefined} className="rc-visually-hidden">
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

/* ── Error state ──────────────────────────────────────────────────────────── */

export type ErrorKind = "failed" | "permission" | "not-found" | "invalid" | "unavailable" | "offline" | "unknown";

const ERROR_COPY: Record<ErrorKind, { title: string; description: string; icon: typeof AlertCircle }> = {
  failed: { title: "This could not be loaded", description: "Something went wrong while loading. Try again in a moment.", icon: AlertCircle },
  permission: { title: "You don't have access to this", description: "This page is only available to some accounts.", icon: Lock },
  "not-found": { title: "This could not be found", description: "It may have been removed, or the link may be wrong.", icon: FileQuestion },
  invalid: { title: "That request could not be used", description: "Check what you entered and try again.", icon: AlertTriangle },
  unavailable: { title: "The source is unavailable", description: "An external data source did not respond. The rest of the page still works.", icon: CloudOff },
  offline: { title: "You're offline", description: "Changes will fail until you reconnect.", icon: CloudOff },
  unknown: { title: "Something went wrong", description: "An unexpected error occurred. Try again, and contact support if it keeps happening.", icon: ServerCrash },
};

interface ErrorStateProps {
  kind?: ErrorKind;
  /** Overrides the default title for the kind. */
  title?: ReactNode;
  description?: ReactNode;
  /** Shows a Retry action. */
  onRetry?: () => void;
  retryLabel?: string;
  /** Other recovery actions (sign in, go home…). */
  actions?: ReactNode;
  /** Optional technical detail behind a disclosure; never a stack trace or raw API body. */
  details?: ReactNode;
  bare?: boolean;
  headingLevel?: 1 | 2 | 3 | 4;
  className?: string;
  /** Errors that appear after an action are announced (role="alert"); page states are not. */
  announce?: boolean;
}

/** Plain words: what happened and what to do. DESIGN_SYSTEM.md §8.4, §10. */
export function ErrorState({ kind = "failed", title, description, onRetry, retryLabel = "Try again", actions, details, bare, headingLevel = 3, className, announce }: ErrorStateProps) {
  const copy = ERROR_COPY[kind];
  const Icon = copy.icon;
  const Heading = `h${headingLevel}` as "h1" | "h2" | "h3" | "h4";
  return (
    <div className={cx(styles.state, styles.errorState, bare && styles.bare, className)} role={announce ? "alert" : undefined}>
      <Icon size={20} className={styles.stateIcon} aria-hidden="true" />
      <Heading className={styles.stateTitle}>{title ?? copy.title}</Heading>
      <p className={styles.stateText}>{description ?? copy.description}</p>
      {(onRetry || actions) && (
        <div className={styles.stateActions}>
          {onRetry && (
            <Button variant="secondary" onClick={onRetry}>
              {retryLabel}
            </Button>
          )}
          {actions}
        </div>
      )}
      {details && (
        <details className={styles.details}>
          <summary>Technical details</summary>
          {details}
        </details>
      )}
    </div>
  );
}

/* ── Alert ────────────────────────────────────────────────────────────────── */

const ALERT_ICON = { info: Info, success: CheckCircle2, warning: AlertTriangle, danger: AlertCircle };

interface AlertProps {
  tone?: "info" | "success" | "warning" | "danger";
  title?: ReactNode;
  children?: ReactNode;
  action?: ReactNode;
  /** role="alert" only for errors that appear after an action; static notices stay silent. */
  announce?: boolean;
  className?: string;
}

/** An inline, persistent message in the page flow. */
export function Alert({ tone = "info", title, children, action, announce, className }: AlertProps) {
  const Icon = ALERT_ICON[tone];
  return (
    <div className={cx(styles.alert, styles[tone], className)} role={announce ? "alert" : undefined}>
      <Icon size={16} aria-hidden="true" />
      <div className={styles.alertBody}>
        {title && <strong className={styles.alertTitle}>{title}</strong>}
        {children && <div className={styles.alertText}>{children}</div>}
      </div>
      {action && <div className={styles.alertAction}>{action}</div>}
    </div>
  );
}
