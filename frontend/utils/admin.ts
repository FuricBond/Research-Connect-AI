/**
 * P10 — the administration pages' words and rules (FRONTEND_REDESIGN_PLAN.md §15).
 *
 * The research data monitor reads `GET /admin/ingestion-runs`: one row per refresh pass, labelled
 * `research_refresh:{run_tag}:{lane}:{subfield}`; the passes sharing a run_tag are one refresh
 * (backend/app/services/ingestion_run_service.py). Its state comes from those answers only, by the
 * rules in `monitorState`; nothing is assumed when the answer does not say.
 */

import type { IngestionRunListResponse, IngestionRunRead, ReadinessResponse } from "../types/admin";
import type { PlatformRole } from "../types/auth";
import type { StatusMeta, StatusTone } from "./status";

/* ── Times ─────────────────────────────────────────────────────────────── */

/** "3 hours ago" / "in 5 hours", in whole units, from `now`. */
export function formatRelative(iso: string, now: Date = new Date()): string {
  const seconds = Math.round((new Date(iso).getTime() - now.getTime()) / 1000);
  const units: [string, number][] = [
    ["day", 86_400],
    ["hour", 3_600],
    ["minute", 60],
  ];
  for (const [unit, size] of units) {
    const count = Math.trunc(Math.abs(seconds) / size);
    if (count >= 1) {
      const label = `${count} ${unit}${count === 1 ? "" : "s"}`;
      return seconds < 0 ? `${label} ago` : `in ${label}`;
    }
  }
  return seconds < 0 ? "just now" : "any moment";
}

