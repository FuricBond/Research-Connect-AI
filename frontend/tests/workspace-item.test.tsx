/**
 * P7 — the workspace item page (plan §13): `/workspace/[id]` with tabs Overview, Tasks,
 * Submission, Members and Activity.
 *
 * The tab is in the address (`?tab=tasks`), so a link opens it and back and forward follow it. A
 * tab asks for its data the first time it opens and keeps it, so going back to it asks nothing.
 * The item is read by id, so a collaborator sees an item shared with them, and what they can
 * change follows their role. The old submission page redirects to the Submission tab.
 */

import React, { Suspense } from "react";
import { act, configure, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// The tabs other than Overview load their code on first opening (lazyTabs.tsx); on a busy machine
// that can take longer than the default second.
configure({ asyncUtilTimeout: 5000 });

const redirect = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn(), back: vi.fn(), forward: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => window.location.pathname,
  useSearchParams: () => new URLSearchParams(window.location.search),
  redirect,
}));

import SubmissionRedirect from "../app/workspace/[id]/submission/page";
import { SessionProvider } from "../components/auth/SessionProvider";
import { ItemPage, readItemTab } from "../components/workspace/item/ItemPage";
import { clearActiveIdentity, storeSession } from "../services/auth";
import type { WorkspaceMember } from "../types/collaboration";
import type { WorkspaceItem } from "../types/workspace";
import { USER_ID, jsonResponse, makeTokenResponse, makeUser } from "./factories";
import { ITEM_ID, OWNER_ID, makeItem, makeMember, ok } from "./p7-fixtures";

let fetchMock: ReturnType<typeof vi.fn>;
let item: WorkspaceItem;
let members: WorkspaceMember[];

const EMPTY = { items: [], total_count: 0 };

