/**
 * P8 — notifications grouped by source, in words, with their destinations; and the bell's panel.
 *
 * Grouping follows the API's `source_type` (OPPORTUNITY, CALENDAR_EVENT, WORKSPACE,
 * RESEARCH_POSTING, SYSTEM); an unknown source goes under "Other updates" and an unknown kind is
 * said in words, never as the raw identifier. Unread is a word, the count comes from the API, and
 * marking read changes both. The bell opens a disclosure: Escape, a click outside or tabbing away
 * close it, and focus returns to the bell.
 */

import React from "react";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn(), back: vi.fn(), forward: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => window.location.pathname,
  useSearchParams: () => new URLSearchParams(window.location.search),
}));

import NotificationsPageRoute from "../app/notifications/page";
import { SessionProvider } from "../components/auth/SessionProvider";
import { AppShell } from "../components/shell/AppShell";
import { clearActiveIdentity } from "../services/auth";
import type { NotificationItem } from "../types/notification";
import { OTHER_SOURCE_LABEL, groupBySource, notificationHref, notificationSourceLabel, notificationTypeLabel } from "../utils/notifications";
import { jsonResponse } from "./factories";
import { CALL_ID, POSTING_ID, WORKSPACE_ITEM_ID, makeNotification } from "./p8-fixtures";
import { serveShell } from "./shell-support";

const DEADLINE = makeNotification({ notification_type: "DEADLINE_UPCOMING", source_type: "OPPORTUNITY", source_id: CALL_ID, opportunity_id: CALL_ID, title: "ICIRS is due in 3 days", created_at: "2026-10-18T09:00:00+00:00" });
const TASK = makeNotification({ notification_type: "TASK_ASSIGNED", source_type: "WORKSPACE", source_id: WORKSPACE_ITEM_ID, title: "You were assigned a task", created_at: "2026-10-18T08:00:00+00:00", read_at: "2026-10-18T08:30:00+00:00" });
const MATCH = makeNotification({ notification_type: "POSTING_MATCH", source_type: "RESEARCH_POSTING", source_id: POSTING_ID, title: "A posting fits you", created_at: "2026-10-17T08:00:00+00:00" });
const SECOND_DEADLINE = makeNotification({ notification_type: "DEADLINE_EXTENDED", source_type: "OPPORTUNITY", source_id: CALL_ID, opportunity_id: CALL_ID, title: "ICIRS was extended", created_at: "2026-10-16T08:00:00+00:00", read_at: "2026-10-16T09:00:00+00:00" });
const FUTURE = makeNotification({ notification_type: "PEER_ENDORSEMENT" as NotificationItem["notification_type"], source_type: "PEER_NETWORK", source_id: "x", title: "Something new", created_at: "2026-10-15T08:00:00+00:00" });

describe("words and groups", () => {
  it("says every kind and source in words, and unknown ones safely", () => {
    expect(notificationTypeLabel("DEADLINE_TODAY")).toBe("Due today");
    expect(notificationTypeLabel("WORKSPACE_INVITATION")).toBe("Workspace invitation");
    expect(notificationTypeLabel("POSTING_MATCH")).toBe("A posting that fits you");
    expect(notificationTypeLabel("PEER_ENDORSEMENT")).toBe("Peer endorsement");
    expect(notificationTypeLabel(null)).toBe("Notification");
    expect(notificationSourceLabel("OPPORTUNITY")).toBe("Calls for papers");
    expect(notificationSourceLabel("RESEARCH_POSTING")).toBe("Research postings");
    expect(notificationSourceLabel("PEER_NETWORK")).toBe(OTHER_SOURCE_LABEL);
    expect(notificationSourceLabel(undefined)).toBe(OTHER_SOURCE_LABEL);
  });

  it("groups by source, newest group first, keeping the API's order inside each", () => {
    const groups = groupBySource([DEADLINE, TASK, MATCH, SECOND_DEADLINE, FUTURE]);
    expect(groups.map((group) => group.label)).toEqual(["Calls for papers", "Workspace", "Research postings", OTHER_SOURCE_LABEL]);
    expect(groups[0].items.map((item) => item.title)).toEqual(["ICIRS is due in 3 days", "ICIRS was extended"]);
  });

  it("links each notification to where it leads, and only with ids that can be the API's", () => {
    expect(notificationHref(DEADLINE)).toBe(`/calls/${CALL_ID}`);
    expect(notificationHref(TASK)).toBe(`/workspace/${WORKSPACE_ITEM_ID}`);
    expect(notificationHref(MATCH)).toBe(`/postings/${POSTING_ID}`);
    expect(notificationHref(makeNotification({ source_type: "CALENDAR_EVENT", source_id: null, calendar_event_id: CALL_ID }))).toBe("/calendar");
    expect(notificationHref(makeNotification({ source_type: "WORKSPACE", source_id: "not-an-id" }))).toBeNull();
    expect(notificationHref(FUTURE)).toBeNull();
  });
});

