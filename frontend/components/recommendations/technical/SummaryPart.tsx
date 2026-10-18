"use client";

import Link from "next/link";
import { useApiResource } from "../../../hooks/useApiResource";
import { fetchPersonalizationSummary } from "../../../services/api";
import type { LearnedSignalItem } from "../../../types/researcher";
import { Alert } from "../../ui/State/State";
import { Loaded, Metrics, percent } from "./shared";
import styles from "../Recommendations.module.css";

function Learned({ title, items }: { title: string; items: LearnedSignalItem[] }) {
  if (items.length === 0) return null;
  return (
    <div className={styles.group}>
      <h4 className={styles.groupTitle}>{title}</h4>
      <ul className={styles.records}>
        {items.map((item, i) => (
          <li key={i} className={styles.record}>
            <span className={styles.recordHead}>
              <span className={styles.recordTitle}>{item.value}</span>
              <span>{item.strength === "Negative" ? "Counts against" : `Counts for · ${item.strength}`}</span>
            </span>
            <span className={styles.numbers}>Confidence {percent(item.confidence)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * The personalization summary (Phase 3.9, formerly "Your Research Personalization" on the
 * profile): how confident the personalization is, the counts behind it, the stated drivers and
 * what was learned from activity, including demotions from dismissals.
 */
export default function SummaryPart({ profileId }: { profileId: string }) {
  const summary = useApiResource(`technical:summary:${profileId}`, (signal) => fetchPersonalizationSummary(profileId, undefined, signal));
  return (
    <Loaded resource={summary} label="Loading the personalization summary" failure="The personalization summary could not be loaded.">
      {(data) => (
        <>
          <p className={styles.muted}>
            Confidence: {data.personalization_confidence} ({percent(data.confidence_score)})
          </p>
          <Metrics
            label="Personalization summary"
            items={[
              ["Research interests", data.active_interests_count],
              ["Strong expertise", data.strong_expertise_count],
              ["Stated preferences", data.explicit_preferences_count],
              ["Learned signals", `${data.behavioral_signals_count} from ${data.total_feedback_count} action${data.total_feedback_count === 1 ? "" : "s"}`],
            ]}
          />
          {data.is_cold_start && (
            <Alert>
              Recommendations follow relevance for now: there are not yet enough interests or preferences to adjust them.{" "}
              <Link href="/researcher/preferences">Add research preferences</Link>.
            </Alert>
          )}
          {!data.is_cold_start && !data.has_feedback && (
            <Alert>Nothing has been learned from activity yet: save calls or mark recommendations Helpful or Not relevant.</Alert>
          )}
          <div className={styles.group}>
            <h4 className={styles.groupTitle}>Stated drivers</h4>
            {data.top_positive_signals.length > 0 ? (
              <ul className={styles.plainList}>
                {data.top_positive_signals.map((signal, i) => (
                  <li key={i}>{signal}</li>
                ))}
              </ul>
            ) : (
              <p className={styles.muted}>No call type, attendance or career-stage preferences stated yet.</p>
            )}
          </div>
          {data.behavioral_signals_count > 0 ? (
            <>
              <Learned title="Learned topics and themes" items={data.learned_topics} />
              <Learned title="Learned call types" items={data.learned_opportunity_types} />
              <Learned title="Learned attendance" items={data.learned_delivery_modes} />
              {data.top_negative_signals.length > 0 && (
                <div className={styles.group}>
                  <h4 className={styles.groupTitle}>Learned from dismissals (counts against)</h4>
                  <ul className={styles.plainList}>
                    {data.top_negative_signals.map((signal, i) => (
                      <li key={i}>{signal}</li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          ) : (
            <p className={styles.muted}>Nothing learned from activity yet.</p>
          )}
        </>
      )}
    </Loaded>
  );
}
