/**
 * P5 — Calls for papers (/browse) and a call's page (/calls/[id]), FRONTEND_REDESIGN_PLAN.md §11.
 *
 * The list: the API's filters in the address, one request per state, 20 a page, nothing hidden
 * unasked (plan Q10, P5 decision), each call linking to its page. The page: the call and its risk
 * explanation together, not found without a request for an id that cannot be one, failures in
 * plain words with Try again, a risk failure that leaves the rest, and the signed-in actions.
 */

import React from "react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { renderToString } from "react-dom/server";

let search = new URLSearchParams();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn(), forward: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/browse",
  useSearchParams: () => search,
}));

import { SessionProvider } from "../components/auth/SessionProvider";
import { CallDetail } from "../components/calls/CallDetail";
import { OpportunityList } from "../components/OpportunityList";
import { jsonResponse } from "./factories";
import { CALL_ID, makeCall, makeDeadline, makeRisk, listAnswer } from "./p5-fixtures";
import { installDialogPolyfill, serveShell } from "./shell-support";

beforeAll(installDialogPolyfill);
beforeEach(() => visit("/browse"));

function visit(url: string) {
  window.history.replaceState(null, "", url);
  search = new URLSearchParams(window.location.search);
}

const OTHER_ID = "1a2b3c4d-5e6f-4a1b-8c2d-3e4f5a6b7c8d";
const CALLS = [
  makeCall(),
  makeCall({ id: OTHER_ID, title: "Journal of Information Retrieval Research", opportunity_type: "JOURNAL", risk_level: "MODERATE_RISK", risk_score: "0.45" as unknown as number, submission_deadline: "2026-09-01T11:59:59+00:00", indexing: ["Scopus", "DOAJ"] }),
];

type Route = (url: string, init?: RequestInit) => Response | Promise<Response> | undefined;

function serve(role: "STUDENT" | null, route: Route = () => undefined) {
  return serveShell(role, {
    other: (url, init) => {
      const answer = route(url, init);
      if (answer) return Promise.resolve(answer);
      if (url.includes("/api/opportunities?")) return Promise.resolve(jsonResponse(listAnswer(CALLS, 41)));
      if (url.includes("/api/v1/workspace?")) return Promise.resolve(jsonResponse({ items: [], total_count: 0, active_count: 0, archived_count: 0, counts_by_status: {}, counts_by_priority: {} }));
      return undefined;
    },
  });
}

const paths = (fetchMock: ReturnType<typeof serve>, part: string) =>
  fetchMock.mock.calls.map(([url, init]) => ({ url: String(url), method: (init as RequestInit | undefined)?.method ?? "GET" })).filter((call) => call.url.includes(part));
const listCalls = (fetchMock: ReturnType<typeof serve>) => paths(fetchMock, "/api/opportunities?").map((call) => Object.fromEntries(new URL(call.url).searchParams));

const withSession = (node: React.ReactNode) => <SessionProvider>{node}</SessionProvider>;

