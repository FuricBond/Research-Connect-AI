/**
 * Phase 5.15 — "Notify me when a new posting matches my interests".
 *
 * A student turns the alert on with a switch and picks the minimum fit (40, 60 or 80). Each
 * change is one PATCH to /notifications/preferences; the threshold is disabled while the alert
 * is off. Other roles never get posting alerts, so they do not see the switch.
 */

import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn(), back: vi.fn(), forward: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/settings/notifications",
  useSearchParams: () => new URLSearchParams(),
}));

import NotificationSettingsRoute from "../app/settings/notifications/page";
import { SessionProvider } from "../components/auth/SessionProvider";
import { storeSession } from "../services/auth";
import type { PlatformRole } from "../types/auth";
import type { NotificationPreference } from "../types/notification";
import { PROFILE_ID, jsonResponse, makeTokenResponse, makeUser } from "./factories";

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

function serve(role: PlatformRole) {
  storeSession(makeTokenResponse({ user: makeUser({ role }) }));
  fetchMock.mockImplementation((url: string, init?: RequestInit) => {
    if (url.endsWith("/api/v1/auth/me")) return Promise.resolve(jsonResponse(makeUser({ role })));
    if (url.endsWith("/api/v1/notifications/preferences")) {
      if (init?.method === "PATCH") {
        return Promise.resolve(jsonResponse({ ...PREFERENCES, ...JSON.parse(String(init.body)) }));
      }
      return Promise.resolve(jsonResponse(PREFERENCES));
    }
    if (url.includes("/api/v1/notifications/rules")) return Promise.resolve(jsonResponse({ rules: [], total: 0 }));
    return Promise.resolve(jsonResponse({}, 200));
  });
}

function patches(): Record<string, unknown>[] {
  return fetchMock.mock.calls
    .filter(([url, init]) => String(url).endsWith("/notifications/preferences") && (init as RequestInit)?.method === "PATCH")
    .map(([, init]) => JSON.parse(String((init as RequestInit).body)));
}

function renderPage() {
  return render(
    <SessionProvider>
      <NotificationSettingsRoute />
    </SessionProvider>
  );
}

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

describe("posting match alert settings", () => {
  it("turns the alert on, then saves the chosen threshold", async () => {
    serve("STUDENT");
    renderPage();

    const toggle = await screen.findByRole("checkbox", {
      name: "Notify me when a new posting matches my interests",
    });
    const threshold = screen.getByRole("combobox", { name: "Minimum fit for posting alerts" });
    await waitFor(() => expect(toggle).not.toBeChecked());
    expect(threshold).toBeDisabled();

    fireEvent.click(toggle);
    await waitFor(() => expect(patches()).toEqual([{ posting_match_alerts_enabled: true }]));
    await waitFor(() => expect(threshold).toBeEnabled());

    fireEvent.change(threshold, { target: { value: "80" } });
    await waitFor(() =>
      expect(patches()).toEqual([{ posting_match_alerts_enabled: true }, { posting_match_min_score: 80 }])
    );
    expect(threshold).toHaveValue("80");
  });

  it("is not offered to other roles", async () => {
    serve("FACULTY");
    renderPage();

    expect(await screen.findByText("In-App Notifications")).toBeInTheDocument();
    expect(
      screen.queryByRole("checkbox", { name: "Notify me when a new posting matches my interests" })
    ).not.toBeInTheDocument();
  });
});
