"use client";

import Link from "next/link";
import { Check, Loader2, RefreshCw, TriangleAlert, X } from "lucide-react";
import type { ReactNode } from "react";
import type { ApiResource } from "../../hooks/useApiResource";
import type { IngestionRunListResponse } from "../../types/admin";
import {
  formatInterval,
  formatRelative,
  formatWhen,
  groupRefreshes,
  HISTORY_LENGTH,
  laneLabel,
  monitorState,
  passStatusLabel,
  refreshStatusMeta,
  RESEARCH_DATA_HREF,
  RUNS_LIMIT,
  subfieldLabel,
  type MonitorState,
  type Refresh,
} from "../../utils/admin";
import { cx } from "../../utils/cx";
import { Button } from "../ui/Button/Button";
import { SectionHeader } from "../ui/PageHeader/PageHeader";
import { Alert, ErrorState, SkeletonList } from "../ui/State/State";
import { useIngestionRuns, useKeptFor } from "./resources";
import styles from "./Admin.module.css";

/**
 * P10 — the research data monitor (plan §15; replaces the P6.2 DataFreshnessCard). It reads
 * `GET /admin/ingestion-runs` (the newest RUNS_LIMIT passes and the refresh's own status) and
 * shows, in this order: the state in a word with what it rests on ("Healthy · refreshed 3 hours
 * ago · next in 5 hours"), stale and failing states as a prominent message, the refresh's facts,
 * the last HISTORY_LENGTH refreshes as a strip (each square a word to assistive technology, failed
 * ones linking to their row), the recent refreshes, and the latest refresh's passes by lane.
 *
 * The state follows `monitorState` (utils/admin.ts). A request that fails is never a state: the
 * page says the status could not be loaded — permission apart from the rest — and offers Try again.
 */
export function ResearchDataMonitor() {
  const runs = useIngestionRuns();
  // Checking again keeps what is shown until the new answer arrives.
  const data = useKeptFor("ingestion-runs", runs);
  const checking = runs.status === "loading" && data !== undefined;

  return (
    <div className={styles.monitor} aria-busy={checking || undefined}>
      <div className={styles.monitorBar}>
        <p className={styles.footnote}>The scheduled OpenAlex refresh: new and rising papers, then topics and embeddings for what arrived.</p>
        <Button size="sm" variant="secondary" leadingIcon={<RefreshCw size={14} aria-hidden="true" />} loading={checking} onClick={runs.retry}>
          Refresh status
        </Button>
      </div>
      {data !== undefined ? (
        <MonitorBody data={data} announce={runs.retries > 0 && runs.status !== "loading"} />
      ) : runs.status === "error" ? (
        <MonitorError resource={runs} />
      ) : (
        <SkeletonList rows={3} lines={2} label="Loading the research data status" />
      )}
    </div>
  );
}

function MonitorError({ resource }: { resource: ApiResource<IngestionRunListResponse> }) {
  const kind = resource.error?.kind;
  if (kind === "forbidden" || kind === "unauthorized") {
    return <ErrorState kind="permission" title="Only administrators can see the research data status." description="Your account is not an administrator account, so the server did not answer." />;
  }
  return (
    <ErrorState
      kind={kind === "network" ? "offline" : "failed"}
      title="The research data status could not be loaded."
      description={kind === "network" ? "The server did not answer. Check your connection and try again." : "The server could not answer just now. This says nothing about the refresh itself."}
      onRetry={resource.retry}
      announce={resource.retries > 0}
    />
  );
}

