/**
 * Phase 5.16 — notifications that keep themselves current, and an honest status header.
 *
 *  - The navbar shows the unread count to a signed-in user and asks again every 30 seconds
 *    while the tab is visible, when the tab comes back, and after notifications change.
 *  - The notifications page reports the channels that actually reach the user and whether
 *    reminders run on a schedule, marks emailed notifications, and offers "Evaluate Now" to
 *    administrators only.
 *  - The settings page says so when this server does not email notifications.
 */

import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn(), back: vi.fn(), forward: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/notifications",
  useSearchParams: () => new URLSearchParams(),
}));

import { DiscoveryNavbar } from "../components/discovery/DiscoveryNavbar";
import NotificationsPageRoute from "../app/notifications/page";
import NotificationSettingsRoute from "../app/settings/notifications/page";
import { SessionProvider } from "../components/auth/SessionProvider";
import {
  UNREAD_POLL_MS,
  notifyNotificationsChanged,
  useUnreadNotificationCount,
} from "../hooks/useUnreadNotificationCount";
import { storeSession } from "../services/auth";
import type { PlatformRole } from "../types/auth";
import type {
  NotificationDeliveryStatus,
  NotificationItem,
  NotificationPreference,
} from "../types/notification";
import { PROFILE_ID, jsonResponse, makeTokenResponse, makeUser } from "./factories";

const EMAIL_ON: NotificationDeliveryStatus = {
  in_app_enabled: true,
  email_enabled: true,
  email_delivery_available: true,
  reminders_scheduled: true,
  reminder_interval_seconds: 300,
};

const IN_APP_ONLY: NotificationDeliveryStatus = {
  in_app_enabled: true,
  email_enabled: true,
  email_delivery_available: false,
  reminders_scheduled: false,
  reminder_interval_seconds: null,
};

function makeNotification(overrides: Partial<NotificationItem> = {}): NotificationItem {
  return {
    id: "nt000000-0000-4000-8000-000000000001",
    profile_id: PROFILE_ID,
    notification_type: "POSTING_MATCH",
    title: "New posting matches your interests",
    body: "“Doctoral position in retrieval” — 82% fit",
    source_type: "RESEARCH_POSTING",
    source_id: "po000000-0000-4000-8000-000000000001",
    scheduled_for: "2026-10-04T12:00:00+00:00",
    delivered_at: "2026-10-04T12:00:00+00:00",
    read_at: null,
    delivery_status: "DELIVERED",
    delivery_channel: "IN_APP",
    deduplication_key: "dedup-1",
    metadata_json: {},
    email_status: null,
    email_sent_at: null,
    created_at: "2026-10-04T12:00:00+00:00",
    updated_at: "2026-10-04T12:00:00+00:00",
    ...overrides,
  };
}

const PREFERENCES: NotificationPreference = {
  id: "np000000-0000-4000-8000-000000000001",
  profile_id: PROFILE_ID,
  email_enabled: true,
  in_app_enabled: true,
  deadline_reminders_enabled: true,
  extension_notifications_enabled: true,
  conflict_notifications_enabled: true,
  calendar_event_reminders_enabled: true,
  posting_match_alerts_enabled: false,
  posting_match_min_score: 60,
  created_at: "2026-10-01T10:00:00+00:00",
  updated_at: "2026-10-01T10:00:00+00:00",
};

let fetchMock: ReturnType<typeof vi.fn>;

interface Routes {
  unread?: () => number;
  status?: NotificationDeliveryStatus;
  notifications?: NotificationItem[];
}

function serve(role: PlatformRole | null, routes: Routes = {}) {
  if (role !== null) storeSession(makeTokenResponse({ user: makeUser({ role }) }));
  fetchMock.mockImplementation((url: string, init?: RequestInit) => {
    if (url.endsWith("/api/v1/auth/me")) return Promise.resolve(jsonResponse(makeUser({ role: role ?? "STUDENT" })));
    if (url.endsWith("/api/v1/notifications/unread-count")) {
      return Promise.resolve(jsonResponse({ profile_id: PROFILE_ID, unread_count: routes.unread ? routes.unread() : 0 }));
    }
    if (url.endsWith("/api/v1/notifications/delivery-status")) {
      return Promise.resolve(jsonResponse(routes.status ?? IN_APP_ONLY));
    }
    if (url.endsWith("/api/v1/notifications/preferences")) return Promise.resolve(jsonResponse(PREFERENCES));
    if (url.includes("/api/v1/notifications/rules")) return Promise.resolve(jsonResponse({ rules: [], total: 0 }));
    if (url.includes("/read") && init?.method === "POST") return Promise.resolve(jsonResponse({}));
    if (url.includes("/api/v1/notifications")) {
      const items = routes.notifications ?? [];
      return Promise.resolve(
        jsonResponse({ notifications: items, total: items.length, unread_count: items.filter((n) => !n.read_at).length })
      );
    }
    return Promise.resolve(jsonResponse({ detail: `unexpected request ${url}` }, 404));
  });
}

