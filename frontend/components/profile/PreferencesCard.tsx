"use client";

import Link from "next/link";
import type { ApiResource } from "../../hooks/useApiResource";
import type { ResearcherPreferenceIntelligenceResponse } from "../../types/researcher";
import { humanizeEnum } from "../../utils/date";
import { SkeletonList } from "../ui/State/State";
import styles from "./Profile.module.css";

/**
 * The way to preferences (plan §12): how many the researcher stated and how many were inferred
 * from their saved calls, then the two places to act — the preference editor and the page that
 * shows what shapes their recommendations.
 */
export function PreferencesCard({ preferences }: { preferences: ApiResource<ResearcherPreferenceIntelligenceResponse> }) {
  const data = preferences.data;
  return (
    <section className={styles.card} aria-labelledby="preferences-heading">
      <h2 id="preferences-heading" className={styles.cardTitle}>
        Research preferences
      </h2>
      <p className={styles.muted}>The calls, attendance, places and timing you are looking for. They adjust your recommendations; relevance to your research stays first.</p>
      {preferences.status === "loading" || preferences.status === "idle" ? (
        <SkeletonList rows={1} label="Loading your preferences" announce={false} />
      ) : data ? (
        <dl className={styles.facts}>
          <div>
            <dt>Stated</dt>
            <dd>{(data.explicit_preferences ?? []).filter((item) => item.is_active).length}</dd>
          </div>
          <div>
            <dt>From your saved calls</dt>
            <dd>{(data.inferred_preferences ?? []).filter((item) => item.is_active).length}</dd>
          </div>
          <div>
            <dt>Complete</dt>
            <dd>{data.completeness ? `${data.completeness.percentage}%` : "Not available"}</dd>
          </div>
        </dl>
      ) : (
        <p className={styles.muted}>Your preferences could not be loaded.</p>
      )}
      {data && (data.completeness?.missing_dimensions ?? []).length > 0 && (
        <p className={styles.muted}>Not stated yet: {data.completeness.missing_dimensions.map((dimension) => humanizeEnum(dimension).toLowerCase()).join(", ")}.</p>
      )}
      {data && (data.conflicts ?? []).length > 0 && (
        <div className={styles.completeness}>
          <h3 className={styles.subTitle}>Preferences that contradict each other</h3>
          <ul className={styles.plainList}>
            {data.conflicts.map((conflict, i) => (
              <li key={i}>{conflict.reason}</li>
            ))}
          </ul>
        </div>
      )}
      <div className={styles.links}>
        <Link href="/researcher/preferences" className={styles.link}>
          Edit research preferences
        </Link>
        <Link href="/recommendations" className={styles.link}>
          See what shapes your recommendations
        </Link>
      </div>
    </section>
  );
}
