"use client";

import { useState } from "react";
import { useApiResource } from "../../../hooks/useApiResource";
import { fetchResearcherCalibrations, recomputeCalibrations } from "../../../services/api";
import type { CalibrationState } from "../../../types/personalization";
import { humanizeEnum } from "../../../utils/date";
import { Button } from "../../ui/Button/Button";
import { Select } from "../../ui/Field/Field";
import { Loaded, Metrics, percent, recompute, signedDecimal } from "./shared";
import styles from "../Recommendations.module.css";

const STATE: Record<CalibrationState, string> = {
  STABLE: "Stable",
  CALIBRATING: "Calibrating",
  EARLY_SIGNAL: "Early signal",
  CONFLICTED: "Conflicting feedback",
  INSUFFICIENT_DATA: "Not enough evidence",
};

/**
 * Calibration from feedback (Phase 5.6, formerly "Personalization Calibration & Feedback Loop"):
 * how recommendations did against later feedback, and the small modifier (at most ±0.05) each
 * learned signal gets for it.
 */
export default function CalibrationPart({ profileId }: { profileId: string }) {
  const calibration = useApiResource(`technical:calibration:${profileId}`, (signal) => fetchResearcherCalibrations(profileId, undefined, undefined, signal));
  const [state, setState] = useState<CalibrationState | "ALL">("ALL");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");

  return (
    <>
      <p className={styles.muted}>Order of precedence: stated preferences, then learned signals (±0.10), then calibration (±0.05).</p>
      <div className={styles.controls}>
        <Select label="Show" value={state} onChange={(event) => setState(event.target.value as CalibrationState | "ALL")}>
          <option value="ALL">All records</option>
          {(Object.keys(STATE) as CalibrationState[]).map((value) => (
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
            await recompute(() => recomputeCalibrations(profileId), calibration.retry, setNotice, "Calibration recalculated.");
            setBusy(false);
          }}
        >
          Recalculate
        </Button>
      </div>
      <p role="status" className={styles.notice}>
        {notice}
      </p>
      <Loaded resource={calibration} label="Loading calibration" failure="Calibration could not be loaded.">
        {(data) => {
          const shown = data.items.filter((item) => state === "ALL" || item.calibration_state === state);
          return (
            <>
              <Metrics
                label="Calibration"
                items={[
                  ["Signals tracked", data.total_count],
                  ["Calibrated", data.calibrated_signals_count],
                  ["Average confidence", percent(data.average_confidence)],
                  ["Stable or calibrating", (data.state_counts?.STABLE ?? 0) + (data.state_counts?.CALIBRATING ?? 0)],
                ]}
              />
              {shown.length === 0 ? (
                <p className={styles.muted}>No calibration records here. As you save, apply to or dismiss recommended calls, outcomes are attributed and calibrated.</p>
              ) : (
                <ul className={styles.records} aria-label="Calibration records">
                  {shown.map((item) => (
                    <li key={item.id} className={styles.record}>
                      <span className={styles.recordHead}>
                        <span>{humanizeEnum(item.dimension)}</span>
                        <span className={styles.recordTitle}>{item.signal_value}</span>
                        <span>· {STATE[item.calibration_state] ?? humanizeEnum(item.calibration_state)}</span>
                        <span>· modifier {item.net_calibration_modifier === 0 ? "0.000 (neutral)" : signedDecimal(item.net_calibration_modifier)}</span>
                      </span>
                      <span>{item.deterministic_explanation}</span>
                      <span className={styles.numbers}>
                        Recommendations influenced {item.recommendations_influenced_count} · positive feedback {item.positive_outcome_count} · negative feedback{" "}
                        {item.negative_outcome_count} · confidence {percent(item.calibration_confidence)}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </>
          );
        }}
      </Loaded>
    </>
  );
}
