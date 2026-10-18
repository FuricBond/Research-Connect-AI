/**
 * P1 — every list that shows a call's deadline or venue risk uses the canonical indicators
 * (components/research). Before, the recommendations list printed "Risk: INSUFFICIENT EVIDENCE"
 * in green next to "Deadline: 11/10/2026 (3d left)", and the candidate preview called a venue
 * with no assessment "Low Risk".
 *
 * P6: the recommendations are on /recommendations (the shared call card) and the candidate
 * preview is "Calls considered before ranking" under its technical details; the guard follows them.
 */

import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn(), back: vi.fn(), forward: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/recommendations",
  useSearchParams: () => new URLSearchParams(),
}));

import RecommendationsRoute from "../app/recommendations/page";
import CandidatesPart from "../components/recommendations/technical/CandidatesPart";
import HistoryPart from "../components/recommendations/technical/HistoryPart";
import { SessionProvider } from "../components/auth/SessionProvider";
import { clearActiveIdentity, storeSession } from "../services/auth";
import type { PersonalizedCandidateItem } from "../types/researcher";
import { PROFILE_ID, jsonResponse, makeTokenResponse, makeUser } from "./factories";

const BASE = `/api/v1/researchers/${PROFILE_ID}`;
const HOUR = 3_600_000;
const inHours = (hours: number) => new Date(Date.now() + hours * HOUR).toISOString();

function opportunity(id: string, title: string, riskLevel: string | null, deadline: string | null, days: number | null, isPredatory = false) {
  return {
    id,
    title,
    opportunity_type: "CONFERENCE",
    delivery_mode: "IN_PERSON",
    organizer: "Example Society",
    submission_deadline: deadline,
    topics: [],
    status: "OPEN",
    is_predatory_flag: isPredatory,
    risk_level: riskLevel,
    risk_reasons: [],
    deadline_status: "UPCOMING",
    days_remaining: days,
    urgency_tier: "CRITICAL",
  };
}

function rankedItem(id: string, rank: number, title: string, riskLevel: string | null, deadline: string | null, days: number | null) {
  return {
    opportunity_id: id,
    rank,
    base_rank: rank,
    rank_delta: 0,
    final_score: 0.4,
    base_relevance_score: 0.4,
    personalization_score: 0,
    personalization_adjustment: 0,
    score_breakdown: {},
    matched_signals: { matched_topics: [], matched_preferences: [], matched_expertise: [], matched_types: [] },
    provenance: { candidate_id: id, opportunity_id: id, sources: [], matched_topics: [], matched_preferences: [], matched_expertise: [], reasons: [] },
    opportunity: opportunity(id, title, riskLevel, deadline, days),
    explanation: { primary_reasons: ["Matches your topics."] },
  };
}

function candidate(id: string, riskLevel: string | null, isPredatory = false): PersonalizedCandidateItem {
  return {
    candidate_id: id,
    opportunity: opportunity(id, `Call ${id}`, riskLevel, inHours(24 * 3 + 2), 3.08, isPredatory) as PersonalizedCandidateItem["opportunity"],
    provenance: { candidate_id: id, opportunity_id: id, sources: [], matched_topics: [], matched_preferences: [], matched_expertise: [], reasons: [] } as unknown as PersonalizedCandidateItem["provenance"],
    eligibility_passed: true,
    eligibility_reasons: [],
  };
}

let paths: string[] = [];

beforeEach(() => {
  paths = [];
  storeSession(makeTokenResponse());
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      const path = url.replace(/^https?:\/\/[^/]+/, "").split("?")[0];
      paths.push(path);
      if (path === "/api/v1/auth/me") return Promise.resolve(jsonResponse(makeUser()));
      if (path === `${BASE}/personalized-recommendations`) {
        return Promise.resolve(
          jsonResponse({
            researcher_id: PROFILE_ID,
            total_candidates: 2,
            ranked_count: 2,
            is_cold_start: false,
            personalization_enabled: true,
            max_personalization_contribution: 0.15,
            recommendations: [
              rankedItem("opp-1", 1, "Workshop with no risk assessment", "INSUFFICIENT_EVIDENCE", inHours(19), 0.8),
              rankedItem("opp-2", 2, "Conference flagged as high risk", "HIGH_RISK", inHours(24 * 5 + 2), 5.1),
            ],
            metadata: {},
          })
        );
      }
      if (path === `${BASE}/personalized-candidates`) {
        return Promise.resolve(
          jsonResponse({
            researcher_id: PROFILE_ID,
            candidate_count: 3,
            is_cold_start: false,
            coverage: { explicit_preference_count: 1, inferred_preference_count: 0, expertise_count: 0, profile_count: 0, fallback_count: 0, unique_candidate_count: 3, deduplication_ratio: 0 },
            candidates: [candidate("a", null), candidate("b", "MODERATE_RISK"), candidate("c", null, true)],
            metadata: {},
          })
        );
      }
      if (path === `${BASE}/recommendation-history`) {
        return Promise.resolve(
          jsonResponse({
            researcher_id: PROFILE_ID,
            items: [{ id: "snap-1", researcher_id: PROFILE_ID, ranking_version: "phase3.7-v1", candidate_count: 9, returned_count: 1, request_context: {}, created_at: "2026-10-01T09:00:00+00:00", top_opportunity_titles: ["Kept call"] }],
            total: 1,
            limit: 20,
            offset: 0,
          })
        );
      }
      if (path === `${BASE}/recommendation-history/snap-1`) {
        return Promise.resolve(
          jsonResponse({
            id: "snap-1",
            researcher_id: PROFILE_ID,
            ranking_version: "phase3.7-v1",
            candidate_count: 9,
            returned_count: 1,
            request_context: {},
            created_at: "2026-10-01T09:00:00+00:00",
            items: [
              { id: "i1", snapshot_id: "snap-1", opportunity_id: "opp-9", rank: 1, base_relevance_score: 0.5, personalization_score: 0.2, behavioral_adjustment: 0.01, final_score: 0.53, created_at: "", opportunity: { id: "opp-9", title: "Kept call" }, user_feedback: ["SAVE"] },
            ],
          })
        );
      }
      if (path === `${BASE}/recommendation-history/snap-1/items/opp-9/explanation`) {
        return Promise.resolve(jsonResponse({ primary_reasons: ["It matched your stated topic then."], ranking_version: "phase3.7-v1", is_historical: true }));
      }
      return Promise.resolve(jsonResponse({}, 200));
    })
  );
});

