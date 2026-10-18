/**
 * P5 — similar papers and venue matching, reached from a paper (FRONTEND_REDESIGN_PLAN.md §10).
 *
 * The paper travels in the address (`?paper=<id>`), so reload, back and forward keep their own;
 * the answer shown always belongs to the paper in the address (a late answer for the previous
 * paper is never shown); an id that cannot be a paper's is not sent; a shared link to a paper
 * this tab never saw still works from the id, and says what it cannot show. Venue matching hides
 * nothing unasked (plan Q10, P5 decision) and opens the Evidence panel at the part asked for.
 */

import React from "react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

let search = new URLSearchParams();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn(), forward: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/similar",
  useSearchParams: () => search,
}));

import { SessionProvider } from "../components/auth/SessionProvider";
import { OpportunityMatchesPage } from "../components/pages/OpportunityMatches";
import { SimilarResearchPage } from "../components/pages/SimilarResearch";
import { setSelectedWork } from "../hooks/useSelectedWork";
import { jsonResponse } from "./factories";
import { CALL_ID, OTHER_WORK_ID, WORK_ID, makeMatchItem, makeSimilarItem, makeWork, matchAnswer, similarAnswer } from "./p5-fixtures";
import { installDialogPolyfill, serveShell } from "./shell-support";

beforeAll(installDialogPolyfill);
beforeEach(() => visit("/similar"));

function visit(url: string) {
  window.history.replaceState(null, "", url);
  search = new URLSearchParams(window.location.search);
}

type Held = { id: string; resolve: () => void };

function serve(options: { hold?: boolean; venues?: () => Response } = {}) {
  const held: Held[] = [];
  const fetchMock = serveShell(null, {
    other: (url) => {
      const similar = /\/research\/([^/]+)\/similar/.exec(url);
      if (similar) {
        const id = similar[1];
        const answer = jsonResponse(similarAnswer([makeSimilarItem({ work: makeWork({ id: `${id === WORK_ID ? OTHER_WORK_ID : WORK_ID}`, title: `Similar to ${id.slice(0, 4)}` }) })], 1, id));
        if (!options.hold) return Promise.resolve(answer);
        return new Promise<Response>((resolve) => held.push({ id, resolve: () => resolve(answer) }));
      }
      if (/\/research\/[^/]+\/opportunities/.test(url)) return Promise.resolve(options.venues ? options.venues() : jsonResponse(matchAnswer([makeMatchItem()])));
      return undefined;
    },
  });
  return { fetchMock, held };
}

const requests = (fetchMock: ReturnType<typeof serveShell>, part: string) => fetchMock.mock.calls.map(([url]) => String(url)).filter((url) => url.includes(part));
const withSession = (node: React.ReactNode) => <SessionProvider>{node}</SessionProvider>;

describe("Similar papers", () => {
  it("works from the paper in the address, with the way back to its search", async () => {
    setSelectedWork(makeWork(), "/?q=graph%20explainers&type=preprint");
    visit(`/similar?paper=${WORK_ID}`);
    const { fetchMock } = serve();
    render(withSession(<SimilarResearchPage />));

    expect(await screen.findByRole("heading", { level: 2, name: "1 similar paper" })).toBeInTheDocument();
    expect(requests(fetchMock, "/similar")).toEqual([expect.stringContaining(`/research/${WORK_ID}/similar?limit=20&offset=0&explain=true`)]);
    expect(screen.getByRole("heading", { level: 2, name: "Parameterized Explainer for Graph Neural Network" })).toBeInTheDocument();
    const crumbs = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(within(crumbs).getAllByRole("link", { name: "Search" })[0]).toHaveAttribute("href", "/?q=graph%20explainers&type=preprint");
    expect(within(crumbs).getByText("Similar papers")).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Find venues for this paper" })).toHaveAttribute("href", `/opportunities?paper=${WORK_ID}`);
    expect(screen.getByRole("button", { name: /^Why similar\?/ })).toBeInTheDocument();
  });

  it("writes the remembered paper into the address, without a history entry", async () => {
    setSelectedWork(makeWork());
    serve();
    const before = window.history.length;
    render(withSession(<SimilarResearchPage />));
    await screen.findByRole("heading", { level: 2, name: "1 similar paper" });
    expect(window.location.search).toBe(`?paper=${WORK_ID}`);
    expect(window.history.length).toBe(before);
  });

  it("shows only the answer for the paper in the address, and moves focus to the new paper", async () => {
    setSelectedWork(makeWork());
    setSelectedWork(makeWork({ id: OTHER_WORK_ID, title: "GNNExplainer" }));
    visit(`/similar?paper=${WORK_ID}`);
    const { fetchMock, held } = serve({ hold: true });
    const view = render(withSession(<SimilarResearchPage />));
    await waitFor(() => expect(held).toHaveLength(1));

    // Forward to another paper before the first answer arrives.
    visit(`/similar?paper=${OTHER_WORK_ID}`);
    view.rerender(withSession(<SimilarResearchPage />));
    await waitFor(() => expect(held).toHaveLength(2));
    await act(async () => held[1].resolve());
    await act(async () => held[0].resolve());

    expect(await screen.findByRole("button", { name: `Similar to ${OTHER_WORK_ID.slice(0, 4)}` })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: `Similar to ${WORK_ID.slice(0, 4)}` })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "GNNExplainer" })).toHaveFocus();
    expect(requests(fetchMock, "/similar").map((url) => /research\/([^/]+)\//.exec(url)![1])).toEqual([WORK_ID, OTHER_WORK_ID]);
  });

  it("works from a shared link this tab never saw, and says what it cannot show", async () => {
    visit(`/similar?paper=${WORK_ID}`);
    const { fetchMock } = serve();
    render(withSession(<SimilarResearchPage />));
    expect(await screen.findByRole("heading", { level: 2, name: "A paper chosen elsewhere" })).toBeInTheDocument();
    expect(screen.getByText(/not opened in this tab/)).toBeInTheDocument();
    await screen.findByRole("heading", { level: 2, name: "1 similar paper" });
    expect(requests(fetchMock, "/similar")).toHaveLength(1);
  });

  it("does not send an id that cannot be a paper's", async () => {
    visit("/similar?paper=..%2F..%2Fadmin");
    const { fetchMock } = serve();
    render(withSession(<SimilarResearchPage />));
    expect(await screen.findByRole("heading", { name: "Choose a paper to start" })).toBeInTheDocument();
    await act(async () => undefined);
    expect(requests(fetchMock, "/similar")).toHaveLength(0);
  });
});