function MonitorBody({ data, announce }: { data: IngestionRunListResponse; announce: boolean }) {
  const state = monitorState(data);
  const refresh = data.research_refresh;
  const refreshes = groupRefreshes(data.items, RUNS_LIMIT);
  const latest = refreshes[0] ?? null;

  return (
    <>
      <section aria-labelledby="monitor-status" className={styles.section}>
        <SectionHeader id="monitor-status" title="Refresh status" />
        <StatusLine state={state} />
        <p role="status" className="rc-visually-hidden">
          {announce ? `Checked again: ${statusText(state)}` : ""}
        </p>
        <StateMessage state={state} />
        <div className="rc-scroll-x" role="region" aria-label="Research refresh status" tabIndex={0}>
          <table className={styles.facts}>
            <caption className="rc-visually-hidden">Research refresh status</caption>
            <tbody>
              <tr>
                <th scope="row">Scheduled refresh</th>
                <td>{refresh.enabled ? `On, ${formatInterval(refresh.interval_seconds)}` : "Off"}</td>
              </tr>
              <tr>
                <th scope="row">Last run</th>
                <td>{refresh.last_run_started_at ? <When iso={refresh.last_run_started_at} /> : "Never"}</td>
              </tr>
              <tr>
                <th scope="row">Last run status</th>
                <td>{refresh.last_run_status === null ? "No runs yet" : passStatusLabel({ status: refresh.last_run_status, error_message: null })}</td>
              </tr>
              <tr>
                <th scope="row">Papers added (24 h)</th>
                <td className={styles.number}>{refresh.works_added_last_24h.toLocaleString("en")}</td>
              </tr>
              <tr>
                <th scope="row">Next run</th>
                <td>{refresh.next_run_estimate ? <When iso={refresh.next_run_estimate} upcoming /> : "Not scheduled"}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section aria-labelledby="monitor-history" className={styles.section}>
        <SectionHeader
          id="monitor-history"
          title="Recent refreshes"
          description={refreshes.length > 0 ? `The last ${Math.min(refreshes.length, HISTORY_LENGTH)} refreshes, oldest first. A failed one links to its row.` : undefined}
        />
        {refreshes.length === 0 ? (
          <p className={styles.empty}>No research refresh has run yet.</p>
        ) : (
          <>
            <History refreshes={refreshes.slice(0, HISTORY_LENGTH)} />
            <RefreshTable refreshes={refreshes.slice(0, HISTORY_LENGTH)} />
          </>
        )}
      </section>

      {latest && (
        <section aria-labelledby="monitor-lanes" className={styles.section}>
          <SectionHeader id="monitor-lanes" title="Latest refresh by lane" description={`Started ${formatRelative(latest.startedAt)} (${formatWhen(latest.startedAt)}).`} />
          <div className="rc-scroll-x" role="region" aria-label="Passes of the latest refresh" tabIndex={0}>
            <table className={styles.runs}>
              <caption className="rc-visually-hidden">Latest refresh by lane</caption>
              <thead>
                <tr>
                  <th scope="col">Lane</th>
                  <th scope="col">Subfield</th>
                  <th scope="col" className={styles.number}>
                    Added
                  </th>
                  <th scope="col" className={styles.number}>
                    Updated
                  </th>
                  <th scope="col">Outcome</th>
                </tr>
              </thead>
              <tbody>
                {latest.passes.map(({ run, lane, subfield }) => (
                  <tr key={run.id}>
                    <td>{laneLabel(lane)}</td>
                    <td>
                      {subfieldLabel(subfield)} <span className={styles.code}>{subfield}</span>
                    </td>
                    <td className={styles.number}>{run.records_inserted.toLocaleString("en")}</td>
                    <td className={styles.number}>{run.records_updated.toLocaleString("en")}</td>
                    <td className={run.status === "FAILED" ? styles.failedText : undefined}>{passStatusLabel(run)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </>
  );
}

/** "Healthy · refreshed 3 hours ago · next in 5 hours". */
function statusText(state: MonitorState): string {
  return [state.label, ...state.facts].join(" · ");
}

/** The state's word after a dot of its tone (the word carries the meaning, not the colour). */
function StatusLine({ state }: { state: MonitorState }) {
  return (
    <p className={styles.statusLine}>
      <span className={cx(styles.dot, styles[`tone-${state.tone}`])} aria-hidden="true" />
      <strong className={styles.stateWord}>{state.label}</strong>
      {state.facts.map((fact) => (
        <span key={fact} className={styles.fact}>
          <span aria-hidden="true"> · </span>
          <span className="rc-visually-hidden">, </span>
          {fact}
        </span>
      ))}
    </p>
  );
}

/** Stale and failing are prominent; off, not yet run and unknown are explained quietly. */
function StateMessage({ state, action }: { state: MonitorState; action?: ReactNode }) {
  if (!state.explanation) return null;
  if (state.kind === "failing") return <Alert tone="danger" title="The research refresh is failing" action={action}>{state.explanation}</Alert>;
  if (state.kind === "stale") return <Alert tone="warning" title="The research data is stale" action={action}>{state.explanation}</Alert>;
  return <p className={styles.footnote}>{state.explanation}</p>;
}

/** "in 5 hours", or "Overdue: was due 2 hours ago" once the estimate has passed. */
function nextRun(iso: string): string {
  const relative = formatRelative(iso);
  return relative.startsWith("in ") || relative === "any moment" ? relative : `Overdue: was due ${relative}`;
}

function When({ iso, upcoming = false }: { iso: string; upcoming?: boolean }) {
  return (
    <span className={styles.when}>
      <span className={styles.strong}>{upcoming ? nextRun(iso) : formatRelative(iso)}</span>
      <span className={styles.secondary}>{formatWhen(iso)}</span>
    </span>
  );
}

const GLYPHS = {
  check: <Check size={14} aria-hidden="true" />,
  partial: <TriangleAlert size={14} aria-hidden="true" />,
  cross: <X size={14} aria-hidden="true" />,
  running: <Loader2 size={14} aria-hidden="true" />,
};

/** The refresh history as squares, oldest first; each says when and how it went. */
function History({ refreshes }: { refreshes: Refresh[] }) {
  const ordered = [...refreshes].reverse();
  return (
    <div className={styles.history}>
      <ol className={styles.strip} aria-label={`Last ${ordered.length} refreshes, oldest first`}>
        {ordered.map((refresh) => {
          const meta = refreshStatusMeta(refresh);
          const words = `${formatWhen(refresh.startedAt)}: ${meta.label}, ${refresh.added.toLocaleString("en")} papers added`;
          const square = cx(styles.square, styles[`square-${meta.glyph}`]);
          return (
            <li key={refresh.runTag}>
              {refresh.status === "FAILED" || refresh.failedPasses > 0 ? (
                <a href={`#refresh-${refresh.runTag}`} className={square} title={words}>
                  {GLYPHS[meta.glyph]}
                  <span className="rc-visually-hidden">{words}. Details</span>
                </a>
              ) : (
                <span className={square} title={words}>
                  {GLYPHS[meta.glyph]}
                  <span className="rc-visually-hidden">{words}</span>
                </span>
              )}
            </li>
          );
        })}
      </ol>
      <ul className={styles.legend} aria-label="Key">
        {(["check", "partial", "cross", "running"] as const).map((glyph) => (
          <li key={glyph}>
            <span className={cx(styles.square, styles.legendSquare, styles[`square-${glyph}`])} aria-hidden="true">
              {GLYPHS[glyph]}
            </span>
            {{ check: "Completed", partial: "Completed with failures", cross: "Failed", running: "Running" }[glyph]}
          </li>
        ))}
      </ul>
    </div>
  );
}

function RefreshTable({ refreshes }: { refreshes: Refresh[] }) {
  return (
    <div className="rc-scroll-x" role="region" aria-label="Recent refreshes, newest first" tabIndex={0}>
      <table className={styles.runs}>
        <caption className="rc-visually-hidden">Recent refreshes, newest first</caption>
        <thead>
          <tr>
            <th scope="col">Started</th>
            <th scope="col">Outcome</th>
            <th scope="col">Passes</th>
            <th scope="col" className={styles.number}>
              Added
            </th>
            <th scope="col" className={styles.number}>
              Updated
            </th>
          </tr>
        </thead>
        <tbody>
          {refreshes.map((refresh) => {
            const meta = refreshStatusMeta(refresh);
            const reasons = [...new Set(refresh.passes.map((pass) => pass.run.error_message).filter((reason): reason is string => Boolean(reason)))];
            return (
              <tr key={refresh.runTag} id={`refresh-${refresh.runTag}`} tabIndex={-1} className={styles.target}>
                <td>
                  <When iso={refresh.startedAt} />
                </td>
                <td className={meta.tone === "danger" ? styles.failedText : undefined}>
                  {meta.label}
                  {reasons.length > 0 && <span className={styles.secondary}>{reasons.join(", ")}</span>}
                </td>
                <td>
                  {refresh.passes.length - refresh.failedPasses} of {refresh.passes.length} completed
                </td>
                <td className={styles.number}>{refresh.added.toLocaleString("en")}</td>
                <td className={styles.number}>{refresh.updated.toLocaleString("en")}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** The overview's module: the state, the papers added in 24 h, the last and next runs. */
export function ResearchDataSummary() {
  const runs = useIngestionRuns();
  if (runs.status === "loading" || runs.status === "idle") return <SkeletonList rows={2} lines={1} label="Loading the research data status" announce={false} />;
  if (runs.status === "error" || runs.data === undefined) {
    if (runs.error?.kind === "forbidden" || runs.error?.kind === "unauthorized") return <Alert tone="danger">Only administrators can see the research data status.</Alert>;
    return (
      <Alert
        tone="danger"
        announce={runs.retries > 0}
        action={
          <Button size="sm" onClick={runs.retry}>
            Try again
          </Button>
        }
      >
        The research data status could not be loaded. This says nothing about the refresh itself.
      </Alert>
    );
  }
  const state = monitorState(runs.data);
  const refresh = runs.data.research_refresh;
  return (
    <div className={styles.summary}>
      <StatusLine state={state} />
      <StateMessage state={state} />
      <dl className={styles.pairs}>
        <div>
          <dt>Papers added (24 h)</dt>
          <dd className={styles.bigNumber}>{refresh.works_added_last_24h.toLocaleString("en")}</dd>
        </div>
        <div>
          <dt>Last run</dt>
          <dd>{refresh.last_run_started_at ? formatRelative(refresh.last_run_started_at) : "Never"}</dd>
        </div>
        <div>
          <dt>Next run</dt>
          <dd>{refresh.next_run_estimate ? nextRun(refresh.next_run_estimate) : "Not scheduled"}</dd>
        </div>
      </dl>
      <Link href={RESEARCH_DATA_HREF} className={styles.moreLink}>
        Refresh history and lanes
      </Link>
    </div>
  );
}
