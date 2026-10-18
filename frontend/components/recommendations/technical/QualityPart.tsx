"use client";

import { useState } from "react";
import { useApiResource } from "../../../hooks/useApiResource";
import { fetchPersonalizationQuality, recomputePersonalizationQuality } from "../../../services/api";
import type { QualityEvaluationState } from "../../../types/personalization";
import { humanizeEnum } from "../../../utils/date";
import { Button } from "../../ui/Button/Button";
import { Select } from "../../ui/Field/Field";
import { Loaded, Metrics, percent, recompute, signedPercent } from "./shared";
import styles from "../Recommendations.module.css";

const STATE: Record<QualityEvaluationState, string> = {
  POSITIVE: "Better than without it",
  NEGATIVE: "Worse than without it",
  MIXED: "Mixed outcomes",
  STABLE: "Stable",
  EARLY_SIGNAL: "Early signal",
  EVALUATING: "Being evaluated",
  INSUFFICIENT_DATA: "Not enough evidence",
};

/**
 * Personalization quality (Phase 5.7, formerly "Personalization Quality & Contextual
 * Adaptation"): the observed lift against a baseline, engagement, outcomes, diversity and
 * novelty, and the same measures broken down by context (at most ±0.03 of adaptation).
 */
export default function QualityPart({ profileId }: { profileId: string }) {
  const quality = useApiResource(`technical:quality:${profileId}`, (signal) => fetchPersonalizationQuality(profileId, undefined, signal));
  const [dimension, setDimension] = useState("ALL");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");

  return (
    <>
      <div className={styles.controls}>
        <Button
          variant="secondary"
          size="sm"
          loading={busy}
          onClick={async () => {
            setBusy(true);
            await recompute(() => recomputePersonalizationQuality(profileId), quality.retry, setNotice, "Quality evaluated again.");
            setBusy(false);
          }}
        >
          Evaluate again
        </Button>
      </div>
      <p role="status" className={styles.notice}>
        {notice}
      </p>
      <Loaded resource={quality} label="Loading personalization quality" failure="Personalization quality could not be loaded.">
        {(data) => {
          const evaluation = data.evaluation;
          const contexts = data.context_summaries ?? [];
          const dimensions = Array.from(new Set(contexts.map((context) => context.context_dimension)));
          const shown = dimension === "ALL" ? contexts : contexts.filter((context) => context.context_dimension === dimension);
          if (!evaluation) return <p className={styles.muted}>No quality evaluation is recorded yet.</p>;
          return (
            <>
              <Metrics
                label="Personalization quality"
                items={[
                  ["Observed lift", signedPercent(evaluation.observed_personalization_lift, 1)],
                  ["Engagement", `${percent(evaluation.observed_engagement_rate, 1)} (${evaluation.attributed_interactions_count} of ${evaluation.recommendations_evaluated_count})`],
                  ["Positive / negative", `${evaluation.positive_outcomes_count} / ${evaluation.negative_outcomes_count} (${percent(evaluation.observed_positive_rate)} positive)`],
                  ["Diversity / novelty", `${percent(evaluation.diversity_score)} / ${percent(evaluation.novelty_rate)}`],
                ]}
              />
              <p className={styles.muted}>
                {STATE[evaluation.evaluation_state] ?? humanizeEnum(evaluation.evaluation_state)}. {evaluation.deterministic_explanation}
              </p>
              <p className={styles.muted}>Order: stated preferences, learned signals, calibration, quality evaluation, then context (±0.03).</p>
              <div className={styles.group}>
                <h4 className={styles.groupTitle}>By context</h4>
                {dimensions.length > 0 && (
                  <div className={styles.controls}>
                    <Select label="Context" value={dimension} onChange={(event) => setDimension(event.target.value)}>
                      <option value="ALL">All contexts</option>
                      {dimensions.map((value) => (
                        <option key={value} value={value}>
                          {humanizeEnum(value)}
                        </option>
                      ))}
                    </Select>
                  </div>
                )}
                {shown.length === 0 ? (
                  <p className={styles.muted}>No breakdown by context yet.</p>
                ) : (
                  <ul className={styles.records} aria-label="Quality by context">
                    {shown.map((context, i) => (
                      <li key={`${context.context_dimension}-${context.context_value}-${i}`} className={styles.record}>
                        <span className={styles.recordHead}>
                          <span>{humanizeEnum(context.context_dimension)}</span>
                          <span className={styles.recordTitle}>{context.context_value}</span>
                          <span>· {STATE[context.evaluation_state] ?? humanizeEnum(context.evaluation_state)}</span>
                        </span>
                        <span>{context.explanation}</span>
                        <span className={styles.numbers}>
                          Lift {signedPercent(context.observed_lift, 1)} · sample {context.sample_size}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </>
          );
        }}
      </Loaded>
    </>
  );
}
