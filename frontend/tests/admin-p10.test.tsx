/**
 * P10 — the administration pages (FRONTEND_REDESIGN_PLAN.md §15), against API answers shaped like
 * the backend's (backend/app/api/v1/admin.py, backend/app/api/health.py).
 *
 *  - The research data monitor's state follows explicit rules: healthy, running, stale (no refresh
 *    completed for more than two intervals), failing (the newest refresh failed entirely), off, not
 *    run yet, unknown — and a failed request is never one of them.
 *  - The overview's six requests go out together, once each; every module loads and fails on its
 *    own; nothing unknown is shown as a zero.
 *  - Users: 25 a page, role and search in the address, a later answer never shows an older page.
 *  - A role change asks first, naming the person and both roles: Cancel, Escape and the backdrop
 *    send nothing; confirming sends exactly one request; a refusal keeps the server's role.
 *  - The pages are refused to other roles before anything is requested, and a refused request is
 *    a permission state, not an empty one.
 */

import React from "react";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

const replace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, push: vi.fn(), back: vi.fn(), forward: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => window.location.pathname,
  useSearchParams: () => new URLSearchParams(window.location.search),
}));

import AdminPage from "../app/admin/page";
import ResearchDataPage from "../app/admin/research-data/page";
import AdminUsersPage from "../app/admin/users/page";
import { SessionProvider } from "../components/auth/SessionProvider";
import { clearActiveIdentity, storeSession } from "../services/auth";
import type { IngestionRunListResponse, IngestionRunRead, ResearchRefreshStatus } from "../types/admin";
import type { AdminUserRead, AuthenticatedUser, PlatformRole } from "../types/auth";
import { groupRefreshes, monitorState } from "../utils/admin";
import { USER_ID, jsonResponse, makeTokenResponse, makeUser } from "./factories";
import { deferred, ok, refuse } from "./p9-fixtures";
import { installDialogPolyfill } from "./shell-support";

type Handler = (path: string, init: RequestInit) => Promise<Response> | undefined;

const HOUR = 3_600_000;
const NOW = new Date("2026-10-02T12:00:00Z");
const at = (hoursAgo: number, now = NOW) => new Date(now.getTime() - hoursAgo * HOUR).toISOString();

/* ── Fixtures ─────────────────────────────────────────────────────────────── */

let passCount = 0;
function pass(tag: string, lane: "newest" | "rising", status: IngestionRunRead["status"], startedAt: string, overrides: Partial<IngestionRunRead> = {}): IngestionRunRead {
  passCount += 1;
  return {
    id: `run-${passCount}`,
    source_id: "src-1",
    status,
    topic: `research_refresh:${tag}:${lane}:1702`,
    pages_fetched: 1,
    records_parsed: 200,
    records_valid: 200,
    records_invalid: 0,
    records_inserted: status === "COMPLETED" ? 10 : 0,
    records_updated: status === "COMPLETED" ? 20 : 0,
    records_unchanged: 170,
    duplicates_detected: 0,
    potential_duplicates_detected: 0,
    records_expired: 0,
    error_message: status === "FAILED" ? "budget exhausted" : null,
    metrics_detail: null,
    started_at: startedAt,
    completed_at: status === "RUNNING" ? null : startedAt,
    ...overrides,
  };
}

/** One refresh: a newest and a rising pass, newest-first as the API lists them. */
function refresh(tag: string, hoursAgo: number, statuses: [IngestionRunRead["status"], IngestionRunRead["status"]], now = NOW): IngestionRunRead[] {
  const start = new Date(now.getTime() - hoursAgo * HOUR);
  return [pass(tag, "rising", statuses[1], new Date(start.getTime() + 60_000).toISOString()), pass(tag, "newest", statuses[0], start.toISOString())];
}

function answer(items: IngestionRunRead[], status: Partial<ResearchRefreshStatus> = {}): IngestionRunListResponse {
  const newest = groupRefreshes(items)[0];
  return {
    items,
    research_refresh: {
      enabled: true,
      interval_seconds: 8 * 3600,
      last_run_started_at: newest?.startedAt ?? null,
      last_run_status: newest?.status ?? null,
      works_added_last_24h: 37,
      next_run_estimate: newest ? new Date(new Date(newest.startedAt).getTime() + 8 * HOUR).toISOString() : null,
      ...status,
    },
  };
}

const accountId = (n: number) => `7c000000-0000-4000-8000-${String(n).padStart(12, "0")}`;
function account(n: number, overrides: Partial<AdminUserRead> = {}): AdminUserRead {
  return {
    id: accountId(n),
    email: `person${n}@university.edu`,
    full_name: `Person ${n}`,
    role: "STUDENT",
    is_active: true,
    is_verified: true,
    created_at: `2026-02-${String((n % 27) + 1).padStart(2, "0")}T10:00:00+00:00`,
    updated_at: "2026-09-01T10:00:00+00:00",
    ...overrides,
  };
}

