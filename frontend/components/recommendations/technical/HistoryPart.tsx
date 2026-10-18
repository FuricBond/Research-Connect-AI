"use client";

import { useState } from "react";
import { useApiResource } from "../../../hooks/useApiResource";
import { fetchRecommendationEvaluation, fetchRecommendationHistory, fetchRecommendationSnapshotDetail } from "../../../services/api";
import type { DataSufficiencyStatus, EvaluationMetrics, RecommendationItemSnapshot } from "../../../types/researcher";
import { humanizeEnum } from "../../../utils/date";
import { EvidencePanel } from "../../research/lazyPanels";
import { Button } from "../../ui/Button/Button";
import { Select } from "../../ui/Field/Field";
import details from "../../research/Details.module.css";
import { FEEDBACK_LABEL, Loaded, Metrics, decimal, percent, signedDecimal, when } from "./shared";
import styles from "../Recommendations.module.css";

export const RANKING_VERSIONS: Record<string, string> = {
  "phase3.7-v1": "Personalized with your activity",
  "phase3.5-personalized": "Personalized with your preferences",
  "phase2-baseline": "Relevance only",
};

const DATA_STATUS: Record<DataSufficiencyStatus, string> = {
  SUFFICIENT_DATA: "Enough data to measure",
  INSUFFICIENT_DATA: "Too little data to be sure",
  NO_FEEDBACK: "No feedback yet",
  NO_HISTORY: "No history yet",
};

const metric = (value: number | null | undefined, asPercent = false) => (value === null || value === undefined ? "Not measured" : asPercent ? percent(value, 1) : decimal(value));

function MetricTiles({ metrics }: { metrics: EvaluationMetrics }) {
  return (
    <Metrics
      label="Offline quality of past recommendations"
      items={[
        ["Precision at 5", metric(metrics.precision_at_5, true)],
        ["Precision at 10", metric(metrics.precision_at_10, true)],
        ["Recall at 10", metric(metrics.recall_at_10, true)],
        ["NDCG at 10", metric(metrics.ndcg_at_10)],
        ["Hit rate at 5", metric(metrics.hit_rate_at_5, true)],
        ["Save rate", metric(metrics.save_rate, true)],
        ["Engagement", metric(metrics.engagement_rate, true)],
        ["Dismissal", metric(metrics.dismissal_rate, true)],
      ]}
    />
  );
}

