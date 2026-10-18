"use client";

import { useState } from "react";
import { useApiResource } from "../../../hooks/useApiResource";
import { fetchGovernanceEvents, fetchPersonalizationDrift, fetchPersonalizationHealth, recomputePersonalizationHealth } from "../../../services/api";
import type { SignalDriftItem } from "../../../types/personalization";
import { humanizeEnum } from "../../../utils/date";
import { Fact } from "../../research/RiskDetails";
import { Button } from "../../ui/Button/Button";
import { Select } from "../../ui/Field/Field";
import details from "../../research/Details.module.css";
import { Loaded, Metrics, decimal, recompute, signedDecimal, when } from "./shared";
import styles from "../Recommendations.module.css";

type DriftFilter = "ALL" | "DRIFTING" | "STALE" | "STABLE";

const ADAPTATION_NOTE: Record<string, string> = {
  SUSPENDED: "Modifiers are neutral (0.0); the core ranking stands.",
  BOUNDED: "Damped by half so recent noise is not over-fitted.",
};

function drifts(item: SignalDriftItem, filter: DriftFilter): boolean {
  if (filter === "DRIFTING") return item.drift_type !== "STABLE" && item.drift_type !== "UNKNOWN";
  if (filter === "STALE") return item.is_stale;
  if (filter === "STABLE") return item.drift_type === "STABLE" && !item.is_stale;
  return true;
}

/**
 * Health and drift (Phase 5.8, formerly "Personalization Governance & Drift Safety"): the
 * overall health, the gate that decides how far adaptation may go, the eight health measures,
 * each signal's drift between the historical and the recent window, and the audit trail.
 * Stated preferences and exclusions are never overridden by drift.
 */
export default function HealthPart({ profileId }: { profileId: string }) {
  const health = useApiResource(`technical:health:${profileId}`, (signal) => fetchPersonalizationHealth(profileId, undefined, signal));
  const drift = useApiResource(`technical:drift:${profileId}`, (signal) => fetchPersonalizationDrift(profileId, undefined, signal));
  const events = useApiResource(`technical:governance-events:${profileId}`, (signal) => fetchGovernanceEvents(profileId, 10, 0, undefined, signal));
  const [filter, setFilter] = useState<DriftFilter>("ALL");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");

  const reload = () => {
    health.retry();
    drift.retry();
    events.retry();
  };

  return (
    <>
      <div className={styles.controls}>
        <Button
          variant="secondary"
          size="sm"
          loading={busy}
          onClick={async () => {
            setBusy(true);
            await recompute(() => recomputePersonalizationHealth(profileId), reload, setNotice, "Health evaluated again.");
            setBusy(false);
          }}
        >
          Evaluate again
        </Button>
      </div>
      <p role="status" className={styles.notice}>
        {notice}
      </p>
      <Loaded resource={health} label="Loading personalization health" failure="Personalization health could not be loaded.">
        {(data) => (
          <>
            <Metrics
              label="Personalization health"
              items={[
                ["Health", humanizeEnum(data.overall_health_state)],
                ["Gate", humanizeEnum(data.governance_state)],
                ["Adaptation", `${humanizeEnum(data.adaptation_state)} (${data.drifting_signals_count} drifting, ${data.stale_signals_count} stale)`],
              ]}
            />
            <p className={styles.muted}>{data.health_summary}</p>
            <p className={styles.muted}>{data.governance_explanation}</p>
            <p className={styles.muted}>{ADAPTATION_NOTE[data.adaptation_state] ?? "Adaptation to context is active, within its bounds."}</p>
            {data.evaluation && (
              <div className={styles.group}>
                <h4 className={styles.groupTitle}>Health measures</h4>
                <dl className={details.facts}>
                  <Fact term="Signal freshness" value={humanizeEnum(data.evaluation.signal_freshness)} />
                  <Fact term="Evidence sufficiency" value={humanizeEnum(data.evaluation.evidence_sufficiency)} />
                  <Fact term="Quality stability" value={humanizeEnum(data.evaluation.quality_stability)} />
                  <Fact term="Context stability" value={humanizeEnum(data.evaluation.context_stability)} />
                  <Fact term="Preference alignment" value={humanizeEnum(data.evaluation.preference_alignment)} />
                  <Fact term="Recommendation diversity" value={humanizeEnum(data.evaluation.recommendation_diversity)} />
                  <Fact term="Drift" value={data.evaluation.drifting_signals_count > 0 ? "Drift detected" : "Stable"} />
                  <Fact term="Windows (historical / recent)" value={`${data.evaluation.historical_window_days} days / ${data.evaluation.recent_window_days} days`} />
                </dl>
              </div>
            )}
          </>
        )}
      </Loaded>

      <div className={styles.group}>
        <h4 className={styles.groupTitle}>Drift by signal</h4>
        <Loaded resource={drift} label="Loading drift by signal" failure="Drift by signal could not be loaded.">
          {(data) => {
            const all = [...(data.drifting_signals ?? []), ...(data.stale_signals ?? []), ...(data.stable_signals ?? [])];
            const shown = all.filter((item) => drifts(item, filter));
            return (
              <>
                <div className={styles.controls}>
                  <Select label={`Show (${all.length} signals)`} value={filter} onChange={(event) => setFilter(event.target.value as DriftFilter)}>
                    <option value="ALL">All</option>
                    <option value="DRIFTING">Drifting</option>
                    <option value="STALE">Stale</option>
                    <option value="STABLE">Stable</option>
                  </Select>
                </div>
                {shown.length === 0 ? (
                  <p className={styles.muted}>No signals here.</p>
                ) : (
                  <ul className={styles.records} aria-label="Drift by signal">
                    {shown.map((item, i) => (
                      <li key={`${item.dimension}-${item.signal_value}-${i}`} className={styles.record}>
                        <span className={styles.recordHead}>
                          <span>{humanizeEnum(item.dimension)}</span>
                          <span className={styles.recordTitle}>{item.signal_value}</span>
                          <span>· {humanizeEnum(item.drift_type)}</span>
                          {item.is_stale && <span>· Stale</span>}
                          <span>· {humanizeEnum(item.evidence_strength)} evidence</span>
                        </span>
                        <span>{item.explanation}</span>
                        <span className={styles.numbers}>
                          Historical {decimal(item.historical_strength, 2)} · recent {decimal(item.recent_strength, 2)} · difference {signedDecimal(item.difference, 2)}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </>
            );
          }}
        </Loaded>
      </div>

      <div className={styles.group}>
        <h4 className={styles.groupTitle}>Audit trail</h4>
        <Loaded resource={events} label="Loading the audit trail" failure="The audit trail could not be loaded.">
          {(data) =>
            data.items.length === 0 ? (
              <p className={styles.muted}>No governance events recorded yet.</p>
            ) : (
              <ul className={styles.records} aria-label="Governance events">
                {data.items.map((event) => (
                  <li key={event.id} className={styles.record}>
                    <span className={styles.recordHead}>
                      <span className={styles.recordTitle}>{humanizeEnum(event.event_type)}</span>
                      <span>
                        {event.previous_state ? `${humanizeEnum(event.previous_state)} to ` : "To "}
                        {humanizeEnum(event.new_state)}
                      </span>
                    </span>
                    <span>{event.reason}</span>
                    <span className={styles.numbers}>{when(event.reference_time || event.created_at)}</span>
                  </li>
                ))}
              </ul>
            )
          }
        </Loaded>
      </div>
      <p className={styles.muted}>Stated preferences and exclusions are never overridden by drift; suspended personalization returns modifiers to neutral without touching the core ranking.</p>
    </>
  );
}
