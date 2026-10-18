"use client";

import { useEffect, useRef, useState } from "react";
import { useApiResource } from "../../../hooks/useApiResource";
import { fetchSubmissionHistory } from "../../../services/api";
import { ErrorState, SkeletonList } from "../../ui/State/State";
import { dateTime } from "../workflow";
import { useKept } from "../item/useWorkspaceItem";
import { eventLabel } from "./words";
import styles from "./Submission.module.css";

const LIMIT = 50;

/**
 * The submission's history (status changes, documents, versions, details), newest first. Behind
 * a disclosure and loaded only when opened; read again when this page changed something.
 */
export function SubmissionHistory({ submissionId, version }: { submissionId: string; version: number }) {
  const [opened, setOpened] = useState(false);
  const history = useApiResource(opened ? `submission:${submissionId}:history` : null, (signal) => fetchSubmissionHistory(submissionId, { limit: LIMIT }, undefined, signal));
  const shown = useKept(history);
  const seen = useRef(version);
  const { retry } = history;
  useEffect(() => {
    if (seen.current === version) return;
    seen.current = version;
    if (opened) retry();
  }, [version, opened, retry]);

  const items = shown?.items ?? [];
  return (
    <details className={styles.history} onToggle={(event) => event.currentTarget.open && setOpened(true)}>
      <summary className={styles.historySummary}>History</summary>
      <div className={styles.historyBody}>
        {!opened ? null : shown === undefined ? (
          history.status === "error" ? (
            <ErrorState bare headingLevel={3} title="The history could not be loaded" onRetry={retry} />
          ) : (
            <SkeletonList rows={3} label="Loading the history" />
          )
        ) : items.length === 0 ? (
          <p className={styles.text}>Nothing recorded yet.</p>
        ) : (
          <ol className={styles.timeline} aria-busy={history.status === "loading" || undefined}>
            {items.map((event) => (
              <li key={event.id} className={styles.event}>
                <p className={styles.eventTitle}>{eventLabel(event.event_type)}</p>
                {event.description && <p className={styles.text}>{event.description}</p>}
                <time className={styles.time} dateTime={event.created_at}>
                  {dateTime(event.created_at)}
                </time>
              </li>
            ))}
          </ol>
        )}
        {shown && shown.total_count > items.length && (
          <p className={styles.time}>
            Showing the latest {items.length} of {shown.total_count}.
          </p>
        )}
      </div>
    </details>
  );
}
