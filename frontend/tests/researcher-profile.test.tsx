/**
 * P6 — the researcher profile (/researcher, plan §12): profile summary, publications, research
 * topics (what the researcher stated beside what their publications show) and the way to
 * preferences, in four requests besides the shell's. The diagnostics it used to hold now live on
 * /recommendations (tests/recommendations-page.test.tsx).
 */

import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";

const replace = vi.fn();
let search = new URLSearchParams();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, push: vi.fn(), back: vi.fn(), forward: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/researcher",
  useSearchParams: () => search,
}));

import ResearcherPageRoute from "../app/researcher/page";
import { SessionProvider } from "../components/auth/SessionProvider";
import { clearActiveIdentity, storeSession } from "../services/auth";
import type { ResearcherProfile } from "../types/researcher";
import { PROFILE_ID, USER_ID, jsonResponse, makeTokenResponse, makeUser } from "./factories";

const BASE = `/api/v1/researchers/${PROFILE_ID}`;

function makeProfile(overrides: Partial<ResearcherProfile> = {}): ResearcherProfile {
  return {
    id: PROFILE_ID,
    user_id: USER_ID,
    full_name: "Ada Lovelace",
    email: "ada@university.edu",
    academic_status: "PHD",
    department: "Computer Science",
    bio: "Dense retrieval for scientific literature.",
    institution_name: "Test University",
    canonical_researcher_id: "c0000000-0000-4000-8000-000000000001",
    orcid: "0000-0002-1825-0097",
    openalex_id: null,
    external_identifiers: {},
    keywords: ["information retrieval"],
    target_opportunity_types: [],
    completeness: { score: 0.67, percentage: 67, level: "INTERMEDIATE", is_complete: false, missing_fields: ["external_identity"], field_breakdown: {} },
    works_count: 1,
    created_at: "2026-01-01T00:00:00+00:00",
    updated_at: "2026-01-01T00:00:00+00:00",
    ...overrides,
  } as ResearcherProfile;
}

const preferenceItem = (id: string, label: string, source: "EXPLICIT" | "INFERRED" | "DERIVED_FROM_EXPERTISE") => ({
  id,
  profile_id: PROFILE_ID,
  category: "TOPIC",
  preference_type: "PREFERRED",
  preference_key: "topic",
  preference_value: label,
  display_label: label,
  canonical_id: null,
  strength: 0.8,
  confidence: 0.7,
  source,
  is_active: true,
  recency_score: 0.9,
  provenance_reasons: [],
});

const intelligence = {
  researcher_id: PROFILE_ID,
  display_name: "Ada Lovelace",
  interests: [
    {
      topic_name: "Neural ranking",
      topic_slug: "neural-ranking",
      strength: 0.8,
      confidence: 0.7,
      evidence_count: 3,
      recency_score: 0.9,
      classification: "PRIMARY_EXPERTISE",
      is_primary_expertise: true,
      first_observed_year: 2021,
      last_observed_year: 2024,
      source: "OPENALEX",
      provenance_reasons: ["3 of your works are about neural ranking."],
      supporting_works: [],
    },
  ],
  expertise: [],
  emerging: [],
  summary: {
    total_topics_analyzed: 1,
    primary_expertise_count: 1,
    secondary_expertise_count: 0,
    emerging_interest_count: 0,
    total_works_analyzed: 3,
    active_years_span: "2021–2024",
    has_profile_keywords: true,
  },
  generated_at: "2026-10-01T00:00:00+00:00",
};

const preferences = {
  profile_id: PROFILE_ID,
  user_id: USER_ID,
  display_name: "Ada Lovelace",
  explicit_preferences: [preferenceItem("p1", "Graph neural networks", "EXPLICIT")],
  inferred_preferences: [],
  derived_candidates: [preferenceItem("d1", "Neural ranking", "DERIVED_FROM_EXPERTISE")],
  conflicts: [],
  completeness: { score: 0.4, percentage: 40, is_complete: false, missing_dimensions: ["LOCATION"], dimension_breakdown: {} },
  summary: { total_preferences: 1, explicit_count: 1, inferred_count: 0, derived_count: 1, has_conflicts: false, confidence_level: "MEDIUM", completeness_percentage: 40 },
  generated_at: "2026-10-01T00:00:00+00:00",
};

let urls: string[] = [];
let bodies: { url: string; method: string; body: unknown }[] = [];
let profile: ResearcherProfile | null = makeProfile();

beforeEach(() => {
  urls = [];
  bodies = [];
  profile = makeProfile();
  replace.mockReset();
  storeSession(makeTokenResponse());
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      const relative = url.replace(/^https?:\/\/[^/]+/, "");
      const path = relative.split("?")[0];
      const method = init?.method ?? "GET";
      urls.push(`${method} ${relative}`);
      if (init?.body) bodies.push({ url: path, method, body: JSON.parse(String(init.body)) });
      if (path === "/api/v1/auth/me") return Promise.resolve(jsonResponse(makeUser()));
      if (path === BASE && method === "GET") return Promise.resolve(profile ? jsonResponse(profile) : jsonResponse({ detail: "Not found" }, 404));
      if (path === BASE && method === "PATCH") return Promise.resolve(jsonResponse(makeProfile({ keywords: ["information retrieval", "ranking"] })));
      if (path === `${BASE}/works`) {
        return Promise.resolve(
          jsonResponse([{ id: "w1", title: "Dense retrieval at scale", doi: "10.1000/dense", publication_year: 2024, author_position: "first", is_corresponding: true, cited_by_count: 12 }])
        );
      }
      if (path === `${BASE}/research-intelligence`) return Promise.resolve(jsonResponse(intelligence));
      if (path === `${BASE}/preference-intelligence`) return Promise.resolve(jsonResponse(preferences));
      if (path === `${BASE}/preferences` && method === "POST") return Promise.resolve(jsonResponse({ ...preferenceItem("p2", "Neural ranking", "EXPLICIT") }, 201));
      if (path === "/api/v1/researchers" && method === "POST") return Promise.resolve(jsonResponse(makeProfile({ full_name: "Grace Hopper" }), 201));
      return Promise.resolve(jsonResponse({ detail: `unexpected ${method} ${path}` }, 404));
    })
  );
});