function requests(part: string): number {
  return fetchMock.mock.calls.filter(([url]) => String(url).endsWith(part)).length;
}

function setVisibility(state: DocumentVisibilityState) {
  Object.defineProperty(document, "visibilityState", { configurable: true, get: () => state });
}

/**
 * Lets pending requests answer. The hook tests fake setInterval, which also stops waitFor's
 * own polling, so they wait one real macrotask instead (setTimeout is never faked here).
 */
async function settle() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  setVisibility("visible");
});

afterEach(() => {
  vi.useRealTimers();
  setVisibility("visible");
});

describe("navbar unread badge", () => {
  function renderNavbar() {
    return render(
      <SessionProvider>
        <DiscoveryNavbar />
      </SessionProvider>
    );
  }

  it("shows the unread count on the Notifications tab", async () => {
    serve("STUDENT", { unread: () => 3 });
    renderNavbar();

    const tab = await screen.findByRole("link", { name: /Notifications\s*3 unread/ });
    expect(tab).toHaveAttribute("href", "/notifications");
  });

  it("shows no badge at zero and caps large counts at 99+", async () => {
    let unread = 0;
    serve("STUDENT", { unread: () => unread });
    renderNavbar();

    await waitFor(() => expect(requests("/notifications/unread-count")).toBe(1));
    expect(screen.queryByText(/unread/)).not.toBeInTheDocument();

    unread = 250;
    act(() => notifyNotificationsChanged());
    expect(await screen.findByRole("link", { name: /Notifications\s*99\+ unread/ })).toBeInTheDocument();
  });

  it("asks nothing for a signed-out visitor", async () => {
    serve(null);
    renderNavbar();

    expect(await screen.findByRole("link", { name: /Literature Search/ })).toBeInTheDocument();
    await settle();
    expect(requests("/notifications/unread-count")).toBe(0);
    expect(screen.queryByRole("link", { name: /Notifications/ })).not.toBeInTheDocument();
  });
});

describe("useUnreadNotificationCount", () => {
  it("polls every 30 seconds while visible and refreshes on return and on change", async () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    let unread = 1;
    serve("STUDENT", { unread: () => unread });
    const { result, rerender, unmount } = renderHook(({ enabled }) => useUnreadNotificationCount(enabled), {
      initialProps: { enabled: true },
    });

    await settle();
    expect(result.current).toBe(1);
    expect(requests("/notifications/unread-count")).toBe(1);

    // Just short of the interval nothing happens; at 30 s it asks again.
    unread = 4;
    act(() => vi.advanceTimersByTime(UNREAD_POLL_MS - 1));
    expect(requests("/notifications/unread-count")).toBe(1);
    act(() => vi.advanceTimersByTime(1));
    await settle();
    expect(result.current).toBe(4);
    expect(requests("/notifications/unread-count")).toBe(2);

    // A hidden tab makes no requests.
    setVisibility("hidden");
    act(() => vi.advanceTimersByTime(UNREAD_POLL_MS * 3));
    await settle();
    expect(requests("/notifications/unread-count")).toBe(2);

    // Coming back asks at once.
    unread = 6;
    setVisibility("visible");
    act(() => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
    await settle();
    expect(result.current).toBe(6);
    expect(requests("/notifications/unread-count")).toBe(3);

    // So does a page announcing a change.
    unread = 0;
    act(() => notifyNotificationsChanged());
    await settle();
    expect(result.current).toBe(0);
    expect(requests("/notifications/unread-count")).toBe(4);

    // Switched off: no count and no more requests.
    rerender({ enabled: false });
    expect(result.current).toBeNull();
    act(() => vi.advanceTimersByTime(UNREAD_POLL_MS * 2));
    await settle();
    expect(requests("/notifications/unread-count")).toBe(4);

    unmount();
  });

  it("keeps the last count when a request fails", async () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    serve("STUDENT", { unread: () => 2 });
    const { result } = renderHook(() => useUnreadNotificationCount(true));
    await settle();
    expect(result.current).toBe(2);

    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse({ detail: "boom" }, 500)));
    act(() => vi.advanceTimersByTime(UNREAD_POLL_MS));
    await settle();
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(result.current).toBe(2);
  });
});

