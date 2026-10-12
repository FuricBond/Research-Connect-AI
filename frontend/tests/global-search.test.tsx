/**
 * P2.6 — the global paper search, and the search page's query in the URL.
 *
 * The header search runs no search itself: it opens the literature search page at `/?q=…`.
 * The page runs the URL's query once, so a search can be bookmarked, shared and reloaded, and
 * the header and the page never both ask.
 *
 * P2 audit remediation: a search submitted on the page runs at once and the address bar is
 * updated through the browser's history (no page navigation to race with); the latest
 * submission always wins, a late answer or a late router notification for an older query
 * changes nothing, and text typed since the last search is never overwritten.
 */

import React from "react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

let pathname = "/workspace";
let search = new URLSearchParams();
const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace: vi.fn(), back: vi.fn(), forward: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => pathname,
  useSearchParams: () => search,
}));

import { SessionProvider } from "../components/auth/SessionProvider";
import { DiscoverySearch } from "../components/pages/DiscoverySearch";
import { AppShell } from "../components/shell/AppShell";
import { clearActiveIdentity } from "../services/auth";
import { requestSearchFocus, searchHref } from "../utils/search";
import { jsonResponse } from "./factories";
import { installDialogPolyfill, serveShell } from "./shell-support";

const SEARCH_PATH = "/api/v1/discovery/research/search";

function serveSearch() {
  return serveShell(null, {
    other: (url) => (url.includes(SEARCH_PATH) ? Promise.resolve(jsonResponse({ items: [], total: 0, query_intelligence: null })) : undefined),
  });
}

function searchCalls(fetchMock: ReturnType<typeof serveShell>): string[] {
  return fetchMock.mock.calls
    .map(([url]) => String(url))
    .filter((url) => url.includes(SEARCH_PATH))
    .map((url) => new URL(url).searchParams.get("q") ?? "");
}

function renderShell(page: React.ReactNode = <p>Page</p>) {
  return render(
    <SessionProvider>
      <AppShell>{page}</AppShell>
    </SessionProvider>
  );
}

beforeAll(installDialogPolyfill);

beforeEach(() => {
  pathname = "/workspace";
  search = new URLSearchParams();
  push.mockClear();
  window.history.replaceState(null, "", "/");
});

afterEach(() => {
  clearActiveIdentity();
  vi.unstubAllGlobals();
});

