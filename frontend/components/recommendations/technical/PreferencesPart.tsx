"use client";

import type { ResearcherPreferenceIntelligenceResponse, ResearcherPreferenceItem } from "../../../types/researcher";
import { humanizeEnum } from "../../../utils/date";
import { preferenceCategoryLabel, preferenceLabel } from "../../../utils/personalization";
import details from "../../research/Details.module.css";
import { Metrics, percent } from "./shared";
import styles from "../Recommendations.module.css";

function Table({ caption, items }: { caption: string; items: ResearcherPreferenceItem[] }) {
  if (items.length === 0) return <p className={styles.muted}>None.</p>;
  return (
    <div className="rc-scroll-x" role="region" aria-label={caption} tabIndex={0}>
      <table className={details.table}>
        <caption className="rc-visually-hidden">{caption}</caption>
        <thead>
          <tr>
            <th scope="col">Preference</th>
            <th scope="col">Strength</th>
            <th scope="col">Confidence</th>
            <th scope="col">Recency</th>
            <th scope="col">State</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id}>
              <td>
                {preferenceCategoryLabel(item.category)}: {item.preference_type === "EXCLUDED" ? `not ${preferenceLabel(item)}` : preferenceLabel(item)}
                {item.provenance_reasons.length > 0 && <span className={details.source}> — {item.provenance_reasons.join("; ")}</span>}
              </td>
              <td>{percent(item.strength)}</td>
              <td>{percent(item.confidence)}</td>
              <td>{percent(item.recency_score)}</td>
              <td>{item.is_active ? "Active" : "Inactive"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * The preference record in full (Phase 5.1, formerly the profile's preference panel): every
 * stated, inferred and suggested preference with its strength, confidence and recency, and the
 * summary the server keeps. It reads the page's own copy, so opening it asks nothing.
 */
export default function PreferencesPart({ preferences }: { preferences: ResearcherPreferenceIntelligenceResponse | null }) {
  if (!preferences) return <p className={styles.muted}>Your preferences are not loaded; they are listed beside the recommendations once they are.</p>;
  const { summary, completeness } = preferences;
  return (
    <>
      <Metrics
        label="Preference summary"
        items={[
          ["Stated", summary.explicit_count],
          ["Inferred", summary.inferred_count],
          ["Suggested from publications", summary.derived_count],
          ["Confidence", humanizeEnum(summary.confidence_level)],
          ["Complete", `${completeness.percentage}%`],
        ]}
      />
      {completeness.missing_dimensions.length > 0 && (
        <p className={styles.muted}>Not stated yet: {completeness.missing_dimensions.map((dimension) => humanizeEnum(dimension).toLowerCase()).join(", ")}.</p>
      )}
      {preferences.conflicts.length > 0 && (
        <div className={styles.group}>
          <h4 className={styles.groupTitle}>Preferences that contradict each other</h4>
          <ul className={styles.plainList}>
            {preferences.conflicts.map((conflict, i) => (
              <li key={i}>
                {conflict.reason}
                {conflict.is_critical ? " (critical)" : ""}
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className={styles.group}>
        <h4 className={styles.groupTitle}>Stated</h4>
        <Table caption="Stated preferences" items={preferences.explicit_preferences} />
      </div>
      <div className={styles.group}>
        <h4 className={styles.groupTitle}>Inferred from your saved calls</h4>
        <Table caption="Inferred preferences" items={preferences.inferred_preferences} />
      </div>
      <div className={styles.group}>
        <h4 className={styles.groupTitle}>Suggested from your publications</h4>
        <p className={styles.muted}>Expertise is not a preference until you add it: follow these from the research topics on your profile.</p>
        <Table caption="Suggested from your publications" items={preferences.derived_candidates} />
      </div>
    </>
  );
}