describe("notifications page", () => {
  function renderPage() {
    // As in app/layout.tsx: the navigation belongs to the layout, rendered once beside the
    // page. (The page used to render a second copy of it; P0.2 removed that duplicate.)
    return render(
      <SessionProvider>
        <DiscoveryNavbar />
        <NotificationsPageRoute />
      </SessionProvider>
    );
  }

  it("reports email and scheduled reminders when the server delivers them", async () => {
    serve("STUDENT", {
      status: EMAIL_ON,
      notifications: [makeNotification({ email_status: "SENT", email_sent_at: "2026-10-04T12:01:00+00:00" })],
    });
    renderPage();

    expect(await screen.findByText("In-App, Email")).toBeInTheDocument();
    expect(screen.getByText("Every 5 min")).toBeInTheDocument();
    expect(await screen.findByText("Emailed")).toBeInTheDocument();
    // Only administrators can run the reminder pass.
    expect(screen.queryByRole("button", { name: /Evaluate Now/ })).not.toBeInTheDocument();
  });

  it("reports in-app only when the server does not email, and offers Evaluate Now to admins", async () => {
    serve("ADMIN", { status: IN_APP_ONLY, notifications: [makeNotification()] });
    renderPage();

    expect(await screen.findByText("In-App")).toBeInTheDocument();
    expect(screen.getByText("Manual only")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /Evaluate Now/ })).toBeInTheDocument();
    expect(screen.queryByText("Emailed")).not.toBeInTheDocument();
  });

  it("does not count email as a channel when the user switched it off", async () => {
    serve("STUDENT", { status: { ...EMAIL_ON, email_enabled: false } });
    renderPage();

    expect(await screen.findByText("In-App")).toBeInTheDocument();
    expect(screen.queryByText("In-App, Email")).not.toBeInTheDocument();
  });

  it("updates the navbar badge as soon as a notification is marked read", async () => {
    serve("STUDENT", { unread: () => 1, notifications: [makeNotification()] });
    renderPage();

    const markRead = await screen.findByTitle("Mark as Read");
    await waitFor(() => expect(requests("/notifications/unread-count")).toBeGreaterThanOrEqual(1));
    const before = requests("/notifications/unread-count");

    fireEvent.click(markRead);

    await waitFor(() => expect(requests("/notifications/unread-count")).toBe(before + 1));
  });

  it("refreshes the list quietly while the page stays open", async () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    const items = [makeNotification()];
    serve("STUDENT", { notifications: items });
    renderPage();

    expect(await screen.findByText("New posting matches your interests")).toBeInTheDocument();
    items.push(makeNotification({ id: "nt000000-0000-4000-8000-000000000002", title: "Application accepted" }));
    act(() => vi.advanceTimersByTime(UNREAD_POLL_MS));

    expect(await screen.findByText("Application accepted")).toBeInTheDocument();
    expect(screen.getByText("New posting matches your interests")).toBeInTheDocument();
  });
});

describe("notification settings", () => {
  function renderSettings() {
    return render(
      <SessionProvider>
        <NotificationSettingsRoute />
      </SessionProvider>
    );
  }

  it("says when this server does not email notifications", async () => {
    serve("STUDENT", { status: IN_APP_ONLY });
    renderSettings();

    expect(await screen.findByRole("note")).toHaveTextContent("Email isn't set up on this server yet");
    expect(screen.getByRole("checkbox", { name: "Email Alerts" })).toBeChecked();
  });

  it("shows no note when email is delivered", async () => {
    serve("STUDENT", { status: EMAIL_ON });
    renderSettings();

    expect(await screen.findByRole("checkbox", { name: "Email Alerts" })).toBeInTheDocument();
    await waitFor(() => expect(requests("/notifications/delivery-status")).toBe(1));
    expect(screen.queryByText(/Email isn't set up/)).not.toBeInTheDocument();
  });
});
