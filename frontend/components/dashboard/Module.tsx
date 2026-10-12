"use client";

import type { ReactNode } from "react";
import type { ApiResource } from "../../hooks/useApiResource";
import { cx } from "../../utils/cx";
import { Button } from "../ui/Button/Button";
import { Card } from "../ui/Card/Card";
import { SectionHeader } from "../ui/PageHeader/PageHeader";
import { Alert, SkeletonList } from "../ui/State/State";
import styles from "./Dashboard.module.css";

const RESERVE = {
  attention: styles.reserveAttention,
  list: styles.reserveList,
  timeline: styles.reserveTimeline,
  counts: styles.reserveCounts,
};

/**
 * P4 — one dashboard module: a section (its h2 names it) with one card. `reserve` is the height
 * the card keeps from its first paint (a typical answer's), so a module that answers with fewer
 * items, nothing, or an error does not pull the modules below it up (Dashboard.module.css).
 */
export function DashboardModule({
  id,
  title,
  action,
  reserve,
  children,
}: {
  id: string;
  title: ReactNode;
  /** A link to the full page, beside the title. */
  action?: ReactNode;
  reserve: keyof typeof RESERVE;
  children: ReactNode;
}) {
  return (
    <section aria-labelledby={id} className={styles.module}>
      <SectionHeader id={id} title={title} action={action} className={styles.moduleHeader} />
      <Card className={cx(styles.moduleBody, RESERVE[reserve])}>{children}</Card>
    </section>
  );
}

/** A module's waiting state: placeholder rows, busy, named but not announced (see SkeletonList). */
export function ModuleLoading({ label, rows = 3 }: { label: string; rows?: number }) {
  return <SkeletonList rows={rows} label={label} announce={false} />;
}

/**
 * A module that could not load: plain words and Try again. Silent on the first load (a page
 * state); announced when a retry fails too (the answer to an action).
 */
export function ModuleError({ message, resource }: { message: ReactNode; resource: Pick<ApiResource<unknown>, "retry" | "retries"> }) {
  return (
    <Alert
      tone="danger"
      announce={resource.retries > 0}
      action={
        <Button size="sm" onClick={resource.retry}>
          Try again
        </Button>
      }
    >
      {message}
    </Alert>
  );
}

/**
 * Renders one resource's state: loading (also while it waits for another request), error, empty
 * (`empty`, when given) or the data.
 */
export function Loaded<T>({
  resource,
  loading,
  rows,
  failure,
  empty,
  children,
}: {
  resource: ApiResource<T>;
  /** What is loading, for screen readers: "Loading your tracked calls". */
  loading: string;
  rows?: number;
  /** "Your tracked calls could not be loaded." */
  failure: ReactNode;
  empty?: ReactNode;
  children: (data: T) => ReactNode;
}) {
  if (resource.status === "idle" || resource.status === "loading") return <ModuleLoading label={loading} rows={rows} />;
  if (resource.status === "error") return <ModuleError message={failure} resource={resource} />;
  if (resource.status === "empty" && empty !== undefined) return <>{empty}</>;
  return <>{children(resource.data as T)}</>;
}
