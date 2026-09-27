/**
 * The Submissions page. The navigation bar linked to /submissions, but no page existed, so
 * signed-in researchers landed on a 404. The page lists every tracked submission from
 * `GET /api/v1/submissions` and links each one to its workspace submission view.
 */

import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn(), back: vi.fn(), forward: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/submissions",
  useSearchParams: () => new URLSearchParams(),
}));

import SubmissionsRoute from "../app/submissions/page";
import { SessionProvider } from "../components/auth/SessionProvider";
import { storeSession } from "../services/auth";
import type { ResearchSubmission, ResearchSubmissionListResponse, SubmissionSummaryResponse } from "../types/submission";
import { jsonResponse, makeTokenResponse, makeUser } from "./factories";

const WORKSPACE_ITEM_ID = "ws000000-0000-4000-8000-000000000001";

function makeSubmission(): ResearchSubmission {
  return {
    id: "su000000-0000-4000-8000-000000000001",
    workspace_item_id: WORKSPACE_ITEM_ID,
    title: "Query understanding for low-resource languages",
    submission_type: "FULL_PAPER",
    status: "DRAFT",
    venue: null,
    status_updated_at: "2026-09-20T10:00:00+00:00",
    created_at: "2026-09-20T10:00:00+00:00",
    updated_at: "2026-09-21T10:00:00+00:00",
    allowed_transitions: ["READY", "WITHDRAWN"],
    workspace_status: "PLANNING",
    opportunity_id: "op000000-0000-4000-8000-000000000001",
    opportunity_title: "International Conference on Information Retrieval Systems",
    venue_name: "ICIRS 2026",
    deadline_context: {
      submission_deadline: "2026-11-18T23:59:00+00:00",
      days_remaining: 52.4,
      urgency_tier: "NORMAL",
      is_aoe: false,
      has_extension: false,
      has_conflict: false,
    },
  };
}

const SUMMARY: SubmissionSummaryResponse = {
  total_submissions: 1,
  active_submissions: 1,
  accepted_submissions: 0,
  rejected_submissions: 0,
  withdrawn_submissions: 0,
  counts_by_status: { DRAFT: 1 },
  counts_by_type: { FULL_PAPER: 1 },
};

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  storeSession(makeTokenResponse());
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

function serve(list: ResearchSubmissionListResponse) {
  fetchMock.mockImplementation((url: string) => {
    if (url.endsWith("/api/v1/auth/me")) return Promise.resolve(jsonResponse(makeUser()));
    if (url.endsWith("/api/v1/submissions/summary")) return Promise.resolve(jsonResponse(SUMMARY));
    if (url.includes("/api/v1/submissions?")) return Promise.resolve(jsonResponse(list));
    return Promise.resolve(jsonResponse({ detail: `unexpected request ${url}` }, 404));
  });
}

function renderPage() {
  return render(
    <SessionProvider>
      <SubmissionsRoute />
    </SessionProvider>
  );
}

describe("submissions page", () => {
  it("lists tracked submissions and links each to its workspace submission view", async () => {
    serve({ items: [makeSubmission()], total_count: 1, counts_by_status: { DRAFT: 1 }, counts_by_type: { FULL_PAPER: 1 } });

    renderPage();

    expect(await screen.findByText("Query understanding for low-resource languages")).toBeInTheDocument();
    // "Draft" is also an option in the status filter; the badge is the one that matters.
    expect(screen.getAllByText("Draft").some((el) => el.classList.contains("workspace-status-badge"))).toBe(true);
    expect(screen.getByText("ICIRS 2026")).toBeInTheDocument();
    expect(screen.getByText(/52 days left/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open/i })).toHaveAttribute("href", `/workspace/${WORKSPACE_ITEM_ID}/submission`);
  });

  it("explains how to start when there are no submissions", async () => {
    serve({ items: [], total_count: 0, counts_by_status: {}, counts_by_type: {} });

    renderPage();

    expect(await screen.findByText("No submissions yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open workspace/i })).toHaveAttribute("href", "/workspace");
  });
});
