"use client";

import Link from "next/link";
import type { ApiResource } from "../../hooks/useApiResource";
import type { ReadingListResponse } from "../../types/reading_list";
import { EmptyState } from "../ui/State/State";
import { DashboardModule, Loaded } from "./Module";
import styles from "./Dashboard.module.css";

/**
 * Student "Reading progress" (plan §8): to read, reading and done, from the reading list's counts
 * (a one-item request: the counts cover the whole list). The bar repeats the three numbers for
 * the eye only; the numbers are the content.
 */
export function ReadingProgress({ reading }: { reading: ApiResource<ReadingListResponse> }) {
  return (
    <DashboardModule id="dashboard-reading" title="Reading progress" action={<Link href="/reading-list">Reading list</Link>} reserve="counts">
      <Loaded resource={reading} loading="Loading your reading list" failure="Your reading list could not be loaded." rows={1}>
        {(data) => {
          const counts = data.counts_by_status;
          const total = counts.TO_READ + counts.READING + counts.DONE;
          if (total === 0) {
            return (
              <EmptyState
                bare
                variant="first-use"
                headingLevel={3}
                title="No saved papers yet."
                description={
                  <>
                    Save papers from <Link href="/">Literature search</Link> to read them later.
                  </>
                }
              />
            );
          }
          return (
            <>
              <dl className={styles.counts}>
                <div className={styles.count}>
                  <dt>To read</dt>
                  <dd>{counts.TO_READ}</dd>
                </div>
                <div className={styles.count}>
                  <dt>Reading</dt>
                  <dd>{counts.READING}</dd>
                </div>
                <div className={styles.count}>
                  <dt>Done</dt>
                  <dd>{counts.DONE}</dd>
                </div>
              </dl>
              <svg className={styles.bar} viewBox={`0 0 ${total} 1`} preserveAspectRatio="none" aria-hidden="true" focusable="false">
                <rect className={styles.barDone} x={0} width={counts.DONE} height={1} />
                <rect className={styles.barReading} x={counts.DONE} width={counts.READING} height={1} />
                <rect className={styles.barToRead} x={counts.DONE + counts.READING} width={counts.TO_READ} height={1} />
              </svg>
            </>
          );
        }}
      </Loaded>
    </DashboardModule>
  );
}
