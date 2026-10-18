"use client";

import { useState } from "react";
import { Trash2 } from "lucide-react";
import { useApiResource } from "../../../hooks/useApiResource";
import { deleteRecommendationFeedback, fetchFeedbackSummary, fetchRecommendationFeedbackHistory } from "../../../services/api";
import type { FeedbackType } from "../../../types/researcher";
import { humanizeEnum } from "../../../utils/date";
import { IconButton } from "../../ui/Button/Button";
import { Select } from "../../ui/Field/Field";
import details from "../../research/Details.module.css";
import { FEEDBACK_LABEL, Loaded, Metrics, percent, when } from "./shared";
import styles from "../Recommendations.module.css";

/**
 * The feedback log (Phase 3.6, formerly "Recommendation Feedback & Behavioral Learning"): what
 * was learned from it, and every feedback event, each removable (which undoes what it taught).
 * Feedback fades with a 30-day half-life; stated preferences always come first.
 */
export default function FeedbackPart({ profileId, onChanged }: { profileId: string; onChanged: () => void }) {
  const [type, setType] = useState("");
  const summary = useApiResource(`technical:feedback-summary:${profileId}`, (signal) => fetchFeedbackSummary(profileId, undefined, signal));
  const log = useApiResource(`technical:feedback-log:${profileId}:${type}`, (signal) =>
    fetchRecommendationFeedbackHistory(profileId, { limit: 30, feedbackType: type || undefined }, undefined, signal)
  );
  const [removing, setRemoving] = useState<string | null>(null);
  const [notice, setNotice] = useState("");

  async function remove(id: string, title: string) {
    setRemoving(id);
    try {
      await deleteRecommendationFeedback(profileId, id);
      setNotice(`Removed your feedback on ${title}.`);
      summary.retry();
      log.retry();
      onChanged();
    } catch {
      setNotice("That feedback could not be removed. Try again.");
    } finally {
      setRemoving(null);
    }
  }

  return (
    <>
      <p className={styles.muted}>Feedback counts less as it ages (half of its weight after 30 days); your stated preferences always come first.</p>
      <Loaded resource={summary} label="Loading what your feedback taught" failure="The feedback summary could not be loaded.">
        {(data) => (
          <>
            <Metrics
              label="Feedback summary"
              items={[
                ["Feedback given", `${data.total_feedback_count}${data.is_cold_start ? " (not enough to learn from yet)" : ""}`],
                ["Confidence", percent(data.overall_confidence, 1)],
                ["Calls set aside", data.suppressed_count],
                [
                  "For / against / viewed",
                  `${(data.counts_by_type.SAVE ?? 0) + (data.counts_by_type.INTERESTED ?? 0)} / ${(data.counts_by_type.DISMISS ?? 0) + (data.counts_by_type.NOT_INTERESTED ?? 0)} / ${data.counts_by_type.VIEW ?? 0}`,
                ],
              ]}
            />
            <dl className={details.facts}>
              <div className={details.factRow}>
                <dt>Topics that count for</dt>
                <dd>{data.top_positive_topics.length > 0 ? data.top_positive_topics.join(", ") : "None learned yet: save calls or mark them Helpful."}</dd>
              </div>
              <div className={details.factRow}>
                <dt>Topics that count against</dt>
                <dd>{data.top_negative_topics.length > 0 ? data.top_negative_topics.join(", ") : "None learned yet: dismissing calls teaches these."}</dd>
              </div>
            </dl>
          </>
        )}
      </Loaded>

      <div className={styles.group}>
        <h4 className={styles.groupTitle}>Recent feedback</h4>
        <div className={styles.controls}>
          <Select label="Show" value={type} onChange={(event) => setType(event.target.value)}>
            <option value="">All feedback</option>
            {(Object.keys(FEEDBACK_LABEL) as FeedbackType[]).map((value) => (
              <option key={value} value={value}>
                {FEEDBACK_LABEL[value]}
              </option>
            ))}
          </Select>
        </div>
        <p role="status" className={styles.notice}>
          {notice}
        </p>
        <Loaded resource={log} label="Loading your feedback" failure="Your feedback could not be loaded.">
          {(data) =>
            data.items.length === 0 ? (
              <p className={styles.muted}>No feedback here yet.</p>
            ) : (
              <div className="rc-scroll-x" role="region" aria-label="Recent feedback" tabIndex={0}>
                <table className={details.table}>
                  <caption className="rc-visually-hidden">Recent feedback</caption>
                  <thead>
                    <tr>
                      <th scope="col">Call</th>
                      <th scope="col">Feedback</th>
                      <th scope="col">Type / attendance</th>
                      <th scope="col">Where</th>
                      <th scope="col">Recorded</th>
                      <th scope="col">
                        <span className="rc-visually-hidden">Remove</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.items.map((item) => {
                      const title = item.opportunity_title || "this call";
                      return (
                        <tr key={item.id}>
                          <td>{item.opportunity_title || "Untitled call"}</td>
                          <td>{FEEDBACK_LABEL[item.feedback_type] ?? humanizeEnum(item.feedback_type)}</td>
                          <td>
                            {item.opportunity_type ? humanizeEnum(item.opportunity_type) : "Not recorded"} / {item.delivery_mode ? humanizeEnum(item.delivery_mode) : "Not recorded"}
                          </td>
                          <td>{humanizeEnum(item.source)}</td>
                          <td>{when(item.created_at)}</td>
                          <td>
                            <IconButton
                              size="sm"
                              variant="ghost"
                              label={`Remove your feedback on ${title}`}
                              icon={<Trash2 size={16} aria-hidden="true" />}
                              disabled={removing !== null}
                              onClick={() => remove(item.id, title)}
                            />
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )
          }
        </Loaded>
      </div>
    </>
  );
}