const SELF: AdminUserRead = { id: USER_ID, email: "ada@university.edu", full_name: "Ada Lovelace", role: "ADMIN", is_active: true, is_verified: true, created_at: "2026-01-01T00:00:00+00:00", updated_at: "2026-09-01T10:00:00+00:00" };
const GRACE = account(2, { full_name: "Grace Hopper", email: "grace@navy.example", role: "STUDENT" });

/* ── A backend ────────────────────────────────────────────────────────────── */

let fetchMock: ReturnType<typeof vi.fn>;
let accounts: AdminUserRead[];
let me: AuthenticatedUser;
let readiness: () => Promise<Response>;
let runs: () => Promise<Response>;
let extra: Handler;

function serve(role: PlatformRole = "ADMIN") {
  me = makeUser({ role });
  storeSession(makeTokenResponse({ user: me }));
  fetchMock = vi.fn((url: string, init: RequestInit = {}) => {
    const method = init.method ?? "GET";
    const path = String(url).replace(/^https?:\/\/[^/]+/, "");
    if (path === "/api/v1/auth/me") return ok(me);
    const handled = extra(path, init);
    if (handled) return handled;
    if (path === "/api/health/ready") return readiness();
    if (method === "GET" && path.startsWith("/api/v1/admin/ingestion-runs?")) return runs();
    if (method === "GET" && path.startsWith("/api/v1/admin/users?")) {
      const query = new URLSearchParams(path.split("?")[1]);
      const wanted = query.get("role");
      const search = (query.get("search") ?? "").toLowerCase();
      const matching = accounts.filter((item) => (!wanted || item.role === wanted) && (!search || item.email.toLowerCase().includes(search) || item.full_name.toLowerCase().includes(search)));
      const offset = Number(query.get("offset") ?? 0);
      const limit = Number(query.get("limit") ?? 50);
      return ok({ users: matching.slice(offset, offset + limit), total: matching.length });
    }
    const patch = /^\/api\/v1\/admin\/users\/([^/?]+)$/.exec(path);
    if (method === "PATCH" && patch) {
      const index = accounts.findIndex((item) => item.id === patch[1]);
      if (index < 0) return refuse(404, "User not found.");
      accounts[index] = { ...accounts[index], ...JSON.parse(String(init.body)), updated_at: "2026-10-05T09:00:00+00:00" };
      if (accounts[index].id === me.id) me = { ...me, role: accounts[index].role, is_active: accounts[index].is_active };
      return ok(accounts[index]);
    }
    return Promise.resolve(jsonResponse({ detail: `unexpected ${method} ${path}` }, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
}

const requests = () => fetchMock.mock.calls.map(([url, init]) => `${(init as RequestInit | undefined)?.method ?? "GET"} ${String(url).replace(/^https?:\/\/[^/]+/, "")}`).filter((entry) => !entry.endsWith("/auth/me"));
const patches = () => fetchMock.mock.calls.filter(([, init]) => (init as RequestInit | undefined)?.method === "PATCH");
const bodyOf = (call: unknown[]) => JSON.parse(String((call[1] as RequestInit).body));

function renderPage(page: React.ReactElement, address: string) {
  window.history.replaceState(null, "", address);
  return render(<SessionProvider>{page}</SessionProvider>);
}

beforeAll(installDialogPolyfill);

beforeEach(() => {
  replace.mockReset();
  passCount = 0;
  extra = () => undefined;
  accounts = [SELF, GRACE, account(3, { role: "FACULTY", full_name: "Barbara Liskov" }), account(4, { is_active: false, full_name: "Alan Turing" })];
  readiness = () => ok({ status: "ready", database: "ok", schema: "current" });
  runs = () => ok(answer([...refresh("t2", 3, ["COMPLETED", "COMPLETED"], new Date()), ...refresh("t1", 11, ["FAILED", "COMPLETED"], new Date())]));
});

afterEach(() => {
  clearActiveIdentity();
  vi.unstubAllGlobals();
});

/* ── The monitor's state ──────────────────────────────────────────────────── */

describe("research data monitor state", () => {
  const state = (items: IngestionRunRead[], status: Partial<ResearchRefreshStatus> = {}) => monitorState(answer(items, status), NOW);

  it("is healthy when the newest refresh completed within two intervals, and says what it rests on", () => {
    const healthy = state([...refresh("b", 3, ["COMPLETED", "COMPLETED"]), ...refresh("a", 11, ["COMPLETED", "COMPLETED"])]);
    expect(healthy).toMatchObject({ kind: "healthy", label: "Healthy", tone: "success", explanation: null });
    expect(healthy.facts).toEqual(["refreshed 3 hours ago", "next in 5 hours"]);
  });

  it("stays healthy with a failed pass, and says so", () => {
    expect(state(refresh("b", 3, ["FAILED", "COMPLETED"])).facts).toContain("1 of 2 passes failed");
    expect(state(refresh("b", 3, ["FAILED", "COMPLETED"])).kind).toBe("healthy");
  });

  it("is stale when nothing completed for more than two intervals", () => {
    const stale = state(refresh("a", 20, ["COMPLETED", "COMPLETED"]));
    expect(stale).toMatchObject({ kind: "stale", label: "Stale", tone: "warning" });
    expect(stale.explanation).toBe("No refresh has completed for 20 hours: more than two intervals (every 8 h).");
    expect(stale.facts[0]).toBe("refreshed 20 hours ago");
    // Exactly two intervals is not yet stale.
    expect(state(refresh("a", 15.9, ["COMPLETED", "COMPLETED"])).kind).toBe("healthy");
  });

  it("is stale when the answer reaches back two intervals without one completed refresh", () => {
    const items = [...refresh("c", 1, ["RUNNING", "RUNNING"]), ...refresh("b", 9, ["FAILED", "FAILED"]), ...refresh("a", 30, ["FAILED", "FAILED"])];
    const stale = state(items);
    expect(stale.kind).toBe("stale");
    expect(stale.explanation).toBe("No refresh has completed in the last 1 day: more than two intervals (every 8 h).");
    expect(state([...refresh("b", 10, ["FAILED", "FAILED"]), ...refresh("a", 30, ["FAILED", "FAILED"])]).explanation).toBe(
      "The last 2 refreshes failed (budget exhausted); none of the last 2 refreshes completed."
    );
  });

  it("is failing when every pass of the newest refresh failed, counting the streak, before stale", () => {
    const failing = state([...refresh("c", 2, ["FAILED", "FAILED"]), ...refresh("b", 10, ["FAILED", "FAILED"]), ...refresh("a", 30, ["COMPLETED", "COMPLETED"])]);
    expect(failing).toMatchObject({ kind: "failing", label: "Failing", tone: "danger" });
    expect(failing.explanation).toBe("The last 2 refreshes failed (budget exhausted); the last successful refresh was 1 day ago.");
    expect(failing.facts[0]).toBe("last attempt 2 hours ago");
    expect(state(refresh("a", 2, ["FAILED", "FAILED"])).explanation).toBe("The last refresh failed (budget exhausted); no refresh has completed yet.");
  });

  it("is running while a refresh runs and the data is not stale", () => {
    const running = state([...refresh("b", 0.1, ["COMPLETED", "RUNNING"]), ...refresh("a", 8, ["COMPLETED", "COMPLETED"])]);
    expect(running).toMatchObject({ kind: "running", label: "Refreshing now", tone: "info" });
    expect(running.facts).toEqual(["started 6 minutes ago", "last refreshed 8 hours ago"]);
  });

  it("is off when switched off, and not run yet when nothing has run", () => {
    expect(state(refresh("a", 3, ["FAILED", "FAILED"]), { enabled: false })).toMatchObject({ kind: "off", label: "Off", facts: ["last ran 3 hours ago"] });
    expect(state([], { enabled: false, last_run_started_at: null, last_run_status: null })).toMatchObject({ kind: "off", facts: ["has never run"] });
    expect(state([], { last_run_started_at: null, last_run_status: null, next_run_estimate: null })).toMatchObject({ kind: "waiting", label: "Not run yet", facts: [] });
  });

  it("never calls an unknown status healthy", () => {
    const unknown = state(refresh("a", 3, ["COMPLETED", "COMPLETED"]), { last_run_status: "PAUSED" as never });
    expect(unknown).toMatchObject({ kind: "unknown", label: "Unknown", tone: "muted" });
  });

  it("says when the next run is overdue", () => {
    expect(state(refresh("a", 3, ["COMPLETED", "COMPLETED"]), { next_run_estimate: at(1) }).facts).toContain("next run was due 1 hour ago");
  });

  it("groups passes into refreshes and leaves out one the answer may have cut short", () => {
    const items = [...refresh("b", 3, ["COMPLETED", "COMPLETED"]), ...refresh("a", 11, ["COMPLETED", "FAILED"])];
    expect(groupRefreshes(items).map((item) => [item.runTag, item.status, item.failedPasses, item.added])).toEqual([
      ["b", "COMPLETED", 0, 20],
      ["a", "COMPLETED", 1, 10],
    ]);
    // Four rows asked for and four returned: refresh "a" may have more passes than these.
    expect(groupRefreshes(items, 4).map((item) => item.runTag)).toEqual(["b"]);
    expect(groupRefreshes(items, 5).map((item) => item.runTag)).toEqual(["b", "a"]);
  });
});

/* ── The research data page ───────────────────────────────────────────────── */

describe("research data page", () => {
  it("puts the title first, then the state and the history", async () => {
    serve();
    renderPage(<ResearchDataPage />, "/admin/research-data");
    expect(await screen.findByRole("heading", { level: 1, name: "Research data" })).toBeInTheDocument();
    expect(await screen.findByText("Healthy")).toBeInTheDocument();
    const strip = screen.getByRole("list", { name: "Last 2 refreshes, oldest first" });
    const squares = within(strip).getAllByRole("listitem");
    expect(squares).toHaveLength(2);
    // The older refresh had a failed pass: its square says so in words and links to its row.
    const link = within(squares[0]).getByRole("link");
    expect(link).toHaveTextContent(/Completed with failures, 10 papers added\. Details/);
    expect(link).toHaveAttribute("href", "#refresh-t1");
    expect(document.getElementById("refresh-t1")).toHaveTextContent("Completed with failures");
    expect(within(squares[1]).queryByRole("link")).not.toBeInTheDocument();
  });

  it("makes a stale state prominent", async () => {
    runs = () => ok(answer(refresh("a", 30, ["COMPLETED", "COMPLETED"], new Date())));
    serve();
    renderPage(<ResearchDataPage />, "/admin/research-data");
    expect(await screen.findByText("The research data is stale")).toBeInTheDocument();
    expect(screen.getByText("Stale")).toBeInTheDocument();
    expect(screen.queryByText("Healthy")).not.toBeInTheDocument();
  });

  it("makes a failing state prominent, with the failed refreshes linked", async () => {
    runs = () => ok(answer([...refresh("t2", 2, ["FAILED", "FAILED"], new Date()), ...refresh("t1", 10, ["FAILED", "FAILED"], new Date())]));
    serve();
    renderPage(<ResearchDataPage />, "/admin/research-data");
    expect(await screen.findByText("The research refresh is failing")).toBeInTheDocument();
    expect(screen.getByText(/The last 2 refreshes failed \(budget exhausted\)/)).toBeInTheDocument();
    const strip = screen.getByRole("list", { name: "Last 2 refreshes, oldest first" });
    expect(within(strip).getAllByRole("link").map((link) => link.getAttribute("href"))).toEqual(["#refresh-t1", "#refresh-t2"]);
  });

  it("shows the last 20 refreshes, oldest first", async () => {
    const items = Array.from({ length: 25 }, (_, i) => refresh(`r${i}`, 1 + i * 8, ["COMPLETED", "COMPLETED"], new Date())).flat();
    runs = () => ok(answer(items));
    serve();
    renderPage(<ResearchDataPage />, "/admin/research-data");
    const strip = await screen.findByRole("list", { name: "Last 20 refreshes, oldest first" });
    const squares = within(strip).getAllByRole("listitem");
    expect(squares).toHaveLength(20);
    expect(within(screen.getByRole("table", { name: "Recent refreshes, newest first" })).getAllByRole("row")).toHaveLength(21);
  });

  it("says in words when the next run is overdue", async () => {
    runs = () => ok(answer(refresh("a", 3, ["COMPLETED", "COMPLETED"], new Date()), { next_run_estimate: new Date(Date.now() - 90 * 60_000).toISOString() }));
    serve();
    renderPage(<ResearchDataPage />, "/admin/research-data");
    const facts = await screen.findByRole("table", { name: "Research refresh status" });
    expect(within(facts).getByRole("rowheader", { name: "Next run" }).closest("tr")).toHaveTextContent("Overdue: was due 1 hour ago");
  });

  it("a failed request is not a state: no Healthy, no 'nothing has run'", async () => {
    runs = () => refuse(500);
    serve();
    renderPage(<ResearchDataPage />, "/admin/research-data");
    expect(await screen.findByRole("heading", { name: "The research data status could not be loaded." })).toBeInTheDocument();
    expect(screen.queryByText("Healthy")).not.toBeInTheDocument();
    expect(screen.queryByText("No research refresh has run yet.")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});

/* ── The overview ─────────────────────────────────────────────────────────── */

describe("administration overview", () => {
  it("shows health, research data, failed passes, accounts by role and deactivated accounts", async () => {
    serve();
    renderPage(<AdminPage />, "/admin");
    expect(await screen.findByRole("heading", { level: 1, name: "Administration" })).toBeInTheDocument();

    const health = await screen.findByRole("region", { name: "System health" });
    await within(health).findByText("Ready");
    expect(health).toHaveTextContent("DatabaseAnswering");
    expect(health).toHaveTextContent("SchemaUp to date");

    const research = screen.getByRole("region", { name: "Research data" });
    expect(await within(research).findByText("Healthy")).toBeInTheDocument();
    expect(research).toHaveTextContent("Papers added (24 h)37");

    const failed = screen.getByRole("region", { name: "Latest failed passes" });
    const failure = await within(failed).findByRole("link", { name: "Newest papers · Artificial Intelligence" });
    expect(failure).toHaveAttribute("href", "/admin/research-data#refresh-t1");
    expect(failed).toHaveTextContent("Failed (budget exhausted)");
    expect(failed).toHaveTextContent("1 failed pass in the last 2 refreshes.");

    const counts = screen.getByRole("region", { name: "Accounts" });
    expect(await within(counts).findByRole("link", { name: /^2\s*Student researchers$/ })).toHaveAttribute("href", "/admin/users?role=STUDENT");
    expect(within(counts).getByRole("link", { name: /^1\s*Faculty$/ })).toHaveAttribute("href", "/admin/users?role=FACULTY");
    expect(within(counts).getByRole("link", { name: /^1\s*Administrators$/ })).toHaveAttribute("href", "/admin/users?role=ADMIN");
    expect(counts).toHaveTextContent("4 accounts in all.");

    const deactivated = screen.getByRole("region", { name: "Deactivated accounts" });
    expect(await within(deactivated).findByRole("link", { name: "Alan Turing" })).toHaveAttribute("href", "/admin/users?q=person4%40university.edu");
    expect(deactivated).toHaveTextContent("1 account is deactivated: they cannot sign in.");
  });

  it("asks six things, together and once each", async () => {
    serve();
    renderPage(<AdminPage />, "/admin");
    await screen.findByText("4 accounts in all.");
    await screen.findByText("Ready");
    const made = requests();
    expect(made.sort()).toEqual(
      [
        "GET /api/health/ready",
        "GET /api/v1/admin/ingestion-runs?limit=100&research_only=true",
        "GET /api/v1/admin/users?role=STUDENT&limit=1&offset=0",
        "GET /api/v1/admin/users?role=FACULTY&limit=1&offset=0",
        "GET /api/v1/admin/users?role=ADMIN&limit=1&offset=0",
        "GET /api/v1/admin/users?limit=200&offset=0",
      ].sort()
    );
  });

  it("lets each module fail on its own; the others carry on", async () => {
    readiness = () => Promise.reject(new TypeError("Failed to fetch"));
    let failCounts = true;
    extra = (path) => (failCounts && path.includes("role=FACULTY") ? refuse(500) : undefined);
    serve();
    renderPage(<AdminPage />, "/admin");

    const health = await screen.findByRole("region", { name: "System health" });
    expect(await within(health).findByText(/The API did not answer the health check/)).toBeInTheDocument();
    expect(within(health).queryByText("Ready")).not.toBeInTheDocument();

    const counts = screen.getByRole("region", { name: "Accounts" });
    await within(counts).findByText("Some counts could not be loaded.");
    // Unknown is a dash, never a zero, and no total is made up from the rest.
    expect(within(counts).getByRole("link", { name: /—\s*Not counted\s*Faculty/ })).toBeInTheDocument();
    expect(counts).not.toHaveTextContent("in all");

    expect(await within(screen.getByRole("region", { name: "Research data" })).findByText("Healthy")).toBeInTheDocument();

    failCounts = false;
    fireEvent.click(within(counts).getByRole("button", { name: "Try again" }));
    expect(await within(counts).findByText("4 accounts in all.")).toBeInTheDocument();
    // Only the failed count was asked again.
    expect(requests().filter((entry) => entry.includes("role=FACULTY"))).toHaveLength(2);
    expect(requests().filter((entry) => entry.includes("role=STUDENT"))).toHaveLength(1);
  });

  it("reads a 503 readiness answer as not ready, in words", async () => {
    readiness = () => Promise.resolve(jsonResponse({ status: "not_ready", database: "ok", schema: "behind" }, 503));
    serve();
    renderPage(<AdminPage />, "/admin");
    const health = await screen.findByRole("region", { name: "System health" });
    expect(await within(health).findByText("Not ready")).toBeInTheDocument();
    expect(health).toHaveTextContent("Behind: migrations have not been applied");
  });

  it("says deactivated accounts are counted among those read when not all fit", async () => {
    accounts = [SELF, ...Array.from({ length: 205 }, (_, i) => account(10 + i, { is_active: i !== 3 }))];
    serve();
    renderPage(<AdminPage />, "/admin");
    const deactivated = await screen.findByRole("region", { name: "Deactivated accounts" });
    expect(await within(deactivated).findByText(/1 account is deactivated among the 200 oldest of 206 accounts/)).toBeInTheDocument();
  });
});

/* ── Who may see these pages ──────────────────────────────────────────────── */

describe("administration access", () => {
  it.each([
    ["the overview", <AdminPage key="overview" />, "/admin"],
    ["users", <AdminUsersPage key="users" />, "/admin/users"],
    ["research data", <ResearchDataPage key="research" />, "/admin/research-data"],
  ])("refuses %s to faculty before anything is asked", async (_name, page, address) => {
    serve("FACULTY");
    renderPage(page, address);
    expect(await screen.findByRole("heading", { level: 1, name: "This page is for Administrator accounts." })).toBeInTheDocument();
    await act(async () => undefined);
    expect(requests()).toEqual([]);
  });

  it("shows a refused list as a permission state, not as no accounts", async () => {
    extra = (path) => (path.startsWith("/api/v1/admin/users?") ? refuse(403, "Administrator role required") : undefined);
    serve();
    renderPage(<AdminUsersPage />, "/admin/users");
    expect(await screen.findByRole("heading", { name: "Only administrators can see the accounts." })).toBeInTheDocument();
    expect(screen.queryByText(/There are no accounts/)).not.toBeInTheDocument();
    expect(screen.queryByText("Administrator role required")).not.toBeInTheDocument();
  });
});

/* ── Users ────────────────────────────────────────────────────────────────── */

describe("users page", () => {
  const table = () => screen.getByRole("table");
  const rowsOf = () => within(table()).getAllByRole("row").slice(1);
  const rowOf = (name: string) => rowsOf().find((row) => within(row).queryByText(name, { exact: false }) !== null)!;

  it("lists the accounts with their roles, status and own account marked", async () => {
    serve();
    renderPage(<AdminUsersPage />, "/admin/users");
    expect(await screen.findByRole("heading", { level: 1, name: "Users" })).toBeInTheDocument();
    await screen.findByText("Grace Hopper");
    expect(rowsOf()).toHaveLength(4);
    expect(rowOf("Ada Lovelace")).toHaveTextContent("(you)");
    expect(within(rowOf("Grace Hopper")).getByRole("button", { name: "Role of Grace Hopper: Student researcher. Change the role" })).toBeInTheDocument();
    expect(rowOf("Barbara Liskov")).toHaveTextContent("Faculty");
    expect(rowOf("Alan Turing")).toHaveTextContent("Deactivated");
    expect(rowOf("Grace Hopper")).toHaveTextContent("grace@navy.example");
    expect(screen.getByText("4 accounts")).toBeInTheDocument();
  });

  it("pages 25 at a time, with the page in the address, and stops at the ends", async () => {
    accounts = [SELF, ...Array.from({ length: 29 }, (_, i) => account(10 + i))];
    serve();
    renderPage(<AdminUsersPage />, "/admin/users");
    await screen.findByText("Showing 1–25 of 30 accounts");
    expect(rowsOf()).toHaveLength(25);
    expect(screen.getByRole("button", { name: "Previous page" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    await screen.findByText("Showing 26–30 of 30 accounts");
    expect(window.location.search).toBe("?page=2");
    expect(rowsOf()).toHaveLength(5);
    expect(requests()).toContain("GET /api/v1/admin/users?limit=25&offset=25");
    expect(screen.getByRole("button", { name: "Next page" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Previous page" }));
    await screen.findByText("Showing 1–25 of 30 accounts");
    expect(window.location.search).toBe("");
  });

  it("opens a shared address as it was: role, search and page", async () => {
    accounts = [SELF, ...Array.from({ length: 30 }, (_, i) => account(10 + i, { role: "FACULTY", full_name: `Ada Faculty ${i}` }))];
    serve();
    renderPage(<AdminUsersPage />, "/admin/users?role=FACULTY&q=ada&page=2");
    await screen.findByText("Showing 26–30 of 30 accounts");
    expect(requests()).toEqual(["GET /api/v1/admin/users?role=FACULTY&search=ada&limit=25&offset=25"]);
    expect(screen.getByRole("searchbox", { name: "Search by name or email" })).toHaveValue("ada");
    expect(screen.getByRole("button", { name: "Faculty" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("heading", { level: 2, name: "Accounts matching “ada”, faculty" })).toBeInTheDocument();
  });

  it("says when a page is past the last one, and leads to the last", async () => {
    serve();
    renderPage(<AdminUsersPage />, "/admin/users?page=9");
    expect(await screen.findByText("There is no page 9 of these accounts.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Go to page 1" }));
    await screen.findByText("Grace Hopper");
    expect(window.location.search).toBe("");
  });

  it("searches on submit and filters by role, starting again at page 1", async () => {
    serve();
    renderPage(<AdminUsersPage />, "/admin/users?page=1");
    await screen.findByText("Grace Hopper");
    fireEvent.change(screen.getByRole("searchbox", { name: "Search by name or email" }), { target: { value: "grace" } });
    // Typing asks for nothing.
    expect(requests()).toHaveLength(1);
    fireEvent.submit(screen.getByRole("search", { name: "Accounts" }));
    await waitFor(() => expect(rowsOf()).toHaveLength(1));
    expect(window.location.search).toBe("?q=grace");

    fireEvent.click(screen.getByRole("button", { name: "Administrators" }));
    expect(await screen.findByText("No accounts match “grace” among administrators.")).toBeInTheDocument();
    expect(window.location.search).toBe("?role=ADMIN&q=grace");
  });

  it("never shows an older answer for a newer search", async () => {
    const slow = deferred();
    extra = (path) => (path.includes("search=old") ? slow.promise : undefined);
    serve();
    renderPage(<AdminUsersPage />, "/admin/users?q=old");
    await screen.findByText("Loading the accounts");
    fireEvent.change(screen.getByRole("searchbox", { name: "Search by name or email" }), { target: { value: "grace" } });
    fireEvent.submit(screen.getByRole("search", { name: "Accounts" }));
    await screen.findByText("Grace Hopper");
    await act(async () => slow.resolve(jsonResponse({ users: [account(9, { full_name: "Old Answer" })], total: 1 })));
    expect(screen.queryByText("Old Answer")).not.toBeInTheDocument();
    expect(rowsOf()).toHaveLength(1);
  });

  async function openRoleChange(to: string) {
    const trigger = within(rowOf("Grace Hopper")).getByRole("button", { name: /^Role of Grace Hopper/ });
    fireEvent.click(trigger);
    fireEvent.click(screen.getByRole("menuitem", { name: to }));
    return { trigger, dialog: await screen.findByRole("dialog") };
  }

  it("asks before a role change, naming the person and both roles; dismissing sends nothing", async () => {
    serve();
    renderPage(<AdminUsersPage />, "/admin/users");
    await screen.findByText("Grace Hopper");

    let { trigger, dialog } = await openRoleChange("Faculty");
    expect(dialog).toHaveAccessibleName("Change Grace Hopper’s role from Student researcher to Faculty?");
    expect(dialog).toHaveTextContent("grace@navy.example");
    expect(dialog).toHaveTextContent("Faculty can write research postings");
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await waitFor(() => expect(trigger).toHaveFocus());

    ({ dialog } = await openRoleChange("Faculty"));
    fireEvent(dialog, new Event("cancel", { cancelable: true })); // Escape
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    ({ dialog } = await openRoleChange("Administrator"));
    fireEvent.click(dialog); // the backdrop
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    ({ dialog } = await openRoleChange("Faculty"));
    fireEvent.click(within(dialog).getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    expect(patches()).toHaveLength(0);
    expect(rowOf("Grace Hopper")).toHaveTextContent("Student researcher");
  });

  it("confirming sends exactly one change, even clicked twice, and shows the role the server answers", async () => {
    const answerLater = deferred();
    extra = (path, init) => (init.method === "PATCH" ? answerLater.promise : undefined);
    serve();
    renderPage(<AdminUsersPage />, "/admin/users");
    await screen.findByText("Grace Hopper");

    const { dialog } = await openRoleChange("Faculty");
    const confirm = within(dialog).getByRole("button", { name: "Make Grace faculty" });
    fireEvent.click(confirm);
    fireEvent.click(confirm);
    expect(patches()).toHaveLength(1);
    expect(String(patches()[0][0])).toMatch(new RegExp(`/api/v1/admin/users/${GRACE.id}$`));
    expect(bodyOf(patches()[0])).toEqual({ role: "FACULTY" });
    // Nothing is shown before the server agrees.
    expect(rowOf("Grace Hopper")).toHaveTextContent("Student researcher");
    expect(within(dialog).getByRole("button", { name: "Cancel" })).toBeDisabled();

    await act(async () => answerLater.resolve(jsonResponse({ ...GRACE, role: "FACULTY", updated_at: "2026-10-05T09:00:00+00:00" })));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(within(rowOf("Grace Hopper")).getByRole("button", { name: "Role of Grace Hopper: Faculty. Change the role" })).toBeInTheDocument();
    expect(screen.getByText("Grace Hopper is now faculty.")).toHaveAttribute("role", "status");
    expect(patches()).toHaveLength(1);
  });

  it("keeps the server's role when the change is refused, and says why", async () => {
    accounts = [SELF, account(5, { full_name: "Only Admin", role: "ADMIN" }), GRACE];
    extra = (path, init) => (init.method === "PATCH" ? refuse(409, "Cannot demote or deactivate the last active administrator.") : undefined);
    serve();
    renderPage(<AdminUsersPage />, "/admin/users");
    await screen.findByText("Only Admin");

    fireEvent.click(within(rowOf("Only Admin")).getByRole("button", { name: /^Role of Only Admin/ }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Student researcher" }));
    const dialog = await screen.findByRole("dialog", { name: "Change Only Admin’s role from Administrator to Student researcher?" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Make Only student researcher" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Every platform needs an active administrator");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(within(rowOf("Only Admin")).getByRole("button", { name: "Role of Only Admin: Administrator. Change the role" })).toBeInTheDocument();
    expect(screen.queryByText(/is now/)).not.toBeInTheDocument();
    expect(screen.queryByText("Cannot demote or deactivate the last active administrator.")).not.toBeInTheDocument();

    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(await screen.findByText(/Nothing about Only Admin was changed\./)).toBeInTheDocument();
    expect(patches()).toHaveLength(1);
  });

  it("a network failure keeps the role too", async () => {
    extra = (path, init) => (init.method === "PATCH" ? Promise.reject(new TypeError("Failed to fetch")) : undefined);
    serve();
    renderPage(<AdminUsersPage />, "/admin/users");
    await screen.findByText("Grace Hopper");
    const { dialog } = await openRoleChange("Administrator");
    fireEvent.click(within(dialog).getByRole("button", { name: "Make Grace administrator" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("The change could not be sent. Check your connection and try again.");
    expect(rowOf("Grace Hopper")).toHaveTextContent("Student researcher");
  });

  it("changing one's own role says what is lost, then reads the session again", async () => {
    accounts = [SELF, account(5, { full_name: "Other Admin", role: "ADMIN" })];
    serve();
    renderPage(<AdminUsersPage />, "/admin/users");
    await screen.findByText("Other Admin");
    const sessionChecks = () => fetchMock.mock.calls.filter(([url]) => String(url).endsWith("/auth/me")).length;
    const before = sessionChecks();

    fireEvent.click(within(rowOf("Ada Lovelace")).getByRole("button", { name: /^Role of Ada Lovelace/ }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Faculty" }));
    const dialog = await screen.findByRole("dialog", { name: "Change your own role from Administrator to Faculty?" });
    expect(dialog).toHaveTextContent("you lose access to administration");
    fireEvent.click(within(dialog).getByRole("button", { name: "Make me faculty" }));

    expect(await screen.findByRole("heading", { level: 1, name: "This page is for Administrator accounts." })).toBeInTheDocument();
    expect(sessionChecks()).toBe(before + 1);
    expect(patches()).toHaveLength(1);
  });

  it("deactivates at once with Undo, and Undo sends the reverse", async () => {
    serve();
    renderPage(<AdminUsersPage />, "/admin/users");
    await screen.findByText("Grace Hopper");
    fireEvent.click(within(rowOf("Grace Hopper")).getByRole("button", { name: "Actions for Grace Hopper" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Deactivate account" }));
    expect(await screen.findByText("Grace Hopper is deactivated: signed out everywhere and unable to sign in.")).toBeInTheDocument();
    expect(rowOf("Grace Hopper")).toHaveTextContent("Deactivated");
    expect(bodyOf(patches()[0])).toEqual({ is_active: false });

    fireEvent.click(screen.getByRole("button", { name: "Undo" }));
    expect(await screen.findByText(/^Undone: Grace Hopper can sign in again/)).toBeInTheDocument();
    expect(bodyOf(patches()[1])).toEqual({ is_active: true });
    expect(rowOf("Grace Hopper")).toHaveTextContent("Active");
    expect(screen.queryByRole("button", { name: "Undo" })).not.toBeInTheDocument();
  });

  it("asks before deactivating one's own account; Cancel sends nothing", async () => {
    serve();
    renderPage(<AdminUsersPage />, "/admin/users");
    await screen.findByText("Grace Hopper");
    fireEvent.click(within(rowOf("Ada Lovelace")).getByRole("button", { name: "Actions for Ada Lovelace" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Deactivate my account" }));
    const dialog = await screen.findByRole("dialog", { name: "Deactivate your own account?" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(patches()).toHaveLength(0);
  });
});
