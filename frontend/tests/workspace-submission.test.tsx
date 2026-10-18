/**
 * P7 — the Submission tab of a workspace item (it replaces /workspace/[id]/submission).
 *
 * Drafting checks the title before anything is sent, creates one draft however often it is
 * pressed, and keeps what was typed when the server refuses. Status changes are the server's
 * `allowed_transitions`; "ready" is held back while the readiness check has blockers, and says
 * why. The details form checks the portal address and keeps the draft on failure.
 */

import React, { Suspense } from "react";
import { act, configure, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// The tabs other than Overview load their code on first opening (lazyTabs.tsx); on a busy machine
// that can take longer than the default second.
configure({ asyncUtilTimeout: 5000 });

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn(), back: vi.fn(), forward: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => window.location.pathname,
  useSearchParams: () => new URLSearchParams(window.location.search),
  redirect: vi.fn(),
}));

import { SessionProvider } from "../components/auth/SessionProvider";
import { ItemPage } from "../components/workspace/item/ItemPage";
import { clearActiveIdentity, storeSession } from "../services/auth";
import type { ResearchSubmission } from "../types/submission";
import { jsonResponse, makeTokenResponse, makeUser } from "./factories";
import { ITEM_ID, SUBMISSION_ID, deferred, makeItem, makeReadiness, makeSubmission, ok, refuse } from "./p7-fixtures";

let fetchMock: ReturnType<typeof vi.fn>;
let submissions: ResearchSubmission[];
let answerCreate: (body: Record<string, unknown>) => Promise<Response>;
let answerUpdate: (body: Record<string, unknown>) => Promise<Response>;
let answerTransition: (body: Record<string, unknown>) => Promise<Response>;
let readiness = makeReadiness();

