/**
 * P7 — the calendar's views (plan §16: "Calendar — agenda view by default" on phones; a month
 * grid of seven columns that fits 360px on wider screens).
 *
 * The view, month and filter are in the address. Days with events are buttons that list them;
 * events open a dialog with their source and a link to the call. Adding a milestone checks the
 * form first and sends it once; deleting one asks first. The .ics export is covered by
 * calendar-export.test.tsx, unchanged.
 */

import React from "react";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn(), back: vi.fn(), forward: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/calendar",
  useSearchParams: () => new URLSearchParams(window.location.search),
}));

import CalendarRoute from "../app/calendar/page";
import { SessionProvider } from "../components/auth/SessionProvider";
import { dayKey, monthKey, monthWeeks } from "../components/calendar/calendarModel";
import { clearActiveIdentity, storeSession } from "../services/auth";
import type { ResearchCalendar, ResearchCalendarEvent } from "../types/calendar";
import { jsonResponse, makeTokenResponse, makeUser } from "./factories";
import { CALL_ID, deferred, ok } from "./p7-fixtures";

const CALENDAR: ResearchCalendar = {
  id: "ca000000-0000-4000-8000-000000000001",
  user_id: "11111111-2222-3333-4444-555555555555",
  profile_id: null,
  name: "My research calendar",
  description: null,
  timezone: "UTC",
  is_default: true,
  event_count: 2,
  created_at: "2026-01-01T00:00:00+00:00",
  updated_at: "2026-01-01T00:00:00+00:00",
};

const today = new Date();
const TODAY = dayKey(today);

function makeEvent(overrides: Partial<ResearchCalendarEvent> = {}): ResearchCalendarEvent {
  return {
    id: "ef000000-0000-4000-8000-000000000001",
    calendar_id: CALENDAR.id,
    opportunity_id: CALL_ID,
    submission_id: null,
    title: "ICIRS 2026 paper submission",
    description: null,
    event_type: "OPPORTUNITY_SUBMISSION",
    start_datetime: `${TODAY}T23:59:00Z`,
    end_datetime: null,
    date_str: TODAY,
    all_day: false,
    timezone: "UTC",
    is_canonical_projection: true,
    provenance_metadata: { opportunity_title: "International Conference on Information Retrieval Systems", latest_revision: { reason: "Extended by one week." } },
    status: "ACTIVE",
    created_at: "2026-01-01T00:00:00+00:00",
    updated_at: "2026-01-01T00:00:00+00:00",
    ...overrides,
  };
}

const MILESTONE = makeEvent({
  id: "ef000000-0000-4000-8000-000000000002",
  opportunity_id: null,
  title: "Finish the related-work section",
  event_type: "RESEARCH_MILESTONE",
  is_canonical_projection: false,
  provenance_metadata: {},
});

let fetchMock: ReturnType<typeof vi.fn>;
let events: ResearchCalendarEvent[];
let answerCreate: (body: Record<string, unknown>) => Promise<Response>;

function setPhone(phone: boolean) {
  window.matchMedia = vi.fn((query: string) => ({
    matches: phone && query.includes("max-width"),
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })) as unknown as typeof window.matchMedia;
}

