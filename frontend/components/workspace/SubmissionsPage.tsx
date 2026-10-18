"use client";

import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { useAddressSearch } from "../../hooks/useAddressSearch";
import { useApiResource } from "../../hooks/useApiResource";
import { fetchSubmissions, fetchSubmissionSummary } from "../../services/api";
import type { SubmissionStatus } from "../../types/submission";
import { submissionStatusMeta } from "../../utils/status";
import { DeadlineCountdown } from "../research/DeadlineCountdown";
import { StatusBadge } from "../ui/Badge/Badge";
import { Button } from "../ui/Button/Button";
import { PageHeader } from "../ui/PageHeader/PageHeader";
import { EmptyState, ErrorState, SkeletonList } from "../ui/State/State";
import { submissionTypeLabel } from "./submission/words";
import { shortDate } from "./workflow";
import { ChipCount } from "./ChipCount";
import { WorkspaceNav } from "./WorkspaceNav";
import { itemHref } from "./WorkspaceRow";
import styles from "./Workspace.module.css";

const STATUSES: SubmissionStatus[] = ["DRAFT", "READY", "SUBMITTED", "UNDER_REVIEW", "ACCEPTED", "REJECTED", "WITHDRAWN"];

export function readSubmissionStatus(params: URLSearchParams): SubmissionStatus | null {
  const status = params.get("status");
  return STATUSES.includes(status as SubmissionStatus) ? (status as SubmissionStatus) : null;
}

/**
 * P7 — /submissions: every submission across the workspace, newest change first, filtered by
 * status chips with their counts (`?status=SUBMITTED`). Each opens its item's Submission tab.
 * Two requests: the list and the counts.
 */
export function SubmissionsPage() {
  const [params, go] = useAddressSearch();
  const status = readSubmissionStatus(params);
  const list = useApiResource(`submissions:list:${status ?? "all"}`, (signal) =>
    fetchSubmissions({ status: status ?? undefined, sort_by: "updated_at", sort_order: "desc", limit: 100 }, undefined, signal)
  );
  const summary = useApiResource("submissions:summary", (signal) => fetchSubmissionSummary(undefined, signal));
  const counts = summary.data;

  const chips: { status: SubmissionStatus | null; label: string; count: number | null }[] = [
    { status: null, label: "All", count: counts ? counts.total_submissions : null },
    ...STATUSES.map((value) => ({ status: value, label: submissionStatusMeta(value).label, count: counts ? (counts.counts_by_status[value] ?? 0) : null })),
  ];
  const href = (value: SubmissionStatus | null) => (value ? `/submissions?status=${value}` : "/submissions");
  const items = list.data?.items ?? [];

  return (
    <>
      <PageHeader title="Submissions" description="Every manuscript you are tracking, from first draft to decision, with its deadline." />
      <WorkspaceNav current="submissions" />

      <div className={styles.toolbar}>
        <div className={styles.chips} role="group" aria-label="Filter by status">
          {chips.map((chip) => (
            <button key={chip.status ?? "ALL"} type="button" className={styles.chip} aria-pressed={chip.status === status} onClick={() => go(href(chip.status))}>
              <span>
                {chip.label}
                <ChipCount count={chip.count} />
              </span>
            </button>
          ))}
        </div>
      </div>

      <section className={styles.results} aria-labelledby="submissions-heading" aria-busy={list.status === "loading" || undefined}>
        <h2 id="submissions-heading" className={styles.resultsTitle}>
          {status ? submissionStatusMeta(status).label : "All submissions"}
        </h2>
        {list.status === "loading" || list.status === "idle" ? (
          <SkeletonList rows={3} lines={2} label="Loading submissions" />
        ) : list.status === "error" ? (
          <ErrorState title="Your submissions could not be loaded" kind={list.error?.kind === "network" ? "offline" : "failed"} onRetry={list.retry} />
        ) : items.length === 0 ? (
          status ? (
            <EmptyState
              variant="no-results"
              title="No submissions with this status."
              actions={
                <Button variant="secondary" onClick={() => go("/submissions")}>
                  Show all submissions
                </Button>
              }
            />
          ) : (
            <EmptyState
              title="No submissions yet"
              description="Draft a submission from a call in your workspace to track it here."
              actions={
                <Link href="/workspace" className={styles.nextStep}>
                  Open workspace
                  <ArrowRight size={14} aria-hidden="true" />
                </Link>
              }
            />
          )
        ) : (
          <ul className={styles.list}>
            {items.map((submission) => {
              const deadline = submission.deadline_context;
              const titleId = `submission-${submission.id}`;
              return (
                <li key={submission.id} className={styles.row} aria-labelledby={titleId}>
                  <div className={styles.rowMain}>
                    <h3 className={styles.rowTitle}>
                      <Link id={titleId} href={itemHref(submission.workspace_item_id, "submission")} className={styles.rowTitleLink}>
                        {submission.title}
                      </Link>
                    </h3>
                    <p className={styles.rowFacts}>
                      {[submissionTypeLabel(submission.submission_type), submission.venue_name || submission.venue || submission.opportunity_title].filter(Boolean).join(" · ")}
                    </p>
                    <div className={styles.subMeta}>
                      <StatusBadge meta={submissionStatusMeta(submission.status)} />
                      {deadline?.submission_deadline && (
                        <DeadlineCountdown deadline={deadline.submission_deadline} daysRemaining={deadline.days_remaining} urgencyTier={deadline.urgency_tier} />
                      )}
                      <span>Updated {shortDate(submission.updated_at)}</span>
                    </div>
                  </div>
                  <div className={styles.rowControls}>
                    <Link href={itemHref(submission.workspace_item_id, "submission")} className={styles.nextStep} aria-describedby={titleId}>
                      Open
                      <ArrowRight size={14} aria-hidden="true" />
                    </Link>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </>
  );
}
