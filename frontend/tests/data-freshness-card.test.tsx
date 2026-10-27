/**
 * Research refresh (step 4/6) — the admin console's Data freshness card; since P10 the research data
 * monitor (`components/admin/ResearchDataMonitor.tsx`), which replaced it (plan §15).
 *
 * It reads `GET /api/v1/admin/ingestion-runs` and shows whether the scheduled research refresh is
 * on, the last run and its status, papers added in the last 24 hours, the next run estimate and the
 * passes of the latest refresh by lane and subfield, with loading, empty and error states. Kept from
 * the card: these facts and their words, `formatRelative`, and the pass/lane parsing of a run's
 * `research_refresh:{run_tag}:{lane}:{subfield}` label. Changed on purpose in P10: the newest 100
 * passes are read (for the last 20 refreshes), lanes and subfields have names, passes are listed in
 * the order they ran, the state has a word, a failed load is worded by the page (never the
 * server's text) and a refused one is told apart from a failure.
 */

import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";

vi.mock("../services/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../services/api")>();
  return { ...actual, fetchIngestionRuns: vi.fn() };
});

import { ResearchDataMonitor } from "../components/admin/ResearchDataMonitor";
import { SessionProvider } from "../components/auth/SessionProvider";
import { clearActiveIdentity, storeSession } from "../services/auth";
import { ApiError, fetchIngestionRuns } from "../services/api";
import type { IngestionRunListResponse, IngestionRunRead } from "../types/admin";
import { formatRelative } from "../utils/admin";
import { jsonResponse, makeTokenResponse, makeUser } from "./factories";

const NOW = new Date("2026-10-02T12:00:00Z");
const mockedFetch = vi.mocked(fetchIngestionRuns);

function makeRun(overrides: Partial<IngestionRunRead> = {}): IngestionRunRead {
  return {
    id: "run-1",
    source_id: "src-1",
    status: "COMPLETED",
    topic: "research_refresh:tag-b:rising:1702",
    pages_fetched: 1,
    records_parsed: 200,
    records_valid: 198,
    records_invalid: 2,
    records_inserted: 12,
    records_updated: 30,
    records_unchanged: 156,
    duplicates_detected: 0,
    potential_duplicates_detected: 0,
    records_expired: 0,
    error_message: null,
    metrics_detail: null,
    started_at: "2026-10-02T09:00:00Z",
    completed_at: "2026-10-02T09:04:00Z",
    ...overrides,
  };
}

function makeResponse(overrides: Partial<IngestionRunListResponse> = {}): IngestionRunListResponse {
  return {
    items: [
      makeRun(),
      makeRun({
        id: "run-2",
        status: "FAILED",
        topic: "research_refresh:tag-b:newest:1702",
        records_inserted: 0,
        records_updated: 0,
        error_message: "budget exhausted",
        started_at: "2026-10-02T08:58:00Z",
      }),
    ],
    research_refresh: {
      enabled: true,
      interval_seconds: 28_800,
      last_run_started_at: "2026-10-02T09:00:00Z",
      last_run_status: "COMPLETED",
      works_added_last_24h: 37,
      next_run_estimate: "2026-10-02T17:00:00Z",
    },
    ...overrides,
  };
}

function statusRow(label: string): HTMLElement {
  const table = screen.getByRole("table", { name: "Research refresh status" });
  const header = within(table).getByRole("rowheader", { name: label });
  return header.closest("tr") as HTMLElement;
}

function renderMonitor() {
  return render(
    <SessionProvider>
      <ResearchDataMonitor />
    </SessionProvider>
  );
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(NOW);
  mockedFetch.mockReset();
  storeSession(makeTokenResponse({ user: makeUser({ role: "ADMIN" }) }));
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => (String(url).endsWith("/api/v1/auth/me") ? Promise.resolve(jsonResponse(makeUser({ role: "ADMIN" }))) : Promise.resolve(jsonResponse({ detail: "unexpected" }, 404))))
  );
});