afterEach(() => clearActiveIdentity());

const withSession = (node: React.ReactNode) => render(<SessionProvider>{node}</SessionProvider>);

describe("recommendations list", () => {
  it("states risk in canonical words, with a neutral unknown and no raw enum", async () => {
    const { container } = withSession(<RecommendationsRoute />);

    expect(await screen.findByRole("link", { name: "Workshop with no risk assessment" })).toBeInTheDocument();
    const unknown = screen.getByText("Risk not assessed").closest(".risk-indicator");
    expect(unknown).toHaveClass("risk-unknown");
    expect(screen.getByText("High risk").closest(".risk-indicator")).toHaveClass("risk-high");
    expect(container.textContent).not.toMatch(/INSUFFICIENT|HIGH_RISK|Risk: /);
  });

  it("states time left from the deadline itself, not from a day count floored to zero", async () => {
    const { container } = withSession(<RecommendationsRoute />);

    await screen.findByRole("link", { name: "Workshop with no risk assessment" });
    const countdowns = Array.from(container.querySelectorAll(".opportunity-card .deadline-countdown")).map((node) => node.textContent);
    expect(countdowns).toHaveLength(2);
    expect(countdowns[0]).toMatch(/^Due .+ · 1[89] hours left$/);
    expect(countdowns[1]).toMatch(/^Due .+ · 5 days left$/);
    expect(container.textContent).not.toMatch(/\d+d left|Deadline: /);
  });
});

describe("calls considered before ranking", () => {
  it("never calls a venue without an assessment low risk", async () => {
    withSession(<CandidatesPart profileId={PROFILE_ID} />);

    expect(await screen.findByText("Call a")).toBeInTheDocument();
    // Only call "a" lacks an assessment ("c" is flagged predatory, which is high risk).
    expect(screen.getAllByText("Risk not assessed")).toHaveLength(1);
    expect(screen.getByText("Some risk signs")).toBeInTheDocument();
    expect(screen.getAllByText("High risk")).toHaveLength(1);
    expect(screen.queryByText(/low risk/i)).not.toBeInTheDocument();
    expect(screen.getAllByText(/^Due .+ · 3 days left$/)).toHaveLength(3);
    expect(document.body.textContent).not.toMatch(/URGENT|\(\d+d left\)/);
  });
});

describe("recommendation history", () => {
  it("explains a kept recommendation as it was then, in the shared Evidence panel", async () => {
    withSession(<HistoryPart profileId={PROFILE_ID} />);

    fireEvent.click(await screen.findByRole("button", { name: /Show the list/ }));
    const table = await screen.findByRole("table", { name: /1 recommendation kept/ });
    expect(within(table).getByText("Saved")).toBeInTheDocument();
    fireEvent.click(within(table).getByRole("button", { name: "Why? Kept call, as recommended then" }));

    const panel = await screen.findByRole("dialog", { name: "Why this match?" });
    expect(await within(panel).findByText("It matched your stated topic then.")).toBeInTheDocument();
    expect(within(panel).getByRole("heading", { name: "How well it matched you" })).toBeInTheDocument();
    // As it was then: nothing live is asked for it.
    await waitFor(() => expect(paths).toContain(`${BASE}/recommendation-history/snap-1/items/opp-9/explanation`));
    expect(paths.some((path) => path.endsWith("/personalization") && path.includes("/recommendations/"))).toBe(false);
  });
});