function serve() {
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    const path = new URL(url).pathname;
    if (path.endsWith("/api/v1/auth/me")) return ok(makeUser());
    if (method !== "GET") return Promise.resolve(jsonResponse({ detail: `unexpected ${method} ${url}` }, 404));
    if (path === `/api/v1/workspace/${ITEM_ID}`) return ok(item);
    if (path === `/api/v1/workspaces/${ITEM_ID}/members`) return ok({ items: members, total_count: members.length });
    if (path === `/api/v1/workspaces/${ITEM_ID}/tasks`) return ok(EMPTY);
    if (path === `/api/v1/workspaces/${ITEM_ID}/invitations`) return ok(EMPTY);
    if (path === `/api/v1/workspaces/${ITEM_ID}/activity`) return ok(EMPTY);
    if (path === `/api/v1/workspace/${ITEM_ID}/submissions`) return ok({ items: [], total_count: 0, counts_by_status: {}, counts_by_type: {} });
    return Promise.resolve(jsonResponse({ detail: `unexpected ${method} ${url}` }, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
}

const gets = (part: string) => fetchMock.mock.calls.filter(([url, init]) => new URL(String(url)).pathname.endsWith(part) && ((init as RequestInit)?.method ?? "GET") === "GET").length;

function page(id = ITEM_ID) {
  return (
    <SessionProvider>
      <Suspense fallback={null}>
        <ItemPage id={id} />
      </Suspense>
    </SessionProvider>
  );
}

function open(address: string, id = ITEM_ID) {
  window.history.replaceState(null, "", address);
  return render(page(id));
}

beforeEach(() => {
  storeSession(makeTokenResponse());
  item = makeItem();
  members = [];
  serve();
});

afterEach(() => clearActiveIdentity());

describe("the tab in the address", () => {
  it("reads ?tab=, defaults to Overview and keeps the old Invitations tab working", () => {
    expect(readItemTab(new URLSearchParams(""))).toBe("overview");
    expect(readItemTab(new URLSearchParams("tab=tasks"))).toBe("tasks");
    expect(readItemTab(new URLSearchParams("tab=invitations"))).toBe("members");
    expect(readItemTab(new URLSearchParams("tab=nonsense"))).toBe("overview");
  });

  it("opens the tab a link names and asks only for that tab's data", async () => {
    open(`/workspace/${ITEM_ID}?tab=tasks`);
    expect(await screen.findByRole("heading", { level: 1, name: "International Conference on Information Retrieval Systems" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Tasks" })).toHaveAttribute("aria-selected", "true");
    expect(await screen.findByRole("heading", { level: 2, name: "Tasks" })).toBeInTheDocument();
    expect(screen.getByRole("tabpanel", { name: "Tasks" })).toBeVisible();

    await waitFor(() => expect(gets("/tasks")).toBe(1));
    expect(gets(`/workspace/${ITEM_ID}`)).toBe(1);
    expect(gets("/activity")).toBe(0);
    expect(gets("/submissions")).toBe(0);
    expect(gets("/invitations")).toBe(0);
  });

  it("records each tab in the address and asks nothing again when a tab is reopened", async () => {
    open(`/workspace/${ITEM_ID}`);
    const tablist = await screen.findByRole("tablist", { name: "Workspace item" });
    expect(within(tablist).getAllByRole("tab").map((tab) => tab.textContent)).toEqual(["Overview", "Tasks", "Submission", "Members", "Activity"]);
    expect(screen.getByRole("tab", { name: "Overview" })).toHaveAttribute("aria-selected", "true");

    fireEvent.click(screen.getByRole("tab", { name: "Tasks" }));
    expect(window.location.search).toBe("?tab=tasks");
    await waitFor(() => expect(gets("/tasks")).toBe(1));

    fireEvent.click(screen.getByRole("tab", { name: "Activity" }));
    expect(window.location.search).toBe("?tab=activity");
    await waitFor(() => expect(gets("/activity")).toBe(1));

    fireEvent.click(screen.getByRole("tab", { name: "Tasks" }));
    expect(screen.getByRole("tabpanel", { name: "Tasks" })).toBeVisible();
    // The Activity panel stays mounted but hidden; nothing was asked again.
    expect(document.getElementById("item-panel-activity")).not.toBeVisible();
    expect(gets("/tasks")).toBe(1);
    expect(gets("/activity")).toBe(1);
    expect(gets(`/workspace/${ITEM_ID}`)).toBe(1);

    fireEvent.click(screen.getByRole("tab", { name: "Overview" }));
    expect(window.location.search).toBe("");
  });

  it("follows the address on back and forward", async () => {
    const view = open(`/workspace/${ITEM_ID}`);
    fireEvent.click(await screen.findByRole("tab", { name: "Members" }));
    expect(window.location.search).toBe("?tab=members");

    // The router re-renders the page on popstate; the page shows what the address says.
    await act(async () => {
      window.history.back();
      await new Promise((resolve) => window.addEventListener("popstate", resolve, { once: true }));
    });
    view.rerender(page());
    expect(window.location.search).toBe("");
    expect(screen.getByRole("tab", { name: "Overview" })).toHaveAttribute("aria-selected", "true");

    await act(async () => {
      window.history.forward();
      await new Promise((resolve) => window.addEventListener("popstate", resolve, { once: true }));
    });
    view.rerender(page());
    expect(screen.getByRole("tab", { name: "Members" })).toHaveAttribute("aria-selected", "true");
  });

  it("moves between tabs with the arrow keys, one Tab stop for the list", async () => {
    open(`/workspace/${ITEM_ID}`);
    const overview = await screen.findByRole("tab", { name: "Overview" });
    expect(overview).toHaveAttribute("tabindex", "0");
    expect(screen.getByRole("tab", { name: "Tasks" })).toHaveAttribute("tabindex", "-1");
    fireEvent.keyDown(overview, { key: "ArrowRight" });
    expect(screen.getByRole("tab", { name: "Tasks" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Tasks" })).toHaveFocus();
    fireEvent.keyDown(screen.getByRole("tab", { name: "Tasks" }), { key: "End" });
    expect(screen.getByRole("tab", { name: "Activity" })).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(screen.getByRole("tab", { name: "Activity" }), { key: "ArrowRight" });
    expect(screen.getByRole("tab", { name: "Overview" })).toHaveAttribute("aria-selected", "true");
  });
});

describe("roles", () => {
  it("lets the owner change the status, add tasks and invite", async () => {
    open(`/workspace/${ITEM_ID}?tab=members`);
    expect(await screen.findByRole("button", { name: "Status: Planning. Change status" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Invite someone" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Tasks" }));
    expect(await screen.findByRole("button", { name: "New task" })).toBeInTheDocument();
  });

  it("shows a viewer the item read-only", async () => {
    item = makeItem({ user_id: OWNER_ID });
    members = [makeMember({ role: "VIEWER" }), makeMember({ id: "3e000000-0000-4000-8000-000000000002", user_id: OWNER_ID, role: "OWNER", user: { id: OWNER_ID, full_name: "Grace Hopper", email: "grace@example.edu", role: "FACULTY" } })];
    open(`/workspace/${ITEM_ID}?tab=tasks`);
    expect(await screen.findByText("Shared with you · Viewer")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Change status/ })).toBeNull();
    expect(screen.getByText("Planning")).toBeInTheDocument();
    await screen.findByRole("heading", { level: 2, name: "Tasks" });
    expect(screen.queryByRole("button", { name: "New task" })).toBeNull();
    fireEvent.click(screen.getByRole("tab", { name: "Members" }));
    expect(await screen.findByRole("heading", { level: 3, name: "Grace Hopper" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Invite someone" })).toBeNull();
  });

  it("lets an editor change the status but not manage members", async () => {
    item = makeItem({ user_id: OWNER_ID });
    members = [makeMember({ role: "EDITOR" })];
    open(`/workspace/${ITEM_ID}?tab=members`);
    expect(await screen.findByRole("button", { name: "Status: Planning. Change status" })).toBeInTheDocument();
    await screen.findByRole("heading", { level: 2, name: "Members" });
    expect(screen.queryByRole("button", { name: "Invite someone" })).toBeNull();
    expect(screen.queryByRole("combobox", { name: /Role of/ })).toBeNull();
  });

  it("asks for the members only when it needs them", async () => {
    open(`/workspace/${ITEM_ID}`);
    await screen.findByRole("heading", { level: 1 });
    // The owner's own item: the role is known without the member list.
    expect(item.user_id).toBe(USER_ID);
    expect(gets("/members")).toBe(0);
  });
});

describe("other addresses", () => {
  it("says an id that cannot be an item's was not found, without asking the API", async () => {
    open("/workspace/not-an-id", "not-an-id");
    expect(await screen.findByRole("heading", { level: 1, name: "This workspace item was not found" })).toBeInTheDocument();
    expect(fetchMock.mock.calls.filter(([url]) => String(url).includes("/api/v1/workspace"))).toHaveLength(0);
  });

  it("explains an item that is not shared with the viewer", async () => {
    fetchMock.mockImplementation((url: string) => {
      if (String(url).endsWith("/api/v1/auth/me")) return ok(makeUser());
      return Promise.resolve(jsonResponse({ detail: "Forbidden" }, 403));
    });
    open(`/workspace/${ITEM_ID}`);
    expect(await screen.findByRole("heading", { level: 1, name: "This workspace item is not shared with you" })).toBeInTheDocument();
  });

  it("sends the old submission page to the Submission tab", async () => {
    await SubmissionRedirect({ params: Promise.resolve({ id: ITEM_ID }) });
    expect(redirect).toHaveBeenCalledWith(`/workspace/${ITEM_ID}?tab=submission`);
  });
});
