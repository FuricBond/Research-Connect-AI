/**
 * P7 — the workspace status menu (plan §13, §19).
 *
 * The status of a tracked call is one menu offering only the moves the server lists for that item
 * (`allowed_transitions`, from the backend's VALID_TRANSITIONS). A move shows at once, is replaced
 * by the server's answer, and is rolled back to the last confirmed status if the server refuses,
 * with "Try again". An answer to an older request never overwrites a newer state.
 */

import React, { type ReactNode } from "react";
import { act, fireEvent, render, renderHook, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn(), back: vi.fn(), forward: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/workspace",
  useSearchParams: () => new URLSearchParams(window.location.search),
}));

import WorkspacePageRoute from "../app/workspace/page";
import { SessionProvider } from "../components/auth/SessionProvider";
import { orderedTransitions } from "../components/workspace/StatusMenu";
import { useWorkspaceList } from "../components/workspace/useWorkspaceList";
import { clearActiveIdentity, storeSession } from "../services/auth";
import type { WorkspaceItem, WorkspaceStatus } from "../types/workspace";
import { jsonResponse, makeTokenResponse, makeUser } from "./factories";
import { ITEM_ID, TRANSITIONS, deferred, listOf, makeItem, ok, refuse } from "./p7-fixtures";

type Answer = (body: { target_status: WorkspaceStatus }) => Promise<Response>;

let fetchMock: ReturnType<typeof vi.fn>;
let items: WorkspaceItem[];
let answerTransition: Answer;

