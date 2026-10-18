/**
 * P8 — Settings: Notifications and Appearance.
 *
 * Every switch has a name a screen reader can say and its state in words. A change is saved on its
 * own (one PATCH with just that setting); when the server refuses, the switch goes back to what it
 * was and the reason is given. Reminders are added only with a valid amount, and a refused one
 * keeps the form. The theme applies at once in light and dark, is kept in this browser, and the
 * account menu's switch shows the same choice.
 */

import React from "react";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn(), back: vi.fn(), forward: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/settings",
  useSearchParams: () => new URLSearchParams(),
  redirect: vi.fn(),
}));

import SettingsRoute from "../app/settings/page";
import { SessionProvider } from "../components/auth/SessionProvider";
import { AppShell } from "../components/shell/AppShell";
import { clearActiveIdentity } from "../services/auth";
import type { NotificationPreference, ReminderRule } from "../types/notification";
import { THEME_STORAGE_KEY } from "../utils/theme";
import { jsonResponse } from "./factories";
import { PREFERENCES, makeRule, settingsRoutes } from "./p8-fixtures";
import { serveShell } from "./shell-support";

let preferences: NotificationPreference;
let rules: ReminderRule[];
let patch: (body: Record<string, unknown>) => Promise<Response>;
let createRule: (body: Record<string, unknown>) => Promise<Response>;

function serve(role: "STUDENT" | "FACULTY" = "STUDENT") {
  const routes = settingsRoutes({ preferences: () => preferences, rules: () => rules, patch: (body) => patch(body) });
  return serveShell(role, {
    other: (url, init) => {
      if (new URL(url).pathname === "/api/v1/notifications/rules" && init?.method === "POST") return createRule(JSON.parse(String(init.body)));
      return routes(url, init);
    },
  });
}

function renderSettings(withShell = false) {
  const page = <SettingsRoute />;
  return render(<SessionProvider>{withShell ? <AppShell>{page}</AppShell> : page}</SessionProvider>);
}

const patches = (fetchMock: ReturnType<typeof serveShell>) =>
  fetchMock.mock.calls
    .filter(([url, init]) => String(url).endsWith("/notifications/preferences") && (init as RequestInit)?.method === "PATCH")
    .map(([, init]) => JSON.parse(String((init as RequestInit).body)));

beforeEach(() => {
  preferences = { ...PREFERENCES };
  rules = [makeRule("f0000000-0000-4000-8000-000000000001", "IN_APP", 7)];
  patch = (body) => {
    preferences = { ...preferences, ...body };
    return Promise.resolve(jsonResponse(preferences));
  };
  createRule = (body) => Promise.resolve(jsonResponse({ ...makeRule("f0000000-0000-4000-8000-000000000002", body.delivery_channel as ReminderRule["delivery_channel"], Number(body.offset_amount), body.offset_unit as ReminderRule["offset_unit"]) }, 201));
  window.localStorage.removeItem(THEME_STORAGE_KEY);
  document.documentElement.removeAttribute("data-theme");
});

afterEach(() => clearActiveIdentity());

describe("notification switches", () => {
  it("name every setting and say its state in words", async () => {
    serve("STUDENT");
    renderSettings();
    const section = within(await screen.findByRole("region", { name: "Notifications" }));
    await section.findByRole("switch", { name: "Email alerts" });
    expect(section.getAllByRole("switch")).toHaveLength(7);
    for (const name of [
      "In-app notifications",
      "Email alerts",
      "Upcoming deadline reminders",
      "Deadline extensions",
      "Deadline conflicts",
      "Calendar planning events",
      "Notify me when a new posting matches my interests",
    ]) {
      const control = section.getByRole("switch", { name });
      expect(control).toHaveAccessibleDescription(/.+/);
      expect(control).toHaveTextContent(/^(On|Off)$/);
    }
  });

  it("saves one setting at a time with the server's answer", async () => {
    const fetchMock = serve();
    renderSettings();
    const conflicts = await screen.findByRole("switch", { name: "Deadline conflicts" });
    expect(conflicts).toBeChecked();
    fireEvent.click(conflicts);
    expect(conflicts).not.toBeChecked();
    await waitFor(() => expect(patches(fetchMock)).toEqual([{ conflict_notifications_enabled: false }]));
    expect(await screen.findByText("Deadline conflicts: off.")).toHaveAttribute("role", "status");
    expect(conflicts).toBeEnabled();
  });

  it("puts a switch back and says why when the server refuses", async () => {
    patch = () => Promise.resolve(jsonResponse({ detail: "Preferences are locked." }, 409));
    serve();
    renderSettings();
    const email = await screen.findByRole("switch", { name: "Email alerts" });
    fireEvent.click(email);
    expect(await screen.findByRole("alert")).toHaveTextContent("Email alerts could not be switched off; it is still on. Preferences are locked.");
    expect(email).toBeChecked();
    expect(email).toHaveTextContent("On");
  });

  it("holds a switch while its change is saving, so it cannot be sent twice", async () => {
    let answer: (response: Response) => void = () => undefined;
    patch = () => new Promise((resolve) => (answer = resolve));
    const fetchMock = serve();
    renderSettings();
    const reminders = await screen.findByRole("switch", { name: "Upcoming deadline reminders" });
    fireEvent.click(reminders);
    expect(reminders).toBeDisabled();
    fireEvent.click(reminders);
    expect(patches(fetchMock)).toHaveLength(1);
    await act(async () => answer(jsonResponse({ ...preferences, deadline_reminders_enabled: false })));
    expect(reminders).toBeEnabled();
    expect(reminders).not.toBeChecked();
  });

  it("is the signed-in account's own: a different account is never asked about", async () => {
    const fetchMock = serve("FACULTY");
    renderSettings();
    await screen.findByRole("switch", { name: "Email alerts" });
    expect(screen.queryByRole("switch", { name: /posting matches/ })).not.toBeInTheDocument();
    const settingsCalls = fetchMock.mock.calls.filter(([url]) => String(url).includes("/notifications/preferences"));
    // The API reads the account from the bearer token; no other user id is sent.
    for (const [, init] of settingsCalls) expect(new Headers((init as RequestInit)?.headers).get("X-User-ID")).toBeNull();
  });
});

