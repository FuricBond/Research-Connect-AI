"use client";

import Link from "next/link";
import { useState } from "react";
import { useAddressSearch } from "../../hooks/useAddressSearch";
import type { ApplicationStatus, PostingApplication, ResearchPosting } from "../../types/posting";
import { APPLICATION_STATUSES, INBOX_POSTINGS, inboxHref, inboxPostings, MY_POSTINGS_HREF, readInboxQuery } from "../../utils/postings";
import { applicationStatusMeta, postingStatusMeta } from "../../utils/status";
import { DeadlineCountdown } from "../research/DeadlineCountdown";
import { StatusBadge } from "../ui/Badge/Badge";
import { Button, ButtonLink } from "../ui/Button/Button";
import { Select } from "../ui/Field/Field";
import { PageHeader } from "../ui/PageHeader/PageHeader";
import { EmptyState, ErrorState, SkeletonList } from "../ui/State/State";
import { ChipCount } from "../workspace/ChipCount";
import { ApplicantCard } from "./ApplicantCard";
import { APPLICATIONS_LIMIT, useAllMyPostings, useApplicationsOf, useKept } from "./resources";
import { useApplicationDecisions } from "./useApplicationDecisions";
import styles from "./Faculty.module.css";

/**
 * P9 — /postings/applicants (plan §14): one inbox for the applications to a faculty member's
 * postings, grouped by posting, filtered by status (and by posting) in the address.
 *
 * There is no aggregate endpoint (plan Q4), so the inbox reads the author's postings and then, all
 * at once, the applications of at most INBOX_POSTINGS of them — the most recently published open
 * postings that have applications: at most 11 requests. Postings beyond that, and postings that
 * are no longer open, are named with a link to their own page, where their applications are.
 * Each application is listed under the posting it was made to (the API's `posting_id`), once.
 */
export function ApplicantsInbox() {
  const [params, go] = useAddressSearch();
  const query = readInboxQuery(params);
  const mine = useAllMyPostings();
  const postings = useKept(mine)?.postings ?? null;
  const chosen = postings ? inboxPostings(postings) : null;
  const lists = useApplicationsOf(chosen?.read.map((posting) => posting.id) ?? []);
  const decisions = useApplicationDecisions();
  // Cards decided on this visit stay where they are until the filter changes, so a decision
  // never makes the card (and the focus in it) vanish under the reader.
  const [stay, setStay] = useState<{ key: string; ids: ReadonlySet<string> }>({ key: "", ids: new Set() });
  const filterKey = inboxHref(query);
  const stayIds = stay.key === filterKey ? stay.ids : new Set<string>();

  const decide: typeof decisions.decide = async (application, target, options) => {
    const agreed = await decisions.decide(application, target, options);
    if (agreed) setStay((before) => ({ key: filterKey, ids: new Set(before.key === filterKey ? before.ids : []).add(application.id) }));
    return agreed;
  };

  const groups = (chosen?.read ?? []).map((posting, index) => {
    const resource = lists[index].applications;
    const listed = resource.data?.applications.filter((application) => application.posting_id === posting.id) ?? null;
    return { posting, resource, applications: listed?.map(decisions.current) ?? null, total: resource.data?.total ?? null };
  });
  const inScope = query.posting ? groups.filter((group) => group.posting.id === query.posting) : groups;
  // Counts only when every list in view answered: a partial count would read as the whole.
  const everyLoaded = inScope.every((group) => group.applications !== null);
  const counts = new Map<ApplicationStatus | null, number>();
  for (const group of inScope) {
    for (const application of group.applications ?? []) {
      counts.set(null, (counts.get(null) ?? 0) + 1);
      counts.set(application.status, (counts.get(application.status) ?? 0) + 1);
    }
  }
  const countOf = (status: ApplicationStatus | null) => (postings && everyLoaded ? (counts.get(status) ?? 0) : null);
  const visible = (application: PostingApplication) => query.status === null || application.status === query.status || stayIds.has(application.id);

  const loading = postings === null && (mine.status === "loading" || mine.status === "idle");
  const unknownPosting = query.posting && postings && !groups.some((group) => group.posting.id === query.posting) ? postings.find((posting) => posting.id === query.posting) ?? null : undefined;
  const shown = inScope.map((group) => ({ ...group, rows: group.applications?.filter(visible) ?? null })).filter((group) => group.rows === null || group.rows.length > 0 || query.status === null);
  const busy = loading || inScope.some((group) => group.resource.status === "loading");

  return (
    <>
      <PageHeader
        title="Applicants"
        description="Applications to your open postings, grouped by posting. Review them in order: shortlist, then make an offer."
        actions={
          <ButtonLink href={MY_POSTINGS_HREF} variant="secondary">
            My postings
          </ButtonLink>
        }
      />

      <div className={styles.toolbar}>
        <div className={styles.chips} role="group" aria-label="Filter by status">
          {([null, ...APPLICATION_STATUSES] as (ApplicationStatus | null)[]).map((status) => (
            <button key={status ?? "ALL"} type="button" className={styles.chip} aria-pressed={query.status === status} onClick={() => go(inboxHref({ ...query, status }))}>
              <span>
                {status ? applicationStatusMeta(status).label : "All"}
                <ChipCount count={countOf(status)} />
              </span>
            </button>
          ))}
        </div>
        {groups.length > 1 && (
          <Select label="Posting" className={styles.postingFilter} value={query.posting ?? ""} onChange={(event) => go(inboxHref({ ...query, posting: event.target.value || null }))}>
            <option value="">All postings</option>
            {groups.map(({ posting }) => (
              <option key={posting.id} value={posting.id}>
                {posting.title}
              </option>
            ))}
          </Select>
        )}
      </div>

      <section className={styles.results} aria-label={query.status ? `${applicationStatusMeta(query.status).label} applications` : "All applications"} aria-busy={busy || undefined}>
        <p role="status" className="rc-visually-hidden">
          {decisions.announcement}
        </p>

        {unknownPosting !== undefined && (
          <EmptyState
            variant="no-results"
            headingLevel={3}
            title={unknownPosting ? <>“{unknownPosting.title}” is not in this inbox.</> : "That posting is not one of your open postings."}
            description={unknownPosting ? "The inbox gathers your open postings; this one's applications are on its own page." : "Choose one of your postings, or see all applications."}
            actions={
              <>
                {unknownPosting && <ButtonLink href={`/postings/${unknownPosting.id}`}>Open the posting</ButtonLink>}
                <Button variant="secondary" onClick={() => go(inboxHref({ ...query, posting: null }))}>
                  Show all postings
                </Button>
              </>
            }
          />
        )}

        {loading ? (
          <SkeletonList rows={3} lines={3} label="Loading your applicants" />
        ) : postings === null ? (
          <ErrorState title="Your postings could not be loaded" kind={mine.error?.kind === "network" ? "offline" : "failed"} headingLevel={3} onRetry={mine.retry} />
        ) : groups.length === 0 ? (
          <EmptyState
            title="No applications yet."
            description={
              chosen && chosen.closed.length > 0
                ? "None of your open postings has applications. Postings that are no longer open keep theirs on their own pages (below)."
                : "Applications to your open internships, assistantships and post-doctoral positions appear here."
            }
            actions={<ButtonLink href={MY_POSTINGS_HREF}>Go to my postings</ButtonLink>}
          />
        ) : shown.length === 0 && unknownPosting === undefined ? (
          <EmptyState
            variant="no-results"
            title="No applications with this status."
            actions={
              <Button variant="secondary" onClick={() => go(inboxHref({ status: null, posting: query.posting }))}>
                Show all statuses
              </Button>
            }
          />
        ) : (
          shown.map((group) => <PostingGroup key={group.posting.id} {...group} decisions={decisions} decide={decide} />)
        )}

        {chosen && (chosen.later.length > 0 || chosen.closed.length > 0) && unknownPosting === undefined && (
          <aside className={styles.elsewhere} aria-labelledby="applicants-elsewhere">
            <h2 id="applicants-elsewhere" className={styles.elsewhereTitle}>
              Applications not shown here
            </h2>
            <p className={styles.facts}>
              This inbox gathers your open postings that have applications, at most {INBOX_POSTINGS} (the most recently published). These postings keep theirs on their own
              pages:
            </p>
            <ul className={styles.elsewhereList}>
              {[...chosen.later, ...chosen.closed].map((posting) => (
                <li key={posting.id}>
                  <Link href={`/postings/${posting.id}`}>{posting.title}</Link>
                  <span className={styles.facts}>
                    {" "}
                    · {postingStatusMeta(posting.status).label} · {posting.application_count} application{posting.application_count === 1 ? "" : "s"}
                  </span>
                </li>
              ))}
            </ul>
          </aside>
        )}
      </section>
    </>
  );
}

