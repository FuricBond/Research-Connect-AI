/**
 * P1 — every list that shows a call's deadline or venue risk uses the canonical indicators
 * (components/research). Before, the recommendations list printed "Risk: INSUFFICIENT EVIDENCE"
 * in green next to "Deadline: 11/10/2026 (3d left)", and the candidate preview called a venue
 * with no assessment "Low Risk".
 */

import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn(), back: vi.fn(), forward: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/researcher",
  useSearchParams: () => new URLSearchParams(),
}));

import { PersonalizedCandidatePreview } from "../components/researcher/PersonalizedCandidatePreview";
import { UnifiedResearchIntelligenceView } from "../components/researcher/UnifiedResearchIntelligenceView";
import { clearActiveIdentity, storeSession } from "../services/auth";
import type { PersonalizedCandidateItem, PersonalizedCandidateSetResponse } from "../types/researcher";
import { PROFILE_ID, USER_ID, jsonResponse, makeTokenResponse } from "./factories";

const HOUR = 3_600_000;
const inHours = (hours: number) => new Date(Date.now() + hours * HOUR).toISOString();

function apiRecommendation(id: string, title: string, riskLevel: string | null, deadline: string | null, days: number | null) {
  return {
    opportunity_id: id,
    title,
    organizer: "Example Society",
    opportunity_type: "CONFERENCE",
    submission_deadline: deadline,
    final_score: 0.4,
    base_relevance_score: 0.4,
    personalization_score: 0,
    risk_explanation: riskLevel
      ? { risk_level: riskLevel, risk_score: 0, is_predatory_flag: false, risk_reasons: [] }
      : null,
    deadline_intelligence:
      days === null ? null : { primary_view: { canonical_assessment: { status: "UPCOMING", urgency_tier: "CRITICAL", days_remaining: days } } },
    workspace_context: { is_saved: false, has_active_submission: false },
    explanation: { primary_reasons: ["Matches your topics."] },
    evidence_tiers: [],
  };
}

describe("recommendations list", () => {
  beforeEach(() => {
    storeSession(makeTokenResponse());
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        const path = url.replace(/^https?:\/\/[^/]+/, "").split("?")[0];
        if (path.endsWith("/recommendations/unified"))
          return Promise.resolve(
            jsonResponse({
              items: [
                apiRecommendation("opp-1", "Workshop with no risk assessment", "INSUFFICIENT_EVIDENCE", inHours(19), 0.8),
                apiRecommendation("opp-2", "Conference flagged as high risk", "HIGH_RISK", inHours(24 * 5 + 2), 5.1),
              ],
              total_count: 2,
              researcher_context: { profile_id: PROFILE_ID, identity_status: "SELF_DECLARED_ONLY", is_cold_start: false },
              invariants_verified: true,
            })
          );
        return Promise.resolve(jsonResponse({ detail: "not used here" }, 404));
      })
    );
  });

  afterEach(() => clearActiveIdentity());

  it("states risk in canonical words, with a neutral unknown and no raw enum", async () => {
    const { container } = render(<UnifiedResearchIntelligenceView profileId={PROFILE_ID} userId={USER_ID} view="recommendations" />);

    expect(await screen.findByText("Workshop with no risk assessment")).toBeInTheDocument();
    const unknown = screen.getByText("Risk not assessed").closest(".risk-indicator");
    expect(unknown).toHaveClass("risk-unknown");
    expect(screen.getByText("High risk").closest(".risk-indicator")).toHaveClass("risk-high");
    expect(container.textContent).not.toMatch(/INSUFFICIENT|HIGH_RISK|Risk: /);
  });

  it("states time left from the deadline itself, not from a day count floored to zero", async () => {
    const { container } = render(<UnifiedResearchIntelligenceView profileId={PROFILE_ID} userId={USER_ID} view="recommendations" />);

    await screen.findByText("Workshop with no risk assessment");
    const countdowns = Array.from(container.querySelectorAll(".deadline-countdown")).map((node) => node.textContent);
    expect(countdowns).toHaveLength(2);
    // 19 hours away: the API's whole-day count is 0, which must not read "due within the hour".
    expect(countdowns[0]).toMatch(/^Due .+ · 1[89] hours left$/);
    expect(countdowns[1]).toMatch(/^Due .+ · 5 days left$/);
    expect(container.textContent).not.toMatch(/\d+d left|Deadline: /);
  });
});

function candidate(id: string, riskLevel: string | null, isPredatory = false): PersonalizedCandidateItem {
  return {
    candidate_id: id,
    opportunity: {
      id,
      title: `Call ${id}`,
      opportunity_type: "CONFERENCE",
      delivery_mode: "IN_PERSON",
      submission_deadline: inHours(24 * 3 + 2),
      topics: [],
      status: "OPEN",
      is_predatory_flag: isPredatory,
      risk_level: riskLevel,
      risk_reasons: [],
      deadline_status: "UPCOMING",
      days_remaining: 3.08,
      urgency_tier: "URGENT",
    },
    provenance: {
      candidate_id: id,
      opportunity_id: id,
      sources: [],
      matched_topics: [],
      matched_preferences: [],
      matched_expertise: [],
      reasons: [],
      retrieval_channels: [],
    },
    eligibility_passed: true,
    eligibility_reasons: [],
  };
}

describe("candidate preview", () => {
  it("never calls a venue without an assessment low risk", () => {
    const response: PersonalizedCandidateSetResponse = {
      researcher_id: PROFILE_ID,
      candidate_count: 3,
      is_cold_start: false,
      coverage: {
        explicit_preference_count: 1,
        inferred_preference_count: 0,
        expertise_count: 0,
        profile_count: 0,
        fallback_count: 0,
        unique_candidate_count: 3,
        deduplication_ratio: 0,
      },
      candidates: [candidate("a", null), candidate("b", "MODERATE_RISK"), candidate("c", null, true)],
      metadata: {},
    };
    render(
      <PersonalizedCandidatePreview candidatesResponse={response} loading={false} error={null} onRefresh={() => undefined} isRefreshing={false} />
    );

    // Only call "a" lacks an assessment ("c" is flagged predatory, which is high risk).
    expect(screen.getAllByText("Risk not assessed")).toHaveLength(1);
    expect(screen.getByText("Some risk signs")).toBeInTheDocument();
    expect(screen.getAllByText("High risk")).toHaveLength(1);
    expect(screen.queryByText(/low risk/i)).not.toBeInTheDocument();
    expect(screen.getAllByText(/^Due .+ · 3 days left$/)).toHaveLength(3);
    expect(document.body.textContent).not.toMatch(/URGENT|\(\d+d left\)/);
  });
});
