/**
 * The collaboration page must be reachable from the workspace.
 *
 * `/workspace/[id]` (members, invitations, tasks and activity) existed, but nothing linked to
 * it, so a researcher could only reach it by typing the URL. Each workspace card now carries
 * a "Collaborate" link next to "Submissions".
 */

import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn(), back: vi.fn(), forward: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/workspace",
  useSearchParams: () => new URLSearchParams(),
}));

import WorkspacePageRoute from "../app/workspace/page";
import { SessionProvider } from "../components/auth/SessionProvider";
import { storeSession } from "../services/auth";
import type { WorkspaceItem, WorkspaceListResponse, WorkspaceSummaryResponse } from "../types/workspace";
import { USER_ID, jsonResponse, makeTokenResponse, makeUser } from "./factories";

const ITEM_ID = "ws000000-0000-4000-8000-000000000001";

const ITEM: WorkspaceItem = {
  id: ITEM_ID,
  user_id: USER_ID,
  opportunity_id: "op000000-0000-4000-8000-000000000001",
  status: "PLANNING",
  priority: "HIGH",
  tags: [],
  notes: null,
  created_at: "2026-09-20T10:00:00+00:00",
  updated_at: "2026-09-21T10:00:00+00:00",
  status_updated_at: "2026-09-21T10:00:00+00:00",
  archived_at: null,
  allowed_transitions: ["APPLIED", "ARCHIVED"],
  opportunity: {
    id: "op000000-0000-4000-8000-000000000001",
    title: "International Conference on Information Retrieval Systems",
    opportunity_type: "CONFERENCE",
    delivery_mode: "IN_PERSON",
    status: "ACTIVE",
    is_predatory_flag: false,
  },
};

const COUNTS = { total_count: 1, active_count: 1, archived_count: 0, counts_by_status: { PLANNING: 1 }, counts_by_priority: { HIGH: 1 } };
const LIST: WorkspaceListResponse = { items: [ITEM], ...COUNTS };
const SUMMARY: WorkspaceSummaryResponse = COUNTS;

beforeEach(() => {
  storeSession(makeTokenResponse());
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      if (url.endsWith("/api/v1/auth/me")) return Promise.resolve(jsonResponse(makeUser()));
      if (url.endsWith("/api/v1/workspace/summary")) return Promise.resolve(jsonResponse(SUMMARY));
      if (url.includes("/api/v1/workspace?")) return Promise.resolve(jsonResponse(LIST));
      return Promise.resolve(jsonResponse({ detail: `unexpected request ${url}` }, 404));
    })
  );
});

describe("workspace page", () => {
  it("links each item to its collaboration page", async () => {
    render(
      <SessionProvider>
        <WorkspacePageRoute />
      </SessionProvider>
    );

    expect(await screen.findByText("International Conference on Information Retrieval Systems")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /collaborate/i })).toHaveAttribute("href", `/workspace/${ITEM_ID}`);
    expect(screen.getByRole("link", { name: /submissions/i })).toHaveAttribute("href", `/workspace/${ITEM_ID}/submission`);
  });
});
