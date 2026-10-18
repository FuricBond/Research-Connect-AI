"use client";

import { useState } from "react";
import { useApiResource } from "../../../hooks/useApiResource";
import { getUnifiedResearchIntelligence } from "../../../services/api";
import { humanizeEnum } from "../../../utils/date";
import { Select } from "../../ui/Field/Field";
import { Alert } from "../../ui/State/State";
import { Loaded, Metrics, percent } from "./shared";
import styles from "../Recommendations.module.css";

const IDENTITY: Record<string, string> = {
  CANONICAL_RESOLVED: "Matched to a scholarly record",
  SELF_DECLARED_ONLY: "Self-declared only",
  COLD_START: "Not enough to go on yet",
};

const SIGNAL_TYPES = ["PROFILE_ATTRIBUTE", "SCHOLARLY_EXPERTISE", "EXPLICIT_PREFERENCE", "INFERRED_PREFERENCE"];

/**
 * The researcher context the recommendations are built on (Phase 4.7, formerly the top of the
 * profile's Personalization section): how the identity was resolved, the headline counts and
 * every signal with its type, source, strength and confidence.
 */
export default function ContextPart({ profileId }: { profileId: string }) {
  const context = useApiResource(`technical:context:${profileId}`, (signal) => getUnifiedResearchIntelligence(profileId, undefined, signal));
  const [type, setType] = useState("ALL");

  return (
    <Loaded resource={context} label="Loading your research context" failure="Your research context could not be loaded.">
      {(data) => {
        const signals = type === "ALL" ? data.signals : data.signals.filter((signal) => signal.signal_type === type);
        return (
          <>
            <p className={styles.muted}>
              Identity: {data.is_identity_ambiguous ? "More than one scholarly record could be yours" : (IDENTITY[data.identity_status] ?? humanizeEnum(data.identity_status))}
            </p>
            {data.is_identity_ambiguous && (
              <Alert tone="warning">More than one scholarly record matches your name, so only verified and stated signals are used.</Alert>
            )}
            {data.is_cold_start && <Alert>No research topics or feedback are recorded yet, so recommendations follow relevance and are not held back.</Alert>}
            <Metrics
              label="Research context"
              items={[
                ["Profile completeness", percent(data.completeness_score)],
                ["Research topics", data.active_interests_count],
                ["Preferences", `${data.explicit_preferences_count} stated · ${data.inferred_preferences_count} inferred`],
                ["Signals", data.signals.length],
              ]}
            />
            {data.signals.length > 0 && (
              <>
                <div className={styles.controls}>
                  <Select label="Show signals" value={type} onChange={(event) => setType(event.target.value)}>
                    <option value="ALL">All</option>
                    {SIGNAL_TYPES.map((value) => (
                      <option key={value} value={value}>
                        {humanizeEnum(value)}
                      </option>
                    ))}
                  </Select>
                </div>
                {signals.length === 0 ? (
                  <p className={styles.muted}>No signals of this type.</p>
                ) : (
                  <ul className={styles.records} aria-label="Signals behind your recommendations">
                    {signals.map((signal, i) => (
                      <li key={signal.signal_id || i} className={styles.record}>
                        <span className={styles.recordHead}>
                          <span className={styles.recordTitle}>{signal.evidence || humanizeEnum(signal.signal_type)}</span>
                          <span>{humanizeEnum(signal.signal_type)}</span>
                          <span>· {humanizeEnum(signal.source)}</span>
                          {!signal.is_explicit && <span>· Inferred</span>}
                        </span>
                        <span className={styles.numbers}>
                          Strength {percent(signal.strength)} · confidence {percent(signal.confidence)}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </>
            )}
          </>
        );
      }}
    </Loaded>
  );
}
