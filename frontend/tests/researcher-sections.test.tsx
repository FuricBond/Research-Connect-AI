/**
 * P6 — where the profile's P0.4 sections went. `/researcher?section=` used to choose one of
 * Profile, Research interests, Recommendations, Personalization or History and feedback. P6
 * moved the recommendations and every diagnostic to /recommendations (plan §12) and named the
 * interests "Research topics" on the profile, so the old links keep working: each section's
 * address opens where its content now is, and nothing of the recommendations loads on the way.
 */

import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

const replace = vi.fn();
let search = new URLSearchParams();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, push: vi.fn(), back: vi.fn(), forward: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/researcher",
  useSearchParams: () => search,
}));

import ResearcherPageRoute from "../app/researcher/page";
import { sectionDestination } from "../components/profile/ProfilePage";
import { SessionProvider } from "../components/auth/SessionProvider";
import { clearActiveIdentity, storeSession } from "../services/auth";
import { PROFILE_ID, USER_ID, jsonResponse, makeTokenResponse, makeUser } from "./factories";

let paths: string[] = [];

beforeEach(() => {
  paths = [];
  replace.mockReset();
  storeSession(makeTokenResponse());
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      const path = url.replace(/^https?:\/\/[^/]+/, "").split("?")[0];
      paths.push(path);
      if (path === "/api/v1/auth/me") return Promise.resolve(jsonResponse(makeUser()));
      if (path === `/api/v1/researchers/${PROFILE_ID}`) {
        return Promise.resolve(
          jsonResponse({
            id: PROFILE_ID,
            user_id: USER_ID,
            full_name: "Ada Lovelace",
            academic_status: "PHD",
            canonical_researcher_id: null,
            keywords: [],
            external_identifiers: {},
            target_opportunity_types: [],
            completeness: { score: 1, percentage: 100, level: "COMPLETE", is_complete: true, missing_fields: [], field_breakdown: {} },
            works_count: 0,
          })
        );
      }
      return Promise.resolve(jsonResponse({}, 200));
    })
  );
});

afterEach(() => {
  search = new URLSearchParams();
  clearActiveIdentity();
});

function renderSection(section: string) {
  search = new URLSearchParams({ section });
  render(
    <SessionProvider>
      <ResearcherPageRoute />
    </SessionProvider>
  );
}

describe("the profile's old sections", () => {
  it.each([
    ["recommendations", "/recommendations"],
    ["personalization", "/recommendations"],
    ["history", "/recommendations"],
    ["interests", "/researcher#topics"],
    ["profile", "/researcher"],
  ])("opens ?section=%s at %s", async (section, destination) => {
    renderSection(section);
    await waitFor(() => expect(replace).toHaveBeenCalledWith(destination));
    // On the way, nothing is asked of the researcher endpoints.
    expect(paths.filter((path) => path.startsWith("/api/v1/researchers/"))).toEqual([]);
  });

  it("opens the profile itself for an unknown section", async () => {
    renderSection("nonsense");
    expect(await screen.findByRole("heading", { level: 1, name: "Ada Lovelace" })).toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });

  it("knows no other destinations", () => {
    expect(sectionDestination(null)).toBeNull();
    expect(sectionDestination("")).toBeNull();
    expect(sectionDestination("settings")).toBeNull();
  });
});