describe("Calls for papers (/browse)", () => {
  it("asks the API for the filters in the address, 20 a page, and shows them", async () => {
    visit("/browse?q=retrieval&type=JOURNAL&mode=ONLINE&upcoming=1&sort=deadline&page=2");
    const fetchMock = serve(null);
    render(withSession(<OpportunityList />));
    expect(await screen.findByRole("heading", { level: 2, name: "41 calls" })).toBeInTheDocument();

    expect(listCalls(fetchMock)).toEqual([{ search: "retrieval", opportunity_type: "JOURNAL", delivery_mode: "ONLINE", upcoming: "true", sort: "deadline", page: "2", page_size: "20" }]);
    expect(screen.getByLabelText("Type")).toHaveValue("JOURNAL");
    expect(screen.getByLabelText("Attendance")).toHaveValue("ONLINE");
    expect(screen.getByLabelText("Upcoming deadlines only")).toBeChecked();
    expect(screen.getByLabelText("Sort")).toHaveValue("deadline");
    expect(screen.getByRole("searchbox", { name: "Search calls" })).toHaveValue("retrieval");
    expect(screen.getByText("Showing 21–40 of 41 calls")).toBeInTheDocument();
  });

  it("hides nothing unasked: 'upcoming deadlines only' starts off", async () => {
    const fetchMock = serve(null);
    render(withSession(<OpportunityList />));
    await screen.findByRole("heading", { level: 2, name: "41 calls" });
    expect(listCalls(fetchMock)).toEqual([{ sort: "newest", page: "1", page_size: "20" }]);
    expect(screen.getByLabelText("Upcoming deadlines only")).not.toBeChecked();
    // A past deadline is shown, and said to be closed.
    expect(screen.getAllByRole("article")[1]).toHaveTextContent("Closed");
  });

  it("records a filter in the address and asks once, from page 1", async () => {
    visit("/browse?page=3");
    const fetchMock = serve(null);
    render(withSession(<OpportunityList />));
    await screen.findByRole("heading", { level: 2, name: "41 calls" });

    fireEvent.change(screen.getByLabelText("Type"), { target: { value: "WORKSHOP" } });
    await waitFor(() => expect(listCalls(fetchMock)).toHaveLength(2));
    expect(window.location.search).toBe("?type=WORKSHOP");
    expect(listCalls(fetchMock)[1]).toMatchObject({ opportunity_type: "WORKSHOP", page: "1" });
  });

  it("searches when the words are submitted, not while they are typed", async () => {
    const fetchMock = serve(null);
    render(withSession(<OpportunityList />));
    await screen.findByRole("heading", { level: 2, name: "41 calls" });
    const box = screen.getByRole("searchbox", { name: "Search calls" });

    fireEvent.change(box, { target: { value: "neur" } });
    fireEvent.change(box, { target: { value: "neural retrieval" } });
    expect(listCalls(fetchMock)).toHaveLength(1);
    fireEvent.submit(box.closest("form")!);
    await waitFor(() => expect(listCalls(fetchMock)).toHaveLength(2));
    expect(window.location.search).toBe("?q=neural%20retrieval");
  });

  it("follows the address back and forward, and ignores a router report the address bar has left", async () => {
    visit("/browse?type=JOURNAL");
    const fetchMock = serve(null);
    const view = render(withSession(<OpportunityList />));
    await screen.findByRole("heading", { level: 2, name: "41 calls" });

    // Back: the bar shows the unfiltered list.
    visit("/browse");
    view.rerender(withSession(<OpportunityList />));
    await waitFor(() => expect(listCalls(fetchMock)).toHaveLength(2));
    expect(screen.getByLabelText("Type")).toHaveValue("");

    // A late router notification for an older address: the bar's state stays.
    search = new URLSearchParams("type=JOURNAL");
    view.rerender(withSession(<OpportunityList />));
    await act(async () => undefined);
    expect(listCalls(fetchMock)).toHaveLength(2);
    expect(screen.getByLabelText("Type")).toHaveValue("");
  });

  it("shows each call's type, risk and deadline in words, linking to its page", async () => {
    serve(null);
    render(withSession(<OpportunityList />));
    await screen.findByRole("heading", { level: 2, name: "41 calls" });
    const [workshop, journal] = screen.getAllByRole("article");

    expect(within(workshop).getByRole("link", { name: "Workshop on Neural Retrieval Methods" })).toHaveAttribute("href", `/calls/${CALL_ID}`);
    expect(workshop).toHaveTextContent("Workshop");
    expect(workshop).toHaveTextContent("ACM · Online · Online");
    expect(within(workshop).getByText("Risk not assessed").closest(".risk-indicator")).toHaveClass("risk-unknown");
    expect(workshop).toHaveTextContent("Indexed in DBLP");
    expect(journal).toHaveTextContent("Some risk signs");
    expect(journal).not.toHaveTextContent(/45%|0\.45|MODERATE_RISK|JOURNAL/);
    // An AoE deadline is the day before its UTC instant, and says so.
    expect(journal).toHaveTextContent("Closed 31 Aug 2026 AoE");
    // A visitor sees no workspace action and asks nothing about a workspace.
    expect(within(workshop).queryByRole("button", { name: /workspace/ })).not.toBeInTheDocument();
  });

  it("looks up the signed-in researcher's tracked calls once and marks them saved", async () => {
    const fetchMock = serve("STUDENT", (url) =>
      url.includes("/api/v1/workspace?")
        ? jsonResponse({ items: [{ id: "w1", opportunity_id: CALL_ID, status: "PLANNING" }], total_count: 1, active_count: 1, archived_count: 0, counts_by_status: {}, counts_by_priority: {} })
        : undefined
    );
    render(withSession(<OpportunityList />));
    await screen.findByRole("heading", { level: 2, name: "41 calls" });
    const [workshop, journal] = screen.getAllByRole("article");
    expect(await within(workshop).findByRole("button", { name: "Saved to workspace" })).toHaveAttribute("aria-pressed", "true");
    expect(within(journal).getByRole("button", { name: "Save to workspace" })).toBeInTheDocument();
    expect(paths(fetchMock, "/api/v1/workspace?")).toHaveLength(1);
  });

  it("offers Clear filters when nothing matches, and Try again after a failure", async () => {
    visit("/browse?type=SPECIAL_ISSUE");
    let fail = false;
    const fetchMock = serve(null, (url) => {
      if (!url.includes("/api/opportunities?")) return undefined;
      if (fail) return jsonResponse({ detail: "Traceback (most recent call last)" }, 503);
      return url.includes("SPECIAL_ISSUE") ? jsonResponse(listAnswer([], 0)) : undefined;
    });
    render(withSession(<OpportunityList />));
    expect(await screen.findByRole("heading", { name: "No calls match these filters" })).toBeInTheDocument();

    fail = true;
    fireEvent.click(screen.getAllByRole("button", { name: "Clear filters" })[0]);
    expect(await screen.findByRole("heading", { name: "Calls for papers could not be loaded" })).toBeInTheDocument();
    expect(document.body).not.toHaveTextContent("Traceback");
    fail = false;
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("heading", { level: 2, name: "41 calls" })).toBeInTheDocument();
    expect(listCalls(fetchMock).length).toBe(3);
  });
});

