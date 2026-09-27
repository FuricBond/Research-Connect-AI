/**
 * Unified recommendations and opportunity intelligence, against the shapes the backend
 * really returns (app/schemas/research_intelligence.py).
 *
 * `GET /researchers/{id}/recommendations/unified` answers `{ items, total_count,
 * researcher_context, ... }`, but the researcher page read `data.recommendations.length`
 * and crashed with "Cannot read properties of undefined (reading 'length')". The API client
 * now maps the wire format onto the view models the components render.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  getOpportunityIntelligence,
  getUnifiedRecommendations,
  toUnifiedRecommendationResponse,
} from "../services/api";
import { storeSession } from "../services/auth";
import type {
  ApiOpportunityIntelligence,
  ApiUnifiedRecommendationItem,
  ApiUnifiedRecommendationResponse,
  UnifiedResearcherContext,
} from "../types/research_intelligence";
import { PROFILE_ID, USER_ID, jsonResponse, makeTokenResponse } from "./factories";

const OPPORTUNITY_ID = "cc87379e-a24c-449e-8c78-21305dbdd099";

const CONTEXT: UnifiedResearcherContext = {
  profile_id: PROFILE_ID,
  user_id: USER_ID,
  full_name: "Priya Raghavan",
  academic_status: "POSTGRADUATE",
  institution_name: "Fairview Institute of Technology",
  department: "Computer Science",
  identity_status: "SELF_DECLARED_ONLY",
  is_identity_ambiguous: false,
  completeness_score: 0.85,
  is_cold_start: false,
  is_partial_profile: false,
  signals: [],
  active_interests_count: 3,
  explicit_preferences_count: 0,
  inferred_preferences_count: 0,
  saved_opportunities_count: 0,
  active_submissions_count: 0,
  upcoming_tasks_count: 0,
  calendar_events_count: 0,
};

function makeItem(overrides: Partial<ApiUnifiedRecommendationItem> = {}): ApiUnifiedRecommendationItem {
  return {
    opportunity_id: OPPORTUNITY_ID,
    title: "Symposium on Human-Computer Interaction and Accessibility",
    opportunity_type: "CONFERENCE",
    publisher: "ACM Press",
    organizer: "ACM",
    submission_deadline: "2026-12-11T05:08:46Z",
    final_score: 0.1036,
    base_relevance_score: 0.1,
    personalization_score: 0.345,
    risk_explanation: {
      risk_score: 0,
      risk_level: "LOW_RISK",
      is_predatory_flag: false,
      risk_reasons: ["Trust Evidence: Organizer verified as recognized scientific society: ACM."],
    },
    deadline_intelligence: {
      reference_time: "2026-09-27T05:38:12Z",
      primary_view: {
        canonical_assessment: { status: "UPCOMING", urgency_tier: "DISTANT", days_remaining: 74.98 },
        selected_observation: { authority_tier: "OFFICIAL" },
      },
    },
    workspace_context: {
      is_saved: true,
      workspace_item_id: "ws000000-0000-4000-8000-000000000001",
      workspace_status: "PLANNING",
      has_active_submission: true,
      submission_status: "DRAFT",
      submission_readiness_score: 40,
      task_count: 2,
    },
    evidence_tiers: [
      { tier: "RESEARCH_INTEREST_EVIDENCE", title: "Research Interests", summary: "Strong match", is_active: true, score_or_status: "0.90", signals: [] },
      { tier: "DEADLINE_EVIDENCE", title: "Deadline", summary: "74 days away", is_active: true, score_or_status: "NORMAL", signals: [] },
      { tier: "RISK_EVIDENCE", title: "Risk", summary: "Verified venue", is_active: true, score_or_status: "LOW_RISK", signals: [] },
    ],
    explanation: {
      primary_reasons: ["Strong alignment with your scholarly expertise in Accessibility."],
      personalization_strength: "Some personalization",
    },
    ...overrides,
  };
}

function makeResponse(items = [makeItem()]): ApiUnifiedRecommendationResponse {
  return { items, total_count: 10, researcher_context: CONTEXT, invariants_verified: true };
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  storeSession(makeTokenResponse());
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

describe("unified recommendations", () => {
  it("reads the recommendations from `items`, the field the backend returns", async () => {
    fetchMock.mockResolvedValue(jsonResponse(makeResponse()));

    const result = await getUnifiedRecommendations(PROFILE_ID, { limit: 25, include_evidence: true });

    expect(result.recommendations).toHaveLength(1);
    expect(result.total_candidates).toBe(10);
    expect(result.returned_count).toBe(1);
    expect(result.researcher_id).toBe(PROFILE_ID);
    expect(result.identity_status).toBe("SELF_DECLARED_ONLY");
    expect(result.relevance_dominance_guarantee).toMatch(/verified/i);
  });

  it("maps scores, sponsor, risk, deadline and workspace context", () => {
    const [item] = toUnifiedRecommendationResponse(makeResponse()).recommendations;

    expect(item.sponsor).toBe("ACM");
    expect(item.composite_score).toBe(0.1036);
    expect(item.relevance_score).toBe(0.1);
    expect(item.risk_level).toBe("LOW_RISK");
    expect(item.is_high_risk).toBe(false);
    expect(item.risk_factors).toHaveLength(1);
    expect(item.deadline_status).toBe("UPCOMING");
    expect(item.deadline_urgency).toBe("DISTANT");
    expect(item.deadline_source_authority).toBe("OFFICIAL");
    expect(item.days_remaining).toBe(74);
    expect(item.workspace_context).toMatchObject({ is_saved: true, saved_status: "PLANNING", submission_stage: "DRAFT" });
    expect(item.primary_match_reason).toMatch(/Accessibility/);
  });

  it("keeps numeric evidence tiers as scores and shows status tiers as labels", () => {
    const [item] = toUnifiedRecommendationResponse(makeResponse()).recommendations;
    const [interest, deadline, risk] = item.evidence_tiers;

    expect(interest).toMatchObject({ tier_title: "Research Interests", score_contribution: 0.9, status_label: null });
    expect(deadline).toMatchObject({ score_contribution: 0, status_label: "NORMAL" });
    expect(risk.status_label).toBe("LOW RISK");
  });

  it("flags high-risk and predatory venues", () => {
    const high = makeItem({ risk_explanation: { risk_score: 0.8, risk_level: "HIGH_RISK", is_predatory_flag: false } });
    const predatory = makeItem({ risk_explanation: { risk_score: 0.4, risk_level: "MODERATE_RISK", is_predatory_flag: true } });

    const items = toUnifiedRecommendationResponse(makeResponse([high, predatory])).recommendations;

    expect(items.map((i) => i.is_high_risk)).toEqual([true, true]);
  });

  it("tolerates a missing deadline assessment and an empty page", () => {
    const noDeadline = makeItem({ deadline_intelligence: null, risk_explanation: null });

    const [item] = toUnifiedRecommendationResponse(makeResponse([noDeadline])).recommendations;
    const empty = toUnifiedRecommendationResponse({ ...makeResponse([]), items: [] });

    expect(item.days_remaining).toBeNull();
    expect(item.risk_level).toBeNull();
    expect(empty.recommendations).toEqual([]);
    expect(empty.returned_count).toBe(0);
  });
});

describe("opportunity intelligence", () => {
  it("maps the intelligence detail the Inspect view shows", async () => {
    const body: ApiOpportunityIntelligence = {
      profile_id: PROFILE_ID,
      opportunity_id: OPPORTUNITY_ID,
      title: "Symposium on Human-Computer Interaction and Accessibility",
      base_relevance_score: 0.1,
      final_score: 0.1036,
      personalization_adjustment: 0.0036,
      evidence_tiers: makeItem().evidence_tiers,
      workspace_context: makeItem().workspace_context,
      deadline_intelligence: { reference_time: "2026-09-27T05:38:12Z" },
    };
    fetchMock.mockResolvedValue(jsonResponse(body));

    const intel = await getOpportunityIntelligence(PROFILE_ID, OPPORTUNITY_ID);

    expect(intel).toMatchObject({
      researcher_id: PROFILE_ID,
      opportunity_title: body.title,
      relevance_score: 0.1,
      composite_score: 0.1036,
      personalization_score: 0.0036,
      evaluated_at: "2026-09-27T05:38:12Z",
    });
    expect(intel.evidence_tiers[1].status_label).toBe("NORMAL");
    expect(String(fetchMock.mock.calls[0][0])).toContain(
      `/api/v1/researchers/${PROFILE_ID}/recommendations/unified/${OPPORTUNITY_ID}/intelligence`
    );
  });
});