describe("header search", () => {
  it("opens the search page with the query in the URL", async () => {
    const fetchMock = serveSearch();
    renderShell();

    const form = screen.getByRole("search", { name: "Papers" });
    const field = within(form).getByRole("searchbox", { name: "Search papers" });
    fireEvent.change(field, { target: { value: "  graph neural networks " } });
    fireEvent.submit(form);

    expect(push).toHaveBeenCalledTimes(1);
    expect(push).toHaveBeenCalledWith("/?q=graph%20neural%20networks");
    expect(field).toHaveValue("");
    // The header itself asked the API nothing.
    expect(searchCalls(fetchMock)).toEqual([]);
  });

  it("does nothing with an empty query but keep the field focused", () => {
    serveSearch();
    renderShell();

    const form = screen.getByRole("search", { name: "Papers" });
    fireEvent.change(within(form).getByRole("searchbox"), { target: { value: "   " } });
    fireEvent.submit(form);

    expect(push).not.toHaveBeenCalled();
    expect(within(form).getByRole("searchbox")).toHaveFocus();
  });

  it("clears on Escape, then leaves the field", () => {
    serveSearch();
    renderShell();
    const field = screen.getByRole("searchbox", { name: "Search papers" });
    field.focus();

    fireEvent.change(field, { target: { value: "retrieval" } });
    fireEvent.keyDown(field, { key: "Escape" });
    expect(field).toHaveValue("");
    expect(field).toHaveFocus();
    fireEvent.keyDown(field, { key: "Escape" });
    expect(field).not.toHaveFocus();
  });

  it("is focused by '/', except while the person is typing elsewhere", () => {
    serveSearch();
    renderShell(<input aria-label="Notes" />);
    const field = screen.getByRole("searchbox", { name: "Search papers" });

    fireEvent.keyDown(document.body, { key: "/" });
    expect(field).toHaveFocus();

    const notes = screen.getByRole("textbox", { name: "Notes" });
    notes.focus();
    fireEvent.keyDown(notes, { key: "/" });
    expect(notes).toHaveFocus();
  });

  it("opens a search sheet on a phone, with the field focused", () => {
    serveSearch();
    renderShell();

    const open = screen.getByRole("button", { name: "Search papers" });
    expect(open).toHaveAttribute("aria-haspopup", "dialog");
    fireEvent.click(open);
    expect(open).toHaveAttribute("aria-expanded", "true");
    const sheet = screen.getByRole("dialog", { name: "Search papers" });
    const field = within(sheet).getByRole("searchbox", { name: "Search papers" });
    expect(field).toHaveFocus();

    fireEvent.change(field, { target: { value: "federated learning" } });
    fireEvent.click(within(sheet).getByRole("button", { name: "Search" }));
    expect(push).toHaveBeenCalledWith(searchHref("federated learning"));
    expect(open).toHaveAttribute("aria-expanded", "false");
  });

  it("is not offered on the search page, which has its own search box", () => {
    serveSearch();
    pathname = "/";
    renderShell();

    expect(screen.queryByRole("searchbox", { name: "Search papers" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Search papers" })).not.toBeInTheDocument();
  });
});

describe("search page query in the URL", () => {
  type Answer = { query: string; resolve: () => void; fail: (status: number) => void };

  /**
   * Search requests that answer only when the test says so; each answer names its query in
   * the "query intelligence" banner, so the page shows whose results it is displaying.
   */
  function serveHeldSearches() {
    const answers: Answer[] = [];
    const fetchMock = serveShell(null, {
      other: (url) => {
        if (!url.includes(SEARCH_PATH)) return undefined;
        const query = new URL(url).searchParams.get("q") ?? "";
        return new Promise<Response>((resolve) => {
          answers.push({
            query,
            resolve: () =>
              resolve(
                jsonResponse({
                  query,
                  items: [],
                  total: 0,
                  limit: 20,
                  offset: 0,
                  has_more: false,
                  ranking_mode: "hybrid",
                  query_intelligence: {
                    original_query: query,
                    normalized_query: query,
                    expanded_query: `${query} expanded`,
                    was_expanded: true,
                    detected_acronyms: [query.toUpperCase()],
                    detected_terms: [`results for ${query}`],
                    transformations: [],
                  },
                })
              ),
            fail: (status) => resolve(jsonResponse({ detail: "boom" }, status)),
          });
        });
      },
    });
    const answer = async (query: string) => {
      const pending = answers.find((a) => a.query === query);
      if (!pending) throw new Error(`no request for ${query}`);
      answers.splice(answers.indexOf(pending), 1);
      await act(async () => pending.resolve());
    };
    return { fetchMock, answer };
  }

  function page() {
    return (
      <SessionProvider>
        <DiscoverySearch />
      </SessionProvider>
    );
  }

  /** Arrives at `url` from outside: a direct link, reload, back/forward (bar and router agree). */
  function visit(url: string) {
    window.history.replaceState(null, "", url);
    search = new URLSearchParams(window.location.search);
  }

  /** The router catches up with the address bar (it applies history updates in a transition). */
  function routerSees(query: string | null, view: ReturnType<typeof render>) {
    search = new URLSearchParams(query === null ? "" : `q=${encodeURIComponent(query)}`);
    view.rerender(page());
  }

  const box = () => screen.getByRole("searchbox", { name: "Search research literature" });
  const addressQuery = () => new URLSearchParams(window.location.search).get("q");
  function submit(text: string) {
    fireEvent.change(box(), { target: { value: text } });
    fireEvent.submit(box().closest("form")!);
  }

  it("runs the URL's query once on arrival and shows it in the box", async () => {
    visit("/?q=information retrieval");
    const fetchMock = serveSearch();
    render(page());

    await waitFor(() => expect(searchCalls(fetchMock)).toEqual(["information retrieval"]));
    expect(box()).toHaveValue("information retrieval");
    expect(await screen.findByText("No research works matched your query")).toBeInTheDocument();
    await act(async () => undefined);
    expect(searchCalls(fetchMock)).toHaveLength(1);
    // Arriving from a link is not a header search: focus is left alone.
    expect(box()).not.toHaveFocus();
  });

  it("searches at once on submit and records the query in the address bar: one request", async () => {
    const fetchMock = serveSearch();
    const view = render(page());
    const before = window.history.length;

    submit("graph neural networks");
    await waitFor(() => expect(searchCalls(fetchMock)).toEqual(["graph neural networks"]));
    expect(window.location.search).toBe("?q=graph%20neural%20networks");
    expect(window.history.length).toBe(before + 1);
    // No page navigation: nothing for the router to race with.
    expect(push).not.toHaveBeenCalled();

    // The router then reports the new address: already searched, so no second request.
    routerSees("graph neural networks", view);
    await act(async () => undefined);
    expect(searchCalls(fetchMock)).toEqual(["graph neural networks"]);
  });

  it("searches again when the query in the URL is submitted again, without a new history entry", async () => {
    visit("/?q=retrieval");
    const fetchMock = serveSearch();
    render(page());
    await waitFor(() => expect(searchCalls(fetchMock)).toHaveLength(1));
    const before = window.history.length;

    fireEvent.click(screen.getByRole("button", { name: "Submit search" }));
    await waitFor(() => expect(searchCalls(fetchMock)).toEqual(["retrieval", "retrieval"]));
    expect(window.history.length).toBe(before);
    expect(push).not.toHaveBeenCalled();
  });

  it("keeps the latest of two overlapping searches, whatever order the answers and the router arrive in", async () => {
    const { fetchMock, answer } = serveHeldSearches();
    const view = render(page());

    submit("alpha");
    submit("beta");
    expect(searchCalls(fetchMock)).toEqual(["alpha", "beta"]);
    expect(addressQuery()).toBe("beta");

    // Unfavourable order: the router reports the older address after the newer one was made.
    routerSees("alpha", view);
    routerSees("beta", view);
    // And the older search answers last.
    await answer("beta");
    await answer("alpha");

    expect(screen.getByText("results for beta")).toBeInTheDocument();
    expect(screen.queryByText("results for alpha")).not.toBeInTheDocument();
    expect(box()).toHaveValue("beta");
    expect(addressQuery()).toBe("beta");
    expect(screen.queryByText(/Retrieving and ranking/)).not.toBeInTheDocument(); // not stuck loading
    expect(searchCalls(fetchMock)).toEqual(["alpha", "beta"]);
  });

  it("does not let a stale answer end the newer search's loading state", async () => {
    const { answer } = serveHeldSearches();
    render(page());

    submit("alpha");
    submit("beta");
    await answer("alpha");
    expect(screen.getByRole("status")).toHaveTextContent(/Retrieving/);
    expect(screen.queryByText("results for alpha")).not.toBeInTheDocument();
    await answer("beta");
    expect(screen.getByText("results for beta")).toBeInTheDocument();
  });

  it("keeps text typed while a search is loading, and searches nothing for it", async () => {
    const { fetchMock, answer } = serveHeldSearches();
    const view = render(page());

    submit("alpha");
    // The person starts refining before anything has come back.
    fireEvent.change(box(), { target: { value: "refined query" } });
    routerSees("alpha", view);
    await answer("alpha");

    expect(box()).toHaveValue("refined query");
    expect(screen.getByText("results for alpha")).toBeInTheDocument();
    expect(addressQuery()).toBe("alpha");
    expect(searchCalls(fetchMock)).toEqual(["alpha"]);
  });

  it("accepts a newer query while one is loading (Enter is never disabled by a search)", async () => {
    const { fetchMock, answer } = serveHeldSearches();
    render(page());

    submit("alpha");
    expect(screen.getByRole("button", { name: "Submit search" })).toBeEnabled();
    submit("gamma");
    await answer("gamma");
    expect(searchCalls(fetchMock)).toEqual(["alpha", "gamma"]);
    expect(screen.getByText("results for gamma")).toBeInTheDocument();
    expect(addressQuery()).toBe("gamma");
  });

  it("asks once when the same query is submitted twice while it loads", async () => {
    const { fetchMock } = serveHeldSearches();
    render(page());

    submit("alpha");
    submit("alpha");
    expect(searchCalls(fetchMock)).toEqual(["alpha"]);
  });

  it("follows an outside change of address (back/forward): shows and searches its query", async () => {
    visit("/?q=first");
    const fetchMock = serveSearch();
    const view = render(page());
    await waitFor(() => expect(searchCalls(fetchMock)).toEqual(["first"]));

    visit("/?q=second");
    view.rerender(page());
    await waitFor(() => expect(searchCalls(fetchMock)).toEqual(["first", "second"]));
    expect(box()).toHaveValue("second");
  });

  it("returns to the start when the URL loses its query", async () => {
    visit("/?q=retrieval");
    serveSearch();
    const view = render(page());
    expect(await screen.findByText("No research works matched your query")).toBeInTheDocument();

    visit("/");
    view.rerender(page());
    expect(await screen.findByText("Begin your literature search")).toBeInTheDocument();
    expect(box()).toHaveValue("");
  });

  it("asks nothing when there is no query", async () => {
    const fetchMock = serveSearch();
    render(page());
    await act(async () => undefined);
    expect(searchCalls(fetchMock)).toEqual([]);
    expect(screen.getByText("Begin your literature search")).toBeInTheDocument();
  });

  it("puts keyboard focus in its box when it shows a header search's query", async () => {
    requestSearchFocus("federated learning");
    visit("/?q=federated%20learning");
    serveSearch();
    render(page());

    await waitFor(() => expect(box()).toHaveFocus());
    expect(box()).toHaveValue("federated learning");
  });
});