beforeEach(() => {
  storeSession(makeTokenResponse());
  window.history.replaceState(null, "", "/calendar");
  events = [makeEvent(), MILESTONE];
  answerCreate = (body) => ok({ ...MILESTONE, id: "ef000000-0000-4000-8000-000000000003", ...body });
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    const path = new URL(url).pathname;
    if (path.endsWith("/api/v1/auth/me")) return ok(makeUser());
    if (path.endsWith("/api/v1/calendar/default")) return ok(CALENDAR);
    if (path === `/api/v1/calendar/${CALENDAR.id}/events` && method === "GET") return ok({ items: events, total: events.length });
    if (path === `/api/v1/calendar/${CALENDAR.id}/events` && method === "POST") return answerCreate(JSON.parse(String(init?.body)));
    if (path.startsWith(`/api/v1/calendar/${CALENDAR.id}/events/`) && method === "DELETE") return ok({ message: "deleted" });
    return Promise.resolve(jsonResponse({ detail: `unexpected ${method} ${url}` }, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  clearActiveIdentity();
  // @ts-expect-error jsdom has no matchMedia of its own
  delete window.matchMedia;
});

const renderPage = () =>
  render(
    <SessionProvider>
      <CalendarRoute />
    </SessionProvider>
  );

describe("the month grid", () => {
  it("has a week of seven days per row, Sunday first, covering the whole month", () => {
    const weeks = monthWeeks(new Date(2026, 9, 1));
    expect(weeks.every((week) => week.length === 7)).toBe(true);
    expect(weeks[0][0].date.getDay()).toBe(0);
    const inMonth = weeks.flat().filter((cell) => cell.inMonth);
    expect(inMonth).toHaveLength(31);
    expect(inMonth[0].key).toBe("2026-10-01");
  });
});

describe("the view", () => {
  it("opens on the agenda on phones", async () => {
    setPhone(true);
    renderPage();
    const agenda = await screen.findByRole("list", { name: /^Events in / });
    expect(screen.getByRole("button", { name: "Agenda" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByRole("table")).toBeNull();
    expect(within(agenda).getByRole("heading", { level: 3, name: /Today/ })).toBeInTheDocument();
    expect(within(agenda).getByRole("button", { name: /ICIRS 2026 paper submission/ })).toHaveTextContent("Extended");
  });

  it("opens on the month grid on wider screens, and a day lists its events", async () => {
    setPhone(false);
    renderPage();
    const grid = await screen.findByRole("table");
    expect(screen.getByRole("button", { name: "Month" })).toHaveAttribute("aria-pressed", "true");
    expect(within(grid).getAllByRole("columnheader").map((cell) => cell.textContent)).toEqual(["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]);

    const day = within(grid).getByRole("button", { name: /, today: 2 events$/ });
    fireEvent.click(day);
    expect(day).toHaveAttribute("aria-pressed", "true");
    const panel = within(screen.getByRole("region", { name: /\d{4}$/ }));
    fireEvent.click(panel.getByRole("button", { name: /ICIRS 2026 paper submission/ }));

    const dialog = within(await screen.findByRole("dialog", { name: "ICIRS 2026 paper submission" }));
    expect(dialog.getByText("This deadline was extended")).toBeInTheDocument();
    expect(dialog.getByText("Extended by one week.")).toBeInTheDocument();
    expect(dialog.getByText("The call's official dates")).toBeInTheDocument();
    expect(dialog.getByRole("link", { name: "Open the call for papers" })).toHaveAttribute("href", `/calls/${CALL_ID}`);
    // A call's dates are not the person's to delete.
    expect(dialog.queryByRole("button", { name: "Delete milestone" })).toBeNull();
  });

  it("keeps the view, month and filter in the address", async () => {
    setPhone(false);
    renderPage();
    await screen.findByRole("table");
    fireEvent.click(screen.getByRole("button", { name: "Next month" }));
    const next = new Date(today.getFullYear(), today.getMonth() + 1, 1);
    expect(window.location.search).toBe(`?month=${monthKey(next)}`);
    fireEvent.click(screen.getByRole("button", { name: "Agenda" }));
    expect(new URLSearchParams(window.location.search).get("view")).toBe("agenda");
    // Nothing that month: says so, and offers no false zero.
    expect(await screen.findByRole("heading", { name: `Nothing in ${next.toLocaleDateString(undefined, { month: "long", year: "numeric" })}.` })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Today" }));
    expect(new URLSearchParams(window.location.search).get("month")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Your milestones (1)" }));
    expect(new URLSearchParams(window.location.search).get("type")).toBe("MILESTONES");
    expect(screen.queryByRole("button", { name: /ICIRS 2026 paper submission/ })).toBeNull();
    expect(screen.getByRole("button", { name: /Finish the related-work section/ })).toBeInTheDocument();
  });
});

describe("milestones", () => {
  it("checks the form, sends it once, and keeps it when the server refuses", async () => {
    setPhone(true);
    const pending = deferred();
    answerCreate = () => pending.promise;
    renderPage();
    const add = await screen.findByRole("button", { name: "Add milestone" });
    await waitFor(() => expect(add).toBeEnabled());
    fireEvent.click(add);
    const dialog = within(await screen.findByRole("dialog", { name: "Add a milestone" }));
    const submit = dialog.getByRole("button", { name: "Add milestone" });

    fireEvent.click(submit);
    expect(await dialog.findByText("Give the milestone a title.")).toBeInTheDocument();
    expect(dialog.getByText("Choose its date.")).toBeInTheDocument();
    expect(fetchMock.mock.calls.filter(([, init]) => (init as RequestInit)?.method === "POST")).toHaveLength(0);

    fireEvent.change(dialog.getByRole("textbox", { name: /^Title/ }), { target: { value: "Send the draft to co-authors" } });
    fireEvent.change(dialog.getByLabelText(/^Date/), { target: { value: TODAY } });
    fireEvent.click(submit);
    fireEvent.click(submit);
    const posts = () => fetchMock.mock.calls.filter(([, init]) => (init as RequestInit)?.method === "POST");
    expect(posts()).toHaveLength(1);
    expect(JSON.parse(String((posts()[0][1] as RequestInit).body))).toEqual({
      title: "Send the draft to co-authors",
      description: null,
      event_type: "RESEARCH_MILESTONE",
      date_str: TODAY,
      start_datetime: `${TODAY}T17:00:00Z`,
      all_day: false,
    });

    await act(async () => pending.resolve(jsonResponse({ detail: "Calendar is read-only." }, 400)));
    expect(await dialog.findByRole("alert")).toHaveTextContent("The milestone could not be added. Calendar is read-only.");
    expect(dialog.getByRole("textbox", { name: /^Title/ })).toHaveValue("Send the draft to co-authors");

    answerCreate = (body) => ok({ ...MILESTONE, id: "ef000000-0000-4000-8000-000000000003", ...body });
    fireEvent.click(submit);
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Add a milestone" })).toBeNull());
    expect(await screen.findByRole("button", { name: /Send the draft to co-authors/ })).toBeInTheDocument();
  });

  it("asks before deleting a milestone", async () => {
    setPhone(true);
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /Finish the related-work section/ }));
    const dialog = within(await screen.findByRole("dialog", { name: "Finish the related-work section" }));
    fireEvent.click(dialog.getByRole("button", { name: "Delete milestone" }));
    expect(dialog.getByText('Delete "Finish the related-work section"?')).toBeInTheDocument();
    expect(fetchMock.mock.calls.filter(([, init]) => (init as RequestInit)?.method === "DELETE")).toHaveLength(0);
    fireEvent.click(dialog.getByRole("button", { name: "Delete milestone" }));
    await waitFor(() => expect(screen.queryByRole("button", { name: /Finish the related-work section/ })).toBeNull());
    expect(fetchMock.mock.calls.filter(([, init]) => (init as RequestInit)?.method === "DELETE")).toHaveLength(1);
  });
});