afterEach(() => {
  search = new URLSearchParams();
  clearActiveIdentity();
});

function renderProfile(section?: string) {
  search = new URLSearchParams(section ? { section } : {});
  return render(
    <SessionProvider>
      <ResearcherPageRoute />
    </SessionProvider>
  );
}

const pageRequests = () => urls.filter((url) => !url.endsWith("/api/v1/auth/me")).map((url) => url.split("?")[0]);

describe("researcher profile", () => {
  it("shows the summary, publications, topics and preferences in four requests", async () => {
    renderProfile();

    expect(await screen.findByRole("heading", { level: 1, name: "Ada Lovelace" })).toBeInTheDocument();
    expect(screen.getByText("PhD · Test University · Computer Science")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Dense retrieval at scale" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Neural ranking" })).toBeInTheDocument();
    expect(screen.getByText("Profile completeness 67% — Intermediate")).toBeInTheDocument();
    expect(screen.getByText(/Still to add: an ORCID iD or OpenAlex author ID/)).toBeInTheDocument();

    await waitFor(() => expect(pageRequests()).toHaveLength(4));
    expect(pageRequests().sort()).toEqual(
      [`GET ${BASE}`, `GET ${BASE}/works`, `GET ${BASE}/research-intelligence`, `GET ${BASE}/preference-intelligence`].sort()
    );
    // Nothing from the recommendations or their diagnostics.
    expect(urls.some((url) => /personalized|personalization|feedback|recommendation/.test(url))).toBe(false);
  });

  it("names both kinds of topic: what you stated and what your publications show", async () => {
    renderProfile();
    const topics = await screen.findByRole("region", { name: "Research topics" });

    const stated = await within(topics).findByRole("list", { name: "Topics you stated" });
    expect(within(stated).getAllByRole("listitem").map((item) => item.textContent)).toEqual(["Graph neural networks", "information retrieval"]);
    const found = await within(topics).findByRole("list", { name: "Topics in your publications" });
    expect(found).toHaveTextContent("Neural ranking");
    expect(within(found).getByText("Primary expertise")).toBeInTheDocument();
    expect(within(topics).getByRole("link", { name: "Edit research preferences" })).toHaveAttribute("href", "/researcher/preferences");
  });

  it("follows a topic suggested from the publications only when asked", async () => {
    renderProfile();
    const follow = await screen.findByRole("button", { name: "Follow Neural ranking" });
    expect(bodies.filter((entry) => entry.method === "POST")).toEqual([]);

    fireEvent.click(follow);
    await waitFor(() => expect(bodies.some((entry) => entry.url === `${BASE}/preferences`)).toBe(true));
    expect(bodies.find((entry) => entry.url === `${BASE}/preferences`)?.body).toMatchObject({ category: "TOPIC", preference_value: "Neural ranking" });
    expect(await screen.findByText("Added Neural ranking to the topics you follow.")).toBeInTheDocument();
  });

  it("works the topics out again right after a profile edit", async () => {
    renderProfile();
    fireEvent.click(await screen.findByRole("button", { name: "Edit profile" }));
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(urls).toContain(`GET ${BASE}/research-intelligence?refresh=true`));
    expect(urls.filter((url) => url.includes("research-intelligence"))).toEqual([
      `GET ${BASE}/research-intelligence?refresh=false`,
      `GET ${BASE}/research-intelligence?refresh=true`,
    ]);
  });

  it("does not ask for publications before the profile is linked to a scholarly record", async () => {
    profile = makeProfile({ canonical_researcher_id: null, orcid: null, works_count: 0 });
    renderProfile();

    expect(await screen.findByText(/Add an ORCID iD or OpenAlex author ID to your profile and your publications are linked here/)).toBeInTheDocument();
    await waitFor(() => expect(pageRequests()).toHaveLength(3));
    expect(urls.some((url) => url.includes("/works"))).toBe(false);
  });

  it("creates a profile with only what the person entered", async () => {
    profile = null;
    renderProfile();

    fireEvent.change(await screen.findByLabelText(/Full name/), { target: { value: "Grace Hopper" } });
    fireEvent.click(screen.getByRole("button", { name: "Create profile" }));

    await waitFor(() => expect(bodies.some((entry) => entry.url === "/api/v1/researchers")).toBe(true));
    const sent = bodies.find((entry) => entry.url === "/api/v1/researchers")!.body as Record<string, unknown>;
    expect(sent).toEqual({ full_name: "Grace Hopper", email: "ada@university.edu", academic_status: "PHD" });
    expect(sent).not.toHaveProperty("keywords");
    expect(sent).not.toHaveProperty("bio");
  });
});