describe("Find venues", () => {
  it("hides nothing unasked, and asks again only for a filter that changed", async () => {
    setSelectedWork(makeWork());
    visit(`/opportunities?paper=${WORK_ID}`);
    const { fetchMock } = serve();
    render(withSession(<OpportunityMatchesPage />));
    expect(await screen.findByRole("heading", { level: 2, name: "1 matching call" })).toBeInTheDocument();

    const [first] = requests(fetchMock, "/opportunities?");
    expect(new URL(first).searchParams.has("upcoming_only")).toBe(false);
    expect(screen.getByLabelText("Upcoming deadlines only")).not.toBeChecked();

    // Typing a location asks nothing until the person is done with the field.
    const location = screen.getByLabelText("Location");
    fireEvent.change(location, { target: { value: "Lon" } });
    fireEvent.change(location, { target: { value: "London" } });
    expect(requests(fetchMock, "/opportunities?")).toHaveLength(1);
    fireEvent.blur(location);
    await waitFor(() => expect(requests(fetchMock, "/opportunities?")).toHaveLength(2));
    expect(new URL(requests(fetchMock, "/opportunities?")[1]).searchParams.get("location")).toBe("London");

    fireEvent.click(screen.getByLabelText("Upcoming deadlines only"));
    await waitFor(() => expect(requests(fetchMock, "/opportunities?")).toHaveLength(3));
    expect(new URL(requests(fetchMock, "/opportunities?")[2]).searchParams.get("upcoming_only")).toBe("true");
  });

  it("shows each call's match, deadline and risk apart, and links it to its page", async () => {
    setSelectedWork(makeWork());
    visit(`/opportunities?paper=${WORK_ID}`);
    serve();
    render(withSession(<OpportunityMatchesPage />));
    const card = (await screen.findAllByRole("article"))[0];
    expect(within(card).getByRole("link", { name: "Workshop on Neural Retrieval Methods" })).toHaveAttribute("href", `/calls/${CALL_ID}`);
    expect(card).toHaveTextContent("Good match · 61%");
    expect(card).toHaveTextContent("Paper type fit · Similar meaning");
    expect(card).toHaveTextContent(/Due 19 Oct 2026 AoE · \d+ days? left|Due 19 Oct 2026 AoE/);
    expect(within(card).getByRole("button", { name: "Venue risk: Risk not assessed. Show the evidence" })).toBeInTheDocument();
    expect(card).not.toHaveTextContent(/Type Fit|Topic Overlap|INSUFFICIENT_EVIDENCE/);
  });

  it("opens the Evidence panel at the part its trigger asked for", async () => {
    setSelectedWork(makeWork());
    visit(`/opportunities?paper=${WORK_ID}`);
    serve();
    render(withSession(<OpportunityMatchesPage />));
    const card = (await screen.findAllByRole("article"))[0];

    fireEvent.click(within(card).getByRole("button", { name: "Venue risk: Risk not assessed. Show the evidence" }));
    let panel = await screen.findByRole("dialog", { name: "Why this venue?" });
    expect(within(panel).getByRole("heading", { name: "Venue risk" })).toHaveFocus();
    expect(panel).toHaveTextContent("Not enough evidence to assess this venue.");
    expect(within(panel).getByRole("heading", { name: "Deadlines" })).toBeInTheDocument();
    fireEvent.click(within(panel).getByRole("button", { name: "Close" }));

    fireEvent.click(within(card).getByRole("button", { name: "Why this venue? Workshop on Neural Retrieval Methods" }));
    panel = await screen.findByRole("dialog", { name: "Why this venue?" });
    expect(within(panel).getByRole("heading", { level: 2, name: "Why this venue?" })).toHaveFocus();
    expect(panel).toHaveTextContent("Ranked #1 mainly for paper type fit and similar meaning.");
    // The call is not a paper: the paper facts are not shown for it.
    expect(panel).not.toHaveTextContent("About the paper");
  });

  it("says when the paper is no longer in the corpus", async () => {
    setSelectedWork(makeWork());
    visit(`/opportunities?paper=${WORK_ID}`);
    serve({ venues: () => jsonResponse({ detail: "Research work not found" }, 404) });
    render(withSession(<OpportunityMatchesPage />));
    expect(await screen.findByRole("heading", { name: "This paper could not be found" })).toBeInTheDocument();
  });
});
