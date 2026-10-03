/**
 * Phase 5.14 — the Reading List page.
 *
 * It lists saved papers with status tabs and counts, changes a status (PATCH), saves notes when
 * the box loses focus (PATCH), removes a paper (DELETE) and exports the selection or the whole
 * list as BibTeX.
 */

import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn(), back: vi.fn(), forward: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/reading-list",
  useSearchParams: () => new URLSearchParams(),
}));

import ReadingListRoute from "../app/reading-list/page";
import { SessionProvider } from "../components/auth/SessionProvider";
import { storeSession } from "../services/auth";
import type { ReadingListItem, ReadingListResponse, ReadingStatus } from "../types/reading_list";
import { jsonResponse, makeTokenResponse, makeUser } from "./factories";

function makeItem(index: number, status: ReadingStatus, notes: string | null = null): ReadingListItem {
  return {
    id: `rl000000-0000-4000-8000-00000000000${index}`,
    work_id: `wk000000-0000-4000-8000-00000000000${index}`,
    status,
    notes,
    status_updated_at: "2026-10-01T10:00:00+00:00",
    started_at: null,
    finished_at: null,
    created_at: "2026-10-01T10:00:00+00:00",
    updated_at: "2026-10-01T10:00:00+00:00",
    work: {
      id: `wk000000-0000-4000-8000-00000000000${index}`,
      title: `Paper ${index}`,
      doi: `10.1000/paper-${index}`,
      publication_year: 2024,
      work_type: "article",
      venue_name: "Journal of Retrieval",
      authors: ["Ada Lovelace", "Charles Babbage"],
      landing_page_url: null,
    },
  };
}

const ITEMS = [makeItem(1, "TO_READ"), makeItem(2, "READING", "Compare with BM25.")];
const COUNTS = { TO_READ: 1, READING: 1, DONE: 0 };

function listResponse(items: ReadingListItem[]): ReadingListResponse {
  return { items, total_count: items.length, limit: 50, offset: 0, counts_by_status: COUNTS };
}

let fetchMock: ReturnType<typeof vi.fn>;
let createObjectURL: ReturnType<typeof vi.fn>;
const originalCreateObjectURL = URL.createObjectURL;
const originalRevokeObjectURL = URL.revokeObjectURL;