afterEach(() => {
  clearActiveIdentity();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("ResearchDataMonitor (was DataFreshnessCard)", () => {
  it("shows a loading state while the runs are fetched", async () => {
    mockedFetch.mockReturnValue(new Promise(() => {}));
    renderMonitor();

    expect(await screen.findByText("Loading the research data status")).toHaveAttribute("role", "status");
    await waitFor(() => expect(mockedFetch).toHaveBeenCalledWith({ limit: 100 }, expect.any(AbortSignal)));
  });

  it("shows the schedule, last run, papers added, next run and the latest refresh's passes", async () => {
    mockedFetch.mockResolvedValue(makeResponse());
    renderMonitor();

    await screen.findByRole("table", { name: "Research refresh status" });
    expect(statusRow("Scheduled refresh")).toHaveTextContent("On, every 8 h");
    expect(statusRow("Last run")).toHaveTextContent("3 hours ago");
    expect(statusRow("Last run status")).toHaveTextContent("Completed");
    expect(statusRow("Papers added (24 h)")).toHaveTextContent("37");
    expect(statusRow("Next run")).toHaveTextContent("in 5 hours");

    // The passes of the latest refresh, in the order they ran, with lane and subfield names.
    const runs = screen.getByRole("table", { name: "Latest refresh by lane" });
    const rows = within(runs).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent(/Newest papers\s*Artificial Intelligence\s*1702\s*0\s*0\s*Failed \(budget exhausted\)/);
    expect(rows[1]).toHaveTextContent(/Rising papers\s*Artificial Intelligence\s*1702\s*12\s*30\s*Completed/);
  });

  it("says when the refresh is off and nothing has run", async () => {
    mockedFetch.mockResolvedValue(
      makeResponse({
        items: [],
        research_refresh: {
          enabled: false,
          interval_seconds: 28_800,
          last_run_started_at: null,
          last_run_status: null,
          works_added_last_24h: 0,
          next_run_estimate: null,
        },
      })
    );
    renderMonitor();

    expect(await screen.findByText("No research refresh has run yet.")).toBeInTheDocument();
    expect(statusRow("Scheduled refresh")).toHaveTextContent("Off");
    expect(statusRow("Last run")).toHaveTextContent("Never");
    expect(statusRow("Last run status")).toHaveTextContent("No runs yet");
    expect(statusRow("Next run")).toHaveTextContent("Not scheduled");
  });

  it("shows an error and recovers on Refresh", async () => {
    mockedFetch.mockRejectedValueOnce(new ApiError(503, "Service Unavailable"));
    renderMonitor();

    expect(await screen.findByRole("heading", { name: "The research data status could not be loaded." })).toBeInTheDocument();
    expect(screen.queryByText(/Healthy/)).not.toBeInTheDocument();

    mockedFetch.mockResolvedValueOnce(makeResponse());
    fireEvent.click(screen.getByRole("button", { name: /refresh/i }));

    await waitFor(() => expect(screen.queryByText("The research data status could not be loaded.")).not.toBeInTheDocument());
    expect(statusRow("Papers added (24 h)")).toHaveTextContent("37");
    expect(mockedFetch).toHaveBeenCalledTimes(2);
  });

  it("tells a refused request apart from a failure, in its own words", async () => {
    mockedFetch.mockRejectedValue(new ApiError(403, "Forbidden", "Administrator role required"));
    renderMonitor();

    expect(await screen.findByRole("heading", { name: "Only administrators can see the research data status." })).toBeInTheDocument();
    expect(screen.queryByText("The research data status could not be loaded.")).not.toBeInTheDocument();
    expect(screen.queryByText("Administrator role required")).not.toBeInTheDocument();
  });
});

describe("formatRelative", () => {
  it("formats past and future times in whole units", () => {
    expect(formatRelative("2026-10-02T11:59:30Z", NOW)).toBe("just now");
    expect(formatRelative("2026-10-02T11:00:00Z", NOW)).toBe("1 hour ago");
    expect(formatRelative("2026-09-30T12:00:00Z", NOW)).toBe("2 days ago");
    expect(formatRelative("2026-10-02T12:45:00Z", NOW)).toBe("in 45 minutes");
  });
});
