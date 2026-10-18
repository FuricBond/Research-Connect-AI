"use client";

import Link from "next/link";
import { useState } from "react";
import { useAddressSearch } from "../../hooks/useAddressSearch";
import type { WorkspaceItem, WorkspaceStatus } from "../../types/workspace";
import { workspaceStatusMeta } from "../../utils/status";
import { Button } from "../ui/Button/Button";
import { Dialog } from "../ui/Dialog/Dialog";
import { SearchInput, Select } from "../ui/Field/Field";
import { PageHeader } from "../ui/PageHeader/PageHeader";
import { Alert, EmptyState, ErrorState, SkeletonList } from "../ui/State/State";
import { useWorkspaceList, type WorkspaceQuery } from "./useWorkspaceList";
import { ChipCount } from "./ChipCount";
import { WorkspaceNav } from "./WorkspaceNav";
import { WorkspaceRow } from "./WorkspaceRow";
import styles from "./Workspace.module.css";

const STATUSES: WorkspaceStatus[] = ["SAVED", "CONSIDERING", "PLANNING", "APPLIED", "ACCEPTED", "REJECTED", "ARCHIVED"];
const SORTS: { value: WorkspaceQuery["sort"]; label: string }[] = [
  { value: "deadline", label: "Deadline" },
  { value: "priority", label: "Priority" },
  { value: "updated", label: "Recently updated" },
];

/** `/workspace?status=PLANNING&sort=priority&q=retrieval`: defaults are left out of the address. */
export function readWorkspaceQuery(params: URLSearchParams): WorkspaceQuery {
  const status = params.get("status");
  const sort = params.get("sort");
  return {
    status: STATUSES.includes(status as WorkspaceStatus) ? (status as WorkspaceStatus) : null,
    sort: sort === "priority" || sort === "updated" ? sort : "deadline",
    search: params.get("q") ?? "",
  };
}

export function workspaceHref(query: WorkspaceQuery): string {
  const params = new URLSearchParams();
  if (query.status) params.set("status", query.status);
  if (query.sort !== "deadline") params.set("sort", query.sort);
  if (query.search.trim()) params.set("q", query.search.trim());
  const text = params.toString();
  return `/workspace${text ? `?${text}` : ""}`;
}

/**
 * P7 — /workspace (plan §13, list first): the calls you track, filtered by status chips with
 * their counts, searched and sorted (deadline first by default), all in the address. Each row's
 * status is a menu of the moves the server allows, applied at once and rolled back if the server
 * refuses (useWorkspaceList). Two requests per load: the list and the counts.
 */
