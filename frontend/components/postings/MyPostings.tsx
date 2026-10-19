"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { Plus } from "lucide-react";
import { useAddressSearch } from "../../hooks/useAddressSearch";
import type { ApiResource } from "../../hooks/useApiResource";
import type { ApplicationListResponse, PostingStatus, ResearchPosting } from "../../types/posting";
import { POSTING_TYPE_LABELS } from "../../types/posting";
import { canEdit, INBOX_POSTINGS, inboxHref, inboxPostings, mineHref, MINE_PAGE_SIZE, NEW_POSTING_HREF, POSTING_STATUSES, postingActionsFor, readMineQuery } from "../../utils/postings";
import { postingStatusMeta } from "../../utils/status";
import { DeadlineCountdown } from "../research/DeadlineCountdown";
import { StatusBadge } from "../ui/Badge/Badge";
import { Button, ButtonLink } from "../ui/Button/Button";
import { Menu } from "../ui/Menu/Menu";
import { PageHeader } from "../ui/PageHeader/PageHeader";
import { Pagination } from "../ui/Pagination/Pagination";
import { Alert, EmptyState, ErrorState, SkeletonList } from "../ui/State/State";
import { ChipCount } from "../workspace/ChipCount";
import { CancelPostingDialog, DeleteDraftDialog } from "./lazy";
import { PostingsNav } from "./PostingsNav";
import { useApplicationsOf, useKept, useMyPostingSummary, useMyPostingsPage } from "./resources";
import { usePostingChanges } from "./usePostingChanges";
import styles from "./Faculty.module.css";

type Confirming = { kind: "cancel" | "delete"; posting: ResearchPosting } | null;

/**
 * P9 — My postings (`/postings?view=mine`, plan §14): every posting of the author's, drafts
 * included, filtered by status in the address with the server's counts, 25 a page. From 1024px a
 * table (title, status, applicants, new, deadline, actions); below, each row stacks as a card with
 * its labels, so a phone never scrolls sideways. A row's actions are the moves the server lists for
 * that posting; "Cancel posting" and "Delete draft" ask first.
 *
 * Requests: the page of postings and the counts, together; then "New" (applications not reviewed
 * yet) for at most INBOX_POSTINGS open postings with applications on the page, one request each.
 * A posting whose new applications were not counted shows a dash, never a zero.
 */
