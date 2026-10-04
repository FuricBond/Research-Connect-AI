/**
 * Fix 1/9 — the calendar .ics export works when signed in.
 *
 * The export endpoint requires sign-in, and the page used a plain download link, which sends no
 * Bearer token, so every export failed with 401. The export is now fetched with the session's
 * credentials and saved from a Blob as `research-calendar.ics`; a 401 is reported to the
 * session exactly as `fetchJson` reports one, and the page shows progress and any error.
 */

import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn(), back: vi.fn(), forward: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/calendar",
  useSearchParams: () => new URLSearchParams(),
}));

import CalendarRoute from "../app/calendar/page";
import { SessionProvider } from "../components/auth/SessionProvider";
import { ApiError, downloadCalendarIcs, setUnauthorizedHandler } from "../services/api";
import { storeSession } from "../services/auth";
import type { ResearchCalendar } from "../types/calendar";
import { headersOf, jsonResponse, makeTokenResponse, makeUser } from "./factories";

const CALENDAR: ResearchCalendar = {
  id: "ca000000-0000-4000-8000-000000000001",
  user_id: "11111111-2222-3333-4444-555555555555",
  profile_id: null,
  name: "My research calendar",
  description: null,
  timezone: "UTC",
  is_default: true,
  event_count: 0,
  created_at: "2026-01-01T00:00:00+00:00",
  updated_at: "2026-01-01T00:00:00+00:00",
};
const ICS = "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n";

let fetchMock: ReturnType<typeof vi.fn>;
let createObjectURL: ReturnType<typeof vi.fn>;
let revokeObjectURL: ReturnType<typeof vi.fn>;
let clicked: { href: string; download: string }[];
const originalCreateObjectURL = URL.createObjectURL;
const originalRevokeObjectURL = URL.revokeObjectURL;

beforeEach(() => {
  storeSession(makeTokenResponse());
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  createObjectURL = vi.fn(() => "blob:research-calendar");
  revokeObjectURL = vi.fn();
  URL.createObjectURL = createObjectURL as unknown as typeof URL.createObjectURL;
  URL.revokeObjectURL = revokeObjectURL as unknown as typeof URL.revokeObjectURL;
  clicked = [];
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
    clicked.push({ href: this.href, download: this.download });
  });
});

afterEach(() => {
  URL.createObjectURL = originalCreateObjectURL;
  URL.revokeObjectURL = originalRevokeObjectURL;
  setUnauthorizedHandler(null);
});

describe("downloadCalendarIcs", () => {
  it("fetches the export with the bearer token and saves it as research-calendar.ics", async () => {
    fetchMock.mockResolvedValue(new Response(ICS, { status: 200, headers: { "Content-Type": "text/calendar" } }));

    await downloadCalendarIcs(CALENDAR.id);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const requested = new URL(String(fetchMock.mock.calls[0][0]));
    expect(requested.pathname).toBe(`/api/v1/calendar/${CALENDAR.id}/export.ics`);
    // No identity in the query string: the token travels in the header only.
    expect(requested.search).toBe("");
    expect(headersOf(fetchMock.mock.calls[0])).toEqual({ Authorization: "Bearer header.payload.signature" });

    expect(createObjectURL).toHaveBeenCalledWith(expect.any(Blob));
    expect(clicked).toEqual([{ href: "blob:research-calendar", download: "research-calendar.ics" }]);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:research-calendar");
    expect(document.querySelector("a[download]")).toBeNull();
  });

  it("reports a 401 to the session and saves nothing", async () => {
    const onUnauthorized = vi.fn();
    setUnauthorizedHandler(onUnauthorized);
    fetchMock.mockResolvedValue(jsonResponse({ detail: "Token has expired." }, 401));

    const error = await downloadCalendarIcs(CALENDAR.id).catch((err: unknown) => err);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(401);
    expect((error as ApiError).detail).toBe("Token has expired.");
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
    expect(createObjectURL).not.toHaveBeenCalled();
    expect(clicked).toEqual([]);
  });
});

describe("calendar page export button", () => {
  function serve(exportResponse: () => Promise<Response>) {
    fetchMock.mockImplementation((url: string) => {
      if (url.endsWith("/api/v1/auth/me")) return Promise.resolve(jsonResponse(makeUser()));
      if (url.endsWith("/api/v1/calendar/default")) return Promise.resolve(jsonResponse(CALENDAR));
      if (url.includes(`/api/v1/calendar/${CALENDAR.id}/events`)) return Promise.resolve(jsonResponse({ items: [], total: 0 }));
      if (url.endsWith(`/api/v1/calendar/${CALENDAR.id}/export.ics`)) return exportResponse();
      return Promise.resolve(jsonResponse({ detail: `unexpected request ${url}` }, 404));
    });
  }

  function renderPage() {
    return render(
      <SessionProvider>
        <CalendarRoute />
      </SessionProvider>
    );
  }

  it("is a button (not a bare link), shows progress, then saves the file", async () => {
    let answer: (response: Response) => void = () => undefined;
    serve(() => new Promise<Response>((resolve) => (answer = resolve)));
    renderPage();

    const button = await screen.findByRole("button", { name: /Export Calendar \(\.ics\)/ });
    expect(screen.queryByRole("link", { name: /Export Calendar/ })).not.toBeInTheDocument();

    fireEvent.click(button);
    expect(await screen.findByRole("button", { name: /Exporting/ })).toBeDisabled();

    answer(new Response(ICS, { status: 200 }));
    expect(await screen.findByRole("button", { name: /Export Calendar \(\.ics\)/ })).toBeEnabled();
    expect(clicked).toEqual([{ href: "blob:research-calendar", download: "research-calendar.ics" }]);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows the error when the export fails", async () => {
    serve(() => Promise.resolve(jsonResponse({ detail: "Forbidden: Calendar belongs to another user." }, 403)));
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: /Export Calendar \(\.ics\)/ }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Forbidden: Calendar belongs to another user.");
    await waitFor(() => expect(screen.getByRole("button", { name: /Export Calendar \(\.ics\)/ })).toBeEnabled());
    expect(createObjectURL).not.toHaveBeenCalled();
  });
});