export function WorkspacePage() {
  const [params, go] = useAddressSearch();
  const query = readWorkspaceQuery(params);
  const { list, summary, items, pending, failed, announcement, changeStatus, update, remove, retryFailed, dismissFailed } = useWorkspaceList(query);
  const [searchDraft, setSearchDraft] = useState(query.search);
  const [removing, setRemoving] = useState<WorkspaceItem | null>(null);
  const [removeFailed, setRemoveFailed] = useState(false);

  const counts = summary.data;
  const chips: { status: WorkspaceStatus | null; label: string; count: number | null }[] = [
    { status: null, label: "All", count: counts ? counts.total_count : null },
    ...STATUSES.map((status) => ({
      status,
      label: workspaceStatusMeta(status).label,
      count: counts ? (status === "ARCHIVED" ? counts.archived_count : (counts.counts_by_status[status] ?? 0)) : null,
    })),
  ];
  const filtered = query.status !== null || query.search.trim() !== "";
  const loading = (list.status === "loading" || list.status === "idle") && items === null;

  return (
    <>
      <PageHeader title="Workspace" description="The calls you are tracking: what is due next and what your next step is." />
      <WorkspaceNav current="calls" />

      <div className={styles.toolbar}>
        <div className={styles.chips} role="group" aria-label="Filter by status">
          {chips.map((chip) => {
            const active = chip.status === query.status;
            return (
              <button
                key={chip.status ?? "ALL"}
                type="button"
                className={styles.chip}
                aria-pressed={active}
                onClick={() => go(workspaceHref({ ...query, status: chip.status }))}
              >
                <span>
                  {chip.label}
                  <ChipCount count={chip.count} />
                </span>
              </button>
            );
          })}
        </div>
        <div className={styles.filterRow}>
          <form
            role="search"
            aria-label="Search your workspace"
            className={styles.search}
            onSubmit={(event) => {
              event.preventDefault();
              go(workspaceHref({ ...query, search: searchDraft }));
            }}
          >
            <SearchInput
              label="Search titles and notes"
              value={searchDraft}
              onChange={(event) => setSearchDraft(event.target.value)}
              onClear={() => {
                setSearchDraft("");
                go(workspaceHref({ ...query, search: "" }));
              }}
            />
            <Button type="submit" variant="secondary">
              Search
            </Button>
          </form>
          <Select label="Sort by" value={query.sort} onChange={(event) => go(workspaceHref({ ...query, sort: event.target.value as WorkspaceQuery["sort"] }))}>
            {SORTS.map((sort) => (
              <option key={sort.value} value={sort.value}>
                {sort.label}
              </option>
            ))}
          </Select>
        </div>
      </div>

      <section className={styles.results} aria-labelledby="workspace-results-heading" aria-busy={list.status === "loading" || undefined}>
        <h2 id="workspace-results-heading" className={styles.resultsTitle}>
          {query.status ? workspaceStatusMeta(query.status).label : "All calls"}
        </h2>
        <p role="status" className="rc-visually-hidden">
          {announcement}
        </p>
        {failed && (
          <Alert
            tone="danger"
            announce
            title={`${failed.title} could not be moved to ${workspaceStatusMeta(failed.target).label.toLowerCase()}.`}
            action={
              <span className={styles.alertActions}>
                <Button size="sm" variant="secondary" onClick={retryFailed}>
                  Try again
                </Button>
                <Button size="sm" variant="ghost" onClick={dismissFailed}>
                  Dismiss
                </Button>
              </span>
            }
          >
            Its status is back to what the server last confirmed.
          </Alert>
        )}

        {loading ? (
          <SkeletonList rows={4} lines={2} label="Loading your workspace" />
        ) : list.status === "error" && items === null ? (
          <ErrorState title="Your workspace could not be loaded" kind={list.error?.kind === "network" ? "offline" : "failed"} onRetry={list.retry} />
        ) : !items || items.length === 0 ? (
          filtered ? (
            <EmptyState
              variant="no-results"
              title="No calls match."
              description="Try another status or clear the search."
              actions={
                <Button variant="secondary" onClick={() => go("/workspace")}>
                  Clear filters
                </Button>
              }
            />
          ) : (
            <EmptyState
              title="Your workspace is empty."
              description="Save calls for papers to track their deadlines and your submissions here."
              actions={
                <Link href="/browse" className={styles.nextStep}>
                  Browse calls for papers
                </Link>
              }
            />
          )
        ) : (
          <ul className={styles.list}>
            {items.map((item) => (
              <WorkspaceRow
                key={item.id}
                item={item}
                saving={pending.has(item.id)}
                onStatus={changeStatus}
                onUpdate={update}
                onRemove={(target) => {
                  setRemoveFailed(false);
                  setRemoving(target);
                }}
              />
            ))}
          </ul>
        )}
      </section>

      <Dialog
        open={removing !== null}
        onClose={() => setRemoving(null)}
        size="sm"
        title={`Remove "${removing?.opportunity?.title ?? "this call"}" from your workspace?`}
        footer={
          <>
            <Button variant="secondary" onClick={() => setRemoving(null)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              loading={removing !== null && pending.has(removing.id)}
              onClick={async () => {
                if (!removing) return;
                const ok = await remove(removing);
                if (ok) setRemoving(null);
                else setRemoveFailed(true);
              }}
            >
              Remove
            </Button>
          </>
        }
      >
        <p>
          Its notes, tags, tasks, submissions and their documents are deleted with it, and collaborators lose access. This cannot be undone; to keep them, archive it
          instead.
        </p>
        {removeFailed && (
          <Alert tone="danger" announce>
            It could not be removed. Try again.
          </Alert>
        )}
      </Dialog>
    </>
  );
}
