"use client";

/**
 * P9 — the author's review of a posting's applications on its own page, loaded only when the
 * reader is its author (see lazy.tsx). Researchers who only read or apply never download it.
 */

import Link from "next/link";
import type { ResearchPosting } from "../../types/posting";
import { inboxHref } from "../../utils/postings";
import { EmptyState, ErrorState, SkeletonList } from "../ui/State/State";
import { ApplicantCard } from "./ApplicantCard";
import { APPLICATIONS_LIMIT, usePostingApplications } from "./resources";
import { useApplicationDecisions } from "./useApplicationDecisions";
import styles from "./Faculty.module.css";

/** The author's review of this posting's applications, with the same decisions as the inbox. */
export function Applications({ posting }: { posting: ResearchPosting }) {
  const resource = usePostingApplications(posting.id);
  const decisions = useApplicationDecisions();
  const applications = resource.data?.applications.filter((application) => application.posting_id === posting.id).map(decisions.current) ?? null;

  return (
    <section id="applications" className={styles.detailSection} aria-labelledby="posting-applications" aria-busy={resource.status === "loading" || undefined}>
      <div className={styles.sectionHead}>
        <h2 id="posting-applications" className={styles.detailTitle}>
          Applications ({posting.application_count})
        </h2>
        {posting.status === "OPEN" && posting.application_count > 0 && (
          <Link href={inboxHref({ status: null, posting: posting.id })} className={styles.sectionLink}>
            Open in Applicants
          </Link>
        )}
      </div>
      <p role="status" className="rc-visually-hidden">
        {decisions.announcement}
      </p>
      {resource.status === "error" ? (
        <ErrorState bare headingLevel={3} title="The applications could not be loaded." kind={resource.error?.kind === "network" ? "offline" : "failed"} onRetry={resource.retry} />
      ) : applications === null ? (
        <SkeletonList rows={2} lines={2} label="Loading the applications" announce={false} />
      ) : applications.length === 0 ? (
        <EmptyState bare headingLevel={3} title="No applications yet." description={posting.status === "OPEN" ? "Applications appear here as researchers apply." : undefined} />
      ) : (
        <ul className={styles.applicants}>
          {applications.map((application) => (
            <li key={application.id}>
              <ApplicantCard application={application} pending={decisions.pending.has(application.id)} decide={decisions.decide} failure={decisions.failure} onDismissFailure={decisions.dismissFailure} />
            </li>
          ))}
        </ul>
      )}
      {resource.data && resource.data.total > resource.data.applications.length && (
        <p className={styles.facts}>
          Showing the {APPLICATIONS_LIMIT} newest of {resource.data.total} applications.
        </p>
      )}
    </section>
  );
}