function PostingGroup({
  posting,
  resource,
  rows,
  total,
  decisions,
  decide,
}: {
  posting: ResearchPosting;
  resource: ReturnType<typeof useApplicationsOf>[number]["applications"];
  rows: PostingApplication[] | null;
  total: number | null;
  decisions: ReturnType<typeof useApplicationDecisions>;
  decide: ReturnType<typeof useApplicationDecisions>["decide"];
}) {
  const headingId = `applicants-${posting.id}`;
  const listed = resource.data?.applications.length ?? 0;
  return (
    <section className={styles.group} aria-labelledby={headingId}>
      <div className={styles.groupHead}>
        <h2 id={headingId} className={styles.groupTitle}>
          <Link href={`/postings/${posting.id}`} className={styles.titleLink}>
            {posting.title}
          </Link>
        </h2>
        <p className={styles.groupMeta}>
          <StatusBadge meta={postingStatusMeta(posting.status)} />
          {posting.application_deadline ? <DeadlineCountdown deadline={posting.application_deadline} daysRemaining={posting.days_until_deadline} /> : <span>No application deadline</span>}
          <span>
            {posting.application_count} application{posting.application_count === 1 ? "" : "s"}
          </span>
        </p>
      </div>
      {rows === null ? (
        resource.status === "error" ? (
          <ErrorState bare headingLevel={3} title={<>The applications for “{posting.title}” could not be loaded.</>} kind={resource.error?.kind === "network" ? "offline" : "failed"} onRetry={resource.retry} />
        ) : (
          <SkeletonList rows={2} lines={2} label={`Loading the applications for ${posting.title}`} announce={false} />
        )
      ) : rows.length === 0 ? (
        <p className={styles.facts}>No applications with this status.</p>
      ) : (
        <ul className={styles.applicants}>
          {rows.map((application) => (
            <li key={application.id}>
              <ApplicantCard
                application={application}
                pending={decisions.pending.has(application.id)}
                decide={decide}
                failure={decisions.failure}
                onDismissFailure={decisions.dismissFailure}
              />
            </li>
          ))}
        </ul>
      )}
      {total !== null && total > listed && (
        <p className={styles.facts}>
          Showing the {APPLICATIONS_LIMIT} newest of {total} applications.
        </p>
      )}
    </section>
  );
}
