/**
 * P11 — accessibility refinements found while walking the plan's five screen-reader workflows
 * (FRONTEND_REDESIGN_PLAN.md §17). Applying to a posting: the parts of the "Apply for this opening"
 * section replace one another, and focus is never dropped on the page as they do — the form takes
 * it from "Apply now", Cancel gives it back, and after sending the section's heading takes it while
 * the confirmation is announced once as a status message. Tracking a call: a workspace status move
 * swaps the menu for "Saving…" and then for a new menu, and focus follows instead of dropping to
 * the page. Research preferences (the axe suite's one serious finding): every select is named, and
 * the three-state rows and the removal of a topic or keyword are buttons.
 */

import React, { useState } from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

let params: { id?: string } = {};
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn(), back: vi.fn(), forward: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => window.location.pathname,
  useSearchParams: () => new URLSearchParams(window.location.search),
  useParams: () => params,
}));

import PostingDetailPage from "../app/postings/[id]/page";
import ResearcherPreferencesPage from "../app/researcher/preferences/page";
import { SessionProvider } from "../components/auth/SessionProvider";
import { StatusMenu } from "../components/workspace/StatusMenu";
import { clearActiveIdentity, storeSession } from "../services/auth";
import type { ResearchPosting } from "../types/posting";
import type { ResearcherPreferenceItem } from "../types/researcher";
import type { WorkspaceStatus } from "../types/workspace";
import { PROFILE_ID, USER_ID, jsonResponse, makeTokenResponse, makeUser } from "./factories";
import { TRANSITIONS, makeItem } from "./p7-fixtures";
import { makePosting, ok, refuse } from "./p9-fixtures";
import { installDialogPolyfill } from "./shell-support";

let posting: ResearchPosting;
let fetchMock: ReturnType<typeof vi.fn>;

