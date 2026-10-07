/**
 * P0.4 — UnifiedResearchIntelligenceView can show only its recommendations or only its
 * personalization part, and then requests only that part's data. Without a `view` it renders
 * both, as before. Its user-facing text no longer names internal build phases.
 */

import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn(), back: vi.fn(), forward: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/researcher",
  useSearchParams: () => new URLSearchParams(),
}));

import { ResearcherIntelligenceView } from "../components/researcher/ResearcherIntelligenceView";
import { UnifiedResearchIntelligenceView } from "../components/researcher/UnifiedResearchIntelligenceView";
import { clearActiveIdentity, storeSession } from "../services/auth";
import { PROFILE_ID, USER_ID, jsonResponse, makeTokenResponse } from "./factories";

let paths: string[] = [];

beforeEach(() => {
  paths = [];
  storeSession(makeTokenResponse());
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      const path = url.replace(/^https?:\/\/[^/]+/, "").split("?")[0];
      paths.push(path);
      if (path.endsWith("/recommendations/unified"))
        return Promise.resolve(jsonResponse({ recommendations: [], total: 0, query: null, profile_id: PROFILE_ID }));
      if (path.endsWith("/intelligence/unified"))
        return Promise.resolve(
          jsonResponse({
            profile_id: PROFILE_ID,
            full_name: "Ada Lovelace",
            academic_status: "UNKNOWN",
            institution_name: "Example University",
            identity_status: "SELF_DECLARED_ONLY",
            is_identity_ambiguous: false,
            signals: [],
            explicit_preferences_count: 4,
            inferred_preferences_count: 0,
            active_interests_count: 0,
            profile_completeness: 0.5,
          })
        );
      return Promise.resolve(jsonResponse({ detail: "not used here" }, 404));
    })
  );
});

afterEach(() => clearActiveIdentity());

const requested = (suffix: string) => paths.some((path) => path.endsWith(suffix));

describe("UnifiedResearchIntelligenceView parts", () => {
  it("recommendations: asks only for recommendations", async () => {
    render(<UnifiedResearchIntelligenceView profileId={PROFILE_ID} userId={USER_ID} view="recommendations" />);

    expect(await screen.findByRole("heading", { name: /Unified Evidence-Backed Recommendations/ })).toBeInTheDocument();
    await waitFor(() => expect(requested("/recommendations/unified")).toBe(true));
    expect(requested("/intelligence/unified")).toBe(false);
    expect(paths.some((path) => /adaptive-signals|calibration|governance|quality|personalization\/settings/.test(path))).toBe(false);
  });

  it("personalization: asks for the researcher context, not the recommendations", async () => {
    render(<UnifiedResearchIntelligenceView profileId={PROFILE_ID} userId={USER_ID} view="personalization" />);

    expect(await screen.findByText("Ada Lovelace")).toBeInTheDocument();
    // One h1 per page: the researcher page's section header; the profile card is an h2 under it.
    expect(screen.getByRole("heading", { name: "Ada Lovelace" }).tagName).toBe("H2");
    expect(screen.queryByRole("heading", { level: 1 })).not.toBeInTheDocument();
    await waitFor(() => expect(requested("/intelligence/unified")).toBe(true));
    expect(requested("/recommendations/unified")).toBe(false);
    expect(screen.queryByRole("heading", { name: /Unified Evidence-Backed Recommendations/ })).not.toBeInTheDocument();
  });

  it("says nothing about build phases and no raw status values", async () => {
    const { container } = render(<UnifiedResearchIntelligenceView profileId={PROFILE_ID} userId={USER_ID} />);

    await screen.findByText("Ada Lovelace");
    await screen.findByRole("heading", { name: /Unified Evidence-Backed Recommendations/ });
    expect(container.textContent).not.toMatch(/Phase \d/);
    expect(container.textContent).not.toContain("UNKNOWN");
    expect(container.textContent).toContain("4 stated · 0 inferred");
  });
});

describe("Research interests section", () => {
  it("puts its empty state one level under the section's h1, and points to the Profile section", () => {
    // Alone in its section, the view follows the page's h1; an h3 here skipped a level.
    render(
      <ResearcherIntelligenceView intelligence={null} loading={false} error={null} onRefresh={() => undefined} isRefreshing={false} />
    );
    expect(screen.getByRole("heading", { name: "No Research Intelligence Inferred Yet" }).tagName).toBe("H2");
    expect(screen.getByText(/in your Profile section/)).toBeInTheDocument();
  });
});