let items: NotificationItem[];
let markRead: () => Promise<Response>;

function serve(role: "STUDENT" | "ADMIN" = "STUDENT") {
  return serveShell(role, {
    unread: () => items.filter((item) => !item.read_at).length,
    other: (url, init) => {
      const parsed = new URL(url);
      if (parsed.pathname.endsWith("/read") && init?.method === "POST") return markRead();
      if (parsed.pathname.endsWith("/read-all") && init?.method === "POST") return Promise.resolve(jsonResponse({ marked_read_count: 3 }));
      if (parsed.pathname === "/api/v1/notifications") {
        const unreadOnly = parsed.searchParams.get("unread_only") === "true";
        const list = unreadOnly ? items.filter((item) => !item.read_at) : items;
        const limit = Number(parsed.searchParams.get("limit") ?? 50);
        return Promise.resolve(jsonResponse({ notifications: list.slice(0, limit), total: list.length, unread_count: items.filter((item) => !item.read_at).length }));
      }
      return undefined;
    },
  });
}

function renderPage() {
  return render(
    <SessionProvider>
      <AppShell>
        <NotificationsPageRoute />
      </AppShell>
    </SessionProvider>
  );
}

beforeEach(() => {
  window.history.replaceState(null, "", "/notifications");
  items = [DEADLINE, TASK, MATCH, SECOND_DEADLINE, FUTURE];
  markRead = () => Promise.resolve(jsonResponse({ ...DEADLINE, read_at: "2026-10-18T10:00:00+00:00" }));
});

afterEach(() => clearActiveIdentity());