describe("a call's page (/calls/[id])", () => {
  const detail = (overrides = {}) => makeCall({ deadline_intelligence: makeDeadline(14), apc_or_fee: { has_fee: true, amount: 350, currency: "EUR" }, last_verified_at: "2026-10-01T09:00:00Z", ...overrides });

  function serveCall(role: "STUDENT" | null, overrides: { call?: () => Response; risk?: () => Response } = {}) {
    return serve(role, (url, init) => {
      if (url.endsWith(`/api/opportunities/${CALL_ID}`)) return overrides.call ? overrides.call() : jsonResponse(detail());
      if (url.endsWith(`/api/opportunities/${CALL_ID}/risk-explanation`)) return overrides.risk ? overrides.risk() : jsonResponse(makeRisk());
      if (url.endsWith("/api/v1/workspace") && (init as RequestInit)?.method === "POST") return jsonResponse({ id: "w9", opportunity_id: CALL_ID, status: "SAVED" }, 201);
      if (url.endsWith("/api/v1/calendar/default")) return jsonResponse({ id: "cal-1" });
      if (url.includes(`/api/v1/calendar/cal-1/opportunities/${CALL_ID}/project`)) return jsonResponse({ opportunity_id: CALL_ID, calendar_id: "cal-1", projected_events: [{}, {}, {}, {}], created_count: 4, updated_count: 0, unchanged_count: 0 });
      return undefined;
    });
  }

  it("loads the call and its risk explanation together, once each, and titles the page", async () => {
    const fetchMock = serveCall(null);
    render(withSession(<CallDetail id={CALL_ID} />));
    expect(await screen.findByRole("heading", { level: 1, name: "Workshop on Neural Retrieval Methods" })).toBeInTheDocument();
    await waitFor(() => expect(document.title).toBe("Workshop on Neural Retrieval Methods — ResearchConnect AI"));

    expect(paths(fetchMock, `/api/opportunities/${CALL_ID}`).map((call) => call.url.split("8300").pop())).toHaveLength(2);
    expect(paths(fetchMock, "/deadlines")).toHaveLength(0);
    expect(paths(fetchMock, "/api/v1/workspace")).toHaveLength(0);
    expect(screen.getByRole("navigation", { name: "Breadcrumb" })).toHaveTextContent("Calls for papers");
  });

  it("lists the dates in academic order, each in its own time zone, with the main deadline marked", async () => {
    serveCall(null, { call: () => jsonResponse(detail({ deadline_intelligence: makeDeadline(5) })) });
    render(withSession(<CallDetail id={CALL_ID} />));
    const dates = await screen.findByRole("region", { name: "Dates" });
    const items = within(dates).getAllByRole("listitem");
    expect(items.map((item) => item.querySelector("p")?.textContent?.replace("Main deadline", "").trim())).toEqual(["Abstract", "Paper submission", "Notification", "Camera-ready"]);
    expect(items[1]).toHaveTextContent("Main deadline");
    expect(items[1]).toHaveTextContent("20 Oct 2026, 23:59 AoE");
    expect(items[1]).toHaveTextContent("5 days left");
    // The abstract date has passed (it is a week before the paper).
    expect(items[0]).toHaveTextContent("Closed");
    expect(items[1]).toHaveTextContent("Source: WikiCFP");
  });

  it("explains the venue risk with its evidence, and states the facts it has", async () => {
    serveCall(null);
    render(withSession(<CallDetail id={CALL_ID} />));
    const risk = await screen.findByRole("region", { name: "Venue risk" });
    expect(await within(risk).findByText("Listed in DBLP.")).toBeInTheDocument();
    expect(risk).toHaveTextContent("Low risk");
    expect(risk).toHaveTextContent("Missing information (1)");
    expect(within(risk).getByText("Technical details").closest("details")).not.toHaveAttribute("open");
    const facts = screen.getByRole("complementary", { name: "Facts" });
    expect(facts).toHaveTextContent("EUR 350");
    expect(facts).toHaveTextContent("Online");
    expect(facts).toHaveTextContent("Open");
    expect(facts).not.toHaveTextContent(/ACTIVE|ONLINE|WORKSHOP/);
  });

  it("starts loading the title face with its first paint, so a long title does not re-wrap later", () => {
    // A title that arrived before its font re-wrapped when the font swapped in (CLS 0.022 at 390px).
    const html = renderToString(withSession(<CallDetail id={CALL_ID} />));
    expect(html).toContain('aria-busy="true"');
    expect(html).toMatch(/class="[^"]*fontPrimer[^"]*"[^>]*>Call for papers</);
  });

  it("is 'not found' for an id that cannot be a call's, without asking the API", async () => {
    const fetchMock = serveCall(null);
    render(withSession(<CallDetail id="not-a-real-id" />));
    expect(await screen.findByRole("heading", { level: 1, name: "Call for papers not found" })).toBeInTheDocument();
    await act(async () => undefined);
    expect(paths(fetchMock, "/api/opportunities")).toHaveLength(0);
    expect(screen.getByRole("link", { name: "Browse calls for papers" })).toHaveAttribute("href", "/browse");
  });

  it("is 'not found' when the API does not know the call", async () => {
    serveCall(null, { call: () => jsonResponse({ detail: "Opportunity not found" }, 404), risk: () => jsonResponse({ detail: "Opportunity not found" }, 404) });
    render(withSession(<CallDetail id={CALL_ID} />));
    expect(await screen.findByRole("heading", { level: 1, name: "Call for papers not found" })).toBeInTheDocument();
  });

  it("explains a failure in plain words and retries it", async () => {
    let fail = true;
    const fetchMock = serveCall(null, { call: () => (fail ? jsonResponse({ detail: "Traceback (most recent call last)" }, 500) : jsonResponse(detail())) });
    render(withSession(<CallDetail id={CALL_ID} />));
    expect(await screen.findByRole("heading", { level: 1, name: "This call could not be loaded" })).toBeInTheDocument();
    expect(document.body).not.toHaveTextContent("Traceback");
    fail = false;
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Workshop on Neural Retrieval Methods" })).toBeInTheDocument();
    expect(paths(fetchMock, `/api/opportunities/${CALL_ID}`).filter((call) => !call.url.includes("risk"))).toHaveLength(2);
  });

  it("keeps the rest of the page when only the risk explanation fails", async () => {
    serveCall(null, { risk: () => jsonResponse({ detail: "boom" }, 500) });
    render(withSession(<CallDetail id={CALL_ID} />));
    const risk = await screen.findByRole("region", { name: "Venue risk" });
    expect(await within(risk).findByText(/could not be loaded/)).toBeInTheDocument();
    expect(within(risk).getByRole("button", { name: "Try again" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Dates" })).toBeInTheDocument();
    // The level the call itself carries is still shown.
    expect(screen.getAllByText("Risk not assessed").length).toBeGreaterThan(0);
  });

  it("offers a visitor sign-in to save, keeping the way back to this call", async () => {
    serveCall(null);
    render(withSession(<CallDetail id={CALL_ID} />));
    expect(await screen.findByRole("link", { name: "Sign in to save" })).toHaveAttribute("href", `/login?next=${encodeURIComponent(`/calls/${CALL_ID}`)}`);
    expect(screen.queryByRole("button", { name: "Add dates to calendar" })).not.toBeInTheDocument();
  });

  it("shows a tracked call's workspace status, saves, and adds its dates to the calendar", async () => {
    const fetchMock = serveCall("STUDENT");
    render(withSession(<CallDetail id={CALL_ID} />));
    await screen.findByRole("heading", { level: 1, name: "Workshop on Neural Retrieval Methods" });
    expect(paths(fetchMock, "/api/v1/workspace?")).toHaveLength(1);

    fireEvent.click(await screen.findByRole("button", { name: "Save to workspace" }));
    expect(await screen.findByRole("button", { name: "Saved to workspace" })).toBeInTheDocument();
    expect(screen.getByText(/In your workspace/)).toHaveTextContent("Saved");
    expect(screen.getByRole("link", { name: "Open in workspace" })).toHaveAttribute("href", "/workspace/w9");

    fireEvent.click(screen.getByRole("button", { name: "Add dates to calendar" }));
    expect(await screen.findByText("Added 4 dates to your calendar.")).toBeInTheDocument();
    expect(paths(fetchMock, "/project").map((call) => call.method)).toEqual(["POST"]);
  });
});
