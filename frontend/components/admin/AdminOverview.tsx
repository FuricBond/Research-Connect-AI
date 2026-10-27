"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import type { ApiResource } from "../../hooks/useApiResource";
import { ROLE_LABELS, type PlatformRole } from "../../types/auth";
import {
  ACCOUNT_SCAN_LIMIT,
  formatRelative,
  formatWhen,
  groupRefreshes,
  HISTORY_LENGTH,
  laneLabel,
  readinessMeta,
  RESEARCH_DATA_HREF,
  ROLE_PLURALS,
  RUNS_LIMIT,
  subfieldLabel,
  USERS_HREF,
  usersHref,
} from "../../utils/admin";
import { cx } from "../../utils/cx";
import { Button } from "../ui/Button/Button";
import { Card } from "../ui/Card/Card";
import { PageHeader, SectionHeader } from "../ui/PageHeader/PageHeader";
import { Alert, SkeletonList } from "../ui/State/State";
import { ResearchDataSummary } from "./ResearchDataMonitor";
import { useAccountScan, useIngestionRuns, useReadiness, useRoleCount } from "./resources";
import styles from "./Admin.module.css";

/**
 * P10 — the administration overview (`/admin`, plan §15), the administrator's home: system health
 * (the backend's readiness), the research data monitor's summary, the latest failed refresh
 * passes, accounts by role, and deactivated accounts. Six requests, all at once (resources.ts);
 * each module loads and fails on its own and reserves its height, so one answering late or not at
 * all moves nothing else. Nothing is counted that the server did not count.
 */
export function AdminOverview() {
  return (
    <div className={styles.page}>
      <PageHeader title="Administration" description="The platform's health, its research data and its accounts." />
      <div className={styles.overview}>
        <Module id="overview-health" title="System health" reserve="health">
          <SystemHealth />
        </Module>
        <Module id="overview-research" title="Research data" reserve="research">
          <ResearchDataSummary />
        </Module>
        <Module id="overview-failed" title="Latest failed passes" reserve="list">
          <FailedPasses />
        </Module>
        <Module
          id="overview-accounts"
          title="Accounts"
          reserve="accounts"
          action={
            <Link href={USERS_HREF} className={styles.moreLink}>
              All users
            </Link>
          }
        >
          <AccountCounts />
        </Module>
        {/* Last on the page: nothing below it can move, so it keeps no height. */}
        <Module id="overview-inactive" title="Deactivated accounts" reserve="none">
          <DeactivatedAccounts />
        </Module>
      </div>
    </div>
  );
}

const RESERVE = {
  health: styles.reserveHealth,
  research: styles.reserveResearch,
  list: styles.reserveList,
  accounts: styles.reserveAccounts,
  none: undefined,
};

function Module({ id, title, action, reserve, children }: { id: string; title: string; action?: ReactNode; reserve: keyof typeof RESERVE; children: ReactNode }) {
  return (
    <section aria-labelledby={id} className={styles.module}>
      <SectionHeader id={id} title={title} action={action} />
      <Card className={cx(styles.moduleBody, RESERVE[reserve])}>{children}</Card>
    </section>
  );
}

/** Plain words and Try again; silent on the first load, announced when a retry fails too. */
function ModuleError({ children, resources }: { children: ReactNode; resources: Pick<ApiResource<unknown>, "retry" | "retries" | "status">[] }) {
  const failed = resources.filter((resource) => resource.status === "error");
  return (
    <Alert
      tone="danger"
      announce={failed.some((resource) => resource.retries > 0)}
      action={
        <Button size="sm" onClick={() => failed.forEach((resource) => resource.retry())}>
          Try again
        </Button>
      }
    >
      {children}
    </Alert>
  );
}

function forbidden(resource: ApiResource<unknown>): boolean {
  return resource.error?.kind === "forbidden" || resource.error?.kind === "unauthorized";
}

/** Placeholder rows no taller than the module's reservation, so its answer never pulls the page up. */
const WAITING = (label: string, rows = 2) => <SkeletonList rows={rows} lines={1} label={label} announce={false} />;

function SystemHealth() {
  const health = useReadiness();
  if (health.status === "loading" || health.status === "idle") return WAITING("Checking the system health", 1);
  if (health.status === "error" || !health.data) {
    return (
      <ModuleError resources={[health]}>
        {health.error?.kind === "network"
          ? "The API did not answer the health check: it may be down, or your connection may be."
          : "The health check gave no answer this page can read, so the platform's state is unknown."}
      </ModuleError>
    );
  }
  const meta = readinessMeta(health.data);
  return (
    <div className={styles.summary}>
      <p className={styles.statusLine}>
        <span className={cx(styles.dot, styles[`tone-${meta.status.tone}`])} aria-hidden="true" />
        <strong className={styles.stateWord}>{meta.status.label}</strong>
      </p>
      <dl className={styles.pairs}>
        <div>
          <dt>Database</dt>
          <dd>{meta.database}</dd>
        </div>
        <div>
          <dt>Schema</dt>
          <dd>{meta.schema}</dd>
        </div>
      </dl>
      <p className={styles.footnote}>The backend&rsquo;s readiness check: the database answers and its schema is the one this release expects.</p>
    </div>
  );
}

/** The overview lists a few; the research data page has them all. */
const FAILED_SHOWN = 3;