function serve() {
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    if (url.endsWith("/api/v1/auth/me")) return ok(makeUser());
    if (url.endsWith("/api/v1/workspace/summary")) return ok(listOf(items));
    if (url.includes("/api/v1/workspace?")) return ok(listOf(items));
    if (url.endsWith(`/api/v1/workspace/${ITEM_ID}/transition`) && method === "POST") return answerTransition(JSON.parse(String(init?.body)));
    return Promise.resolve(jsonResponse({ detail: `unexpected ${method} ${url}` }, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
}

const transitions = () => fetchMock.mock.calls.filter(([url, init]) => String(url).includes("/transition") && (init as RequestInit)?.method === "POST");
const summaries = () => fetchMock.mock.calls.filter(([url]) => String(url).endsWith("/api/v1/workspace/summary"));

function renderPage() {
  return render(
    <SessionProvider>
      <WorkspacePageRoute />
    </SessionProvider>
  );
}

async function row() {
  const link = await screen.findByRole("link", { name: "International Conference on Information Retrieval Systems" });
  return within(link.closest("li") as HTMLElement);
}

beforeEach(() => {
  storeSession(makeTokenResponse());
  window.history.replaceState(null, "", "/workspace");
  items = [makeItem({ status: "PLANNING" })];
  answerTransition = ({ target_status }) => ok(makeItem({ status: target_status }));
  serve();
});

afterEach(() => clearActiveIdentity());

describe("the status menu", () => {
  it("lists a status's allowed moves in workflow order", () => {
    expect(orderedTransitions(TRANSITIONS.PLANNING)).toEqual(["SAVED", "CONSIDERING", "APPLIED", "ARCHIVED"]);
    expect(orderedTransitions(TRANSITIONS.APPLIED)).toEqual(["PLANNING", "ACCEPTED", "REJECTED", "ARCHIVED"]);
    expect(orderedTransitions([])).toEqual([]);
  });

  it("offers only the moves the server allows for the item", async () => {
    renderPage();
    const card = await row();
    fireEvent.click(card.getByRole("button", { name: "Status: Planning. Change status" }));
    const menu = card.getByRole("menu", { name: "Status: Planning. Change status" });
    expect(within(menu).getAllByRole("menuitem").map((item) => item.textContent)).toEqual([
      "Move to saved",
      "Move to considering",
      "Move to applied",
      "Move to archived",
    ]);
    // Not allowed from Planning: an outcome before applying, or the status it already has.
    for (const name of ["Move to accepted", "Move to not accepted", "Move to planning"]) expect(within(menu).queryByRole("menuitem", { name })).toBeNull();
  });

  it("shows a status with no allowed moves as a badge, not a menu", async () => {
    items = [makeItem({ status: "ACCEPTED", allowed_transitions: [] })];
    renderPage();
    const card = await row();
    expect(card.getByText("Accepted")).toBeInTheDocument();
    expect(card.queryByRole("button", { name: /Change status/ })).toBeNull();
  });

  it("follows the server's list, not a guess from the status", async () => {
    // The server may allow fewer moves than the state machine (for example while a rule applies).
    items = [makeItem({ status: "APPLIED", allowed_transitions: ["ARCHIVED"] })];
    renderPage();
    const card = await row();
    fireEvent.click(card.getByRole("button", { name: "Status: Applied. Change status" }));
    expect(card.getAllByRole("menuitem").map((item) => item.textContent)).toEqual(["Move to archived"]);
  });
});

describe("changing the status", () => {
  it("shows the move at once, then keeps the server's answer and refreshes the counts", async () => {
    const pending = deferred();
    answerTransition = () => pending.promise;
    renderPage();
    const card = await row();
    await waitFor(() => expect(summaries()).toHaveLength(1));

    fireEvent.click(card.getByRole("button", { name: "Status: Planning. Change status" }));
    fireEvent.click(card.getByRole("menuitem", { name: "Move to applied" }));

    // Optimistic: the new status shows while the request is in flight, with nothing else to choose.
    expect(card.getByText("Applied")).toBeInTheDocument();
    expect(card.getByText("Saving…")).toBeInTheDocument();
    expect(card.queryByRole("button", { name: /Change status/ })).toBeNull();
    expect(JSON.parse(String((transitions()[0][1] as RequestInit).body))).toEqual({ target_status: "APPLIED" });

    await act(async () => pending.resolve(jsonResponse(makeItem({ status: "APPLIED" }))));
    expect(await card.findByRole("button", { name: "Status: Applied. Change status" })).toBeInTheDocument();
    expect(card.queryByText("Saving…")).toBeNull();
    // Announced in the page's live region.
    expect(screen.getByText("International Conference on Information Retrieval Systems: Applied.")).toHaveAttribute("role", "status");
    await waitFor(() => expect(summaries()).toHaveLength(2));
  });

  it("rolls back to the confirmed status when the server refuses, and can try again", async () => {
    answerTransition = () => refuse(409, "Cannot move this item.");
    renderPage();
    const card = await row();

    fireEvent.click(card.getByRole("button", { name: "Status: Planning. Change status" }));
    fireEvent.click(card.getByRole("menuitem", { name: "Move to applied" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("International Conference on Information Retrieval Systems could not be moved to applied.");
    expect(alert).toHaveTextContent("Its status is back to what the server last confirmed.");
    expect(card.getByRole("button", { name: "Status: Planning. Change status" })).toBeInTheDocument();
    expect(card.queryByText("Applied")).toBeNull();

    answerTransition = ({ target_status }) => ok(makeItem({ status: target_status }));
    fireEvent.click(within(alert).getByRole("button", { name: "Try again" }));
    expect(await card.findByRole("button", { name: "Status: Applied. Change status" })).toBeInTheDocument();
    expect(transitions()).toHaveLength(2);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("archives and restores through the row's menu, only when allowed", async () => {
    renderPage();
    const card = await row();
    fireEvent.click(card.getByRole("button", { name: /More actions for International Conference/ }));
    fireEvent.click(card.getByRole("menuitem", { name: "Archive" }));
    expect(await card.findByRole("button", { name: "Status: Archived. Change status" })).toBeInTheDocument();
    expect(JSON.parse(String((transitions()[0][1] as RequestInit).body))).toEqual({ target_status: "ARCHIVED" });

    fireEvent.click(card.getByRole("button", { name: /More actions for International Conference/ }));
    expect(card.getByRole("menuitem", { name: "Restore" })).toBeEnabled();
  });
});

describe("overlapping changes (useWorkspaceList)", () => {
  const wrapper = ({ children }: { children: ReactNode }) => <SessionProvider>{children}</SessionProvider>;
  const query = { status: null, sort: "deadline" as const, search: "" };

  it("never lets a late answer to an older change overwrite a newer one", async () => {
    const first = deferred();
    const second = deferred();
    const answers = [first, second];
    answerTransition = () => answers.shift()!.promise;
    const { result } = renderHook(() => useWorkspaceList(query), { wrapper });
    await waitFor(() => expect(result.current.items).toHaveLength(1));
    const item = result.current.items![0];

    act(() => void result.current.changeStatus(item, "APPLIED"));
    act(() => void result.current.changeStatus(item, "ARCHIVED"));
    expect(result.current.items![0].status).toBe("ARCHIVED");

    await act(async () => second.resolve(jsonResponse(makeItem({ status: "ARCHIVED" }))));
    expect(result.current.items![0].status).toBe("ARCHIVED");
    // The first request answers last: ignored, whether it succeeded or failed.
    await act(async () => first.resolve(jsonResponse(makeItem({ status: "APPLIED" }))));
    expect(result.current.items![0].status).toBe("ARCHIVED");
    expect(result.current.failed).toBeNull();
    expect(result.current.pending.size).toBe(0);
  });

  it("ignores a late failure of an older change", async () => {
    const first = deferred();
    const second = deferred();
    const answers = [first, second];
    answerTransition = () => answers.shift()!.promise;
    const { result } = renderHook(() => useWorkspaceList(query), { wrapper });
    await waitFor(() => expect(result.current.items).toHaveLength(1));
    const item = result.current.items![0];

    act(() => void result.current.changeStatus(item, "APPLIED"));
    act(() => void result.current.changeStatus(item, "SAVED"));
    await act(async () => second.resolve(jsonResponse(makeItem({ status: "SAVED" }))));
    await act(async () => first.resolve(jsonResponse({ detail: "late" }, 500)));
    expect(result.current.items![0].status).toBe("SAVED");
    expect(result.current.failed).toBeNull();
  });

  it("never sends a move the item does not allow", async () => {
    const { result } = renderHook(() => useWorkspaceList(query), { wrapper });
    await waitFor(() => expect(result.current.items).toHaveLength(1));
    await act(async () => result.current.changeStatus(result.current.items![0], "ACCEPTED"));
    expect(transitions()).toHaveLength(0);
    expect(result.current.items![0].status).toBe("PLANNING");
  });
});
