/**
 * Phase 5.13 — the Find a Supervisor page.
 *
 * A student sees ranked faculty from `GET /api/v1/researchers/{id}/supervisor-matches`, with
 * matching papers. An empty result shows the server's guidance and explains that faculty opt in
 * on Find Peers. Any other role sees a notice and the endpoint is never called.
 */

import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn(), back: vi.fn(), forward: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/supervisors",
  useSearchParams: () => new URLSearchParams(),
}));

import SupervisorsRoute from "../app/supervisors/page";
import { SessionProvider } from "../components/auth/SessionProvider";
import { storeSession } from "../services/auth";
import type { PlatformRole } from "../types/auth";
import type { SupervisorMatchResponse } from "../types/supervisor";
import { PROFILE_ID, jsonResponse, makeTokenResponse, makeUser } from "./factories";

function makeResponse(overrides: Partial<SupervisorMatchResponse> = {}): SupervisorMatchResponse {
  return {
    researcher_id: PROFILE_ID,
    matches: [
      {
        supervisor: {
          profile_id: "fa000000-0000-4000-8000-000000000001",
          full_name: "Dr. Grace Hopper",
          institution: "Open University",
          department: null,
          academic_status: "FACULTY",
          contact_email: null,
          collaboration_status: "SEEKING_COLLABORATORS",
          collaboration_interests: [],
          collaboration_note: null,
        },
        match_score: 0.55,
        tier: "MODERATE",
        confidence: 0.7,
        shared_topics: ["ranking"],
        matching_papers: [
          {
            work_id: "wk000000-0000-4000-8000-000000000001",
            title: "Neural ranking models",
            publication_year: 2024,
            similarity: 0.88,
            shared_topics: ["ranking"],
            doi: "10.1000/ranking",
            landing_page_url: null,
          },
        ],
        open_postings: [],
        signals: [],
        explanation_reasons: ["You share research topics: ranking."],
      },
    ],
    total_candidates_evaluated: 4,
    returned_count: 1,
    algorithm_version: "5.13.1",
    semantic_available: true,
    data_sufficiency: "SUFFICIENT",
    guidance: null,
    ...overrides,
  };
}

let fetchMock: ReturnType<typeof vi.fn>;

function serve(role: PlatformRole, response: SupervisorMatchResponse) {
  storeSession(makeTokenResponse({ user: makeUser({ role }) }));
  fetchMock.mockImplementation((url: string) => {
    if (url.endsWith("/api/v1/auth/me")) return Promise.resolve(jsonResponse(makeUser({ role })));
    if (url.includes(`/api/v1/researchers/${PROFILE_ID}/supervisor-matches`)) {
      return Promise.resolve(jsonResponse(response));
    }
    return Promise.resolve(jsonResponse({ detail: `unexpected request ${url}` }, 404));
  });
}

function supervisorRequests(): string[] {
  return fetchMock.mock.calls
    .map((call) => String(call[0]))
    .filter((url) => url.includes("/supervisor-matches"));
}

function renderPage() {
  return render(
    <SessionProvider>
      <SupervisorsRoute />
    </SessionProvider>
  );
}

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

describe("supervisors page", () => {
  it("lists ranked supervisors with their matching papers for a student", async () => {
    serve("STUDENT", makeResponse());

    renderPage();

    expect(await screen.findByRole("heading", { name: "Dr. Grace Hopper" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Neural ranking models" })).toHaveAttribute(
      "href",
      "https://doi.org/10.1000/ranking"
    );
    expect(screen.getByText(/1 of 4 discoverable faculty members matched/)).toBeInTheDocument();
    expect(supervisorRequests()[0]).toContain("limit=25");
  });

  it("shows the guidance and the Find Peers opt-in when nothing matched", async () => {
    serve(
      "STUDENT",
      makeResponse({
        matches: [],
        returned_count: 0,
        total_candidates_evaluated: 0,
        data_sufficiency: "NO_CANDIDATES",
        guidance: "No faculty members are currently discoverable.",
      })
    );

    renderPage();

    expect(await screen.findByText("No faculty members are currently discoverable.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Find Peers" })).toHaveAttribute("href", "/peers");
    expect(screen.getByText(/choose to be discoverable/)).toBeInTheDocument();
  });

  it("says when matches were ranked on topics only", async () => {
    serve("STUDENT", makeResponse({ semantic_available: false }));

    renderPage();

    expect(await screen.findByText(/ranked on research topics only/)).toBeInTheDocument();
  });

  it("shows other roles a notice and never requests matches", async () => {
    serve("FACULTY", makeResponse());

    renderPage();

    expect(await screen.findByText(/Find a Supervisor is for student accounts/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Find Peers" })).toHaveAttribute("href", "/peers");
    expect(supervisorRequests()).toEqual([]);
  });
});
