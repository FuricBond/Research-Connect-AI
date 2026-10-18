"use client";

import { Suspense, useRef, useState, type FormEvent } from "react";
import { useAddressSearch } from "../hooks/useAddressSearch";
import { useApiResource } from "../hooks/useApiResource";
import { fetchOpportunities } from "../services/api";
import type { WorkspaceItem } from "../types/workspace";
import {
  CALLS_PAGE_SIZE,
  EMPTY_CALLS,
  callsHref,
  hasCallFilters,
  parseCallsState,
  rememberCallsOrigin,
  serializeCallsState,
  toOpportunityFilters,
  type CallSort,
  type CallsState,
} from "../utils/callsState";
import { CALL_TYPES, DELIVERY_MODES, callTypeLabel, deliveryModeLabel } from "../utils/research";
import { OpportunityCard } from "./research/OpportunityCard";
import { useTrackedCalls } from "./research/trackedCalls";
import { Button } from "./ui/Button/Button";
import { Checkbox, SearchInput, Select } from "./ui/Field/Field";
import { Pagination } from "./ui/Pagination/Pagination";
import { EmptyState, ErrorState, SkeletonList } from "./ui/State/State";
import styles from "./OpportunityList.module.css";

const SORT_LABELS: Record<CallSort, string> = {
  newest: "Newest first",
  deadline: "Deadline, soonest first",
  title: "Title, A to Z",
};

function ListSkeleton() {
  return (
    <div className={styles.list}>
      <SkeletonList rows={4} lines={2} label="Loading calls for papers" announce={false} />
    </div>
  );
}

