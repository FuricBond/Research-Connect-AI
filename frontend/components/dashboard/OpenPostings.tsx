"use client";

import Link from "next/link";
import type { ApiResource } from "../../hooks/useApiResource";
import type { ResearchPostingListResponse } from "../../types/posting";
import { postingStatusMeta } from "../../utils/status";
import { DeadlineCountdown } from "../research/DeadlineCountdown";
import { StatusBadge } from "../ui/Badge/Badge";
import { EmptyState } from "../ui/State/State";
import { DashboardModule, Loaded } from "./Module";
import styles from "./Dashboard.module.css";

const SHOWN = 5;

/**
 * Faculty "Your open postings" (plan §8): each open posting with its applicants, application
 * deadline and status, from the same `GET /postings/mine` that "Needs your decision" reads.
 */
export function OpenPostings({ mine }: { mine: ApiResource<ResearchPostingListResponse> }) {
  return (
    <DashboardModule id="dashboard-open-postings" title="Your open postings" action={<Link href="/postings">Manage postings</Link>} reserve="timeline">
      <Loaded resource={mine} loading="Loading your postings" failure="Your postings could not be loaded.">
        {(data) => {
          const open = data.postings.filter((posting) => posting.status === "OPEN");
          if (open.length === 0) {
            return (
              <EmptyState
                bare
                variant="first-use"
                headingLevel={3}
                title="You have no open postings."
                description={
                  <>
                    Projects, thesis topics and assistantships you publish on <Link href="/postings">Research postings</Link> appear here.
                  </>
                }
              />
            );
          }
          return (
            <>
              <ul className={styles.list}>
                {open.slice(0, SHOWN).map((posting) => (
                  <li key={posting.id} className={styles.item}>
                    <Link href={`/postings/${posting.id}`} className={styles.itemTitle}>
                      {posting.title}
                    </Link>
                    <div className={styles.meta}>
                      <StatusBadge meta={postingStatusMeta(posting.status)} />
                      <span>
                        {posting.application_count} applicant{posting.application_count === 1 ? "" : "s"}
                      </span>
                      {posting.application_deadline ? (
                        <DeadlineCountdown deadline={posting.application_deadline} daysRemaining={posting.days_until_deadline} />
                      ) : (
                        <span>No application deadline</span>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
              {open.length > SHOWN && (
                <Link href="/postings" className={styles.more}>
                  See all {open.length} open postings
                </Link>
              )}
            </>
          );
        }}
      </Loaded>
    </DashboardModule>
  );
}
