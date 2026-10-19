"use client";

import Link from "next/link";
import type { ApiResource } from "../../hooks/useApiResource";
import type { ApplicationListResponse, ResearchPosting, ResearchPostingListResponse } from "../../types/posting";
import { APPLICANTS_HREF, inboxHref } from "../../utils/postings";
import { EmptyState } from "../ui/State/State";
import { DashboardModule, Loaded, ModuleError, ModuleLoading } from "./Module";
import { DECISION_POSTINGS, usePostingApplications } from "./resources";
import styles from "./Dashboard.module.css";

/** Applications that wait on the author. */
const AWAITING = new Set(["SUBMITTED", "UNDER_REVIEW"]);

/**
 * Faculty "Needs your decision" (plan §8): applications submitted or under review across the
 * author's postings. There is no aggregate endpoint (plan Q4), so the applications of at most
 * three open postings — those with the most applications — are fetched, one request each, after
 * the postings list; when more postings have applications the module says so and links to them.
 * P9: each posting opens in the applicant inbox, filtered to it, where the decisions are taken.
 */
export function NeedsDecision({ mine }: { mine: ApiResource<ResearchPostingListResponse> }) {
  const withApplications = (mine.data?.postings ?? [])
    .filter((posting) => posting.status === "OPEN" && posting.application_count > 0)
    .sort((a, b) => b.application_count - a.application_count);
  const chosen = withApplications.slice(0, DECISION_POSTINGS);

  // A fixed number of hooks; a slot without a posting waits (null) and requests nothing.
  const slots = [
    usePostingApplications(chosen[0]?.id ?? null),
    usePostingApplications(chosen[1]?.id ?? null),
    usePostingApplications(chosen[2]?.id ?? null),
  ].slice(0, DECISION_POSTINGS);

  return (
    <DashboardModule id="dashboard-decisions" title="Needs your decision" action={<Link href={APPLICANTS_HREF}>All applicants</Link>} reserve="timeline">
      <Loaded resource={mine} loading="Loading your postings" failure="Your postings could not be loaded.">
        {() => {
          if (chosen.length === 0) return <NothingWaiting />;
          const pending = chosen.map((posting, index) => ({ posting, applications: slots[index] }));
          if (pending.some(({ applications }) => applications.status === "loading" || applications.status === "idle")) {
            return <ModuleLoading label="Loading applications" />;
          }
          const failed = pending.filter(({ applications }) => applications.status === "error");
          const waiting = pending
            .filter(({ applications }) => applications.data)
            .map(({ posting, applications }) => ({ posting, ...count(applications.data!) }))
            .filter(({ submitted, underReview }) => submitted + underReview > 0);
          const others = withApplications.length - chosen.length;
          return (
            <>
              {failed.map(({ posting, applications }) => (
                <ModuleError key={posting.id} message={<>The applications for “{posting.title}” could not be loaded.</>} resource={applications} />
              ))}
              {waiting.length === 0 && failed.length === 0 ? (
                <NothingWaiting />
              ) : (
                <ul className={styles.list}>
                  {waiting.map(({ posting, submitted, underReview }) => (
                    <DecisionRow key={posting.id} posting={posting} submitted={submitted} underReview={underReview} />
                  ))}
                </ul>
              )}
              {others > 0 && (
                <p className={styles.more}>
                  {others} more open posting{others === 1 ? " has" : "s have"} applications. <Link href={APPLICANTS_HREF}>See all applicants</Link>
                </p>
              )}
            </>
          );
        }}
      </Loaded>
    </DashboardModule>
  );
}

function count(data: ApplicationListResponse) {
  let submitted = 0;
  let underReview = 0;
  for (const application of data.applications) {
    if (!AWAITING.has(application.status)) continue;
    if (application.status === "SUBMITTED") submitted += 1;
    else underReview += 1;
  }
  return { submitted, underReview };
}

function DecisionRow({ posting, submitted, underReview }: { posting: ResearchPosting; submitted: number; underReview: number }) {
  const parts = [submitted > 0 ? `${submitted} new` : null, underReview > 0 ? `${underReview} under review` : null].filter(Boolean);
  return (
    <li className={styles.item}>
      <Link href={inboxHref({ status: null, posting: posting.id })} className={styles.itemTitle}>
        {posting.title}
      </Link>
      <span className={styles.meta}>
        <span className={styles.strong}>{parts.join(" · ")}</span>
        <span>
          {posting.application_count} application{posting.application_count === 1 ? "" : "s"} in all
        </span>
      </span>
    </li>
  );
}

function NothingWaiting() {
  return (
    <EmptyState
      bare
      variant="done"
      headingLevel={3}
      title="No application is waiting for your decision."
      description="New applications to your open postings appear here."
    />
  );
}
