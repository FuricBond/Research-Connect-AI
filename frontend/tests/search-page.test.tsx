/**
 * P5 — the literature search (FRONTEND_REDESIGN_PLAN.md §9) with its whole state in the address:
 * a direct link restores the filters and asks the API exactly that; a filter, a page and a new
 * query are recorded in the history and searched once; sorting reorders the page without asking
 * again; back and forward bring their own search; and the Evidence and paper panels are proper
 * dialogs that load nothing until opened. (The P2 race guarantees are in global-search.test.tsx.)
 */

import React from "react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { renderToString } from "react-dom/server";

let search = new URLSearchParams();
const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace: vi.fn(), back: vi.fn(), forward: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/",
  useSearchParams: () => search,
}));

import { SessionProvider } from "../components/auth/SessionProvider";
import { DiscoverySearch } from "../components/pages/DiscoverySearch";
import { getPaperOrigin, getSelectedWork } from "../hooks/useSelectedWork";
import { jsonResponse } from "./factories";
import { OTHER_WORK_ID, WORK_ID, makeExplanation, makeSearchItem, makeSimilarItem, makeWork, searchAnswer, similarAnswer } from "./p5-fixtures";
import { installDialogPolyfill, serveShell } from "./shell-support";

const SEARCH_PATH = "/api/v1/discovery/research/search";

beforeAll(installDialogPolyfill);
beforeEach(() => {
  push.mockReset();
  visit("/");
});

function visit(url: string) {
  window.history.replaceState(null, "", url);
  search = new URLSearchParams(window.location.search);
}

const TWO_RESULTS = [
  makeSearchItem({ rank: 1, work: makeWork({ id: WORK_ID, title: "Older but more relevant", publication_year: 2019, cited_by_count: 5 }) }),
  makeSearchItem({
    rank: 2,
    final_score: 0.41,
    work: makeWork({ id: OTHER_WORK_ID, title: "Newer and more cited", publication_year: 2023, cited_by_count: 900, abstract: null, doi: null }),
    explanation: makeExplanation({ rank: 2 }),
  }),
];

function serve(answer: (params: URLSearchParams) => Response | Promise<Response> = () => jsonResponse(searchAnswer(TWO_RESULTS, 45))) {
  return serveShell(null, {
    other: (url) => {
      if (url.includes(SEARCH_PATH)) return Promise.resolve(answer(new URL(url).searchParams));
      if (url.includes("/similar")) return Promise.resolve(jsonResponse(similarAnswer([makeSimilarItem()], 12)));
      return undefined;
    },
  });
}

const searches = (fetchMock: ReturnType<typeof serve>) =>
  fetchMock.mock.calls.map(([url]) => String(url)).filter((url) => url.includes(SEARCH_PATH)).map((url) => new URL(url).searchParams);
const similarCalls = (fetchMock: ReturnType<typeof serve>) => fetchMock.mock.calls.map(([url]) => String(url)).filter((url) => url.includes("/similar"));

const page = () => (
  <SessionProvider>
    <DiscoverySearch />
  </SessionProvider>
);

async function showResults() {
  return screen.findByRole("heading", { level: 2, name: "45 results" });
}

