/**
 * P0.4 — the researcher profile is split into sections that load only what they show.
 *
 * The page used to mount ten panels at once (25 requests, 25,000px tall) and expose internal
 * phase labels. Now `?section=` chooses one of Profile, Research interests, Recommendations,
 * Personalization or History and feedback; every panel is still reachable.
 */

import fs from "node:fs";
import path from "node:path";
import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

let search = new URLSearchParams();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn(), back: vi.fn(), forward: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/researcher",
  useSearchParams: () => search,
}));

// The panels are tested elsewhere; here they only show which ones a section mounts.
const { stubModule, profileStub } = vi.hoisted(() => ({
  stubModule: (exportName: string, label: string) => async () => {
    const { createElement } = await import("react");
    return {
      [exportName]: (props: { view?: string }) =>
        createElement("div", { "data-testid": "panel" }, label + (props.view ? `:${props.view}` : "")),
    };
  },
  // The profile panel can also report a saved edit, as the real one does after a PATCH.
  profileStub: async () => {
    const { createElement, Fragment } = await import("react");
    return {
      ResearcherProfileView: (props: { profile: unknown; onProfileUpdated?: (profile: unknown) => void }) =>
        createElement(
          Fragment,
          null,
          createElement("div", { "data-testid": "panel" }, "profile"),
          createElement("button", { type: "button", onClick: () => props.onProfileUpdated?.(props.profile) }, "Save profile")
        ),
    };
  },
}));
vi.mock("../components/researcher/ResearcherProfileView", profileStub);
vi.mock("../components/researcher/ResearcherIntelligenceView", stubModule("ResearcherIntelligenceView", "intelligence"));
vi.mock("../components/researcher/ResearcherPreferencesView", stubModule("ResearcherPreferencesView", "preferences"));
vi.mock("../components/researcher/UnifiedResearchIntelligenceView", stubModule("UnifiedResearchIntelligenceView", "unified"));
vi.mock("../components/researcher/PersonalizedRankingPreview", stubModule("PersonalizedRankingPreview", "ranking"));
vi.mock("../components/researcher/PersonalizedCandidatePreview", stubModule("PersonalizedCandidatePreview", "candidates"));
vi.mock("../components/researcher/PersonalizationSummaryView", stubModule("PersonalizationSummaryView", "summary"));
vi.mock("../components/researcher/FeedbackHistoryView", stubModule("FeedbackHistoryView", "feedback"));
vi.mock("../components/researcher/RecommendationHistoryView", stubModule("RecommendationHistoryView", "history"));

import ResearcherPageRoute from "../app/researcher/page";
import { SessionProvider } from "../components/auth/SessionProvider";
import { clearActiveIdentity, storeSession } from "../services/auth";
import { PROFILE_ID, USER_ID, jsonResponse, makeTokenResponse, makeUser } from "./factories";

let paths: string[] = [];
let urls: string[] = [];

beforeEach(() => {
  paths = [];
  urls = [];
  storeSession(makeTokenResponse());
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      urls.push(url.replace(/^https?:\/\/[^/]+/, ""));
      const path = url.replace(/^https?:\/\/[^/]+/, "").split("?")[0];
      paths.push(path);
      if (path === "/api/v1/auth/me") return Promise.resolve(jsonResponse(makeUser()));
      if (path === `/api/v1/researchers/${PROFILE_ID}`)
        return Promise.resolve(jsonResponse({ id: PROFILE_ID, user_id: USER_ID, full_name: "Ada Lovelace", canonical_researcher_id: null }));
      return Promise.resolve(jsonResponse({}, 200));
    })
  );
});

afterEach(() => {
  search = new URLSearchParams();
  clearActiveIdentity();
});

async function renderSection(section?: string) {
  search = new URLSearchParams(section ? { section } : {});
  render(
    <SessionProvider>
      <ResearcherPageRoute />
    </SessionProvider>
  );
  await screen.findByRole("navigation", { name: "Profile sections" });
  return screen.getAllByTestId("panel").map((panel) => panel.textContent);
}

const sectionRequests = () => paths.filter((path) => path.startsWith(`/api/v1/researchers/${PROFILE_ID}/`));

describe("researcher profile sections", () => {
  it("opens on the profile alone, with no recommendation or personalization requests", async () => {
    expect(await renderSection()).toEqual(["profile"]);
    await waitFor(() => expect(paths).toContain(`/api/v1/researchers/${PROFILE_ID}`));
    expect(sectionRequests()).toEqual([]);
    expect(screen.getByRole("link", { name: "Profile" })).toHaveAttribute("aria-current", "page");
  });

  it("loads interests and preferences only in their section", async () => {
    expect(await renderSection("interests")).toEqual(["intelligence", "preferences"]);
    expect(screen.getByRole("heading", { level: 1, name: "Research interests" })).toBeInTheDocument();
    await waitFor(() => expect(sectionRequests().length).toBe(2));
    expect(sectionRequests().some((path) => path.includes("personalized-candidates"))).toBe(false);
  });

  it("keeps recommendations, with the ranking and its feedback, in their own section", async () => {
    expect(await renderSection("recommendations")).toEqual(["unified:recommendations", "ranking"]);
    expect(screen.getByRole("link", { name: "Recommendations" })).toHaveAttribute("aria-current", "page");
  });

  it("keeps every personalization panel reachable", async () => {
    expect(await renderSection("personalization")).toEqual(["unified:personalization", "summary", "candidates"]);
    await waitFor(() => expect(sectionRequests().some((path) => path.includes("personalized-candidates"))).toBe(true));
  });

  it("keeps the history and feedback panels reachable", async () => {
    expect(await renderSection("history")).toEqual(["feedback", "history"]);
  });

  it("recomputes the research interests right after a profile edit, as before the split", async () => {
    // The interests (and the recommendations built on them) are inferred from the profile; a
    // plain read would return the interests persisted before the edit.
    await renderSection();
    await waitFor(() => expect(paths).toContain(`/api/v1/researchers/${PROFILE_ID}`));
    fireEvent.click(screen.getByRole("button", { name: "Save profile" }));
    await waitFor(() =>
      expect(urls).toContain(`/api/v1/researchers/${PROFILE_ID}/research-intelligence?refresh=true`)
    );
    expect(urls.filter((url) => url.includes("research-intelligence"))).toHaveLength(1);
  });

  it("falls back to the profile for an unknown section", async () => {
    expect(await renderSection("nonsense")).toEqual(["profile"]);
  });

  it("links every section by URL", async () => {
    await renderSection();
    const hrefs = ["Profile", "Research interests", "Recommendations", "Personalization", "History and feedback"].map((name) =>
      screen.getByRole("link", { name }).getAttribute("href")
    );
    expect(hrefs).toEqual([
      "/researcher",
      "/researcher?section=interests",
      "/researcher?section=recommendations",
      "/researcher?section=personalization",
      "/researcher?section=history",
    ]);
  });
});

describe("profile section styles", () => {
  it("keeps a section's single column within the page", () => {
    // An implicit `auto` grid track grows to the widest panel's min-content: the sections
    // scrolled sideways by up to 551px on phones until the column was capped.
    const css = fs.readFileSync(path.join(__dirname, "../styles/profile.css"), "utf8");
    const start = css.indexOf(".profile-section-body {");
    expect(start).toBeGreaterThanOrEqual(0);
    expect(css.slice(start, css.indexOf("}", start))).toMatch(/grid-template-columns:\s*minmax\(0,\s*1fr\)/);
  });
});