function Browse() {
  const [params, go] = useAddressSearch();
  const state = parseCallsState(params);
  const key = serializeCallsState(state);
  const resultsHeading = useRef<HTMLHeadingElement>(null);

  const list = useApiResource(`calls:${key}`, (signal) => fetchOpportunities(toOpportunityFilters(state), signal), {
    isEmpty: (data) => data.items.length === 0,
    scope: "public",
  });
  const tracked = useTrackedCalls();
  // Calls saved on this page since it loaded (the lookup is not asked again).
  const [savedHere, setSavedHere] = useState<Record<string, WorkspaceItem>>({});

  // The search box keeps what is typed; a query that arrives from the address (a link, back,
  // forward) replaces it — never a late answer.
  const [text, setText] = useState(state.q);
  const [shownQuery, setShownQuery] = useState(state.q);
  if (state.q !== shownQuery) {
    setShownQuery(state.q);
    setText(state.q);
  }

  const update = (change: Partial<CallsState>) => go(callsHref({ ...state, page: 1, ...change }));
  const submitSearch = (event: FormEvent) => {
    event.preventDefault();
    update({ q: text.trim() });
  };
  const toPage = (page: number) => {
    go(callsHref({ ...state, page }));
    resultsHeading.current?.focus();
  };

  const data = list.data;
  const total = data?.total ?? 0;
  const status =
    list.status === "loading" || list.status === "idle"
      ? "Loading calls for papers…"
      : list.status === "error"
        ? ""
        : total === 0
          ? "No calls match these filters."
          : `${total.toLocaleString("en")} call${total === 1 ? "" : "s"} for papers`;

  return (
    <div className={styles.layout}>
      <form className={styles.filters} role="search" aria-label="Calls for papers" onSubmit={submitSearch}>
        <div className={styles.searchRow}>
          <SearchInput
            label="Search calls"
            value={text}
            onChange={(event) => setText(event.target.value)}
            onClear={() => {
              setText("");
              if (state.q) update({ q: "" });
            }}
            placeholder="Title, topic or organiser"
            className={styles.search}
          />
          <Button type="submit" variant="primary">
            Search
          </Button>
        </div>
        <div className={styles.filterRow}>
          <Select label="Type" value={state.type ?? ""} onChange={(event) => update({ type: event.target.value || null })}>
            <option value="">All types</option>
            {CALL_TYPES.map((type) => (
              <option key={type} value={type}>
                {callTypeLabel(type)}
              </option>
            ))}
          </Select>
          <Select label="Attendance" value={state.mode ?? ""} onChange={(event) => update({ mode: event.target.value || null })}>
            <option value="">Any</option>
            {DELIVERY_MODES.map((mode) => (
              <option key={mode} value={mode}>
                {deliveryModeLabel(mode)}
              </option>
            ))}
          </Select>
          <Select label="Sort" value={state.sort} onChange={(event) => update({ sort: event.target.value as CallSort })}>
            {(Object.keys(SORT_LABELS) as CallSort[]).map((sort) => (
              <option key={sort} value={sort}>
                {SORT_LABELS[sort]}
              </option>
            ))}
          </Select>
          {/* The hint stays outside the label, so it describes the box without becoming its name. */}
          <div className={styles.check}>
            <Checkbox
              label="Upcoming deadlines only"
              aria-describedby="calls-upcoming-hint"
              checked={state.upcoming}
              onChange={(event) => update({ upcoming: event.target.checked })}
            />
            <p id="calls-upcoming-hint" className={styles.hint}>
              Leaves out calls whose deadline has passed and calls with no listed deadline.
            </p>
          </div>
        </div>
      </form>

      <section className={styles.results} aria-labelledby="calls-results-heading" aria-busy={list.status === "loading" || undefined}>
        <div className={styles.resultsHeader}>
          <h2 id="calls-results-heading" ref={resultsHeading} tabIndex={-1} className={styles.resultsTitle}>
            {list.status === "success" ? `${total.toLocaleString("en")} call${total === 1 ? "" : "s"}` : "Calls"}
          </h2>
          {hasCallFilters(state) && (
            <Button variant="ghost" size="sm" onClick={() => go(callsHref({ ...EMPTY_CALLS, sort: state.sort }))}>
              Clear filters
            </Button>
          )}
        </div>
        <p role="status" className="rc-visually-hidden">
          {status}
        </p>

        {(list.status === "loading" || list.status === "idle") && <ListSkeleton />}

        {list.status === "error" && (
          <ErrorState
            kind={list.error?.kind === "network" ? "offline" : "failed"}
            title="Calls for papers could not be loaded"
            description={list.error?.kind === "network" ? "The server could not be reached. Check your connection and try again." : "Something went wrong while loading. Try again in a moment."}
            onRetry={list.retry}
            announce={list.retries > 0}
          />
        )}

        {list.status === "empty" &&
          (total > 0 ? (
            <EmptyState
              variant="no-results"
              title="This page is past the last one"
              description={`There are ${total.toLocaleString("en")} calls on ${Math.ceil(total / CALLS_PAGE_SIZE)} pages.`}
              actions={<Button onClick={() => toPage(1)}>Go to the first page</Button>}
            />
          ) : hasCallFilters(state) ? (
            <EmptyState
              variant="no-results"
              title="No calls match these filters"
              description="Try other words, another type or attendance, or include calls without an upcoming deadline."
              actions={<Button onClick={() => go(callsHref({ ...EMPTY_CALLS, sort: state.sort }))}>Clear filters</Button>}
            />
          ) : (
            <EmptyState title="No calls for papers yet" description="Calls appear here as they are collected from conference and journal sources." />
          ))}

        {list.status === "success" && data && (
          <>
            <ul className={styles.list}>
              {data.items.map((call) => (
                <li key={call.id}>
                  <OpportunityCard
                    call={call}
                    saved={tracked.byCall.has(call.id) || call.id in savedHere}
                    onSaved={(item) => setSavedHere((previous) => ({ ...previous, [call.id]: item }))}
                    onFollow={() => rememberCallsOrigin(callsHref(state))}
                  />
                </li>
              ))}
            </ul>
            <Pagination page={state.page} total={total} pageSize={CALLS_PAGE_SIZE} onPage={toPage} noun="calls" label="Calls pages" />
          </>
        )}
      </section>
    </div>
  );
}

/**
 * P5 — Calls for papers (`/browse`, FRONTEND_REDESIGN_PLAN.md §11): search, type, attendance,
 * upcoming and sort — the filters the API has — with 20 calls a page, every one in the address
 * (back, forward, reload and sharing keep them). Each call links to its page, `/calls/[id]`; a
 * signed-in researcher can save it to the workspace. One request per state of the list (plus,
 * signed in, one lookup of the calls already tracked); a newer state's answer always wins.
 */
export function OpportunityList() {
  return (
    <Suspense fallback={<ListSkeleton />}>
      <Browse />
    </Suspense>
  );
}