describe("the notifications page", () => {
  it("shows one group per source with the kind in words, the title as the link and unread as a word", async () => {
    serve();
    renderPage();
    const main = within(await screen.findByRole("main"));
    expect(await main.findByRole("heading", { level: 1, name: "Notifications" })).toBeInTheDocument();
    expect(await main.findByRole("heading", { level: 2, name: "Calls for papers (2)" })).toBeInTheDocument();
    expect(main.getAllByRole("heading", { level: 2 }).map((heading) => heading.textContent)).toEqual([
      "Calls for papers (2)",
      "Workspace (1)",
      "Research postings (1)",
      `${OTHER_SOURCE_LABEL} (1)`,
    ]);

    const deadline = within(main.getByRole("listitem", { name: "ICIRS is due in 3 days" }));
    expect(deadline.getByText("Deadline coming up")).toBeInTheDocument();
    expect(deadline.getByRole("link", { name: "ICIRS is due in 3 days" })).toHaveAttribute("href", `/calls/${CALL_ID}`);
    expect(deadline.getByText("Unread")).toBeInTheDocument();
    expect(deadline.getByRole("button", { name: "Mark as read" })).toBeInTheDocument();

    const task = within(main.getByRole("listitem", { name: "You were assigned a task" }));
    expect(task.getByRole("link", { name: "You were assigned a task" })).toHaveAttribute("href", `/workspace/${WORKSPACE_ITEM_ID}`);
    expect(task.queryByText("Unread")).not.toBeInTheDocument();

    // The unknown kind and source are said in words; nothing raw, no link to nowhere.
    const future = within(main.getByRole("listitem", { name: "Something new" }));
    expect(future.getByText("Peer endorsement")).toBeInTheDocument();
    expect(future.queryByRole("link")).not.toBeInTheDocument();
    expect(main.queryByText(/PEER_|_ENDORSEMENT|RESEARCH_POSTING|DEADLINE_UPCOMING/)).not.toBeInTheDocument();
  });

  it("counts unread from the API and marks one read, here and on the bell", async () => {
    const fetchMock = serve();
    renderPage();
    const main = within(await screen.findByRole("main"));
    expect(await main.findByRole("button", { name: "Unread (3)" })).toHaveAttribute("aria-pressed", "false");
    expect(await screen.findByRole("button", { name: "Notifications, 3 unread" })).toBeInTheDocument();

    items = items.map((item) => (item.id === DEADLINE.id ? { ...item, read_at: "2026-10-18T10:00:00+00:00" } : item));
    fireEvent.click(within(main.getByRole("listitem", { name: "ICIRS is due in 3 days" })).getByRole("button", { name: "Mark as read" }));

    expect(await main.findByRole("button", { name: "Unread (2)" })).toBeInTheDocument();
    expect(within(main.getByRole("listitem", { name: "ICIRS is due in 3 days" })).queryByText("Unread")).not.toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Notifications, 2 unread" })).toBeInTheDocument();
    expect(fetchMock.mock.calls.filter(([url, init]) => String(url).endsWith(`/notifications/${DEADLINE.id}/read`) && (init as RequestInit)?.method === "POST")).toHaveLength(1);
  });

  it("keeps a notification unread and says so when marking it read fails", async () => {
    markRead = () => Promise.resolve(jsonResponse({ detail: "boom" }, 500));
    serve();
    renderPage();
    const main = within(await screen.findByRole("main"));
    const row = within(await main.findByRole("listitem", { name: "ICIRS is due in 3 days" }));
    fireEvent.click(row.getByRole("button", { name: "Mark as read" }));
    expect(await main.findByRole("alert")).toHaveTextContent("It could not be marked as read. Try again.");
    expect(row.getByText("Unread")).toBeInTheDocument();
    expect(main.getByRole("button", { name: "Unread (3)" })).toBeInTheDocument();
  });

  it("filters to unread in the address, and says when all are read", async () => {
    serve();
    renderPage();
    const main = within(await screen.findByRole("main"));
    fireEvent.click(await main.findByRole("button", { name: "Unread (3)" }));
    expect(window.location.search).toBe("?show=unread");
    await waitFor(() => expect(main.queryByRole("listitem", { name: "You were assigned a task" })).not.toBeInTheDocument());
    expect(main.getByRole("listitem", { name: "ICIRS is due in 3 days" })).toBeInTheDocument();

    items = items.map((item) => ({ ...item, read_at: item.read_at ?? "2026-10-18T10:00:00+00:00" }));
    fireEvent.click(main.getByRole("button", { name: "Mark all as read" }));
    expect(await main.findByRole("heading", { name: "You're all caught up." })).toBeInTheDocument();
  });

  it("offers a retry when the list cannot be loaded", async () => {
    let fail = true;
    serveShell("STUDENT", {
      other: (url) => {
        if (new URL(url).pathname !== "/api/v1/notifications") return undefined;
        return Promise.resolve(fail ? jsonResponse({ detail: "down" }, 503) : jsonResponse({ notifications: [DEADLINE], total: 1, unread_count: 1 }));
      },
    });
    renderPage();
    const main = within(await screen.findByRole("main"));
    expect(await main.findByRole("heading", { name: "Your notifications could not be loaded" })).toBeInTheDocument();
    fail = false;
    fireEvent.click(main.getByRole("button", { name: "Try again" }));
    expect(await main.findByRole("listitem", { name: "ICIRS is due in 3 days" })).toBeInTheDocument();
  });
});