describe("the address restores the search", () => {
  it("asks the API for exactly the filters in a direct link, and shows them", async () => {
    visit("/?q=graph%20explainers&type=preprint&year=2018-2024&oa=1&cites=10&mode=research_similarity&page=2&per=10");
    const fetchMock = serve();
    render(page());
    await showResults();

    const [asked] = searches(fetchMock);
    expect(searches(fetchMock)).toHaveLength(1);
    expect(Object.fromEntries(asked)).toMatchObject({
      q: "graph explainers",
      work_type: "preprint",
      min_year: "2018",
      max_year: "2024",
      is_oa: "true",
      min_citations: "10",
      ranking_mode: "research_similarity",
      limit: "10",
      offset: "10",
      explain: "true",
    });
    const rail = screen.getByRole("complementary", { name: "Filters" });
    expect(within(rail).getByLabelText("Publication type")).toHaveValue("preprint");
    expect(within(rail).getByLabelText("From year")).toHaveValue(2018);
    expect(within(rail).getByLabelText("Open access only")).toBeChecked();
    expect(within(rail).getByLabelText("Ranking")).toHaveValue("research_similarity");
    expect(screen.getByRole("searchbox", { name: "Search research literature" })).toHaveValue("graph explainers");
  });

  it("drops what it does not support and searches the rest", async () => {
    visit("/?q=retrieval&type=novel&year=soon&page=-2&sort=random");
    const fetchMock = serve();
    render(page());
    await showResults();
    const asked = Object.fromEntries(searches(fetchMock)[0]);
    expect(asked).toMatchObject({ q: "retrieval", offset: "0", limit: "20" });
    expect(asked).not.toHaveProperty("work_type");
    expect(asked).not.toHaveProperty("min_year");
  });

  it("follows back and forward to a search with other filters", async () => {
    visit("/?q=retrieval");
    const fetchMock = serve();
    const view = render(page());
    await showResults();

    visit("/?q=retrieval&type=dataset&page=3");
    view.rerender(page());
    await waitFor(() => expect(searches(fetchMock)).toHaveLength(2));
    expect(Object.fromEntries(searches(fetchMock)[1])).toMatchObject({ q: "retrieval", work_type: "dataset", offset: "40" });
    expect(screen.getByRole("complementary", { name: "Filters" }).querySelector("select")).toHaveValue("dataset");
  });
});

describe("changing the search records it in the address", () => {
  it("searches once for a filter change, from the first page, with a history entry", async () => {
    visit("/?q=retrieval&page=2");
    const fetchMock = serve();
    render(page());
    await showResults();
    const before = window.history.length;

    fireEvent.change(within(screen.getByRole("complementary", { name: "Filters" })).getByLabelText("Publication type"), { target: { value: "article" } });
    await waitFor(() => expect(searches(fetchMock)).toHaveLength(2));
    expect(window.location.search).toBe("?q=retrieval&type=article");
    expect(window.history.length).toBe(before + 1);
    expect(Object.fromEntries(searches(fetchMock)[1])).toMatchObject({ work_type: "article", offset: "0" });
    expect(push).not.toHaveBeenCalled();
  });

  it("applies a year only when it has been typed, not on every keystroke", async () => {
    visit("/?q=retrieval");
    const fetchMock = serve();
    render(page());
    await showResults();
    const from = within(screen.getByRole("complementary", { name: "Filters" })).getByLabelText("From year");

    for (const value of ["2", "20", "201", "2018"]) fireEvent.change(from, { target: { value } });
    expect(searches(fetchMock)).toHaveLength(1);
    fireEvent.blur(from);
    await waitFor(() => expect(searches(fetchMock)).toHaveLength(2));
    expect(window.location.search).toBe("?q=retrieval&year=2018-");
  });

  it("keeps the filters when a new query is submitted", async () => {
    visit("/?q=retrieval&type=article&oa=1&page=3");
    const fetchMock = serve();
    render(page());
    await showResults();

    const box = screen.getByRole("searchbox", { name: "Search research literature" });
    fireEvent.change(box, { target: { value: "dense retrieval" } });
    fireEvent.submit(box.closest("form")!);
    await waitFor(() => expect(searches(fetchMock)).toHaveLength(2));
    expect(window.location.search).toBe("?q=dense%20retrieval&type=article&oa=1");
  });

  it("sorts the page in hand without asking again, and says so", async () => {
    visit("/?q=retrieval");
    const fetchMock = serve();
    render(page());
    await showResults();
    const titles = () => screen.getAllByRole("article").map((card) => within(card).getAllByRole("button")[0].textContent);
    expect(titles()).toEqual(["Older but more relevant", "Newer and more cited"]);

    fireEvent.change(screen.getByLabelText("Sort"), { target: { value: "newest" } });
    expect(titles()).toEqual(["Newer and more cited", "Older but more relevant"]);
    expect(window.location.search).toBe("?q=retrieval&sort=newest");
    expect(screen.getByText(/Reorders the papers on this page/)).toBeInTheDocument();
    await act(async () => undefined);
    expect(searches(fetchMock)).toHaveLength(1);
  });

  it("moves to the next page with one request and puts focus on the results heading", async () => {
    visit("/?q=retrieval");
    const fetchMock = serve();
    render(page());
    await showResults();

    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    await waitFor(() => expect(searches(fetchMock)).toHaveLength(2));
    expect(window.location.search).toBe("?q=retrieval&page=2");
    expect(Object.fromEntries(searches(fetchMock)[1])).toMatchObject({ offset: "20" });
    expect(await showResults()).toHaveFocus();
  });
});

