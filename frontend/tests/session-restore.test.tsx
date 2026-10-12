/**
 * P2.7 — /workspace while the stored session is being restored.
 *
 * Before P2 the first paint showed the visitor's navigation and a small "Checking your session"
 * box; the signed-in navigation, the page and then the stat strip arrived in turn and pushed the
 * page down (CLS 0.23 at 390px). Now: the page's shape, no visitor controls, no protected data
 * and no redirect until the backend has answered; then the page keeps its layout while its own
 * data loads.
 */

import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen, waitFor, within } from "@testing-library/react";

const replace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, push: vi.fn(), back: vi.fn(), forward: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/workspace",
  useSearchParams: () => new URLSearchParams(),
}));

import WorkspacePageRoute from "../app/workspace/page";
import { SessionProvider } from "../components/auth/SessionProvider";
import { AppShell } from "../components/shell/AppShell";
import { clearActiveIdentity } from "../services/auth";
import { jsonResponse } from "./factories";
import { requestsTo, serveShell, type ShellRoutes } from "./shell-support";

const SUMMARY = {
  total_count: 4,
  active_count: 3,
  archived_count: 1,
  counts_by_status: { SAVED: 1, CONSIDERING: 1, PLANNING: 1, APPLIED: 1 },
};

function renderWorkspace() {
  return render(
    <SessionProvider>
      <AppShell>
        <WorkspacePageRoute />
      </AppShell>
    </SessionProvider>
  );
}

/** Workspace requests that never answer, or answer with an empty workspace. */
function workspace(answer: boolean): ShellRoutes["other"] {
  return (url) => {
    if (!url.includes("/api/v1/workspace")) return undefined;
    if (!answer) return new Promise<Response>(() => {});
    if (url.endsWith("/api/v1/workspace/summary")) return Promise.resolve(jsonResponse(SUMMARY));
    return Promise.resolve(jsonResponse({ items: [], total: 0 }));
  };
}

beforeEach(() => {
  replace.mockClear();
});

afterEach(() => {
  clearActiveIdentity();
  vi.unstubAllGlobals();
});

describe("while the session is being restored", () => {
  it("shows the page's shape, no visitor controls, no protected data and no redirect", async () => {
    const fetchMock = serveShell("STUDENT", { pendingSession: true, other: workspace(true) });
    renderWorkspace();
    await act(async () => undefined);

    expect(screen.getByRole("status")).toHaveTextContent("Checking your session");
    expect(screen.queryByRole("heading", { name: "Opportunity Workspace" })).not.toBeInTheDocument();
    // Nothing that is about to change: no Sign in, no visitor navigation.
    expect(screen.queryByRole("link", { name: "Sign in" })).not.toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Primary" });
    expect(nav).toHaveAttribute("aria-busy", "true");
    expect(within(nav).queryAllByRole("link")).toHaveLength(0);
    // Only the session check has been asked; nothing protected, no redirect.
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(requestsTo(fetchMock, "/api/v1/auth/me")).toBe(1);
    expect(replace).not.toHaveBeenCalled();
  });
});

describe("once the session is restored", () => {
  it("keeps the page's layout while the workspace loads, with no false zeros", async () => {
    serveShell("STUDENT", { other: workspace(false) });
    renderWorkspace();

    expect(await screen.findByRole("heading", { name: "Opportunity Workspace" })).toBeInTheDocument();
    // The stat strip is already there, waiting for its numbers.
    const strip = document.querySelector<HTMLElement>(".workspace-stats-strip")!;
    expect(strip).toHaveAttribute("aria-busy", "true");
    for (const label of ["Active Pipeline", "Applied", "Archived"]) expect(within(strip).getByText(label)).toBeInTheDocument();
    expect(strip).not.toHaveTextContent(/\d/);
    // Tab counts are unknown, not zero; the workspace is not called empty.
    const saved = screen.getByRole("button", { name: /^Saved/ });
    expect(saved).toHaveTextContent("Saved–");
    expect(saved).not.toHaveTextContent("0");
    expect(screen.queryByText("Your workspace is empty")).not.toBeInTheDocument();
  });

  it("then shows the real numbers, with one session request in all", async () => {
    const fetchMock = serveShell("STUDENT", { other: workspace(true) });
    renderWorkspace();

    expect(await screen.findByText("Your workspace is empty")).toBeInTheDocument();
    expect(document.querySelector(".workspace-stats-strip")).not.toHaveAttribute("aria-busy");
    expect(screen.getByRole("button", { name: /^Saved/ })).toHaveTextContent("Saved1");
    expect(requestsTo(fetchMock, "/api/v1/auth/me")).toBe(1);
    expect(requestsTo(fetchMock, "/notifications/unread-count")).toBe(1);
  });
});

describe("signed out", () => {
  it("is sent to sign in once, and the workspace is never asked for", async () => {
    const fetchMock = serveShell(null, { other: workspace(true) });
    renderWorkspace();

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login?next=%2Fworkspace"));
    expect(replace).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls.filter(([url]) => String(url).includes("/api/v1/workspace"))).toHaveLength(0);
    expect(screen.getByRole("status")).toHaveTextContent("Taking you to sign in");
  });
});