export function MyPostings() {
  const [params, go] = useAddressSearch();
  const query = readMineQuery(params);
  const list = useMyPostingsPage(query.status, query.page);
  const summary = useMyPostingSummary();
  const data = useKept(list);
  const changes = usePostingChanges(summary.retry);
  const [confirming, setConfirming] = useState<Confirming>(null);
  const resultsHeading = useRef<HTMLHeadingElement>(null);

  const rows = data ? data.postings.map(changes.current).filter((posting): posting is ResearchPosting => posting !== null) : null;
  const counted = data ? inboxPostings(data.postings).read : [];
  const lists = useApplicationsOf(counted.map((posting) => posting.id));
  const newOf = (posting: ResearchPosting): ApiResource<ApplicationListResponse> | null => lists.find((slot) => slot.postingId === posting.id)?.applications ?? null;

  const counts = summary.data;
  const chips: { status: PostingStatus | null; label: string; count: number | null }[] = [
    { status: null, label: "All", count: counts ? counts.total : null },
    ...POSTING_STATUSES.map((status) => ({ status, label: postingStatusMeta(status).label, count: counts ? (counts.by_status[status] ?? 0) : null })),
  ];
  const loading = data === undefined && (list.status === "loading" || list.status === "idle");
  const failure = changes.failure && !confirming ? changes.failure : null;

  const onAction = (posting: ResearchPosting, target: PostingStatus, confirm: boolean) => {
    if (confirm) {
      changes.dismissFailure();
      setConfirming({ kind: "cancel", posting });
      return;
    }
    void changes.transition(posting, target);
  };

  return (
    <>
      <PageHeader
        title="My postings"
        description="Your projects, thesis topics and openings, drafts included: their status, applicants and deadlines."
        actions={
          <ButtonLink href={NEW_POSTING_HREF} variant="primary" leadingIcon={<Plus size={16} aria-hidden="true" />}>
            New posting
          </ButtonLink>
        }
      />
      <PostingsNav current="mine" />

      <div className={styles.toolbar}>
        <div className={styles.chips} role="group" aria-label="Filter by status">
          {chips.map((chip) => (
            <button key={chip.status ?? "ALL"} type="button" className={styles.chip} aria-pressed={chip.status === query.status} onClick={() => go(mineHref({ status: chip.status, page: 1 }))}>
              <span>
                {chip.label}
                <ChipCount count={chip.count} />
              </span>
            </button>
          ))}
        </div>
      </div>

      <section className={styles.results} aria-labelledby="mine-heading" aria-busy={list.status === "loading" || undefined}>
        <h2 id="mine-heading" ref={resultsHeading} tabIndex={-1} className={styles.resultsTitle}>
          {query.status ? `${postingStatusMeta(query.status).label} postings` : "All postings"}
        </h2>
        <p role="status" className="rc-visually-hidden">
          {changes.announcement}
        </p>
        {failure && (
          <Alert
            tone="danger"
            announce
            action={
              <Button size="sm" variant="ghost" onClick={changes.dismissFailure}>
                Dismiss
              </Button>
            }
          >
            {failure.message} It is still {postingStatusMeta(failure.posting.status).label.toLowerCase()}.
          </Alert>
        )}

        {loading ? (
          <SkeletonList rows={4} lines={2} label="Loading your postings" />
        ) : rows === null ? (
          <ErrorState title="Your postings could not be loaded" kind={list.error?.kind === "network" ? "offline" : "failed"} headingLevel={3} onRetry={list.retry} />
        ) : rows.length === 0 ? (
          query.status ? (
            <EmptyState
              variant="no-results"
              title={`You have no ${postingStatusMeta(query.status).label.toLowerCase()} postings.`}
              actions={
                <Button variant="secondary" onClick={() => go(mineHref({ status: null, page: 1 }))}>
                  Show all postings
                </Button>
              }
            />
          ) : (
            <EmptyState
              title="You have not written any postings yet."
              description="A posting starts as a draft only you can see; publish it when it is ready for researchers."
              actions={<ButtonLink href={NEW_POSTING_HREF}>Write a posting</ButtonLink>}
            />
          )
        ) : (
          <>
            <table className={styles.table} role="table">
              <caption className="rc-visually-hidden">Your postings{query.status ? `, ${postingStatusMeta(query.status).label.toLowerCase()}` : ""}</caption>
              <thead role="rowgroup">
                <tr role="row">
                  <th role="columnheader" scope="col">Posting</th>
                  <th role="columnheader" scope="col">Status</th>
                  <th role="columnheader" scope="col" className={styles.numeric}>Applicants</th>
                  <th role="columnheader" scope="col" className={styles.numeric}>New</th>
                  <th role="columnheader" scope="col">Deadline</th>
                  <th role="columnheader" scope="col">
                    <span className="rc-visually-hidden">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody role="rowgroup">
                {rows.map((posting) => (
                  <PostingRow
                    key={posting.id}
                    posting={posting}
                    newApplications={newOf(posting)}
                    inInbox={counted.some((item) => item.id === posting.id)}
                    pending={changes.pending.has(posting.id)}
                    onAction={onAction}
                    onDelete={() => {
                      changes.dismissFailure();
                      setConfirming({ kind: "delete", posting });
                    }}
                  />
                ))}
              </tbody>
            </table>
            {rows.some((posting) => posting.application_count > 0) && (
              <p className={styles.footnote}>
                New: applications not reviewed yet, counted for up to {INBOX_POSTINGS} of your most recently published open postings with applications. A dash means not counted.
              </p>
            )}
            {data && data.total > MINE_PAGE_SIZE && (
              <Pagination page={query.page} total={data.total} pageSize={MINE_PAGE_SIZE} noun="postings" label="Postings pages" onPage={(page) => go(mineHref({ ...query, page }))} />
            )}
          </>
        )}
      </section>

      {confirming?.kind === "cancel" && (
        <CancelPostingDialog
          posting={confirming.posting}
          failure={changes.failure?.posting.id === confirming.posting.id ? changes.failure.message : null}
          onClose={() => setConfirming(null)}
          onConfirm={async () => (await changes.transition(confirming.posting, "CANCELLED")) !== null}
        />
      )}
      {confirming?.kind === "delete" && (
        <DeleteDraftDialog
          posting={confirming.posting}
          failure={changes.failure?.posting.id === confirming.posting.id ? changes.failure.message : null}
          onClose={() => setConfirming(null)}
          onConfirm={async () => {
            const deleted = await changes.remove(confirming.posting);
            // Its row (and the menu that opened the dialog) is gone: the list's heading takes focus.
            if (deleted) window.setTimeout(() => resultsHeading.current?.focus(), 0);
            return deleted;
          }}
        />
      )}
    </>
  );
}