beforeEach(() => {
  storeSession(makeTokenResponse());
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    if (url.endsWith("/api/v1/auth/me")) return Promise.resolve(jsonResponse(makeUser()));
    if (url.includes("/api/v1/reading-list/export.bib")) {
      return Promise.resolve(new Response("@article{x,\n}\n", { status: 200 }));
    }
    if (url.includes("/api/v1/reading-list?")) {
      const status = new URL(url).searchParams.get("status");
      return Promise.resolve(jsonResponse(listResponse(ITEMS.filter((i) => !status || i.status === status))));
    }
    const match = url.match(/\/api\/v1\/reading-list\/([^/?]+)$/);
    if (match && method === "PATCH") {
      const item = ITEMS.find((i) => i.id === match[1])!;
      return Promise.resolve(jsonResponse({ ...item, ...JSON.parse(String(init?.body)) }));
    }
    if (match && method === "DELETE") return Promise.resolve(new Response(null, { status: 204 }));
    return Promise.resolve(jsonResponse({ detail: `unexpected request ${method} ${url}` }, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
  // jsdom has no object URLs and cannot navigate, so both are stubbed.
  createObjectURL = vi.fn(() => "blob:reading-list");
  URL.createObjectURL = createObjectURL as unknown as typeof URL.createObjectURL;
  URL.revokeObjectURL = vi.fn();
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
});

afterEach(() => {
  URL.createObjectURL = originalCreateObjectURL;
  URL.revokeObjectURL = originalRevokeObjectURL;
});

function requests(method: string): string[] {
  return fetchMock.mock.calls
    .filter(([, init]) => ((init as RequestInit | undefined)?.method ?? "GET") === method)
    .map(([url]) => String(url));
}

function bodyOf(method: string, urlPart: string): Record<string, unknown> {
  const call = fetchMock.mock.calls.find(
    ([url, init]) => String(url).includes(urlPart) && (init as RequestInit | undefined)?.method === method
  );
  return JSON.parse(String((call![1] as RequestInit).body));
}

function renderPage() {
  return render(
    <SessionProvider>
      <ReadingListRoute />
    </SessionProvider>
  );
}

function card(title: string): HTMLElement {
  return screen.getByRole("heading", { name: title }).closest("article") as HTMLElement;
}

describe("reading list page", () => {
  it("lists saved papers with authors, venue, year and a DOI link", async () => {
    renderPage();

    await screen.findByRole("heading", { name: "Paper 1" });
    const first = card("Paper 1");
    expect(first).toHaveTextContent("Ada Lovelace, Charles Babbage");
    expect(first).toHaveTextContent("Journal of Retrieval");
    expect(first).toHaveTextContent("2024");
    expect(within(first).getByRole("link", { name: "DOI: 10.1000/paper-1" })).toHaveAttribute(
      "href",
      "https://doi.org/10.1000/paper-1"
    );
    expect(within(card("Paper 2")).getByLabelText(/Notes/)).toHaveValue("Compare with BM25.");
  });

  it("filters by status with counts on the tabs", async () => {
    renderPage();
    await screen.findByRole("heading", { name: "Paper 1" });

    expect(screen.getByRole("button", { name: "All (2)" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: "Reading (1)" }));

    await waitFor(() => expect(screen.queryByRole("heading", { name: "Paper 1" })).not.toBeInTheDocument());
    expect(screen.getByRole("heading", { name: "Paper 2" })).toBeInTheDocument();
    expect(requests("GET").some((url) => url.includes("/api/v1/reading-list?status=READING"))).toBe(true);
  });

  it("changes a status and saves notes on blur with PATCH", async () => {
    renderPage();
    await screen.findByRole("heading", { name: "Paper 1" });

    fireEvent.change(within(card("Paper 1")).getByLabelText("Status"), { target: { value: "DONE" } });
    await waitFor(() => expect(requests("PATCH")).toHaveLength(1));
    expect(bodyOf("PATCH", ITEMS[0].id)).toEqual({ status: "DONE" });

    const notes = within(card("Paper 1")).getByLabelText(/Notes/);
    fireEvent.change(notes, { target: { value: "Read section 3." } });
    fireEvent.blur(notes);
    await waitFor(() => expect(requests("PATCH")).toHaveLength(2));
    const notesCall = fetchMock.mock.calls.filter(([, init]) => (init as RequestInit | undefined)?.method === "PATCH")[1];
    expect(JSON.parse(String((notesCall[1] as RequestInit).body))).toEqual({ notes: "Read section 3." });
  });

  it("does not save notes that did not change", async () => {
    renderPage();
    await screen.findByRole("heading", { name: "Paper 2" });

    fireEvent.blur(within(card("Paper 2")).getByLabelText(/Notes/));

    expect(requests("PATCH")).toHaveLength(0);
  });

  it("removes a paper with DELETE", async () => {
    renderPage();
    await screen.findByRole("heading", { name: "Paper 1" });

    fireEvent.click(screen.getByRole("button", { name: "Remove Paper 1" }));

    await waitFor(() => expect(requests("DELETE")).toHaveLength(1));
    expect(requests("DELETE")[0]).toContain(`/api/v1/reading-list/${ITEMS[0].id}`);
  });

  it("exports the selected papers and the whole list as BibTeX", async () => {
    renderPage();
    await screen.findByRole("heading", { name: "Paper 1" });

    const exportSelected = screen.getByRole("button", { name: "Export selected (.bib)" });
    expect(exportSelected).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox", { name: "Select Paper 2" }));
    fireEvent.click(exportSelected);

    await waitFor(() => expect(createObjectURL).toHaveBeenCalledTimes(1));
    const selectedExport = requests("GET").find((url) => url.includes("/export.bib"))!;
    expect(new URL(selectedExport).searchParams.getAll("item_ids")).toEqual([ITEMS[1].id]);

    fireEvent.click(screen.getByRole("button", { name: "Export all (.bib)" }));
    await waitFor(() => expect(createObjectURL).toHaveBeenCalledTimes(2));
    const allExport = requests("GET").filter((url) => url.includes("/export.bib"))[1];
    expect(new URL(allExport).search).toBe("");
  });
});