function serveStudent() {
  storeSession(makeTokenResponse({ user: makeUser({ role: "STUDENT" }) }));
  fetchMock = vi.fn((url: string, init: RequestInit = {}) => {
    const method = init.method ?? "GET";
    const path = url.replace(/^https?:\/\/[^/]+/, "");
    if (path === "/api/v1/auth/me") return ok(makeUser({ role: "STUDENT" }));
    if (method === "GET" && path === `/api/v1/postings/${posting.id}`) return ok(posting);
    if (method === "GET" && path === `/api/v1/postings/${posting.id}/fit`) return refuse(404, "No fit");
    if (method === "POST" && path === `/api/v1/postings/${posting.id}/applications`) {
      posting = { ...posting, viewer_application_status: "SUBMITTED", viewer_application_id: "8b000000-0000-4000-8000-000000000001" };
      return Promise.resolve(jsonResponse({ id: posting.viewer_application_id, status: "SUBMITTED" }, 201));
    }
    return Promise.resolve(jsonResponse({ detail: `unexpected ${method} ${path}` }, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
}

beforeAll(installDialogPolyfill);

beforeEach(() => {
  posting = makePosting(1, { is_owner: false });
  params = { id: posting.id };
});

afterEach(() => {
  clearActiveIdentity();
  vi.unstubAllGlobals();
});

describe("applying to a posting by keyboard and screen reader", () => {
  it("never drops focus as the form opens, is cancelled and is sent, and announces the confirmation once", async () => {
    serveStudent();
    window.history.replaceState(null, "", `/postings/${posting.id}`);
    render(
      <SessionProvider>
        <PostingDetailPage />
      </SessionProvider>
    );

    const applyNow = await screen.findByRole("button", { name: "Apply now" });
    applyNow.focus();
    fireEvent.click(applyNow);
    const note = await screen.findByRole("textbox", { name: /Statement of interest/ });
    await waitFor(() => expect(note).toHaveFocus());

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Apply now" })).toHaveFocus());

    fireEvent.click(screen.getByRole("button", { name: "Apply now" }));
    fireEvent.change(await screen.findByRole("textbox", { name: /Statement of interest/ }), { target: { value: "I build retrieval evaluation pipelines." } });
    fireEvent.click(screen.getByRole("button", { name: "Submit application" }));

    const heading = screen.getByRole("heading", { name: "Apply for this opening" });
    await waitFor(() => expect(heading).toHaveFocus());
    const confirmation = await screen.findByText(/Your application has been submitted\./);
    expect(confirmation.closest('[role="status"]')).not.toBeNull();
    // The posting is read again (it now carries the application); the confirmation stays, said once.
    await waitFor(() => expect(fetchMock.mock.calls.filter(([url]) => String(url).endsWith(`/api/v1/postings/${posting.id}`))).toHaveLength(2));
    expect(screen.queryByText(/You have applied to this opening/)).not.toBeInTheDocument();
    expect(screen.getAllByText(/has been submitted/)).toHaveLength(1);
  });

  it("does not announce an application made earlier: it is part of the page, not news", async () => {
    posting = makePosting(1, { is_owner: false, viewer_application_status: "SHORTLISTED", viewer_application_id: "8b000000-0000-4000-8000-000000000001" });
    serveStudent();
    window.history.replaceState(null, "", `/postings/${posting.id}`);
    render(
      <SessionProvider>
        <PostingDetailPage />
      </SessionProvider>
    );

    const earlier = await screen.findByText(/You have applied to this opening/);
    expect(earlier.closest('[role="status"]')).toBeNull();
    expect(screen.queryByRole("button", { name: "Apply now" })).not.toBeInTheDocument();
  });
});

// ── Research preferences (a page from before the redesign) ─────────────────────

function preference(id: string, category: ResearcherPreferenceItem["category"], value: string): ResearcherPreferenceItem {
  return {
    id, profile_id: PROFILE_ID, category, preference_type: "PREFERRED", preference_key: value.toLowerCase(), preference_value: value, display_label: value,
    strength: 1, confidence: 1, source: "EXPLICIT", is_active: true, recency_score: 1, provenance_reasons: [],
  };
}

function servePreferences(items: ResearcherPreferenceItem[]) {
  storeSession(makeTokenResponse({ user: makeUser({ role: "STUDENT" }) }));
  fetchMock = vi.fn((url: string, init: RequestInit = {}) => {
    const method = init.method ?? "GET";
    const path = url.replace(/^https?:\/\/[^/]+/, "").split("?")[0];
    if (path === "/api/v1/auth/me") return ok(makeUser({ role: "STUDENT" }));
    if (method === "GET" && path === `/api/v1/researchers/${PROFILE_ID}`) return ok({ id: PROFILE_ID, user_id: USER_ID, display_name: "Ada Lovelace" });
    if (method === "GET" && path === `/api/v1/researchers/${PROFILE_ID}/preferences/structured`) {
      return ok({
        profile_id: PROFILE_ID, user_id: USER_ID, raw_preferences: items,
        funding: { funding_required: false, min_funding_amount: null, currency: "USD" }, academic: { academic_level: null, career_stage: null },
        summary: { total_preferences: items.length, explicit_count: items.length, inferred_count: 0, derived_count: 0, has_conflicts: false, confidence_level: "LOW", completeness_percentage: 20 },
        completeness: { score: 0.2, percentage: 20, is_complete: false, missing_dimensions: [], dimension_breakdown: {} },
      });
    }
    const removed = new RegExp(`^/api/v1/researchers/${PROFILE_ID}/preferences/([^/]+)$`).exec(path);
    if (method === "DELETE" && removed) {
      items = items.filter((item) => item.id !== removed[1]);
      return Promise.resolve(new Response(null, { status: 204 }));
    }
    return Promise.resolve(jsonResponse({ detail: `unexpected ${method} ${path}` }, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
}

describe("research preferences", () => {
  it("names every select, and cycles a type or removes a topic or keyword with a named button, by keyboard", async () => {
    servePreferences([preference("a1", "TOPIC", "Information retrieval"), preference("b2", "KEYWORD", "ranking")]);
    window.history.replaceState(null, "", "/researcher/preferences");
    render(
      <SessionProvider>
        <ResearcherPreferencesPage />
      </SessionProvider>
    );

    const removeTopic = await screen.findByRole("button", { name: "Remove Information retrieval" });
    for (const select of screen.getAllByRole("combobox")) expect(select).toHaveAccessibleName();
    expect(screen.getByRole("combobox", { name: "Academic Level:" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Career Stage:" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Prefer or exclude this topic" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove ranking" })).toHaveAttribute("type", "button");
    // The three-state rows (neutral, preferred, excluded) are buttons that say their state.
    expect(screen.getByRole("button", { name: "Conference Neutral" })).toHaveAttribute("type", "button");
    expect(screen.getByRole("button", { name: "Hybrid Neutral" })).toHaveAttribute("type", "button");

    // A native button: Enter and Space work without a handler of their own.
    expect(removeTopic.tagName).toBe("BUTTON");
    fireEvent.click(removeTopic);
    await waitFor(() => expect(screen.queryByRole("button", { name: "Remove Information retrieval" })).not.toBeInTheDocument());
    // The page stays (no spinner in its place) and focus goes to the field beside the list.
    await waitFor(() => expect(screen.getByRole("textbox", { name: "Topic" })).toHaveFocus());
    expect(fetchMock.mock.calls.filter(([, init]) => (init as RequestInit | undefined)?.method === "DELETE").map(([url]) => String(url).split("?")[0].split("/").pop())).toEqual(["a1"]);
  });
});

// ── A workspace item's status menu ─────────────────────────────────────────────

describe("a workspace status move by keyboard", () => {
  it("keeps focus on the status while the move saves and hands it to the new menu button", async () => {
    let finish: () => void = () => undefined;
    function Row() {
      const [item, setItem] = useState(makeItem({ status: "SAVED", allowed_transitions: TRANSITIONS.SAVED }));
      const [saving, setSaving] = useState(false);
      const move = (target: WorkspaceStatus) => {
        setSaving(true);
        setItem((current) => ({ ...current, status: target, allowed_transitions: TRANSITIONS[target] }));
        finish = () => setSaving(false);
      };
      return <StatusMenu item={item} saving={saving} onChange={move} />;
    }
    render(<Row />);

    const trigger = screen.getByRole("button", { name: "Status: Saved. Change status" });
    trigger.focus();
    fireEvent.click(trigger);
    fireEvent.click(await screen.findByRole("menuitem", { name: "Move to planning" }));
    await waitFor(() => expect(screen.getByText("Saving…").parentElement).toHaveFocus());

    act(() => finish());
    await waitFor(() => expect(screen.getByRole("button", { name: "Status: Planning. Change status" })).toHaveFocus());
  });

  it("leaves focus alone when it has moved elsewhere in the meantime", async () => {
    let finish: () => void = () => undefined;
    function Row() {
      const [saving, setSaving] = useState(false);
      return (
        <>
          <StatusMenu item={makeItem({ status: "SAVED", allowed_transitions: TRANSITIONS.SAVED })} saving={saving} onChange={() => { setSaving(true); finish = () => setSaving(false); }} />
          <button type="button">Elsewhere</button>
        </>
      );
    }
    render(<Row />);
    fireEvent.click(screen.getByRole("button", { name: "Status: Saved. Change status" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "Move to considering" }));
    screen.getByRole("button", { name: "Elsewhere" }).focus();
    act(() => finish());
    await waitFor(() => expect(screen.getByRole("button", { name: "Status: Saved. Change status" })).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Elsewhere" })).toHaveFocus();
  });
});