describe("the bell's panel", () => {
  function renderShell() {
    window.history.replaceState(null, "", "/dashboard");
    return render(
      <SessionProvider>
        <AppShell>
          <p>Page</p>
          <button type="button">Elsewhere</button>
        </AppShell>
      </SessionProvider>
    );
  }

  it("shows the latest five grouped by source, each linking to where it leads", async () => {
    items = [DEADLINE, TASK, MATCH, SECOND_DEADLINE, FUTURE, makeNotification({ title: "Sixth" })];
    serve();
    renderShell();
    const bell = await screen.findByRole("button", { name: "Notifications, 4 unread" });
    fireEvent.click(bell);
    const panel = within(document.getElementById(bell.getAttribute("aria-controls") as string) as HTMLElement);
    expect(await panel.findByRole("link", { name: "ICIRS is due in 3 days" })).toHaveAttribute("href", `/calls/${CALL_ID}`);
    expect(panel.getAllByRole("heading", { level: 3 }).map((heading) => heading.textContent)).toEqual(["Calls for papers", "Workspace", "Research postings", OTHER_SOURCE_LABEL]);
    expect(panel.queryByText("Sixth")).not.toBeInTheDocument();
    expect(panel.getByText("4 unread")).toBeInTheDocument();
    expect(panel.getByRole("link", { name: "Notification settings" })).toHaveAttribute("href", "/settings#notifications");
  });

  it("has its links the moment it opens, so Tab after Enter lands inside it", async () => {
    serve();
    renderShell();
    const bell = await screen.findByRole("button", { name: /^Notifications/ });
    fireEvent.click(bell);
    // No waiting: the panel's content renders with the update that opens it.
    const panel = within(document.getElementById(bell.getAttribute("aria-controls") as string) as HTMLElement);
    expect(panel.getByRole("link", { name: "View all notifications" })).toBeInTheDocument();
    expect(panel.getByRole("heading", { level: 2, name: "Notifications" })).toBeInTheDocument();
  });

  it("closes on a click outside and when focus moves out, and asks again on the next opening", async () => {
    const fetchMock = serve();
    renderShell();
    const bell = await screen.findByRole("button", { name: /^Notifications/ });
    fireEvent.click(bell);
    expect(bell).toHaveAttribute("aria-expanded", "true");
    await within(document.getElementById(bell.getAttribute("aria-controls") as string) as HTMLElement).findByText("ICIRS is due in 3 days");
    fireEvent.pointerDown(screen.getByText("Page"));
    expect(bell).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(bell);
    const panel = document.getElementById(bell.getAttribute("aria-controls") as string) as HTMLElement;
    const link = await within(panel).findByRole("link", { name: "View all notifications" });
    act(() => link.focus());
    fireEvent.blur(link, { relatedTarget: screen.getByRole("button", { name: "Elsewhere" }) });
    expect(bell).toHaveAttribute("aria-expanded", "false");
    await waitFor(() => expect(fetchMock.mock.calls.filter(([url]) => String(url).includes("/api/v1/notifications?limit=5"))).toHaveLength(2));
  });

  it("says so when the latest cannot be loaded, and can try again", async () => {
    let fail = true;
    serveShell("STUDENT", {
      other: (url) => {
        if (new URL(url).pathname !== "/api/v1/notifications") return undefined;
        return Promise.resolve(fail ? jsonResponse({ detail: "down" }, 503) : jsonResponse({ notifications: [], total: 0, unread_count: 0 }));
      },
    });
    renderShell();
    const bell = await screen.findByRole("button", { name: /^Notifications/ });
    fireEvent.click(bell);
    const panel = within(document.getElementById(bell.getAttribute("aria-controls") as string) as HTMLElement);
    expect(await panel.findByText("The latest notifications could not be loaded.")).toBeInTheDocument();
    fail = false;
    fireEvent.click(panel.getByRole("button", { name: "Try again" }));
    expect(await panel.findByText("No notifications yet.")).toBeInTheDocument();
  });
});