/** "2 Oct 2026, 09:00", in the reader's time zone. */
export function formatWhen(iso: string): string {
  return new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

/** "every 8 h", "every 1.5 h". */
export function formatInterval(seconds: number): string {
  const hours = seconds / 3600;
  return `every ${Number.isInteger(hours) ? hours : hours.toFixed(1)} h`;
}

/** "3 days", "5 hours": how long, in the largest whole unit. */
function formatDuration(ms: number): string {
  const ago = formatRelative(new Date(0).toISOString(), new Date(Math.abs(ms)));
  return ago.replace(/ ago$/, "");
}

/* ── Passes, lanes, subfields ──────────────────────────────────────────── */

const LANE_LABELS: Record<string, string> = {
  newest: "Newest papers",
  rising: "Rising papers",
};

/** The lane's name in words; an unknown lane is shown as sent. */
export function laneLabel(lane: string): string {
  return LANE_LABELS[lane] ?? lane;
}

/**
 * OpenAlex subfield names for the Computer Science field (plan Q7: names, not ids). An id not
 * listed here is shown as "Subfield 1234".
 */
const SUBFIELD_NAMES: Record<string, string> = {
  "1702": "Artificial Intelligence",
  "1703": "Computational Theory and Mathematics",
  "1704": "Computer Graphics and Computer-Aided Design",
  "1705": "Computer Networks and Communications",
  "1706": "Computer Science Applications",
  "1707": "Computer Vision and Pattern Recognition",
  "1708": "Hardware and Architecture",
  "1709": "Human-Computer Interaction",
  "1710": "Information Systems",
  "1711": "Signal Processing",
  "1712": "Software",
};

export function subfieldLabel(id: string): string {
  return SUBFIELD_NAMES[id] ?? `Subfield ${id}`;
}

export interface Pass {
  run: IngestionRunRead;
  /** The refresh it belongs to; a row with another label is its own refresh. */
  runTag: string;
  lane: string;
  subfield: string;
}

/** Run tag, lane and subfield from a `research_refresh:{run_tag}:{lane}:{subfield}` label. */
export function passOf(run: IngestionRunRead): Pass {
  const parts = (run.topic ?? "").split(":");
  if (parts[0] === "research_refresh" && parts.length >= 4 && parts[1]) {
    return { run, runTag: parts[1], lane: parts[2], subfield: parts.slice(3).join(":") };
  }
  return { run, runTag: `run-${run.id}`, lane: "—", subfield: run.topic ?? "—" };
}

/** A pass's outcome in words: "Completed", "Failed (budget exhausted)", "Running". */
export function passStatusLabel(run: Pick<IngestionRunRead, "status" | "error_message">): string {
  if (run.status === "COMPLETED") return "Completed";
  if (run.status === "RUNNING") return "Running";
  if (run.status === "FAILED") return run.error_message ? `Failed (${run.error_message})` : "Failed";
  return "Unknown";
}

/* ── Refreshes ─────────────────────────────────────────────────────────── */

export type RefreshStatus = "RUNNING" | "COMPLETED" | "FAILED";

export interface Refresh {
  runTag: string;
  /** When its first pass started (as the backend's last_run_started_at). */
  startedAt: string;
  /** As the backend rules a refresh: RUNNING if a pass runs, FAILED if every pass failed. */
  status: RefreshStatus;
  passes: Pass[];
  failedPasses: number;
  added: number;
  updated: number;
}

/** backend run_status(): RUNNING if any pass is running, FAILED if every pass failed, else COMPLETED. */
function refreshStatus(passes: Pass[]): RefreshStatus {
  const statuses = new Set(passes.map((pass) => pass.run.status));
  if (statuses.has("RUNNING")) return "RUNNING";
  if (statuses.size === 1 && statuses.has("FAILED")) return "FAILED";
  return "COMPLETED";
}

/**
 * The passes in an answer grouped into refreshes, newest first. When the answer holds as many rows
 * as were asked for, the oldest refresh may be missing passes that did not fit, so it is left out
 * (unless it is the only one).
 */
export function groupRefreshes(items: readonly IngestionRunRead[], limit?: number): Refresh[] {
  const order: string[] = [];
  const byTag = new Map<string, Pass[]>();
  for (const run of items) {
    const pass = passOf(run);
    if (!byTag.has(pass.runTag)) {
      byTag.set(pass.runTag, []);
      order.push(pass.runTag);
    }
    byTag.get(pass.runTag)!.push(pass);
  }
  const refreshes = order.map((runTag): Refresh => {
    const passes = byTag.get(runTag)!;
    const startedAt = passes.reduce((first, pass) => (pass.run.started_at < first ? pass.run.started_at : first), passes[0].run.started_at);
    return {
      runTag,
      startedAt,
      status: refreshStatus(passes),
      passes: [...passes].sort((a, b) => (a.run.started_at < b.run.started_at ? -1 : a.run.started_at > b.run.started_at ? 1 : 0)),
      failedPasses: passes.filter((pass) => pass.run.status === "FAILED").length,
      added: passes.reduce((sum, pass) => sum + pass.run.records_inserted, 0),
      updated: passes.reduce((sum, pass) => sum + pass.run.records_updated, 0),
    };
  });
  refreshes.sort((a, b) => (a.startedAt < b.startedAt ? 1 : a.startedAt > b.startedAt ? -1 : 0));
  if (limit !== undefined && items.length >= limit && refreshes.length > 1) refreshes.pop();
  return refreshes;
}

/** A refresh's outcome as a status: "Completed with failures" when some passes failed. */
export function refreshStatusMeta(refresh: Pick<Refresh, "status" | "failedPasses">): StatusMeta & { glyph: "check" | "partial" | "cross" | "running" } {
  if (refresh.status === "RUNNING") return { label: "Running", tone: "info", glyph: "running" };
  if (refresh.status === "FAILED") return { label: "Failed", tone: "danger", glyph: "cross" };
  if (refresh.failedPasses > 0) return { label: "Completed with failures", tone: "warning", glyph: "partial" };
  return { label: "Completed", tone: "success", glyph: "check" };
}

/** The refresh history: the newest HISTORY_LENGTH refreshes (plan §15: the last 20 runs). */
export const HISTORY_LENGTH = 20;
/** Rows asked for: the backend's maximum, enough for 20 refreshes of up to five passes. */
export const RUNS_LIMIT = 100;

/* ── The monitor's state ───────────────────────────────────────────────── */

export type MonitorKind = "healthy" | "running" | "stale" | "failing" | "off" | "waiting" | "unknown";

export interface MonitorState {
  kind: MonitorKind;
  /** The state's word: "Healthy", "Stale", "Failing"… */
  label: string;
  tone: StatusTone;
  /** What follows the word on the status line: "refreshed 3 hours ago", "next in 5 hours". */
  facts: string[];
  /** For anything but healthy: what it means, in a sentence. */
  explanation: string | null;
  /** The newest refresh that completed, if the answer holds one. */
  lastSuccess: Refresh | null;
}

const STATE_WORDS: Record<MonitorKind, { label: string; tone: StatusTone }> = {
  healthy: { label: "Healthy", tone: "success" },
  running: { label: "Refreshing now", tone: "info" },
  stale: { label: "Stale", tone: "warning" },
  failing: { label: "Failing", tone: "danger" },
  off: { label: "Off", tone: "neutral" },
  waiting: { label: "Not run yet", tone: "neutral" },
  unknown: { label: "Unknown", tone: "muted" },
};

/**
 * The research refresh's state, from the answer alone:
 *
 *  - off       the scheduled refresh is switched off (whatever ran before);
 *  - waiting   it is on and nothing has run yet;
 *  - failing   the newest refresh failed: every one of its passes failed;
 *  - stale     no refresh completed for more than two intervals — the last success is older, or
 *              the answer's refreshes reach back further than that without one;
 *  - running   a refresh is running and the data is not stale;
 *  - healthy   the newest refresh completed (some passes may have failed: that is said) within
 *              two intervals;
 *  - unknown   the newest refresh has a status this page does not know.
 *
 * A failed request is never a state here: the page says the status could not be loaded.
 */
export function monitorState(data: IngestionRunListResponse, now: Date = new Date(), limit = RUNS_LIMIT): MonitorState {
  const refresh = data.research_refresh;
  const refreshes = groupRefreshes(data.items, limit);
  const newest = refreshes[0] ?? null;
  const lastSuccess = refreshes.find((item) => item.status === "COMPLETED") ?? null;
  const status = refresh.last_run_status ?? newest?.status ?? null;
  const interval = refresh.interval_seconds * 1000;
  const facts: string[] = [];
  const make = (kind: MonitorKind, explanation: string | null): MonitorState => ({ kind, ...STATE_WORDS[kind], facts, explanation, lastSuccess });
  const next = (): string | null => {
    if (!refresh.next_run_estimate) return null;
    const relative = formatRelative(refresh.next_run_estimate, now);
    return relative.startsWith("in ") || relative === "any moment" ? `next ${relative}` : `next run was due ${relative}`;
  };

  if (!refresh.enabled) {
    facts.push(refresh.last_run_started_at ? `last ran ${formatRelative(refresh.last_run_started_at, now)}` : "has never run");
    return make("off", "The scheduled refresh is switched off, so no new papers arrive on their own.");
  }
  if (status === null) {
    const upcoming = next();
    if (upcoming) facts.push(upcoming);
    return make("waiting", "The scheduled refresh is on; its first run has not started yet.");
  }

  const lastSuccessAge = lastSuccess ? now.getTime() - new Date(lastSuccess.startedAt).getTime() : null;
  const oldest = refreshes[refreshes.length - 1] ?? null;
  const reachesBack = oldest ? now.getTime() - new Date(oldest.startedAt).getTime() : 0;
  const stale = interval > 0 && (lastSuccessAge !== null ? lastSuccessAge > 2 * interval : reachesBack > 2 * interval);
  const sinceSuccess = lastSuccess
    ? `the last successful refresh was ${formatRelative(lastSuccess.startedAt, now)}`
    : refreshes.length === 1
      ? "no refresh has completed yet"
      : `none of the last ${refreshes.length} refreshes completed`;

  if (status === "FAILED") {
    const failedInARow = refreshes.findIndex((item) => item.status !== "FAILED");
    const count = failedInARow === -1 ? refreshes.length : failedInARow;
    const reason = newest?.passes.find((pass) => pass.run.error_message)?.run.error_message;
    if (refresh.last_run_started_at) facts.push(`last attempt ${formatRelative(refresh.last_run_started_at, now)}`);
    const upcoming = next();
    if (upcoming) facts.push(upcoming);
    const failed = count > 1 ? `The last ${count} refreshes failed` : "The last refresh failed";
    return make("failing", `${failed}${reason ? ` (${reason})` : ""}; ${sinceSuccess}.`);
  }
  if (stale) {
    if (lastSuccess) facts.push(`refreshed ${formatRelative(lastSuccess.startedAt, now)}`);
    const upcoming = next();
    if (upcoming) facts.push(upcoming);
    const age = lastSuccessAge !== null ? `for ${formatDuration(lastSuccessAge)}` : `in the last ${formatDuration(reachesBack)}`;
    return make("stale", `No refresh has completed ${age}: more than two intervals (${formatInterval(refresh.interval_seconds)}).`);
  }
  if (status === "RUNNING") {
    if (refresh.last_run_started_at) facts.push(`started ${formatRelative(refresh.last_run_started_at, now)}`);
    if (lastSuccess && lastSuccess !== newest) facts.push(`last refreshed ${formatRelative(lastSuccess.startedAt, now)}`);
    return make("running", null);
  }
  if (status === "COMPLETED") {
    facts.push(`refreshed ${formatRelative(lastSuccess?.startedAt ?? refresh.last_run_started_at ?? now.toISOString(), now)}`);
    const upcoming = next();
    if (upcoming) facts.push(upcoming);
    if (newest && newest.failedPasses > 0) facts.push(`${newest.failedPasses} of ${newest.passes.length} passes failed`);
    return make("healthy", null);
  }
  return make("unknown", "The newest refresh reported a status this page does not recognise.");
}

/* ── System health (GET /api/health/ready) ─────────────────────────────── */

const DATABASE_WORDS: Record<string, string> = {
  ok: "Answering",
  unreachable: "Not reachable",
};

const SCHEMA_WORDS: Record<string, string> = {
  current: "Up to date",
  behind: "Behind: migrations have not been applied",
  unrecognized: "Not recognised: migrated by other code",
  uninitialized: "Not set up: migrations have never run",
  unknown: "Could not be checked",
  not_checked: "Not checked (not a PostgreSQL database)",
};

export function readinessMeta(health: ReadinessResponse): { status: StatusMeta; database: string; schema: string } {
  return {
    status: health.status === "ready" ? { label: "Ready", tone: "success" } : { label: "Not ready", tone: "danger" },
    database: DATABASE_WORDS[health.database] ?? "Unknown",
    schema: SCHEMA_WORDS[health.schema] ?? "Unknown",
  };
}

/* ── Accounts ──────────────────────────────────────────────────────────── */

/** The roles in the order they are offered. */
export const ROLES: readonly PlatformRole[] = ["STUDENT", "FACULTY", "ADMIN"];

export const ROLE_PLURALS: Record<PlatformRole, string> = {
  STUDENT: "Student researchers",
  FACULTY: "Faculty",
  ADMIN: "Administrators",
};

export const USERS_HREF = "/admin/users";
export const RESEARCH_DATA_HREF = "/admin/research-data";

/** Accounts per page on the users page (plan §15). */
export const USERS_PAGE_SIZE = 25;
/** The most accounts one answer holds (backend limit): the overview reads one such page. */
export const ACCOUNT_SCAN_LIMIT = 200;

export interface UsersQuery {
  role: PlatformRole | null;
  q: string;
  page: number;
}

export function readUsersQuery(params: URLSearchParams): UsersQuery {
  const role = params.get("role");
  const page = Number.parseInt(params.get("page") ?? "1", 10);
  return {
    role: role !== null && (ROLES as readonly string[]).includes(role) ? (role as PlatformRole) : null,
    q: (params.get("q") ?? "").trim().slice(0, 255),
    page: Number.isFinite(page) && page >= 1 ? page : 1,
  };
}

export function usersHref(query: Partial<UsersQuery>): string {
  const params = new URLSearchParams();
  if (query.role) params.set("role", query.role);
  if (query.q) params.set("q", query.q);
  if (query.page && query.page > 1) params.set("page", String(query.page));
  const search = params.toString();
  return search ? `${USERS_HREF}?${search}` : USERS_HREF;
}

/** What a role change does, as the backend applies it (the role is read on every request). */
export function roleChangeConsequence(to: PlatformRole, ownAccount: boolean): string {
  const effect = "It takes effect on their next request; nothing else about the account changes.";
  if (ownAccount && to !== "ADMIN") return "This is your own account: you lose access to administration as soon as the change is made, and another administrator would have to give it back.";
  if (to === "ADMIN") return `Administrators can see and change every account, including roles, and see the platform's data. ${effect}`;
  if (to === "FACULTY") return `Faculty can write research postings and decide on applications. ${effect}`;
  return `Student researchers apply to postings and can find a supervisor; they cannot write or manage research postings or administer the platform. ${effect}`;
}