/** The newest failed passes among the refreshes the monitor shows, each linked to its refresh. */
function FailedPasses() {
  const runs = useIngestionRuns();
  if (runs.status === "loading" || runs.status === "idle") return WAITING("Loading the failed passes");
  if (runs.status === "error" || !runs.data) {
    if (forbidden(runs)) return <Alert tone="danger">Only administrators can see the refresh runs.</Alert>;
    return <ModuleError resources={[runs]}>The refresh runs could not be loaded.</ModuleError>;
  }
  const refreshes = groupRefreshes(runs.data.items, RUNS_LIMIT).slice(0, HISTORY_LENGTH);
  if (refreshes.length === 0) return <p className={styles.empty}>No research refresh has run yet, so nothing has failed.</p>;
  const failed = refreshes.flatMap((refresh) => refresh.passes.filter((pass) => pass.run.status === "FAILED")).sort((a, b) => (a.run.started_at < b.run.started_at ? 1 : -1));
  const window = refreshes.length === 1 ? "the last refresh" : `the last ${refreshes.length} refreshes`;
  if (failed.length === 0) return <p className={styles.empty}>No pass failed in {window}.</p>;
  return (
    <div className={styles.summary}>
      <ul className={styles.list}>
        {failed.slice(0, FAILED_SHOWN).map((pass) => (
          <li key={pass.run.id} className={styles.listItem}>
            <Link href={`${RESEARCH_DATA_HREF}#refresh-${pass.runTag}`} className={styles.itemLink}>
              {laneLabel(pass.lane)} · {subfieldLabel(pass.subfield)}
            </Link>
            <span className={styles.secondary}>
              {pass.run.error_message ? `Failed (${pass.run.error_message})` : "Failed"} · <span title={formatWhen(pass.run.started_at)}>{formatRelative(pass.run.started_at)}</span>
            </span>
          </li>
        ))}
      </ul>
      <p className={styles.footnote}>
        {failed.length} failed {failed.length === 1 ? "pass" : "passes"} in {window}
        {failed.length > FAILED_SHOWN ? `; the newest ${FAILED_SHOWN} are listed` : ""}.
      </p>
    </div>
  );
}

/** Accounts per role: each the server's total for that role (one row asked for). */
function AccountCounts() {
  const students = useRoleCount("STUDENT");
  const faculty = useRoleCount("FACULTY");
  const admins = useRoleCount("ADMIN");
  const counts: [PlatformRole, typeof students][] = [
    ["STUDENT", students],
    ["FACULTY", faculty],
    ["ADMIN", admins],
  ];
  if (counts.some(([, resource]) => resource.status === "loading" || resource.status === "idle")) return WAITING("Counting the accounts", 1);
  if (counts.some(([, resource]) => forbidden(resource))) return <Alert tone="danger">Only administrators can see the accounts.</Alert>;
  const failed = counts.filter(([, resource]) => resource.status === "error").map(([, resource]) => resource);
  const known = counts.every(([, resource]) => resource.data !== undefined);
  const total = known ? counts.reduce((sum, [, resource]) => sum + (resource.data?.total ?? 0), 0) : null;
  return (
    <div className={styles.summary}>
      {failed.length > 0 && <ModuleError resources={failed}>Some counts could not be loaded.</ModuleError>}
      <ul className={styles.counts}>
        {counts.map(([role, resource]) => (
          <li key={role}>
            <Link href={usersHref({ role })} className={styles.countLink}>
              <span className={styles.bigNumber}>
                {resource.data ? resource.data.total.toLocaleString("en") : "—"}
                {!resource.data && <span className="rc-visually-hidden">Not counted</span>}
              </span>
              <span>{ROLE_PLURALS[role]}</span>
            </Link>
          </li>
        ))}
      </ul>
      {total !== null && (
        <p className={styles.footnote}>
          {total.toLocaleString("en")} {total === 1 ? "account" : "accounts"} in all.
        </p>
      )}
    </div>
  );
}

const DEACTIVATED_SHOWN = 3;

/**
 * Deactivated accounts, from one page of the oldest ACCOUNT_SCAN_LIMIT accounts (the API cannot
 * filter by activity): exact when every account fits, otherwise said to be among those read.
 */
function DeactivatedAccounts() {
  const scan = useAccountScan();
  if (scan.status === "loading" || scan.status === "idle") return WAITING("Looking for deactivated accounts");
  if (scan.status === "error" || !scan.data) {
    if (forbidden(scan)) return <Alert tone="danger">Only administrators can see the accounts.</Alert>;
    return <ModuleError resources={[scan]}>The accounts could not be loaded.</ModuleError>;
  }
  const { users, total } = scan.data;
  const deactivated = users.filter((user) => !user.is_active);
  const complete = total <= users.length;
  const scope = complete ? "" : ` among the ${users.length.toLocaleString("en")} oldest of ${total.toLocaleString("en")} accounts`;
  if (deactivated.length === 0) return <p className={styles.empty}>No account is deactivated{scope}.</p>;
  return (
    <div className={styles.summary}>
      <p className={styles.lead}>
        {deactivated.length.toLocaleString("en")} {deactivated.length === 1 ? "account is" : "accounts are"} deactivated{scope}: they cannot sign in.
      </p>
      <ul className={styles.list}>
        {deactivated.slice(0, DEACTIVATED_SHOWN).map((user) => (
          <li key={user.id} className={styles.listItem}>
            <Link href={usersHref({ q: user.email })} className={styles.itemLink}>
              {user.full_name || user.email}
            </Link>
            <span className={styles.secondary}>
              {user.email} · {ROLE_LABELS[user.role]}
            </span>
          </li>
        ))}
      </ul>
      {deactivated.length > DEACTIVATED_SHOWN && (
        <p className={styles.footnote}>
          {deactivated.length - DEACTIVATED_SHOWN} more; find them by name or email in <Link href={USERS_HREF}>Users</Link>.
        </p>
      )}
      {!complete && <p className={styles.footnote}>Only the first {ACCOUNT_SCAN_LIMIT} accounts are read here.</p>}
    </div>
  );
}

