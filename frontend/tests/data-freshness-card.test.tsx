/**
 * Research refresh (step 4/6) — the admin console's Data freshness card.
 *
 * It reads `GET /api/v1/admin/ingestion-runs` and shows whether the scheduled research
 * refresh is on, the last run and its status, papers added in the last 24 hours, the next
 * run estimate and the last five passes, with loading, empty and error states.
 */

import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";

vi.mock("../services/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../services/api")>();
  return { ...actual, fetchIngestionRuns: vi.fn() };
});

import { DataFreshnessCard, formatRelative } from "../components/admin/DataFreshnessCard";
import { ApiError, fetchIngestionRuns } from "../services/api";
import type { IngestionRunListResponse, IngestionRunRead } from "../types/admin";

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

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(NOW);
});

afterEach(() => {
  vi.useRealTimers();
});

describe("DataFreshnessCard", () => {
  it("shows a loading state while the runs are fetched", () => {
    mockedFetch.mockReturnValue(new Promise(() => {}));
    render(<DataFreshnessCard />);

    expect(screen.getByRole("status")).toHaveTextContent("Loading data freshness");
    expect(mockedFetch).toHaveBeenCalledWith({ limit: 5 }, expect.any(AbortSignal));
  });

  it("shows the schedule, last run, papers added, next run and recent passes", async () => {
    mockedFetch.mockResolvedValue(makeResponse());
    render(<DataFreshnessCard />);

    await screen.findByRole("table", { name: "Research refresh status" });
    expect(statusRow("Scheduled refresh")).toHaveTextContent("On, every 8 h");
    expect(statusRow("Last run")).toHaveTextContent("3 hours ago");
    expect(statusRow("Last run status")).toHaveTextContent("Completed");
    expect(statusRow("Papers added (24 h)")).toHaveTextContent("37");
    expect(statusRow("Next run")).toHaveTextContent("in 5 hours");

    const runs = screen.getByRole("table", { name: "Recent research refresh runs" });
    const rows = within(runs).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent(/rising\s*1702\s*12\s*30\s*Completed/);
    expect(rows[1]).toHaveTextContent(/newest\s*1702\s*0\s*0\s*Failed \(budget exhausted\)/);
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
    render(<DataFreshnessCard />);

    expect(await screen.findByText("No research refresh has run yet.")).toBeInTheDocument();
    expect(statusRow("Scheduled refresh")).toHaveTextContent("Off");
    expect(statusRow("Last run")).toHaveTextContent("Never");
    expect(statusRow("Last run status")).toHaveTextContent("No runs yet");
    expect(statusRow("Next run")).toHaveTextContent("Not scheduled");
  });

  it("shows an error and recovers on Refresh", async () => {
    mockedFetch.mockRejectedValueOnce(new ApiError(503, "Service Unavailable"));
    render(<DataFreshnessCard />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load data freshness.");

    mockedFetch.mockResolvedValueOnce(makeResponse());
    fireEvent.click(screen.getByRole("button", { name: /refresh/i }));

    await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
    expect(statusRow("Papers added (24 h)")).toHaveTextContent("37");
    expect(mockedFetch).toHaveBeenCalledTimes(2);
  });

  it("shows the backend's message for a client error", async () => {
    mockedFetch.mockRejectedValue(new ApiError(403, "Forbidden", "Administrator role required"));
    render(<DataFreshnessCard />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Administrator role required");
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