function serve() {
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    const path = new URL(url).pathname;
    const body = init?.body ? JSON.parse(String(init.body)) : {};
    if (path.endsWith("/api/v1/auth/me")) return ok(makeUser());
    if (path === `/api/v1/workspace/${ITEM_ID}`) return ok(makeItem());
    if (path === `/api/v1/workspace/${ITEM_ID}/submissions`) return ok({ items: submissions, total_count: submissions.length, counts_by_status: {}, counts_by_type: {} });
    if (path === "/api/v1/submissions" && method === "POST") return answerCreate(body);
    if (path === `/api/v1/submissions/${SUBMISSION_ID}` && method === "PATCH") return answerUpdate(body);
    if (path === `/api/v1/submissions/${SUBMISSION_ID}/transition` && method === "POST") return answerTransition(body);
    if (path === `/api/v1/submissions/${SUBMISSION_ID}/readiness`) return ok(readiness);
    if (path === `/api/v1/submissions/${SUBMISSION_ID}/documents`) return ok({ items: [], total_count: 0, submission_id: SUBMISSION_ID, counts_by_status: {}, counts_by_type: {} });
    return Promise.resolve(jsonResponse({ detail: `unexpected ${method} ${url}` }, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
}

const sent = (method: string, part: string) => fetchMock.mock.calls.filter(([url, init]) => String(url).includes(part) && (init as RequestInit)?.method === method);

function openTab() {
  window.history.replaceState(null, "", `/workspace/${ITEM_ID}?tab=submission`);
  return render(
    <SessionProvider>
      <Suspense fallback={null}>
        <ItemPage id={ITEM_ID} />
      </Suspense>
    </SessionProvider>
  );
}

beforeEach(() => {
  storeSession(makeTokenResponse());
  submissions = [];
  readiness = makeReadiness();
  answerCreate = (body) => ok(makeSubmission({ title: String(body.title), submission_type: body.submission_type as ResearchSubmission["submission_type"] }));
  answerUpdate = (body) => ok(makeSubmission({ ...(body as Partial<ResearchSubmission>), updated_at: "2026-09-22T10:00:00+00:00" }));
  answerTransition = (body) => ok(makeSubmission({ status: body.target_status as ResearchSubmission["status"], allowed_transitions: ["DRAFT", "SUBMITTED", "WITHDRAWN"] }));
  serve();
});

afterEach(() => clearActiveIdentity());

describe("drafting a submission", () => {
  it("checks the title first, then creates exactly one draft however often it is pressed", async () => {
    const pending = deferred();
    answerCreate = () => pending.promise;
    openTab();
    const create = await screen.findByRole("button", { name: "Create draft" });

    fireEvent.click(create);
    const title = screen.getByRole("textbox", { name: /^Title/ });
    expect(await screen.findByText("Give the submission a title: the manuscript's or the proposal's.")).toBeInTheDocument();
    expect(title).toHaveAttribute("aria-invalid", "true");
    expect(title).toHaveFocus();
    expect(sent("POST", "/api/v1/submissions")).toHaveLength(0);

    fireEvent.change(title, { target: { value: "Dense retrieval for scholarly search" } });
    fireEvent.change(screen.getByRole("combobox", { name: "Format" }), { target: { value: "SHORT_PAPER" } });
    fireEvent.click(create);
    fireEvent.click(create);
    expect(sent("POST", "/api/v1/submissions")).toHaveLength(1);
    expect(JSON.parse(String((sent("POST", "/api/v1/submissions")[0][1] as RequestInit).body))).toEqual({
      workspace_item_id: ITEM_ID,
      title: "Dense retrieval for scholarly search",
      submission_type: "SHORT_PAPER",
    });

    await act(async () => pending.resolve(jsonResponse(makeSubmission({ title: "Dense retrieval for scholarly search", submission_type: "SHORT_PAPER" }))));
    expect(await screen.findByRole("heading", { level: 2, name: "Dense retrieval for scholarly search" })).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Submission progress" })).toBeInTheDocument();
  });

  it("keeps what was typed when the server refuses, and creates it on the next press", async () => {
    answerCreate = () => refuse(500, "boom");
    openTab();
    fireEvent.change(await screen.findByRole("textbox", { name: /^Title/ }), { target: { value: "Retrieval with citations" } });
    fireEvent.click(screen.getByRole("button", { name: "Create draft" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("The draft could not be created. Try again.");
    expect(screen.getByRole("textbox", { name: /^Title/ })).toHaveValue("Retrieval with citations");

    answerCreate = (body) => ok(makeSubmission({ title: String(body.title) }));
    fireEvent.click(screen.getByRole("button", { name: "Create draft" }));
    expect(await screen.findByRole("heading", { level: 2, name: "Retrieval with citations" })).toBeInTheDocument();
    expect(sent("POST", "/api/v1/submissions")).toHaveLength(2);
  });
});

describe("a submission's status", () => {
  beforeEach(() => {
    submissions = [makeSubmission()];
  });

  it("offers the server's moves and holds back 'ready' while the readiness check has blockers", async () => {
    openTab();
    expect(await screen.findByText("The full paper is still missing.")).toBeInTheDocument();
    const ready = screen.getByRole("button", { name: "Mark ready to submit" });
    expect(ready).toBeDisabled();
    expect(ready).toHaveAccessibleDescription("It can be marked ready once the items under Readiness are fixed.");
    expect(screen.getByRole("button", { name: "Withdraw" })).toBeEnabled();
    expect(screen.queryByRole("button", { name: "Mark as submitted" })).toBeNull();
    expect(screen.getByRole("listitem", { current: "step" })).toHaveTextContent("Draft");
  });

  it("moves to the next status when ready, and says why the server refused otherwise", async () => {
    readiness = makeReadiness({ overall_readiness: "READY", can_mark_submission_ready: true, blocking_issues: [] });
    answerTransition = () => refuse(400, "Cannot transition submission to 'READY': 1 blocking readiness issue(s) detected.");
    openTab();
    const ready = await screen.findByRole("button", { name: "Mark ready to submit" });
    await waitFor(() => expect(ready).toBeEnabled());
    fireEvent.click(ready);
    expect(await screen.findByRole("alert")).toHaveTextContent("It could not be moved to ready to submit. Cannot transition submission to 'READY': 1 blocking readiness issue(s) detected.");

    answerTransition = (body) => ok(makeSubmission({ status: body.target_status as ResearchSubmission["status"], allowed_transitions: ["DRAFT", "SUBMITTED", "WITHDRAWN"] }));
    fireEvent.click(screen.getByRole("button", { name: "Mark ready to submit" }));
    expect(await screen.findByRole("button", { name: "Mark as submitted" })).toBeInTheDocument();
    expect(screen.getByRole("listitem", { current: "step" })).toHaveTextContent("Ready");
    expect(JSON.parse(String((sent("POST", "/transition").at(-1)![1] as RequestInit).body))).toEqual({ target_status: "READY" });
  });
});

describe("a submission's details", () => {
  beforeEach(() => {
    submissions = [makeSubmission()];
  });

  it("checks the portal address and keeps the edits when saving fails", async () => {
    answerUpdate = () => refuse(503, "unavailable");
    openTab();
    const details = within(await screen.findByRole("region", { name: "Details" }));
    const portal = details.getByRole("textbox", { name: "Submission portal" });
    fireEvent.change(portal, { target: { value: "openreview.net/forum" } });
    fireEvent.click(details.getByRole("button", { name: "Save details" }));
    expect(await details.findByText("Enter a web address starting with https:// or http://.")).toBeInTheDocument();
    expect(sent("PATCH", `/api/v1/submissions/${SUBMISSION_ID}`)).toHaveLength(0);

    fireEvent.change(portal, { target: { value: "https://openreview.net/forum?id=abc" } });
    fireEvent.change(details.getByRole("textbox", { name: "Venue or track" }), { target: { value: "Main track" } });
    fireEvent.click(details.getByRole("button", { name: "Save details" }));
    expect(await details.findByRole("alert")).toHaveTextContent("The details could not be saved. Try again.");
    expect(portal).toHaveValue("https://openreview.net/forum?id=abc");

    answerUpdate = (body) => ok(makeSubmission({ ...(body as Partial<ResearchSubmission>), updated_at: "2026-09-22T10:00:00+00:00" }));
    fireEvent.click(details.getByRole("button", { name: "Save details" }));
    expect(await details.findByText("Details saved.")).toBeInTheDocument();
    const body = JSON.parse(String((sent("PATCH", `/api/v1/submissions/${SUBMISSION_ID}`).at(-1)![1] as RequestInit).body));
    expect(body).toMatchObject({ submission_url: "https://openreview.net/forum?id=abc", venue: "Main track", title: "Query understanding for low-resource languages" });
    expect(details.getByRole("link", { name: /Open the submission portal/ })).toHaveAttribute("href", "https://openreview.net/forum?id=abc");
  });
});
