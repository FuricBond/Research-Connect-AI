/**
 * P0.3 — the signed-in home: a starting point built from data the API already has.
 *
 * Signing in used to land on the 25,000px researcher profile. The home shows what needs
 * attention (tracked calls due soon, application or posting status) and the way into each area,
 * with at most three requests and nothing invented.
 */

import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn(), back: vi.fn(), forward: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/dashboard",
  useSearchParams: () => new URLSearchParams(),
}));

import DashboardPage from "../app/dashboard/page";
import { SessionProvider } from "../components/auth/SessionProvider";
import { clearActiveIdentity, storeSession } from "../services/auth";
import type { PlatformRole } from "../types/auth";
import type { WorkspaceItem, WorkspaceStatus } from "../types/workspace";
import { upcomingDeadlines } from "../utils/workspace";
import { USER_ID, jsonResponse, makeTokenResponse, makeUser } from "./factories";

const DAY = 86_400_000;
const inDays = (days: number) => new Date(Date.now() + days * DAY).toISOString();

function tracked(title: string, days: number | null, status: WorkspaceStatus = "PLANNING"): WorkspaceItem {
  return {
    id: `ws-${title}`,
    user_id: USER_ID,
    opportunity_id: `op-${title}`,
    status,
    priority: "HIGH",
    tags: [],
    notes: null,
    created_at: "2026-09-20T10:00:00+00:00",
    updated_at: "2026-09-21T10:00:00+00:00",
    status_updated_at: "2026-09-21T10:00:00+00:00",
    archived_at: null,
    allowed_transitions: [],
    opportunity: {
      id: `op-${title}`,
      title,
      opportunity_type: "CONFERENCE",
      delivery_mode: "OFFLINE",
      status: "ACTIVE",
      submission_deadline: days === null ? null : inDays(days),
      is_predatory_flag: false,
    },
  };
}

const ITEMS = [
  tracked("Workshop due in three days", 3.4),
  tracked("Conference due next month", 45),
  tracked("Accepted already", 2, "ACCEPTED"),
  tracked("Call with no deadline", null),
  tracked("Symposium due in ten days", 10.2, "APPLIED"),
];

let calls: string[] = [];
let workspaceFails = false;

function serve(role: PlatformRole) {
  calls = [];
  storeSession(makeTokenResponse({ user: makeUser({ role, full_name: "Priya Raghavan" }) }));
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      const path = url.replace(/^https?:\/\/[^/]+/, "");
      calls.push(path.split("?")[0]);
      if (path === "/api/v1/auth/me") return Promise.resolve(jsonResponse(makeUser({ role, full_name: "Priya Raghavan" })));
      if (path.startsWith("/api/v1/workspace?")) {
        if (workspaceFails) return Promise.resolve(jsonResponse({ detail: "boom" }, 500));
        return Promise.resolve(
          jsonResponse({ items: ITEMS, total_count: 5, active_count: 3, archived_count: 0, counts_by_status: {}, counts_by_priority: {} })
        );
      }
      if (path.startsWith("/api/v1/reading-list?"))
        return Promise.resolve(jsonResponse({ items: [], total_count: 5, limit: 1, offset: 0, counts_by_status: { TO_READ: 2, READING: 2, DONE: 1 } }));
      if (path === "/api/v1/postings/applications/mine/summary")
        return Promise.resolve(jsonResponse({ total: 2, active: 2, by_status: { UNDER_REVIEW: 1, SUBMITTED: 1 } }));
      if (path === "/api/v1/postings/mine/summary")
        return Promise.resolve(
          jsonResponse({ author_profile_id: "p", total: 2, by_status: {}, by_type: {}, total_applications: 3, open_accepting_applications: 1 })
        );
      return Promise.resolve(jsonResponse({ detail: `unexpected ${path}` }, 404));
    })
  );
}

function renderHome() {
  return render(
    <SessionProvider>
      <DashboardPage />
    </SessionProvider>
  );
}

afterEach(() => {
  workspaceFails = false;
  clearActiveIdentity();
});

describe("upcomingDeadlines", () => {
  it("keeps open calls due within the window, soonest first", () => {
    expect(upcomingDeadlines(ITEMS, 30).map(({ item }) => item.opportunity.title)).toEqual([
      "Workshop due in three days",
      "Symposium due in ten days",
    ]);
  });
});

describe("signed-in home", () => {
  it("greets the researcher and lists what needs attention", async () => {
    serve("STUDENT");
    renderHome();

    expect(await screen.findByRole("heading", { level: 1, name: "Welcome back, Priya Raghavan" })).toBeInTheDocument();
    const attention = screen.getByRole("region", { name: "Needs attention" });
    const deadlines = await within(attention).findAllByRole("listitem");
    expect(deadlines.map((li) => li.querySelector("a")?.textContent)).toEqual([
      "Workshop due in three days",
      "Symposium due in ten days",
    ]);
    expect(deadlines[0].textContent).toContain("3 days left");
    expect(within(attention).queryByText("Accepted already")).not.toBeInTheDocument();
    expect(within(attention).queryByText("Conference due next month")).not.toBeInTheDocument();
    expect(await within(attention).findByText(/2 applications in progress \(1 under review, 1 submitted\)/)).toBeInTheDocument();
  });

  it("uses at most three requests, made once", async () => {
    serve("STUDENT");
    renderHome();
    await screen.findByText(/applications in progress/);
    await screen.findByText("2 to read · 2 reading · 1 done.");

    const pageRequests = calls.filter((path) => path !== "/api/v1/auth/me");
    expect(pageRequests.sort()).toEqual(
      ["/api/v1/postings/applications/mine/summary", "/api/v1/reading-list", "/api/v1/workspace"].sort()
    );
  });

  it("shows faculty their postings, not applications", async () => {
    serve("FACULTY");
    renderHome();

    expect(await screen.findByText(/1 of 2 postings open for applications · 3 applications received/)).toBeInTheDocument();
    expect(calls).not.toContain("/api/v1/postings/applications/mine/summary");
    expect(screen.queryByRole("link", { name: /Find a Supervisor/ })).not.toBeInTheDocument();
  });

  it("offers administrators the administration console first", async () => {
    serve("ADMIN");
    renderHome();

    const links = within(await screen.findByRole("region", { name: "Continue your work" })).getAllByRole("link");
    expect(links[0]).toHaveAttribute("href", "/admin");
  });

  it("explains a failed section and retries it", async () => {
    workspaceFails = true;
    serve("STUDENT");
    renderHome();

    expect(await screen.findByRole("alert")).toHaveTextContent("Your tracked calls could not be loaded.");
    workspaceFails = false;
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(screen.getByText("Workshop due in three days")).toBeInTheDocument());
  });
});