function PostingRow({
  posting,
  newApplications,
  inInbox,
  pending,
  onAction,
  onDelete,
}: {
  posting: ResearchPosting;
  newApplications: ApiResource<ApplicationListResponse> | null;
  inInbox: boolean;
  pending: boolean;
  onAction: (posting: ResearchPosting, target: PostingStatus, confirm: boolean) => void;
  onDelete: () => void;
}) {
  const titleId = `mine-${posting.id}`;
  const actions = postingActionsFor(posting);
  const items = [
    ...actions.map((action) => ({ id: action.target, label: action.label, danger: action.confirm, onSelect: () => onAction(posting, action.target, action.confirm) })),
    ...(posting.status === "DRAFT" ? [{ id: "delete", label: "Delete draft", danger: true, onSelect: onDelete }] : []),
  ];
  const fresh = newApplications?.data ? newApplications.data.applications.filter((application) => application.status === "SUBMITTED").length : null;
  const applicantsHref = inInbox ? inboxHref({ status: null, posting: posting.id }) : `/postings/${posting.id}#applications`;

  return (
    <tr role="row" className={styles.row}>
      <td role="cell" className={styles.titleCell}>
        <div className={styles.titleBlock}>
          <Link id={titleId} href={`/postings/${posting.id}`} className={styles.titleLink}>
            {posting.title}
          </Link>
          <span className={styles.facts}>{POSTING_TYPE_LABELS[posting.posting_type]}</span>
        </div>
      </td>
      <td role="cell" data-label="Status">
        <StatusBadge meta={postingStatusMeta(posting.status)} />
      </td>
      <td role="cell" data-label="Applicants" className={styles.numeric}>
        {posting.application_count > 0 ? (
          <Link href={applicantsHref}>
            {posting.application_count}
            <span className="rc-visually-hidden"> applicant{posting.application_count === 1 ? "" : "s"} to {posting.title}</span>
          </Link>
        ) : posting.opening_terms.accepts_applications ? (
          "0"
        ) : (
          <span>
            —<span className="rc-visually-hidden">Applications are not taken on the platform</span>
          </span>
        )}
      </td>
      <td role="cell" data-label="New" className={styles.numeric}>
        {posting.application_count === 0 ? (
          posting.opening_terms.accepts_applications ? (
            "0"
          ) : (
            <span>
              —<span className="rc-visually-hidden">Applications are not taken on the platform</span>
            </span>
          )
        ) : fresh !== null ? (
          <span className={fresh > 0 ? styles.strong : undefined}>{fresh}</span>
        ) : newApplications?.status === "loading" ? (
          <span className={styles.facts}>…<span className="rc-visually-hidden">Counting</span></span>
        ) : (
          <span>
            —<span className="rc-visually-hidden">Not counted</span>
          </span>
        )}
      </td>
      <td role="cell" data-label="Deadline">
        {posting.application_deadline ? <DeadlineCountdown deadline={posting.application_deadline} daysRemaining={posting.days_until_deadline} /> : <span className={styles.facts}>None</span>}
      </td>
      <td role="cell" className={styles.actionsCell}>
        {canEdit(posting) && (
          <ButtonLink href={`/postings/${posting.id}/edit`} size="sm" variant="secondary" aria-describedby={titleId}>
            Edit
          </ButtonLink>
        )}
        {items.length > 0 && <Menu trigger="Actions" triggerLabel={`Actions for ${posting.title}`} items={items} align="end" disabled={pending} />}
        {pending && (
          <span className={styles.saving} role="status">
            Saving…
          </span>
        )}
      </td>
    </tr>
  );
}