describe("results", () => {
  it("states each paper's facts, relevance band and reasons in words, with no primary button per card", async () => {
    visit("/?q=retrieval");
    serve();
    render(page());
    await showResults();
    const [first, second] = screen.getAllByRole("article");

    expect(within(first).getByText("NeurIPS · 2019")).toBeInTheDocument();
    expect(first).toHaveTextContent("Preprint");
    expect(first).toHaveTextContent("5 citations");
    expect(within(first).getByRole("link", { name: /doi:10\.48550\/arxiv\.2011\.04573/ })).toHaveAttribute("href", "https://doi.org/10.48550/arxiv.2011.04573");
    expect(first).toHaveTextContent("Good relevance · 56%");
    expect(first).toHaveTextContent("Similar meaning · Shared topics");
    expect(first).not.toHaveTextContent(/Semantic: |Lexical: |0\.56/);
    // "Why this result?" is named with its paper, so a list of links is not twenty identical names.
    expect(within(first).getByRole("button", { name: "Why this result? Older but more relevant" })).toBeInTheDocument();
    // Missing facts are left out or said, never invented.
    expect(within(second).getByText("No abstract available.")).toBeInTheDocument();
    expect(within(second).queryByRole("link", { name: /doi:/ })).not.toBeInTheDocument();
    expect(within(first).getByRole("link", { name: "Find similar" })).toHaveAttribute("href", `/similar?paper=${WORK_ID}`);
    expect(within(first).getByRole("link", { name: "Find venues" })).toHaveAttribute("href", `/opportunities?paper=${WORK_ID}`);
  });

  it("remembers the paper and the search it came from when a paper tool is opened", async () => {
    visit("/?q=retrieval&type=article");
    serve();
    render(page());
    await showResults();
    fireEvent.click(within(screen.getAllByRole("article")[0]).getByRole("link", { name: "Find venues" }));
    expect(getSelectedWork()?.id).toBe(WORK_ID);
    expect(getPaperOrigin()).toBe("/?q=retrieval&type=article");
  });

  it("offers Clear filters when filters found nothing", async () => {
    visit("/?q=retrieval&type=dataset");
    const fetchMock = serve((params) => jsonResponse(searchAnswer(params.get("work_type") ? [] : TWO_RESULTS, params.get("work_type") ? 0 : 45)));
    render(page());
    expect(await screen.findByRole("heading", { name: "No papers matched your search" })).toBeInTheDocument();

    fireEvent.click(screen.getAllByRole("button", { name: /^Clear filters/ })[0]);
    await showResults();
    expect(window.location.search).toBe("?q=retrieval");
    expect(searches(fetchMock)).toHaveLength(2);
  });

  it("explains a failure in its own words, never the server's, and retries", async () => {
    visit("/?q=retrieval");
    let fail = true;
    const fetchMock = serve(() => (fail ? jsonResponse({ detail: "psycopg.OperationalError: connection refused" }, 500) : jsonResponse(searchAnswer(TWO_RESULTS, 45))));
    render(page());
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The search could not be completed");
    expect(document.body).not.toHaveTextContent("psycopg");

    fail = false;
    fireEvent.click(within(alert).getByRole("button", { name: "Try again" }));
    await showResults();
    expect(searches(fetchMock)).toHaveLength(2);
  });

  it("says when a search is slow, while it is still loading", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      visit("/?q=retrieval");
      serve(() => new Promise<Response>(() => {}));
      render(page());
      expect(await screen.findByRole("status")).toHaveTextContent("Searching papers…");
      await act(async () => {
        vi.advanceTimersByTime(3100);
      });
      expect(screen.getByRole("status")).toHaveTextContent(/Still searching/);
      expect(screen.getByText(/taking longer than usual/)).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("the Evidence panel", () => {
  it("is a dialog named by its question, with the paper, the meters and the exact decomposition; focus returns", async () => {
    visit("/?q=retrieval");
    serve();
    render(page());
    await showResults();
    const why = screen.getByRole("button", { name: "Why this result? Older but more relevant" });
    why.focus();
    fireEvent.click(why);

    const panel = await screen.findByRole("dialog", { name: "Why this result?" });
    expect(panel).toHaveAccessibleDescription("Older but more relevant");
    expect(within(panel).getByRole("heading", { level: 2, name: "Why this result?" })).toHaveFocus();
    expect(panel).toHaveTextContent("Ranked #1 mainly for similar meaning and shared topics.");
    expect(panel).toHaveTextContent("Meaning");
    expect(panel).toHaveTextContent("76 out of 100, very strong");
    expect(panel).toHaveTextContent("Search terms");
    // A signal with no weight did not count and is not a meter.
    expect(within(panel).queryByText("Recency")).not.toBeInTheDocument();
    // A signal the backend had no data for is said in words, never drawn as a zero.
    expect(panel).toHaveTextContent("CitationsNot available for this item");
    expect(panel.textContent).not.toMatch(/(^|[^0-9])0 out of 100/);
    expect(within(panel).getByText("The abstract discusses explanation methods for graph neural networks.")).toBeInTheDocument();
    expect(within(panel).getByText("Pennsylvania State University")).toBeInTheDocument();
    // Today's exact numbers stay, behind a disclosure, for examiners.
    const technical = within(panel).getByText("Technical details").closest("details")!;
    expect(technical).not.toHaveAttribute("open");
    expect(technical).toHaveTextContent("0.5634");
    expect(within(technical).getByRole("table", { name: "Signal contributions" })).toBeInTheDocument();

    fireEvent.click(within(panel).getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog", { name: "Why this result?" })).not.toBeInTheDocument();
    expect(why).toHaveFocus();
  });
});

describe("the paper panel", () => {
  it("opens from the title, asks for similar papers only then, and returns focus", async () => {
    visit("/?q=retrieval");
    const fetchMock = serve();
    render(page());
    await showResults();
    expect(similarCalls(fetchMock)).toHaveLength(0);

    const title = screen.getByRole("button", { name: "Older but more relevant" });
    title.focus();
    fireEvent.click(title);
    const panel = await screen.findByRole("dialog", { name: "Older but more relevant" });
    expect(panel).toHaveAccessibleDescription("NeurIPS · 2019 · Preprint");
    expect(within(panel).getByRole("heading", { level: 2 })).toHaveFocus();
    expect(within(panel).getByText(/Despite recent progress/)).toBeInTheDocument();
    expect(within(panel).getByRole("link", { name: /Open publisher page/ })).toHaveAttribute("href", "https://arxiv.org/abs/2011.04573");

    expect(await within(panel).findByText("GNNExplainer: Generating Explanations for Graph Neural Networks")).toBeInTheDocument();
    expect(similarCalls(fetchMock)).toHaveLength(1);
    expect(similarCalls(fetchMock)[0]).toContain(`/api/v1/discovery/research/${WORK_ID}/similar?limit=5&offset=0`);
    expect(within(panel).getByRole("link", { name: "All 12 similar papers" })).toHaveAttribute("href", `/similar?paper=${WORK_ID}`);

    fireEvent.keyDown(panel, { key: "Escape" });
    fireEvent(panel, new Event("cancel"));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Older but more relevant" })).not.toBeInTheDocument());
    expect(title).toHaveFocus();
  });

  it("offers saving and the citation export only to a signed-in researcher", async () => {
    visit("/?q=retrieval");
    serve();
    render(page());
    await showResults();
    fireEvent.click(screen.getByRole("button", { name: "Older but more relevant" }));
    const panel = await screen.findByRole("dialog", { name: "Older but more relevant" });
    expect(within(panel).queryByRole("button", { name: /reading list/ })).not.toBeInTheDocument();
    expect(within(panel).queryByRole("button", { name: "Export citation" })).not.toBeInTheDocument();
  });
});

describe("the first paint (layout shift)", () => {
  it("prerenders only the title and the search box, so neither the start page nor results replace anything", () => {
    // The page is prerendered without the URL. Painting the start page first and swapping it for
    // results moved the layout by 104–179px (CLS 0.07–0.11, P5 measurement); now the start page
    // or the results are only ever added below the search box.
    const html = renderToString(page());
    expect(html).toContain("Literature search");
    expect(html).toContain('aria-label="Submit search"');
    expect(html).not.toContain("Begin your literature search");
    expect(html).not.toContain("Try:");
  });
});
