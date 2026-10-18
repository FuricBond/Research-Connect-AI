"use client";

import { useState } from "react";
import { useApiResource } from "../../../hooks/useApiResource";
import { fetchAdaptiveSignalsExplanation, fetchResearcherAdaptiveSignals, recomputeAdaptiveSignals } from "../../../services/api";
import type { AdaptiveEvidenceState } from "../../../types/personalization";
import { humanizeEnum } from "../../../utils/date";
import { Button } from "../../ui/Button/Button";
import { Select } from "../../ui/Field/Field";
import { Loaded, Metrics, percent, recompute, signedPercent, when } from "./shared";
import styles from "../Recommendations.module.css";

const STATE: Record<AdaptiveEvidenceState, string> = {
  STRONG: "Strong",
  ESTABLISHED: "Established",
  EMERGING: "Emerging",
  CONFLICT: "Mixed feedback",
  INSUFFICIENT_EVIDENCE: "Not enough evidence",
};

/**
 * Signals learned from activity (Phase 5.4, formerly "Adaptive Behavioral Signals"): each with
 * its evidence for and against, strength, confidence and the server's explanation. They adjust a
 * score by at most 10% and never override a stated preference.
 */
export default function SignalsPart({ profileId }: { profileId: string }) {
  const signals = useApiResource(`technical:signals:${profileId}`, (signal) => fetchResearcherAdaptiveSignals(profileId, undefined, undefined, signal));
  const summary = useApiResource(`technical:signals-summary:${profileId}`, (signal) => fetchAdaptiveSignalsExplanation(profileId, undefined, signal));
  const [state, setState] = useState<AdaptiveEvidenceState | "ALL">("ALL");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");

  const reload = () => {
    signals.retry();
    summary.retry();
  };

  return (
    <>
      <p className={styles.muted}>
        Learned from repeated saves, dismissals and feedback. Stated preferences always come first; these adjust a score by at most 10%.
      </p>
      <Loaded resource={summary} label="Loading the summary of learned signals" failure="The summary of learned signals could not be loaded.">
        {(data) => (
          <>
            <p className={styles.muted}>{data.summary_explanation}</p>
            <Metrics
              label="Learned signals by state"
              items={[
                ["Established", data.established_signals_count],
                ["Emerging", data.emerging_signals_count],
                ["Mixed", data.conflict_signals_count],
                ["Sparse", data.insufficient_signals_count],
              ]}
            />
          </>
        )}
      </Loaded>
      <div className={styles.controls}>
        <Select label="Show" value={state} onChange={(event) => setState(event.target.value as AdaptiveEvidenceState | "ALL")}>
          <option value="ALL">All signals</option>
          {(Object.keys(STATE) as AdaptiveEvidenceState[]).map((value) => (
            <option key={value} value={value}>
              {STATE[value]}
            </option>
          ))}
        </Select>
        <Button
          variant="secondary"
          size="sm"
          loading={busy}
          onClick={async () => {
            setBusy(true);
            await recompute(() => recomputeAdaptiveSignals(profileId), reload, setNotice, "Learned signals recalculated.");
            setBusy(false);
          }}
        >
          Recalculate
        </Button>
      </div>
      <p role="status" className={styles.notice}>
        {notice}
      </p>
      <Loaded resource={signals} label="Loading learned signals" failure="Learned signals could not be loaded.">
        {(data) => {
          const shown = data.items.filter((item) => state === "ALL" || item.evidence_state === state);
          if (shown.length === 0) return <p className={styles.muted}>No learned signals here yet. They appear as you save and give feedback on calls.</p>;
          return (
            <ul className={styles.records} aria-label="Learned signals">
              {shown.map((item) => (
                <li key={item.id} className={styles.record}>
                  <span className={styles.recordHead}>
                    <span>{humanizeEnum(item.dimension)}</span>
                    <span className={styles.recordTitle}>{item.signal_value}</span>
                    <span>· {STATE[item.evidence_state] ?? humanizeEnum(item.evidence_state)}</span>
                  </span>
                  <span>{item.deterministic_explanation}</span>
                  <span className={styles.numbers}>
                    Strength {signedPercent(item.weighted_signal_strength)} · confidence {percent(item.confidence)} · {item.positive_evidence_count} for, {item.negative_evidence_count} against
                    ({item.total_evidence_count} in all) · last {when(item.latest_evidence_timestamp)}
                  </span>
                </li>
              ))}
            </ul>
          );
        }}
      </Loaded>
    </>
  );
}