/** One kept list: its calls with their scores then, the feedback they got, and "Why?" as it was then. */
function Snapshot({ profileId, snapshotId, onWhy }: { profileId: string; snapshotId: string; onWhy: (item: RecommendationItemSnapshot) => void }) {
  const detail = useApiResource(`technical:snapshot:${profileId}:${snapshotId}`, (signal) => fetchRecommendationSnapshotDetail(profileId, snapshotId, undefined, signal));
  return (
    <Loaded resource={detail} label="Loading the recommendations kept" failure="The recommendations kept could not be loaded.">
      {(data) => (
        <div className="rc-scroll-x" role="region" aria-label={`Recommendations kept on ${when(data.created_at)}`} tabIndex={0}>
          <table className={details.table}>
            <caption>
              {data.returned_count} recommendation{data.returned_count === 1 ? "" : "s"} kept on {when(data.created_at)}
            </caption>
            <thead>
              <tr>
                <th scope="col">Call</th>
                <th scope="col">Relevance</th>
                <th scope="col">Preferences</th>
                <th scope="col">Activity</th>
                <th scope="col">Final</th>
                <th scope="col">Feedback</th>
                <th scope="col">
                  <span className="rc-visually-hidden">Explanation</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((item) => {
                const title = item.opportunity?.title || "Untitled call";
                return (
                  <tr key={item.id}>
                    <td>
                      {item.rank}. {title}
                      {item.opportunity && (
                        <span className={details.source}>
                          {" "}
                          · {[item.opportunity.opportunity_type, item.opportunity.delivery_mode].filter(Boolean).map((value) => humanizeEnum(value)).join(" · ")}
                        </span>
                      )}
                    </td>
                    <td>{decimal(item.base_relevance_score)}</td>
                    <td>{decimal(item.personalization_score)}</td>
                    <td>{signedDecimal(item.behavioral_adjustment)}</td>
                    <td>{decimal(item.final_score)}</td>
                    <td>
                      {item.user_feedback.length > 0
                        ? item.user_feedback.map((feedback) => FEEDBACK_LABEL[feedback as keyof typeof FEEDBACK_LABEL] ?? humanizeEnum(feedback)).join(", ")
                        : "None"}
                    </td>
                    <td>
                      <Button variant="link" size="sm" aria-haspopup="dialog" onClick={() => onWhy(item)}>
                        Why?<span className="rc-visually-hidden"> {title}, as recommended then</span>
                      </Button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Loaded>
  );
}

/**
 * Recommendation history (Phase 3.7, formerly "Recommendation History & Evaluation"): the
 * offline quality of past recommendations, a comparison by ranking version, and each list kept,
 * with every call's scores then and "Why?" — the shared Evidence panel, showing the explanation
 * as it was when it was recommended.
 */
export default function HistoryPart({ profileId }: { profileId: string }) {
  const [version, setVersion] = useState("");
  const evaluation = useApiResource(`technical:evaluation:${profileId}:${version}`, (signal) =>
    fetchRecommendationEvaluation(profileId, { rankingVersion: version || undefined, includeComparison: true }, undefined, signal)
  );
  const history = useApiResource(`technical:history:${profileId}:${version}`, (signal) =>
    fetchRecommendationHistory(profileId, { limit: 20, offset: 0, rankingVersion: version || undefined }, undefined, signal)
  );
  const [open, setOpen] = useState<string | null>(null);
  const [why, setWhy] = useState<RecommendationItemSnapshot | null>(null);

  return (
    <>
      <div className={styles.controls}>
        <Select label="Ranking version" value={version} onChange={(event) => setVersion(event.target.value)}>
          <option value="">All ranking versions</option>
          {Object.entries(RANKING_VERSIONS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </Select>
      </div>

      <Loaded resource={evaluation} label="Loading the quality of past recommendations" failure="The quality of past recommendations could not be loaded.">
        {(data) => (
          <>
            <p className={styles.muted}>
              {data.data_status ? `${DATA_STATUS[data.data_status] ?? humanizeEnum(data.data_status)} · ` : ""}
              {data.total_snapshots ?? 0} lists kept, {data.total_recommendations ?? 0} recommendations, {data.total_feedback_events ?? 0} feedback events
            </p>
            {data.metrics ? <MetricTiles metrics={data.metrics} /> : <p className={styles.muted}>Nothing measured yet.</p>}
            {data.metrics?.notes && <p className={styles.muted}>{data.metrics.notes}</p>}
            {data.ranking_comparison && Object.keys(data.ranking_comparison).length > 1 && (
              <div className="rc-scroll-x" role="region" aria-label="By ranking version" tabIndex={0}>
                <table className={details.table}>
                  <caption>By ranking version</caption>
                  <thead>
                    <tr>
                      <th scope="col">Version</th>
                      <th scope="col">Precision at 5</th>
                      <th scope="col">NDCG at 10</th>
                      <th scope="col">Save rate</th>
                      <th scope="col">Sample</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(data.ranking_comparison).map(([key, comparison]) => (
                      <tr key={key}>
                        <td>{comparison.display_name}</td>
                        <td>{metric(comparison.metrics.precision_at_5, true)}</td>
                        <td>{metric(comparison.metrics.ndcg_at_10)}</td>
                        <td>{metric(comparison.metrics.save_rate, true)}</td>
                        <td>{comparison.sample_size} items</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </Loaded>

      <div className={styles.group}>
        <h4 className={styles.groupTitle}>Lists kept</h4>
        <Loaded resource={history} label="Loading the lists kept" failure="The lists kept could not be loaded.">
          {(data) =>
            data.items.length === 0 ? (
              <p className={styles.muted}>No lists kept yet. Each time recommendations are made, the list is kept here for review and evaluation.</p>
            ) : (
              <>
                <p className={styles.muted}>
                  {data.total} list{data.total === 1 ? "" : "s"} kept{data.total > data.items.length ? `; the latest ${data.items.length} are shown` : ""}.
                </p>
                <ul className={styles.records} aria-label="Lists kept">
                  {data.items.map((snapshot) => (
                    <li key={snapshot.id} className={styles.record}>
                      <span className={styles.recordHead}>
                        <span className={styles.recordTitle}>{when(snapshot.created_at)}</span>
                        <span>· {RANKING_VERSIONS[snapshot.ranking_version] ?? snapshot.ranking_version}</span>
                        <span>
                          · {snapshot.returned_count} of {snapshot.candidate_count}
                        </span>
                      </span>
                      {snapshot.top_opportunity_titles.length > 0 && (
                        <span>
                          {snapshot.top_opportunity_titles
                            .slice(0, 2)
                            .map((title, i) => `${i + 1}. ${title}`)
                            .join(" · ")}
                        </span>
                      )}
                      <div>
                        <Button variant="link" size="sm" aria-expanded={open === snapshot.id} onClick={() => setOpen(open === snapshot.id ? null : snapshot.id)}>
                          {open === snapshot.id ? "Hide the list" : "Show the list"}
                          <span className="rc-visually-hidden"> kept on {when(snapshot.created_at)}</span>
                        </Button>
                      </div>
                      {open === snapshot.id && <Snapshot profileId={profileId} snapshotId={snapshot.id} onWhy={setWhy} />}
                    </li>
                  ))}
                </ul>
              </>
            )
          }
        </Loaded>
      </div>

      {why && (
        <EvidencePanel
          subject={{
            title: why.opportunity?.title || "Recommended call",
            context: "recommendation",
            rank: why.rank,
            score: why.final_score,
            scoreKind: "match",
            explanation: null,
            recommendation: {
              profileId,
              opportunityId: why.opportunity_id,
              rank: why.rank,
              finalScore: why.final_score,
              relevanceScore: why.base_relevance_score,
              personalizationScore: why.personalization_score,
              explanation: null,
              historical: true,
              snapshotId: why.snapshot_id,
            },
          }}
          onClose={() => setWhy(null)}
        />
      )}
    </>
  );
}
