"use client";

import type { ReactNode } from "react";
import type { ApiResource } from "../../../hooks/useApiResource";
import type { FeedbackType } from "../../../types/researcher";
import { Button } from "../../ui/Button/Button";
import { SkeletonList } from "../../ui/State/State";
import styles from "../Recommendations.module.css";

/** Recommendation feedback in the words the page uses for it. */
export const FEEDBACK_LABEL: Record<FeedbackType, string> = {
  VIEW: "Viewed",
  SAVE: "Saved",
  DISMISS: "Dismissed",
  INTERESTED: "Helpful",
  NOT_INTERESTED: "Not relevant",
  APPLY: "Applied",
};

/** A number as a percentage with the precision the diagnostics used before P6. */
export const percent = (value: number | null | undefined, digits = 0) =>
  typeof value === "number" && Number.isFinite(value) ? `${(value * 100).toFixed(digits)}%` : "Not available";

export const signedPercent = (value: number, digits = 0) => `${value > 0 ? "+" : value < 0 ? "−" : ""}${Math.abs(value * 100).toFixed(digits)}%`;

export const decimal = (value: number | null | undefined, digits = 3) =>
  typeof value === "number" && Number.isFinite(value) ? value.toFixed(digits) : "Not available";

export const signedDecimal = (value: number, digits = 3) => `${value > 0 ? "+" : value < 0 ? "−" : ""}${Math.abs(value).toFixed(digits)}`;

export const when = (iso: string | null | undefined) => {
  if (!iso) return "Not recorded";
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "Not recorded" : date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
};

/** Headline numbers: a definition list laid out as tiles. */
export function Metrics({ items, label }: { items: [term: string, value: ReactNode][]; label: string }) {
  return (
    <dl className={styles.metrics} aria-label={label}>
      {items.map(([term, value]) => (
        <div key={term} className={styles.metric}>
          <dt>{term}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

/** What a part shows while it loads and when it fails; the content once it is there. */
export function Loaded<T>({ resource, label, failure, children }: { resource: ApiResource<T>; label: string; failure: string; children: (data: T) => ReactNode }) {
  if (resource.status === "loading" || resource.status === "idle") return <SkeletonList rows={3} label={label} announce={false} />;
  if (resource.status === "error" || resource.data === undefined) {
    return (
      <div className={styles.group}>
        <p className={styles.muted}>{resource.error?.kind === "not-found" ? "There is nothing recorded here yet." : failure}</p>
        {resource.error?.kind !== "not-found" && (
          <div>
            <Button size="sm" variant="secondary" onClick={resource.retry}>
              Try again
            </Button>
          </div>
        )}
      </div>
    );
  }
  return <>{children(resource.data)}</>;
}

/** A recompute action: runs, then reloads what it changed; a failure says so in words. */
export async function recompute(run: () => Promise<unknown>, reload: () => void, setNotice: (text: string) => void, done: string) {
  try {
    await run();
    setNotice(done);
    reload();
  } catch {
    setNotice("That could not be recalculated. Try again.");
  }
}
