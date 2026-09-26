/**
 * P2-03 regression — the calendar page and the events list the backend really returns.
 *
 * `GET /api/v1/calendar/{id}/events` answers `{ items, total }`, but the page read
 * `res.events`, so `events` became undefined and a useMemo reading `.length` threw. That
 * unmounted the entire tree, header and sign-out control included. These render the real
 * route, inside the real session provider, against the backend's actual response shape.
 */

import React from "react";
import { beforeEach, describe, expect, expectTypeOf, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn(), back: vi.fn(), forward: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/calendar",
  useSearchParams: () => new URLSearchParams(),
}));

import CalendarRoute from "../app/calendar/page";
import { SessionProvider } from "../components/auth/SessionProvider";
import { fetchCalendarEvents } from "../services/api";
import { storeSession } from "../services/auth";
import type { CalendarEventListResponse, ResearchCalendar, ResearchCalendarEvent } from "../types/calendar";
import { jsonResponse, makeTokenResponse, makeUser } from "./factories";

const CALENDAR: ResearchCalendar = {
  id: "ca000000-0000-4000-8000-000000000001",
  user_id: "11111111-2222-3333-4444-555555555555",
  profile_id: null,
  name: "My research calendar",
  description: null,
  timezone: "UTC",
  is_default: true,
  event_count: 1,
  created_at: "2026-01-01T00:00:00+00:00",
  updated_at: "2026-01-01T00:00:00+00:00",
};

const EVENT_TITLE = "Camera-ready deadline for the retrieval workshop";

function makeEvent(): ResearchCalendarEvent {
  // Dated today so it falls inside the month the page opens on.
  const today = new Date();
  today.setHours(12, 0, 0, 0);
  return {
    id: "ev000000-0000-4000-8000-000000000001",
    calendar_id: CALENDAR.id,
    opportunity_id: null,
    submission_id: null,
    title: EVENT_TITLE,
    description: null,
    event_type: "RESEARCH_MILESTONE",
    start_datetime: today.toISOString(),
    end_datetime: null,
    date_str: null,
    all_day: false,
    timezone: "UTC",
    is_canonical_projection: false,
    provenance_metadata: {},
    status: "ACTIVE",
    created_at: "2026-01-01T00:00:00+00:00",
    updated_at: "2026-01-01T00:00:00+00:00",
  };
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  storeSession(makeTokenResponse());
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

/** Routes each request the page makes; `eventsBody` is what the events endpoint returns. */
function serve(eventsBody: unknown) {
  fetchMock.mockImplementation((url: string) => {
    if (url.endsWith("/api/v1/auth/me")) return Promise.resolve(jsonResponse(makeUser()));
    if (url.endsWith("/api/v1/calendar/default")) return Promise.resolve(jsonResponse(CALENDAR));
    if (url.includes(`/api/v1/calendar/${CALENDAR.id}/events`)) return Promise.resolve(jsonResponse(eventsBody));
    return Promise.resolve(jsonResponse({ detail: `unexpected request ${url}` }, 404));
  });
}

function renderCalendar() {
  return render(
    <SessionProvider>
      <CalendarRoute />
    </SessionProvider>
  );
}

/** The value shown under the "Total Events" label. */
async function totalEventsShown(): Promise<string> {
  const label = await screen.findByText("Total Events");
  return label.parentElement?.querySelector(".calendar-stat-value")?.textContent ?? "";
}

describe("calendar events list", () => {
  it("reads the events from `items`, the field the backend returns", async () => {
    const body: CalendarEventListResponse = { items: [makeEvent()], total: 1 };
    serve(body);

    renderCalendar();

    expect(await screen.findAllByText(EVENT_TITLE)).not.toHaveLength(0);
    await waitFor(async () => expect(await totalEventsShown()).toBe("1"));
  });

  it("does not read the old `events` field", async () => {
    // The shape the page used to expect. If it were still read, one event would show.
    serve({ events: [makeEvent()], total: 1 });

    renderCalendar();

    await waitFor(async () => expect(await totalEventsShown()).toBe("0"));
    expect(screen.queryByText(EVENT_TITLE)).not.toBeInTheDocument();
  });

  it("defaults a missing list to empty and keeps rendering", async () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    serve({ total: 0 });

    renderCalendar();

    await waitFor(async () => expect(await totalEventsShown()).toBe("0"));
    // A crash would have logged the TypeError and unmounted everything above.
    const crashes = consoleError.mock.calls.filter((args) =>
      args.some((arg) => arg instanceof TypeError || String(arg).includes("reading 'length'"))
    );
    expect(crashes).toHaveLength(0);
    consoleError.mockRestore();
  });
});

describe("calendar events type", () => {
  it("matches the backend's CalendarEventListResponse", () => {
    // Checked by the type checker, which includes this directory.
    expectTypeOf<Awaited<ReturnType<typeof fetchCalendarEvents>>>().toEqualTypeOf<CalendarEventListResponse>();
    expectTypeOf<CalendarEventListResponse>().toHaveProperty("items").toEqualTypeOf<ResearchCalendarEvent[]>();
    expectTypeOf<CalendarEventListResponse>().toHaveProperty("total").toEqualTypeOf<number>();
    expectTypeOf<CalendarEventListResponse>().not.toHaveProperty("events");
  });
});
