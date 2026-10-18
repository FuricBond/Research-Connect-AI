/**
 * Fix 2/9 — the "Push" reminder channel was fake: reminders were marked delivered and nothing
 * was sent. The settings page no longer offers it, and a rule saved before the change is
 * labelled "Push (not available yet)" instead of looking like a working channel.
 *
 * P8: the notification settings are a section of /settings; /settings/notifications redirects
 * there. The protections are the same.
 */

import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn(), back: vi.fn(), forward: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/settings",
  useSearchParams: () => new URLSearchParams(),
}));

import NotificationSettingsRoute from "../app/settings/page";
import { SessionProvider } from "../components/auth/SessionProvider";
import { storeSession } from "../services/auth";
import type { NotificationPreference, ReminderRule } from "../types/notification";
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

function rule(id: string, channel: ReminderRule["delivery_channel"], offset: number): ReminderRule {
  return {
    id,
    profile_id: PROFILE_ID,
    event_type: null,
    offset_amount: offset,
    offset_unit: "DAYS",
    delivery_channel: channel,
    is_active: true,
    created_at: "2026-10-01T10:00:00+00:00",
    updated_at: "2026-10-01T10:00:00+00:00",
  };
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  storeSession(makeTokenResponse({ user: makeUser({ role: "STUDENT" }) }));
  fetchMock = vi.fn((url: string) => {
    if (url.endsWith("/api/v1/auth/me")) return Promise.resolve(jsonResponse(makeUser({ role: "STUDENT" })));
    if (url.endsWith("/api/v1/notifications/preferences")) return Promise.resolve(jsonResponse(PREFERENCES));
    if (url.includes("/api/v1/notifications/rules")) {
      const rules = [rule("ru-1", "IN_APP", 7), rule("ru-2", "PUSH", 3)];
      return Promise.resolve(jsonResponse({ rules, total: rules.length }));
    }
    return Promise.resolve(jsonResponse({}, 200));
  });
  vi.stubGlobal("fetch", fetchMock);
});

describe("reminder channels", () => {
  it("offers only in-app and email for a new reminder", async () => {
    render(
      <SessionProvider>
        <NotificationSettingsRoute />
      </SessionProvider>
    );

    const form = (await screen.findByRole("button", { name: /Add reminder/ })).closest("form") as HTMLElement;
    const channelSelect = within(form).getByRole("combobox", { name: "Channel" });
    const options = within(channelSelect).getAllByRole("option").map((option) => option.textContent);
    expect(options).toEqual(["In the app", "By email"]);
  });

  it("labels a rule saved with Push as not available", async () => {
    render(
      <SessionProvider>
        <NotificationSettingsRoute />
      </SessionProvider>
    );

    expect(await screen.findByText(/Push \(not available yet\)/)).toBeInTheDocument();
    expect(screen.getByText(/^In the app ·/)).toBeInTheDocument();
    expect(screen.queryByText(/\bPUSH\b/)).not.toBeInTheDocument();
    expect(screen.queryByText(/\bIN_APP\b/)).not.toBeInTheDocument();
  });

  it("offers no push switch anywhere in the notification settings", async () => {
    render(
      <SessionProvider>
        <NotificationSettingsRoute />
      </SessionProvider>
    );

    const section = await screen.findByRole("region", { name: "Notifications" });
    await within(section).findByRole("switch", { name: "Email alerts" });
    expect(within(section).queryByRole("switch", { name: /push/i })).not.toBeInTheDocument();
    expect(within(section).queryByRole("checkbox", { name: /push/i })).not.toBeInTheDocument();
    expect(within(section).queryByRole("option", { name: /push/i })).not.toBeInTheDocument();
  });
});
