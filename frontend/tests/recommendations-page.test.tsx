/**
 * P6 — /recommendations (plan §12).
 *
 *  - The ranked calls, grouped by the interest each matched ("Because you follow …"), each with
 *    the match band, the API's main reason and "Why this match?" (the shared Evidence panel).
 *  - Helpful / Not relevant record recommendation feedback (Phase 3.6) and can be undone.
 *  - Save records a "saved" interaction and adds the call to the workspace.
 *  - "What shapes your recommendations": stated and inferred preferences, remove, the switches,
 *    and a reset that says what it keeps before anything is cleared.
 *  - Four requests besides the shell's; the technical details ask for nothing until opened.
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
import { groupRecommendations } from "../components/recommendations/grouping";
import { SessionProvider } from "../components/auth/SessionProvider";
import { clearActiveIdentity, storeSession } from "../services/auth";
import type { PersonalizedRankedCandidate } from "../types/researcher";
import { PROFILE_ID, USER_ID, jsonResponse, makeTokenResponse, makeUser } from "./factories";

const BASE = `/api/v1/researchers/${PROFILE_ID}`;
const HOUR = 3_600_000;

function ranked(id: string, rank: number, title: string, matched: { topics?: string[]; preferences?: string[]; expertise?: string[] }, overrides: Partial<PersonalizedRankedCandidate> = {}): PersonalizedRankedCandidate {
  return {
    opportunity_id: id,
    rank,
    base_rank: rank + 1,
    rank_delta: 1,
    final_score: 0.72,
    base_relevance_score: 0.66,
    personalization_score: 0.4,
    personalization_adjustment: 0.06,
    score_breakdown: {
      explicit_preference_score: 0.5,
      inferred_preference_score: 0.1,
      expertise_match_score: 0.3,
      profile_match_score: 0.2,
      provenance_score: 0.1,
      raw_personalization_score: 0.4,
      relevance_damping: 0.9,
    },
    matched_signals: { matched_topics: matched.topics ?? [], matched_preferences: matched.preferences ?? [], matched_expertise: matched.expertise ?? [], matched_types: [] },
    provenance: { candidate_id: id, opportunity_id: id, sources: [], matched_topics: [], matched_preferences: [], matched_expertise: [], reasons: [] },
    opportunity: {
      id,
      title,
      opportunity_type: "CONFERENCE",
      delivery_mode: "ONLINE",
      organizer: "Example Society",
      submission_deadline: new Date(Date.now() + 24 * 5 * HOUR).toISOString(),
      topics: [],
      status: "OPEN",
      is_predatory_flag: false,
      risk_level: "INSUFFICIENT_EVIDENCE",
      risk_reasons: [],
      days_remaining: 5,
    },
    // The Phase 3.8 explanation as the API sends it (app/schemas/recommendation_explanation.py).
    explanation: {
      opportunity_id: id,
      rank,
      final_score: 0.72,
      base_relevance_score: 0.66,
      personalization_contribution: 0.06,
      personalization_strength: "Personalized",
      primary_reasons: [`It matches your interest in ${matched.topics?.[0] ?? "your research"}.`],
      supporting_reasons: [],
      behavioral_reasons: [],
      preference_reasons: ["You prefer conferences."],
      expertise_reasons: [],
      negative_signals: ["You dismissed a similar call."],
      factors: [{ category: "EXPLICIT_PREFERENCE", title: "Type match", description: "Matches your preferred type: Conference", impact: "POSITIVE", weight_contribution: 0.04 }],
      risk_summary: "Verified academic venue.",
      deadline_summary: "Upcoming submission deadline approaching.",
      confidence: 0.79,
      trust_status: "Verified",
      is_historical: false,
      ranking_version: "phase3.8-v1",
    },
    ...overrides,
  } as PersonalizedRankedCandidate;
}

const RANKING = {
  researcher_id: PROFILE_ID,
  total_candidates: 30,
  ranked_count: 3,
  is_cold_start: false,
  personalization_enabled: true,
  max_personalization_contribution: 0.15,
  recommendations: [
    ranked("op000000-0000-4000-8000-000000000001", 1, "Workshop on graph learning", { topics: ["Graph neural networks"], preferences: ["Topic: Graph neural networks"] }),
    ranked("op000000-0000-4000-8000-000000000002", 2, "Open call with no matched topic", {}),
    ranked("op000000-0000-4000-8000-000000000003", 3, "Conference on message passing", { topics: ["Graph neural networks"], preferences: ["Topic: Graph neural networks"] }),
  ],
  ablation_summary: { total_candidates: 30, reordered_candidates_count: 4, max_rank_promotion: 2, max_rank_demotion: -1, average_personalization_adjustment: 0.03, invariants_verified: true },
  metadata: {},
};

const preference = (id: string, label: string, category: string, source: string, extra: Record<string, unknown> = {}) => ({
  id,
  profile_id: PROFILE_ID,
  category,
  preference_type: "PREFERRED",
  preference_key: category.toLowerCase(),
  preference_value: label,
  display_label: label,
  strength: 0.8,
  confidence: 0.7,
  source,
  is_active: true,
  recency_score: 0.9,
  provenance_reasons: [],
  ...extra,
});

const PREFERENCES = {
  profile_id: PROFILE_ID,
  user_id: USER_ID,
  display_name: "Ada Lovelace",
  explicit_preferences: [preference("p1", "Graph neural networks", "TOPIC", "EXPLICIT")],
  inferred_preferences: [preference("i1", "Conference", "OPPORTUNITY_TYPE", "INFERRED", { strength: 0.6, provenance_reasons: ["3 of 5 saved opportunities were conferences (60%)"] })],
  derived_candidates: [],
  conflicts: [],
  completeness: { score: 0.4, percentage: 40, is_complete: false, missing_dimensions: [], dimension_breakdown: {} },
  summary: { total_preferences: 2, explicit_count: 1, inferred_count: 1, derived_count: 0, has_conflicts: false, confidence_level: "MEDIUM", completeness_percentage: 40 },
  generated_at: "2026-10-01T00:00:00+00:00",
};

const SETTINGS = {
  id: "s1",
  profile_id: PROFILE_ID,
  personalization_enabled: true,
  adaptive_signals_enabled: true,
  feedback_learning_enabled: true,
  personalization_state_version: 3,
  created_at: "2026-01-01T00:00:00+00:00",
  updated_at: "2026-01-01T00:00:00+00:00",
};

let calls: { method: string; path: string; query: string; body: unknown }[] = [];

beforeEach(() => {
  calls = [];
  storeSession(makeTokenResponse());
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      const relative = url.replace(/^https?:\/\/[^/]+/, "");
      const [path, query = ""] = relative.split("?");
      const method = init?.method ?? "GET";
      calls.push({ method, path, query, body: init?.body ? JSON.parse(String(init.body)) : null });
      if (path === "/api/v1/auth/me") return Promise.resolve(jsonResponse(makeUser()));
      if (path === `${BASE}/personalized-recommendations`) return Promise.resolve(jsonResponse(RANKING));
      if (path === `${BASE}/preference-intelligence`) return Promise.resolve(jsonResponse(PREFERENCES));
      if (path === `${BASE}/personalization/settings` && method === "GET") return Promise.resolve(jsonResponse(SETTINGS));
      if (path === `${BASE}/personalization/settings` && method === "PATCH") {
        return Promise.resolve(jsonResponse({ ...SETTINGS, ...(JSON.parse(String(init!.body)) as object) }));
      }
      if (path === `${BASE}/personalization/reset`) {
        return Promise.resolve(
          jsonResponse({ status: "ok", personalization_state_version: 4, adaptive_signals_reset: 2, calibration_states_reset: 1, contextual_modifiers_reset: 0, drift_evaluations_reset: 0, reset_at: null, explicit_preferences_changed: 0, researcher_profile_changed: 0, message: "", timestamp: "" })
        );
      }
      if (path === "/api/v1/workspace" && method === "GET") {
        return Promise.resolve(jsonResponse({ items: [], total_count: 0, active_count: 0, archived_count: 0, counts_by_status: {}, counts_by_priority: {} }));
      }
      if (path === "/api/v1/workspace" && method === "POST") {
        const body = JSON.parse(String(init!.body)) as { opportunity_id: string };
        return Promise.resolve(jsonResponse({ id: "ws1", opportunity_id: body.opportunity_id, status: "SAVED" }, 201));
      }
      if (path.endsWith("/interactions") && method === "POST") return Promise.resolve(jsonResponse({ id: "in1", interaction_type: "SAVED" }, 201));
      if (path === `${BASE}/feedback` && method === "POST") return Promise.resolve(jsonResponse({ id: "fb1", feedback_type: (JSON.parse(String(init!.body)) as { feedback_type: string }).feedback_type }, 201));
      if (path.startsWith(`${BASE}/feedback/`) && method === "DELETE") return Promise.resolve(jsonResponse({ deleted: true }));
      if (path.startsWith(`${BASE}/preferences/`) && method === "DELETE") return Promise.resolve(jsonResponse({ deleted: true, preference_id: "p1" }));
      if (path.includes("/recommendations/") && path.endsWith("/personalization")) {
        return Promise.resolve(
          jsonResponse({
            recommendation_id: "r1",
            opportunity_id: RANKING.recommendations[0].opportunity_id,
            opportunity_title: "Workshop on graph learning",
            personalization_impact: "MODERATE_PERSONALIZATION",
            base_relevance_score: 0.66,
            personalization_score: 0.4,
            final_score: 0.72,
            // The Phase 5.9 response as the API sends it (app/schemas/personalization_transparency.py).
            explicit_preference_factors: [{ category: "TOPIC", value: "Graph neural networks", preference_type: "PREFERRED", summary: "Matches your explicit preferred preference for topic: Graph neural networks" }],
            adaptive_signal_factors: [],
            calibration_factors: [],
            contextual_factors: [],
            governance_state: "ALLOW",
            governance_multiplier: 1,
            governance_notes: null,
            deterministic_explanation: "Your stated topic moved it up a little.",
            contributing_factors_summary: ["✓ Matches your explicit research preferences"],
            algorithm_version: "5.9.1",
            evaluated_at: "2026-10-18T00:00:00+00:00",
            personalization_state_version: 3,
          })
        );
      }
      return Promise.resolve(jsonResponse({ detail: `unexpected ${method} ${path}` }, 404));
    })
  );
});

afterEach(() => clearActiveIdentity());

function renderPage() {
  return render(
    <SessionProvider>
      <RecommendationsRoute />
    </SessionProvider>
  );
}

const pageRequests = () => calls.filter((call) => call.path !== "/api/v1/auth/me");
const card = (title: string) => screen.getByRole("article", { name: title });

describe("grouping", () => {
  it("groups by the interest the most items share, keeps the ranking and puts unmatched calls last", () => {
    const groups = groupRecommendations(RANKING.recommendations);
    expect(groups.map((group) => [group.reason, group.topic, group.items.map((item) => item.rank)])).toEqual([
      ["follow", "Graph neural networks", [1, 3]],
      ["other", null, [2]],
    ]);
  });

  it("says a topic comes from the publications when no preference matched it", () => {
    const [group] = groupRecommendations([ranked("x", 1, "X", { topics: ["Retrieval"], expertise: ["Retrieval (PRIMARY_EXPERTISE)"] })]);
    expect(group.reason).toBe("work");
  });
});

describe("recommendations page", () => {
  it("lists the calls by the interest they matched, with band, reason and Why this match?", async () => {
    renderPage();

    const follow = await screen.findByRole("heading", { level: 2, name: "Because you follow Graph neural networks" });
    const section = follow.closest("section")!;
    expect(within(section).getAllByRole("article")).toHaveLength(2);
    expect(screen.getByRole("heading", { level: 2, name: "More calls for you" })).toBeInTheDocument();

    const first = card("Workshop on graph learning");
    expect(first).toHaveTextContent("1.");
    expect(first).toHaveTextContent("It matches your interest in Graph neural networks.");
    expect(first).toHaveTextContent(/Strong match|Good match|match · 72%/);
    expect(within(first).getByRole("button", { name: "Why this match? Workshop on graph learning" })).toBeInTheDocument();
    // Canonical indicators: a venue without an assessment is "not assessed", never low risk.
    expect(first).toHaveTextContent("Risk not assessed");
    expect(first).not.toHaveTextContent(/INSUFFICIENT|Low risk/);
    expect(screen.getByText(/3 calls, ranked by relevance to your research and adjusted a little/)).toBeInTheDocument();
  });

  it("asks four things besides the shell, and nothing of the diagnostics until they are opened", async () => {
    renderPage();
    await screen.findByRole("heading", { name: "Because you follow Graph neural networks" });
    await screen.findByText("From your saved calls");

    await waitFor(() => expect(pageRequests()).toHaveLength(4));
    expect(pageRequests().map((call) => `${call.method} ${call.path}`).sort()).toEqual(
      [`GET ${BASE}/personalized-recommendations`, `GET ${BASE}/preference-intelligence`, `GET ${BASE}/personalization/settings`, "GET /api/v1/workspace"].sort()
    );

    const technical = screen.getByRole("region", { name: "Technical details" });
    expect(within(technical).getByText("Signals learned from your activity")).toBeInTheDocument();
    expect(calls.some((call) => /adaptive-signals|calibration|quality|health|drift|governance|history|evaluation/.test(call.path))).toBe(false);
  });

  it("records Helpful as recommendation feedback with its rank, and undoes it", async () => {
    renderPage();
    const first = await screen.findByRole("article", { name: "Workshop on graph learning" });

    fireEvent.click(within(first).getByRole("button", { name: "Helpful" }));
    await waitFor(() => expect(within(first).getByRole("button", { name: "Helpful" })).toHaveAttribute("aria-pressed", "true"));
    const sent = calls.find((call) => call.method === "POST" && call.path === `${BASE}/feedback`)!;
    // The backend's FeedbackSource is RECOMMENDATION | DISCOVERY | DIRECT | SEARCH (the e2e suite caught a 422).
    expect(sent.body).toEqual({ opportunity_id: RANKING.recommendations[0].opportunity_id, feedback_type: "INTERESTED", source: "RECOMMENDATION", rank_position: 1 });
    expect(within(first).getByRole("status")).toHaveTextContent("Marked helpful. Your feedback shapes later recommendations.");

    fireEvent.click(within(first).getByRole("button", { name: "Undo" }));
    await waitFor(() => expect(calls.some((call) => call.method === "DELETE" && call.path === `${BASE}/feedback/fb1`)).toBe(true));
    expect(await within(first).findByText("Feedback removed.")).toBeInTheDocument();
    expect(within(first).getByRole("button", { name: "Helpful" })).toHaveAttribute("aria-pressed", "false");
  });

  it("saves a call as a saved interaction and a workspace item", async () => {
    renderPage();
    const first = await screen.findByRole("article", { name: "Workshop on graph learning" });

    fireEvent.click(within(first).getByRole("button", { name: "Save to workspace" }));
    await waitFor(() => expect(within(first).getByRole("button", { name: "Saved to workspace" })).toBeInTheDocument());
    const interaction = calls.find((call) => call.path.endsWith("/interactions"))!;
    expect(interaction.path).toBe(`${BASE}/opportunities/${RANKING.recommendations[0].opportunity_id}/interactions`);
    expect(interaction.body).toMatchObject({ interaction_type: "SAVED", source: "RECOMMENDATION" });
    expect(calls.find((call) => call.method === "POST" && call.path === "/api/v1/workspace")!.body).toEqual({ opportunity_id: RANKING.recommendations[0].opportunity_id });
  });

  it("explains a match in the shared Evidence panel, from the API's own reasons", async () => {
    renderPage();
    const first = await screen.findByRole("article", { name: "Workshop on graph learning" });
    fireEvent.click(within(first).getByRole("button", { name: "Why this match? Workshop on graph learning" }));

    const panel = await screen.findByRole("dialog", { name: "Why this match?" });
    expect(within(panel).getByRole("heading", { name: "How well it matches you" })).toBeInTheDocument();
    expect(panel).toHaveTextContent("Moved up 1 place by your preferences");
    expect(panel).toHaveTextContent("You prefer conferences.");
    expect(await within(panel).findByText("Your stated topic moved it up a little.", { exact: false })).toBeInTheDocument();
    // The real 5.9 lists, named; the checklist without its tick mark.
    expect(panel).toHaveTextContent("Your stated preferences");
    expect(panel).toHaveTextContent("Matches your explicit preferred preference for topic: Graph neural networks");
    expect(within(panel).getByText("Matches your explicit research preferences")).toBeInTheDocument();
    // The 3.8 factors, negatives and confidence as the API words them.
    expect(panel).toHaveTextContent("Matches your preferred type: Conference");
    expect(panel).toHaveTextContent("You dismissed a similar call.");
    expect(panel).toHaveTextContent("79% confidence");
  });

  it("shows what was stated and what was inferred from saved calls, in words", async () => {
    renderPage();
    const shapes = await screen.findByRole("region", { name: "What shapes your recommendations" });

    expect(await within(shapes).findByText("Graph neural networks")).toBeInTheDocument();
    expect(within(shapes).getByText("From your saved calls")).toBeInTheDocument();
    expect(within(shapes).getByText("3 of 5 saved opportunities were conferences (60%)")).toBeInTheDocument();
    expect(shapes).toHaveTextContent("Conference · Moderate");
    expect(within(shapes).getByRole("link", { name: "Edit your research preferences" })).toHaveAttribute("href", "/researcher/preferences");
  });

  it("removes a stated preference and ranks again", async () => {
    renderPage();
    const shapes = await screen.findByRole("region", { name: "What shapes your recommendations" });
    const rankedBefore = () => calls.filter((call) => call.path === `${BASE}/personalized-recommendations`).length;
    await within(shapes).findByText("Graph neural networks");
    const before = rankedBefore();

    fireEvent.click(within(shapes).getByRole("button", { name: "Remove Graph neural networks" }));
    await waitFor(() => expect(calls.some((call) => call.method === "DELETE" && call.path === `${BASE}/preferences/p1`)).toBe(true));
    expect(await within(shapes).findByText("Removed Graph neural networks.")).toBeInTheDocument();
    await waitFor(() => expect(rankedBefore()).toBeGreaterThan(before));
  });

  it("pauses personalization with a switch", async () => {
    renderPage();
    const shapes = await screen.findByRole("region", { name: "What shapes your recommendations" });
    const toggle = await within(shapes).findByRole("switch", { name: "Personalize my recommendations" });
    expect(toggle).toHaveAttribute("aria-checked", "true");

    fireEvent.click(toggle);
    await waitFor(() => expect(calls.find((call) => call.method === "PATCH")?.body).toEqual({ personalization_enabled: false }));
    await waitFor(() => expect(within(shapes).getByRole("switch", { name: "Personalize my recommendations" })).toHaveAttribute("aria-checked", "false"));
    expect(within(shapes).getByRole("switch", { name: "Use what I have done here" })).toBeDisabled();
    expect(within(shapes).getByText("Personalization is off.")).toBeInTheDocument();
  });

  it("resets only after a confirmation that says what is kept", async () => {
    renderPage();
    const shapes = await screen.findByRole("region", { name: "What shapes your recommendations" });
    fireEvent.click(await within(shapes).findByRole("button", { name: "Reset what was learned" }));

    const dialog = await screen.findByRole("dialog", { name: "Reset what was learned?" });
    expect(dialog).toHaveTextContent("the preferences you stated");
    expect(dialog).toHaveTextContent("your researcher profile and publications");
    expect(calls.some((call) => call.path.endsWith("/personalization/reset"))).toBe(false);

    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Reset what was learned?" })).not.toBeInTheDocument());
    expect(calls.some((call) => call.path.endsWith("/personalization/reset"))).toBe(false);

    fireEvent.click(within(shapes).getByRole("button", { name: "Reset what was learned" }));
    fireEvent.click(within(await screen.findByRole("dialog", { name: "Reset what was learned?" })).getByRole("button", { name: "Reset" }));
    await waitFor(() => expect(calls.some((call) => call.method === "POST" && call.path.endsWith("/personalization/reset"))).toBe(true));
    expect(await within(shapes).findByText(/Your stated preferences and profile are unchanged/)).toBeInTheDocument();
  });
});