describe("loading order", () => {
  it("asks for the delivery status only after the preferences have answered", async () => {
    // Both endpoints create a new account's preferences; asked together they collide on the server.
    let answer: (response: Response) => void = () => undefined;
    const held = new Promise<Response>((resolve) => (answer = resolve));
    const routes = settingsRoutes({ preferences: () => preferences, rules: () => rules });
    const fetchMock = serveShell("STUDENT", {
      other: (url, init) => (new URL(url).pathname === "/api/v1/notifications/preferences" && (init?.method ?? "GET") === "GET" ? held : routes(url, init)),
    });
    renderSettings();
    const delivery = () => fetchMock.mock.calls.filter(([url]) => String(url).endsWith("/notifications/delivery-status")).length;
    await waitFor(() => expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/notifications/preferences"))).toBe(true));
    await act(async () => new Promise((resolve) => setTimeout(resolve, 20)));
    expect(delivery()).toBe(0);
    await act(async () => answer(jsonResponse(preferences)));
    await waitFor(() => expect(delivery()).toBe(1));
  });
});

describe("reminder schedule", () => {
  it("checks the amount first, then adds the reminder in words", async () => {
    const fetchMock = serve();
    renderSettings();
    expect(await screen.findByText("7 days before")).toBeInTheDocument();
    const amount = screen.getByRole("spinbutton", { name: "Remind me" });
    fireEvent.change(amount, { target: { value: "0" } });
    fireEvent.click(screen.getByRole("button", { name: "Add reminder" }));
    expect(await screen.findByText("Enter a whole number from 1 to 365.")).toBeInTheDocument();
    expect(amount).toHaveAttribute("aria-invalid", "true");
    expect(fetchMock.mock.calls.filter(([, init]) => (init as RequestInit)?.method === "POST")).toHaveLength(0);

    fireEvent.change(amount, { target: { value: "2" } });
    fireEvent.change(screen.getByRole("combobox", { name: "Unit" }), { target: { value: "HOURS" } });
    fireEvent.change(screen.getByRole("combobox", { name: "Channel" }), { target: { value: "EMAIL" } });
    fireEvent.click(screen.getByRole("button", { name: "Add reminder" }));
    expect(await screen.findByText("2 hours before")).toBeInTheDocument();
    expect(screen.getByText(/^By email ·/)).toBeInTheDocument();
  });

  it("keeps the form and explains a refused reminder", async () => {
    createRule = () => Promise.resolve(jsonResponse({ detail: "A reminder with this offset already exists." }, 409));
    serve();
    renderSettings();
    const amount = await screen.findByRole("spinbutton", { name: "Remind me" });
    fireEvent.change(amount, { target: { value: "7" } });
    fireEvent.click(screen.getByRole("button", { name: "Add reminder" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("A reminder with this offset already exists.");
    expect(amount).toHaveValue(7);
  });
});

describe("appearance", () => {
  it("applies light and dark at once, keeps the choice, and the account menu shows it", async () => {
    serve();
    renderSettings(true);
    const appearance = within(await screen.findByRole("region", { name: "Appearance" }));
    const group = appearance.getByRole("group", { name: "Colour theme" });
    await waitFor(() => expect(within(group).getByRole("radio", { name: /Match the system/ })).toBeChecked());

    fireEvent.click(within(group).getByRole("radio", { name: "Dark" }));
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");
    expect(appearance.getByText("Dark theme.")).toHaveAttribute("role", "status");
    // The account menu's switch (mounted, closed) follows.
    fireEvent.click(await screen.findByRole("button", { name: /account menu/ }));
    expect(screen.getByRole("radio", { name: "Dark theme" })).toBeChecked();

    fireEvent.click(within(group).getByRole("radio", { name: "Light" }));
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");
    expect(screen.getByRole("radio", { name: "Light theme" })).toBeChecked();
  });

  it("starts from the stored choice", async () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, "dark");
    serve();
    renderSettings();
    const group = within(await screen.findByRole("group", { name: "Colour theme" }));
    await waitFor(() => expect(group.getByRole("radio", { name: "Dark" })).toBeChecked());
  });
});

describe("the old address", () => {
  it("sends /settings/notifications to the Notifications section", async () => {
    const { redirect } = await import("next/navigation");
    const { default: OldRoute } = await import("../app/settings/notifications/page");
    try {
      OldRoute();
    } catch {
      // The real redirect throws to stop rendering; the mock just records the call.
    }
    expect(redirect).toHaveBeenCalledWith("/settings#notifications");
  });
});
