/**
 * P0.7 — Similar Research and the Opportunity Matcher work from one paper; opened directly,
 * without one, they explain that and offer ways to provide it instead of a dead end.
 *
 * The selected paper still travels in sessionStorage, as before. A paper picked here — from
 * the reading list — is the person's own choice and is remembered the same way; nothing is
 * ever selected for them.
 */

import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn(), back: vi.fn(), forward: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/similar",
  useSearchParams: () => new URLSearchParams(),
}));

import { SessionProvider } from "../components/auth/SessionProvider";
import { OpportunityMatchesPage } from "../components/pages/OpportunityMatches";
import { SimilarResearchPage } from "../components/pages/SimilarResearch";
import { getSelectedWork, setSelectedWork } from "../hooks/useSelectedWork";
import { clearActiveIdentity, storeSession } from "../services/auth";
import { jsonResponse, makeTokenResponse, makeUser } from "./factories";

const SAVED_WORK = {
  id: "wk000000-0000-4000-8000-000000000001",
  title: "Parameterized Explainer for Graph Neural Network",
  doi: "10.48550/arxiv.2011.04573",
  publication_year: 2020,
  work_type: "preprint",
  venue_name: "arXiv",
  authors: ["Dongsheng Luo"],
  landing_page_url: null,
};

let paths: string[] = [];

function serve(signedIn: boolean) {
  paths = [];
  if (signedIn) storeSession(makeTokenResponse());
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      const path = url.replace(/^https?:\/\/[^/]+/, "").split("?")[0];
      paths.push(path);
      if (path === "/api/v1/auth/me") return Promise.resolve(jsonResponse(makeUser()));
      if (path === "/api/v1/reading-list")
        return Promise.resolve(
          jsonResponse({
            items: [{ id: "rl1", work_id: SAVED_WORK.id, status: "TO_READ", notes: null, work: SAVED_WORK }],
            total_count: 1,
            limit: 5,
            offset: 0,
            counts_by_status: { TO_READ: 1, READING: 0, DONE: 0 },
          })
        );
      if (path.endsWith("/similar"))
        return Promise.resolve(
          jsonResponse({ source_work_id: SAVED_WORK.id, items: [], total: 0, limit: 20, offset: 0, has_more: false, ranking_mode: "hybrid" })
        );
      return Promise.resolve(jsonResponse({ detail: `unexpected ${path}` }, 404));
    })
  );
}

function renderWithSession(node: React.ReactNode) {
  return render(<SessionProvider>{node}</SessionProvider>);
}

beforeEach(() => {
  window.sessionStorage.clear();
});

afterEach(() => {
  clearActiveIdentity();
  window.sessionStorage.clear();
});

describe("Similar Research without a selected paper", () => {
  it("says what it does, why it needs a paper and how to find one", async () => {
    serve(false);
    renderWithSession(<SimilarResearchPage />);

    expect(await screen.findByRole("heading", { level: 1, name: "Similar Research" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Choose a paper to start" })).toBeInTheDocument();
    expect(screen.getByText("Find Similar Research")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Find a paper in Literature Search" })).toHaveAttribute("href", "/");
    // A visitor has no reading list, and no paper is picked for them.
    await waitFor(() => expect(paths).not.toContain("/api/v1/reading-list"));
    expect(paths.some((path) => path.endsWith("/similar"))).toBe(false);
    expect(getSelectedWork()).toBeNull();
  });

  it("lets a signed-in researcher start from a saved paper", async () => {
    serve(true);
    renderWithSession(<SimilarResearchPage />);

    const use = await screen.findByRole("button", { name: `Use this paper: ${SAVED_WORK.title}` });
    expect(paths.some((path) => path.endsWith("/similar"))).toBe(false);

    fireEvent.click(use);

    await waitFor(() => expect(paths).toContain(`/api/v1/discovery/research/${SAVED_WORK.id}/similar`));
    expect(getSelectedWork()?.id).toBe(SAVED_WORK.id);
    expect(await screen.findByText(SAVED_WORK.title)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Choose a paper to start" })).not.toBeInTheDocument();
  });
});

describe("Similar Research with a selected paper", () => {
  it("still opens straight on that paper", async () => {
    serve(false);
    setSelectedWork({ id: SAVED_WORK.id, title: SAVED_WORK.title });
    renderWithSession(<SimilarResearchPage />);

    expect(await screen.findByRole("heading", { level: 1, name: "Similar Research" })).toBeInTheDocument();
    expect(screen.getByText(SAVED_WORK.title)).toBeInTheDocument();
    await waitFor(() => expect(paths).toContain(`/api/v1/discovery/research/${SAVED_WORK.id}/similar`));
  });
});

describe("Opportunity Matcher without a selected paper", () => {
  it("explains itself and offers the same ways in", async () => {
    serve(false);
    renderWithSession(<OpportunityMatchesPage />);

    expect(await screen.findByRole("heading", { level: 1, name: "Opportunity Matcher" })).toBeInTheDocument();
    expect(screen.getByText("Match Calls & Venues")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Find a paper in Literature Search" })).toHaveAttribute("href", "/");
  });
});
