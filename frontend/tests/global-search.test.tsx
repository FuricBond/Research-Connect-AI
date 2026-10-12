/**
 * P2.6 — the global paper search, and the search page's query in the URL.
 *
 * The header search runs no search itself: it opens the literature search page at `/?q=…`.
 * The page runs the URL's query once, so a search can be bookmarked, shared and reloaded, and
 * the header and the page never both ask.
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
import { searchHref } from "../utils/search";
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
  function renderPage() {
    return render(
      <SessionProvider>
        <DiscoverySearch />
      </SessionProvider>
    );
  }

  it("runs the URL's query once on arrival and shows it in the box", async () => {
    search = new URLSearchParams("q=information retrieval");
    const fetchMock = serveSearch();
    renderPage();

    await waitFor(() => expect(searchCalls(fetchMock)).toEqual(["information retrieval"]));
    expect(screen.getByRole("searchbox", { name: "Search research literature" })).toHaveValue("information retrieval");
    expect(await screen.findByText("No research works matched your query")).toBeInTheDocument();
    await act(async () => undefined);
    expect(searchCalls(fetchMock)).toHaveLength(1);
  });

  it("puts a new query in the URL, and the URL runs it: one request, not two", async () => {
    const fetchMock = serveSearch();
    const view = renderPage();

    const box = screen.getByRole("searchbox", { name: "Search research literature" });
    fireEvent.change(box, { target: { value: "graph neural networks" } });
    fireEvent.click(screen.getByRole("button", { name: "Submit search" }));
    expect(push).toHaveBeenCalledWith("/?q=graph%20neural%20networks");
    expect(searchCalls(fetchMock)).toEqual([]);

    // The router then changes the URL.
    search = new URLSearchParams("q=graph neural networks");
    view.rerender(
      <SessionProvider>
        <DiscoverySearch />
      </SessionProvider>
    );
    await waitFor(() => expect(searchCalls(fetchMock)).toEqual(["graph neural networks"]));
  });

  it("searches again when the query already in the URL is submitted again", async () => {
    search = new URLSearchParams("q=retrieval");
    const fetchMock = serveSearch();
    renderPage();
    await waitFor(() => expect(searchCalls(fetchMock)).toHaveLength(1));

    fireEvent.click(screen.getByRole("button", { name: "Submit search" }));
    await waitFor(() => expect(searchCalls(fetchMock)).toEqual(["retrieval", "retrieval"]));
    expect(push).not.toHaveBeenCalled();
  });

  it("returns to the start when the URL loses its query", async () => {
    search = new URLSearchParams("q=retrieval");
    serveSearch();
    const view = renderPage();
    expect(await screen.findByText("No research works matched your query")).toBeInTheDocument();

    search = new URLSearchParams();
    view.rerender(
      <SessionProvider>
        <DiscoverySearch />
      </SessionProvider>
    );
    expect(await screen.findByText("Begin your literature search")).toBeInTheDocument();
    expect(screen.getByRole("searchbox", { name: "Search research literature" })).toHaveValue("");
  });

  it("asks nothing when there is no query", async () => {
    const fetchMock = serveSearch();
    renderPage();
    await act(async () => undefined);
    expect(searchCalls(fetchMock)).toEqual([]);
    expect(screen.getByText("Begin your literature search")).toBeInTheDocument();
  });
});
