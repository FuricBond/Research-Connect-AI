/**
 * P9 — the faculty experience (FRONTEND_REDESIGN_PLAN.md §14): My postings, the posting editor, the
 * applicant inbox and the review decisions, against API answers shaped like the backend's.
 *
 *  - Decisions follow the review pipeline (Mark under review → Shortlist → Make offer) with
 *    "Not selected" last, whatever order the server lists them in; only the server's moves show.
 *  - "Not selected" and "Cancel posting" ask first: dismissing sends nothing, confirming sends
 *    exactly one request, a refusal leaves the server's state and says so.
 *  - The inbox reads the author's postings and the applications of at most the ten most recently
 *    published open postings that have applications; each application stays under its posting.
 *  - The editor checks the backend's rules before sending, sends once, keeps what was entered on
 *    failure, and an edit sends only the changed fields.
 *  - The faculty pages are refused to other roles before anything is requested.
 */

import React from "react";
import { act, fireEvent, render, renderHook, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

const push = vi.fn();
let params: { id?: string } = {};
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push, back: vi.fn(), forward: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => window.location.pathname,
  useSearchParams: () => new URLSearchParams(window.location.search),
  useParams: () => params,
}));

import ApplicantsPage from "../app/postings/applicants/page";
import EditPostingPage from "../app/postings/[id]/edit/page";
import PostingDetailPage from "../app/postings/[id]/page";
import NewPostingPage from "../app/postings/new/page";
import PostingsRoute from "../app/postings/page";
import { SessionProvider } from "../components/auth/SessionProvider";
import { createPayload, EMPTY_FORM, fromPosting, updatePayload, validate } from "../components/postings/postingForm";
import { useApplicationDecisions } from "../components/postings/useApplicationDecisions";
import { clearActiveIdentity, storeSession } from "../services/auth";
import type { PlatformRole } from "../types/auth";
import type { ApplicationStatus, PostingApplication, ResearchPosting } from "../types/posting";
import { decisionsFor, inboxPostings, INBOX_POSTINGS, postingActionsFor } from "../utils/postings";
import { jsonResponse, makeTokenResponse, makeUser } from "./factories";
import { AUTHOR_MOVES, POSTING_MOVES, applicationsOf, deferred, listOf, makeApplication, makePosting, ok, postingId, refuse, summaryOf } from "./p9-fixtures";
import { installDialogPolyfill } from "./shell-support";

type Handler = (url: string, init: RequestInit) => Promise<Response> | undefined;

let fetchMock: ReturnType<typeof vi.fn>;
let mine: ResearchPosting[];
let applications: Record<string, PostingApplication[]>;
let extra: Handler;

function serve(role: PlatformRole = "FACULTY") {
  storeSession(makeTokenResponse({ user: makeUser({ role }) }));
  fetchMock = vi.fn((url: string, init: RequestInit = {}) => {
    const method = init.method ?? "GET";
    const path = url.replace(/^https?:\/\/[^/]+/, "");
    if (path === "/api/v1/auth/me") return ok(makeUser({ role }));
    const handled = extra(path, init);
    if (handled) return handled;
    if (method === "GET" && path === "/api/v1/postings/mine/summary") return ok(summaryOf(mine));
    if (method === "GET" && path.startsWith("/api/v1/postings/mine?")) {
      const query = new URLSearchParams(path.split("?")[1]);
      const status = query.get("status");
      return ok(listOf(mine.filter((posting) => !status || posting.status === status)));
    }
    const listing = /^\/api\/v1\/postings\/([^/?]+)\/applications\?/.exec(path);
    if (method === "GET" && listing) return ok(applicationsOf(applications[listing[1]] ?? []));
    const one = /^\/api\/v1\/postings\/([^/?]+)$/.exec(path);
    if (method === "GET" && one) {
      const found = mine.find((posting) => posting.id === one[1]);
      return found ? ok(found) : refuse(404, "Research posting not found.");
    }
    return Promise.resolve(jsonResponse({ detail: `unexpected ${method} ${path}` }, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
}

const calls = (method: string, part: string | RegExp) =>
  fetchMock.mock.calls.filter(([url, init]) => ((init as RequestInit | undefined)?.method ?? "GET") === method && (typeof part === "string" ? String(url).includes(part) : part.test(String(url))));
const bodyOf = (call: unknown[]) => JSON.parse(String((call[1] as RequestInit).body));

function renderPage(page: React.ReactElement, address: string) {
  window.history.replaceState(null, "", address);
  return render(<SessionProvider>{page}</SessionProvider>);
}

beforeAll(installDialogPolyfill);

beforeEach(() => {
  push.mockReset();
  params = {};
  extra = () => undefined;
  mine = [];
  applications = {};
});

afterEach(() => {
  clearActiveIdentity();
  vi.unstubAllGlobals();
});

// ── Decision order and available moves ────────────────────────────────────────

describe("decision order", () => {
  const labels = (status: ApplicationStatus) => decisionsFor({ allowed_transitions: AUTHOR_MOVES[status], is_posting_author: true }).map((d) => `${d.label}${d.variant === "primary" ? "*" : ""}${d.confirm ? "?" : ""}`);

  it("follows the review pipeline with Not selected last, whatever order the server sends", () => {
    // The server sorts by enum name: REJECTED, SHORTLISTED, UNDER_REVIEW for a new application.
    expect(labels("SUBMITTED")).toEqual(["Mark under review", "Shortlist*", "Not selected?"]);
    expect(labels("UNDER_REVIEW")).toEqual(["Shortlist*", "Make offer", "Not selected?"]);
    expect(labels("SHORTLISTED")).toEqual(["Make offer*", "Not selected?"]);
    expect(labels("OFFERED")).toEqual(["Not selected?"]);
  });

  it("offers nothing once the process has ended, and nothing to anyone but the author", () => {
    for (const status of ["ACCEPTED", "DECLINED", "REJECTED", "WITHDRAWN"] as const) expect(labels(status)).toEqual([]);
    expect(decisionsFor({ allowed_transitions: ["WITHDRAWN"], is_posting_author: false })).toEqual([]);
  });

  it("orders a posting's lifecycle actions with Cancel posting last, asked first", () => {
    const actions = (status: keyof typeof POSTING_MOVES, published = true) =>
      postingActionsFor({ allowed_transitions: POSTING_MOVES[status], is_owner: true, status, published_at: published ? "2026-09-01T00:00:00Z" : null }).map((a) => `${a.label}${a.confirm ? "?" : ""}`);
    expect(actions("DRAFT", false)).toEqual(["Publish", "Archive", "Cancel posting?"]);
    expect(actions("OPEN")).toEqual(["Close", "Mark filled", "Return to draft", "Cancel posting?"]);
    expect(actions("CLOSED")).toEqual(["Reopen", "Mark filled", "Archive"]);
    expect(actions("CANCELLED")).toEqual(["Archive"]);
    expect(actions("ARCHIVED")).toEqual([]);
    expect(postingActionsFor({ allowed_transitions: POSTING_MOVES.OPEN, is_owner: false, status: "OPEN", published_at: null })).toEqual([]);
  });
});

// ── The inbox's aggregation ───────────────────────────────────────────────────

describe("the applicant inbox", () => {
  it("chooses the ten most recently published open postings with applications, and names the rest", () => {
    const open = Array.from({ length: 12 }, (_, i) => makePosting(i + 1, { application_count: 1 }));
    const empty = makePosting(20, { application_count: 0 });
    const closed = makePosting(21, { status: "CLOSED", application_count: 3 });
    const notMine = makePosting(22, { is_owner: false, application_count: 4 });
    const chosen = inboxPostings([...open, empty, closed, notMine]);
    expect(chosen.read.map((p) => p.title)).toEqual(["Posting 12", "Posting 11", "Posting 10", "Posting 9", "Posting 8", "Posting 7", "Posting 6", "Posting 5", "Posting 4", "Posting 3"]);
    expect(chosen.read).toHaveLength(INBOX_POSTINGS);
    expect(chosen.later.map((p) => p.title)).toEqual(["Posting 2", "Posting 1"]);
    expect(chosen.closed.map((p) => p.title)).toEqual(["Posting 21"]);
  });

  it("makes one request for the postings and one per chosen posting, all within the cap", async () => {
    mine = [...Array.from({ length: 12 }, (_, i) => makePosting(i + 1, { application_count: 1 })), makePosting(20, { application_count: 0 }), makePosting(21, { status: "CLOSED", application_count: 2 })];
    for (const posting of mine) applications[posting.id] = posting.application_count ? [makeApplication(Number(posting.title.split(" ")[1]), posting)] : [];
    serve();
    renderPage(<ApplicantsPage />, "/postings/applicants");

    expect(await screen.findByRole("heading", { level: 2, name: "Posting 12" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByRole("article")).toHaveLength(10));
    expect(calls("GET", "/api/v1/postings/mine?")).toHaveLength(1);
    const listed = calls("GET", /\/applications\?limit=200$/).map(([url]) => String(url).split("/postings/")[1].split("/")[0]);
    expect(listed.sort()).toEqual(Array.from({ length: 10 }, (_, i) => postingId(i + 3)).sort());
    // The two older open postings and the closed one are linked, not silently dropped.
    const elsewhere = screen.getByRole("complementary", { name: "Applications not shown here" });
    expect(within(elsewhere).getAllByRole("link").map((link) => link.textContent)).toEqual(["Posting 2", "Posting 1", "Posting 21"]);
  });

  it("keeps each application under the posting it was made to, once, even for one person applying twice", async () => {
    const first = makePosting(1, { application_count: 1 });
    const second = makePosting(2, { application_count: 1 });
    mine = [first, second];
    const same = { profile_id: "7c000000-0000-4000-8000-00000000000a", full_name: "Grace Hopper", institution: "Fairview University", department: null, academic_status: "PHD" };
    applications[first.id] = [makeApplication(1, first, { applicant: same })];
    applications[second.id] = [makeApplication(2, second, { applicant: same, status: "SHORTLISTED" })];
    serve();
    renderPage(<ApplicantsPage />, "/postings/applicants");

    const groupOne = (await screen.findByRole("heading", { level: 2, name: "Posting 1" })).closest("section") as HTMLElement;
    const groupTwo = screen.getByRole("heading", { level: 2, name: "Posting 2" }).closest("section") as HTMLElement;
    await waitFor(() => expect(within(groupOne).getAllByRole("article")).toHaveLength(1));
    expect(within(groupOne).getByRole("article", { name: "Grace Hopper" })).toHaveTextContent("Submitted");
    expect(within(groupTwo).getAllByRole("article")).toHaveLength(1);
    expect(within(groupTwo).getByRole("article", { name: "Grace Hopper" })).toHaveTextContent("Shortlisted");
  });

  it("filters by status and by posting in the address, with counts from the answers", async () => {
    const posting = makePosting(1, { application_count: 2 });
    const other = makePosting(2, { application_count: 1 });
    mine = [posting, other];
    applications[posting.id] = [makeApplication(1, posting), makeApplication(2, posting, { status: "SHORTLISTED" })];
    applications[other.id] = [makeApplication(3, other)];
    serve();
    renderPage(<ApplicantsPage />, `/postings/applicants?status=SUBMITTED&posting=${posting.id}`);

    const chips = await screen.findByRole("group", { name: "Filter by status" });
    await waitFor(() => expect(within(chips).getByRole("button", { name: "All (2)" })).toBeInTheDocument());
    expect(within(chips).getByRole("button", { name: "Submitted (1)" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getAllByRole("article").map((a) => a.getAttribute("aria-labelledby") && a.querySelector("h3")?.textContent)).toEqual(["Applicant 1"]);
    expect(screen.queryByRole("heading", { level: 2, name: "Posting 2" })).not.toBeInTheDocument();
  });

  it("shows the pipeline's decisions on each card, and what happens next when there is nothing to decide", async () => {
    const posting = makePosting(1, { application_count: 3 });
    mine = [posting];
    applications[posting.id] = [makeApplication(1, posting, { status: "UNDER_REVIEW" }), makeApplication(2, posting, { status: "OFFERED" }), makeApplication(3, posting, { status: "ACCEPTED" })];
    serve();
    renderPage(<ApplicantsPage />, "/postings/applicants");

    const reviewing = await screen.findByRole("article", { name: "Applicant 1" });
    expect(within(within(reviewing).getByRole("group", { name: "Decisions on Applicant 1" })).getAllByRole("button").map((b) => b.textContent)).toEqual(["Shortlist", "Make offer", "Not selected"]);
    const offered = screen.getByRole("article", { name: "Applicant 2" });
    expect(within(offered).getAllByRole("button").map((b) => b.textContent)).toEqual(["Not selected"]);
    expect(offered).toHaveTextContent("Waiting for the applicant to accept or decline your offer.");
    const accepted = screen.getByRole("article", { name: "Applicant 3" });
    expect(within(accepted).queryByRole("group", { name: /Decisions/ })).not.toBeInTheDocument();
    expect(accepted).toHaveTextContent("The applicant accepted your offer.");
  });

  it("shows nothing for the inbox without asking for applications when no posting has any", async () => {
    mine = [makePosting(1, { application_count: 0 }), makePosting(2, { status: "DRAFT" })];
    serve();
    renderPage(<ApplicantsPage />, "/postings/applicants");

    expect(await screen.findByText("No applications yet.")).toBeInTheDocument();
    expect(calls("GET", "/applications?")).toHaveLength(0);
  });

  it("says when the postings could not be loaded, and tries again", async () => {
    let fail = true;
    extra = (path) => (path.startsWith("/api/v1/postings/mine?") && fail ? refuse(500) : undefined);
    serve();
    renderPage(<ApplicantsPage />, "/postings/applicants");

    const retry = await screen.findByRole("button", { name: "Try again" });
    fail = false;
    fireEvent.click(retry);
    await waitFor(() => expect(calls("GET", "/api/v1/postings/mine?")).toHaveLength(2));
    expect(await screen.findByText("No applications yet.")).toBeInTheDocument();
  });
});

// ── Decisions: confirmation, single requests, failures, stale answers ─────────

describe("decisions", () => {
  let posting: ResearchPosting;
  beforeEach(() => {
    posting = makePosting(1, { application_count: 1 });
    mine = [posting];
    applications[posting.id] = [makeApplication(1, posting)];
  });

  async function card() {
    return screen.findByRole("article", { name: "Applicant 1" });
  }

  it("asks before Not selected: Cancel and Escape send nothing", async () => {
    serve();
    renderPage(<ApplicantsPage />, "/postings/applicants");
    const article = await card();

    fireEvent.click(within(article).getByRole("button", { name: "Not selected" }));
    let dialog = await screen.findByRole("dialog", { name: "Mark Applicant 1 as not selected for “Posting 1”?" });
    expect(dialog).toHaveTextContent("cannot be reopened");
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    fireEvent.click(within(article).getByRole("button", { name: "Not selected" }));
    dialog = await screen.findByRole("dialog");
    fireEvent(dialog, new Event("cancel", { cancelable: true })); // Escape
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    expect(calls("POST", "/transition")).toHaveLength(0);
    expect(article).toHaveTextContent("Submitted");
  });

  it("confirming sends exactly one Not selected, with the message, even when clicked twice", async () => {
    const answer = deferred();
    extra = (path, init) => (init.method === "POST" && path.endsWith("/transition") ? answer.promise : undefined);
    serve();
    renderPage(<ApplicantsPage />, "/postings/applicants");
    const article = await card();

    fireEvent.click(within(article).getByRole("button", { name: "Not selected" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText(/Message to the applicant/), { target: { value: "Thank you for applying." } });
    const confirm = within(dialog).getByRole("button", { name: "Mark not selected" });
    fireEvent.click(confirm);
    fireEvent.click(confirm);
    expect(calls("POST", "/transition")).toHaveLength(1);
    expect(bodyOf(calls("POST", "/transition")[0])).toEqual({ target_status: "REJECTED", decision_reason: "Thank you for applying.", reviewer_note: null });

    await act(async () => answer.resolve(jsonResponse(makeApplication(1, posting, { status: "REJECTED", decision_reason: "Thank you for applying.", updated_at: "2026-10-05T09:00:00+00:00" }))));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(article).toHaveTextContent("Not selected");
    expect(article).toHaveTextContent("Message to the applicant: Thank you for applying.");
    expect(within(article).queryByRole("group", { name: /Decisions/ })).not.toBeInTheDocument();
    await waitFor(() => expect(within(article).getByRole("heading", { name: "Applicant 1" })).toHaveFocus());
    expect(calls("POST", "/transition")).toHaveLength(1);
  });

  it("a decision waits for the server: one request, the actions disabled meanwhile, then the server's state", async () => {
    const answer = deferred();
    extra = (path, init) => (init.method === "POST" && path.endsWith("/transition") ? answer.promise : undefined);
    serve();
    renderPage(<ApplicantsPage />, "/postings/applicants");
    const article = await card();

    fireEvent.click(within(article).getByRole("button", { name: "Shortlist" }));
    fireEvent.click(within(article).getByRole("button", { name: "Shortlist" }));
    expect(calls("POST", "/transition")).toHaveLength(1);
    expect(bodyOf(calls("POST", "/transition")[0]).target_status).toBe("SHORTLISTED");
    expect(within(article).getByRole("button", { name: "Mark under review" })).toBeDisabled();
    expect(article).toHaveTextContent("Submitted"); // nothing claimed before the server agrees

    await act(async () => answer.resolve(jsonResponse(makeApplication(1, posting, { status: "SHORTLISTED", updated_at: "2026-10-05T09:00:00+00:00" }))));
    await waitFor(() => expect(article).toHaveTextContent("Shortlisted"));
    expect(within(article).getAllByRole("button").filter((b) => b.closest('[role="group"]')).map((b) => b.textContent)).toEqual(["Make offer", "Not selected"]);
    // The button used is gone with the new status: focus is not lost but moves to the applicant's name.
    await waitFor(() => expect(within(article).getByRole("heading", { name: "Applicant 1" })).toHaveFocus());
  });

  it("a refused decision leaves the application as the server last confirmed it, and says so", async () => {
    extra = (path, init) => (init.method === "POST" && path.endsWith("/transition") ? refuse(400, "As author you cannot move an application from SUBMITTED to SHORTLISTED") : undefined);
    serve();
    renderPage(<ApplicantsPage />, "/postings/applicants");
    const article = await card();

    fireEvent.click(within(article).getByRole("button", { name: "Shortlist" }));
    const alert = await within(article).findByRole("alert");
    expect(alert).toHaveTextContent("Applicant 1 could not be shortlisted.");
    expect(alert).toHaveTextContent("It is still submitted.");
    expect(alert).not.toHaveTextContent("SUBMITTED"); // the server's enum words are never shown
    expect(article).toHaveTextContent("Submitted");
    expect(within(article).getByRole("button", { name: "Shortlist" })).toBeEnabled();
  });

  it("a refused Not selected keeps the dialog open with the reason", async () => {
    extra = (path, init) => (init.method === "POST" && path.endsWith("/transition") ? refuse(500) : undefined);
    serve();
    renderPage(<ApplicantsPage />, "/postings/applicants");
    const article = await card();

    fireEvent.click(within(article).getByRole("button", { name: "Not selected" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Mark not selected" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Applicant 1 could not be marked not selected. Try again.");
    expect(article).toHaveTextContent("Submitted");
  });

  it("never lets an older answer overwrite a newer one", async () => {
    serve();
    const listed = makeApplication(1, posting, { updated_at: "2026-10-02T09:00:00+00:00" });
    const { result } = renderHook(() => useApplicationDecisions(), { wrapper: ({ children }) => <SessionProvider>{children}</SessionProvider> });
    const answer = deferred();
    extra = (path, init) => (init.method === "POST" && path.endsWith("/transition") ? answer.promise : undefined);

    let first!: Promise<boolean>;
    act(() => {
      first = result.current.decide(listed, "SHORTLISTED");
    });
    // A second decision on the same application while the first is being sent is not sent.
    let second!: boolean;
    await act(async () => {
      second = await result.current.decide(listed, "UNDER_REVIEW");
    });
    expect(second).toBe(false);
    expect(calls("POST", "/transition")).toHaveLength(1);

    await act(async () => {
      answer.resolve(jsonResponse(makeApplication(1, posting, { status: "SHORTLISTED", updated_at: "2026-10-05T09:00:00+00:00" })));
      await first;
    });
    // A reload that answers with the older state does not bring it back…
    expect(result.current.current(listed).status).toBe("SHORTLISTED");
    // …and a newer state from the server (decided elsewhere) wins over the decision's answer.
    expect(result.current.current(makeApplication(1, posting, { status: "OFFERED", updated_at: "2026-10-06T09:00:00+00:00" })).status).toBe("OFFERED");
  });
});

// ── My postings ───────────────────────────────────────────────────────────────

describe("My postings", () => {
  beforeEach(() => {
    mine = [
      makePosting(1, { title: "RA: benchmark curation", application_count: 3 }),
      makePosting(2, { title: "Thesis: neural ranking", status: "DRAFT", posting_type: "THESIS_TOPIC", opening_terms: { ...makePosting(2).opening_terms, accepts_applications: false, is_structured_opening: false } }),
      makePosting(3, { title: "Old internship", status: "ARCHIVED", application_count: 4 }),
    ];
    applications[mine[0].id] = [makeApplication(1, mine[0]), makeApplication(2, mine[0]), makeApplication(3, mine[0], { status: "SHORTLISTED" })];
  });

  const row = async (title: string) => (await screen.findByRole("link", { name: title })).closest("tr") as HTMLElement;

  it("lists every posting with its status, applicants, new applications and its own actions", async () => {
    serve();
    renderPage(<PostingsRoute />, "/postings?view=mine");

    expect(await screen.findByRole("heading", { level: 1, name: "My postings" })).toBeInTheDocument();
    const table = screen.getByRole("table", { name: "Your postings" });
    expect(within(table).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Posting", "Status", "Applicants", "New", "Deadline", "Actions"]);
    const open = await row("RA: benchmark curation");
    expect(open).toHaveTextContent("Open");
    await waitFor(() => expect(within(open).getAllByRole("cell")[3]).toHaveTextContent("2"));
    expect(within(open).getByRole("link", { name: "3 applicants to RA: benchmark curation" })).toHaveAttribute("href", `/postings/applicants?posting=${mine[0].id}`);
    fireEvent.click(within(open).getByRole("button", { name: "Actions for RA: benchmark curation" }));
    expect(screen.getAllByRole("menuitem").map((item) => item.textContent)).toEqual(["Close", "Mark filled", "Return to draft", "Cancel posting"]);
    fireEvent.keyDown(screen.getByRole("menu"), { key: "Escape" });

    const draft = await row("Thesis: neural ranking");
    expect(within(draft).getByRole("link", { name: "Edit" })).toHaveAttribute("href", `/postings/${mine[1].id}/edit`);
    fireEvent.click(within(draft).getByRole("button", { name: "Actions for Thesis: neural ranking" }));
    expect(screen.getAllByRole("menuitem").map((item) => item.textContent)).toEqual(["Publish", "Archive", "Cancel posting", "Delete draft"]);
    fireEvent.keyDown(screen.getByRole("menu"), { key: "Escape" });

    // An archived posting can no longer be edited (backend update_posting); a closed one's new applications are not counted.
    const archived = await row("Old internship");
    expect(within(archived).queryByRole("link", { name: "Edit" })).not.toBeInTheDocument();
    expect(within(archived).getAllByRole("cell")[3]).toHaveTextContent("—Not counted");
    // Only the open posting with applications was asked about.
    expect(calls("GET", "/applications?").map(([url]) => String(url))).toEqual([expect.stringContaining(mine[0].id)]);
  });

  it("filters by status with the server's counts, in the address", async () => {
    serve();
    renderPage(<PostingsRoute />, "/postings?view=mine");
    const chips = await screen.findByRole("group", { name: "Filter by status" });
    await waitFor(() => expect(within(chips).getByRole("button", { name: "All (3)" })).toBeInTheDocument());
    fireEvent.click(within(chips).getByRole("button", { name: "Draft (1)" }));
    expect(window.location.search).toBe("?view=mine&status=DRAFT");
    await waitFor(() => expect(screen.queryByRole("link", { name: "RA: benchmark curation" })).not.toBeInTheDocument());
    expect(await screen.findByRole("link", { name: "Thesis: neural ranking" })).toBeInTheDocument();
    expect(calls("GET", "/postings/mine?").map(([url]) => String(url).split("?")[1])).toEqual(["limit=25", "status=DRAFT&limit=25"]);
  });

  it("asks before Cancel posting: Cancel sends nothing, Confirm sends one request", async () => {
    let target: string | null = null;
    extra = (path, init) => {
      if (init.method === "POST" && path.endsWith("/transition")) {
        target = JSON.parse(String(init.body)).target_status;
        return ok({ ...mine[0], status: "CANCELLED", allowed_transitions: POSTING_MOVES.CANCELLED, updated_at: "2026-10-05T10:00:00+00:00" });
      }
      return undefined;
    };
    serve();
    renderPage(<PostingsRoute />, "/postings?view=mine");
    const open = await row("RA: benchmark curation");

    fireEvent.click(within(open).getByRole("button", { name: "Actions for RA: benchmark curation" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Cancel posting" }));
    let dialog = await screen.findByRole("dialog", { name: "Cancel “RA: benchmark curation”?" });
    expect(dialog).toHaveTextContent("cannot be published or reopened again");
    expect(dialog).toHaveTextContent("The applications it received are kept");
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(calls("POST", "/transition")).toHaveLength(0);
    expect(open).toHaveTextContent("Open");

    fireEvent.click(within(open).getByRole("button", { name: "Actions for RA: benchmark curation" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Cancel posting" }));
    dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel posting" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(calls("POST", "/transition")).toHaveLength(1);
    expect(target).toBe("CANCELLED");
    expect(open).toHaveTextContent("Cancelled");
    // The counts are asked for again after a confirmed change.
    await waitFor(() => expect(calls("GET", "/postings/mine/summary")).toHaveLength(2));
  });

  it("a refused change says so and leaves the posting as it was", async () => {
    extra = (path, init) => (init.method === "POST" && path.endsWith("/transition") ? refuse(400, "Cannot move a posting from OPEN to CLOSED.") : undefined);
    serve();
    renderPage(<PostingsRoute />, "/postings?view=mine");
    const open = await row("RA: benchmark curation");

    fireEvent.click(within(open).getByRole("button", { name: "Actions for RA: benchmark curation" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Close" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("“RA: benchmark curation” could not be changed.");
    expect(alert).toHaveTextContent("It is still open.");
    expect(alert).not.toHaveTextContent("OPEN to CLOSED");
    expect(open).toHaveTextContent("Open");
  });

  it("asks before deleting a draft", async () => {
    extra = (path, init) => (init.method === "DELETE" ? Promise.resolve(new Response(null, { status: 204 })) : undefined);
    serve();
    renderPage(<PostingsRoute />, "/postings?view=mine");
    const draft = await row("Thesis: neural ranking");

    fireEvent.click(within(draft).getByRole("button", { name: "Actions for Thesis: neural ranking" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Delete draft" }));
    const dialog = await screen.findByRole("dialog", { name: "Delete the draft “Thesis: neural ranking”?" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Delete draft" }));
    await waitFor(() => expect(screen.queryByRole("link", { name: "Thesis: neural ranking" })).not.toBeInTheDocument());
    expect(calls("DELETE", `/postings/${mine[1].id}`)).toHaveLength(1);
  });
});

// ── The editor ────────────────────────────────────────────────────────────────

describe("the posting editor", () => {
  it("knows the backend's rules", () => {
    const now = new Date("2026-10-18T12:00:00Z");
    expect(Object.keys(validate(EMPTY_FORM, null, now)).sort()).toEqual(["description", "title"]);
    const filled = { ...EMPTY_FORM, title: "RA in retrieval", description: "Build retrieval benchmarks with us.", country: "USA", contact_email: "not-an-email", external_url: "javascript:alert(1)", deadline: "2026-10-18", positions: "0", start: "2026-12-01", end: "2026-11-01" };
    expect(validate(filled, null, now)).toEqual({
      country: "Use a two-letter country code, such as US.",
      contact_email: "Enter an email address, such as name@university.edu.",
      external_url: "Enter a web address that starts with https://.",
      deadline: "Choose a day after today.",
      positions: "Give a whole number from 1 to 100.",
      end: "The end cannot be before the start.",
    });
  });

  it("sends only the fields that changed, and terms only for funded openings", () => {
    const posting = makePosting(1, { summary: "Old summary" });
    const initial = fromPosting(posting);
    expect(updatePayload(initial, initial)).toEqual({});
    expect(updatePayload({ ...initial, title: "A new title", summary: "" }, initial)).toEqual({ title: "A new title", summary: null });
    expect(updatePayload({ ...initial, hours: "10" }, initial)).toEqual({ opening_terms: { hours_per_week: 10 } });
    // A supervisor-led category takes no applications here: the change says so to the backend.
    expect(updatePayload({ ...initial, posting_type: "PROJECT" }, initial)).toEqual({ posting_type: "PROJECT", opening_terms: { accepts_applications: false } });
    // Reordering spaces in the skills is not a change.
    expect(updatePayload({ ...initial, skills: " Python " }, initial)).toEqual({});
    const project = createPayload({ ...EMPTY_FORM, title: "A project", description: "A supervisor-led research project." });
    expect(project.opening_terms).toBeUndefined();
    expect("institution" in project).toBe(false); // blank: the author's own is used
  });

  it("explains what to fix before sending anything, and moves focus to the first field", async () => {
    serve();
    renderPage(<NewPostingPage />, "/postings/new");

    fireEvent.click(await screen.findByRole("button", { name: "Save draft" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Check these 2 fields before saving:");
    expect(alert).toHaveTextContent("Title: Give a title of 5 to 300 characters.");
    await waitFor(() => expect(screen.getByLabelText(/^Title/)).toHaveFocus());
    expect(screen.getByLabelText(/^Title/)).toHaveAttribute("aria-invalid", "true");
    expect(calls("POST", "/api/v1/postings")).toHaveLength(0);
  });

  it("saves a draft once, keeps everything on failure, then opens the posting", async () => {
    let attempt = 0;
    extra = (path, init) => {
      if (init.method === "POST" && path === "/api/v1/postings") {
        attempt += 1;
        return attempt === 1 ? refuse(500) : Promise.resolve(jsonResponse(makePosting(7, { status: "DRAFT" }), 201));
      }
      return undefined;
    };
    serve();
    renderPage(<NewPostingPage />, "/postings/new");

    fireEvent.change(await screen.findByLabelText(/^Title/), { target: { value: "Research assistantship in retrieval" } });
    fireEvent.change(screen.getByLabelText(/^Category/), { target: { value: "RESEARCH_ASSISTANTSHIP" } });
    fireEvent.change(screen.getByRole("textbox", { name: /^Description/ }), { target: { value: "Build and maintain retrieval benchmarks." } });
    fireEvent.change(screen.getByLabelText(/^Required skills/), { target: { value: "Python, PyTorch, python" } });
    fireEvent.change(screen.getByLabelText(/^Hours per week/), { target: { value: "20" } });
    // The preview shows the posting as researchers will see it.
    expect(screen.getByRole("complementary", { name: "Preview" })).toHaveTextContent("Research assistantship in retrieval");

    const save = screen.getByRole("button", { name: "Save draft" });
    fireEvent.click(save);
    expect(await screen.findByRole("alert")).toHaveTextContent("The posting could not be saved. Nothing you entered was lost. Try again.");
    expect(screen.getByLabelText(/^Title/)).toHaveValue("Research assistantship in retrieval");
    expect(push).not.toHaveBeenCalled();

    fireEvent.click(save);
    fireEvent.click(save);
    await waitFor(() => expect(push).toHaveBeenCalledWith(`/postings/${postingId(7)}`));
    const posts = calls("POST", /\/api\/v1\/postings$/);
    expect(posts).toHaveLength(2); // the failed one and one more, not three
    const sent = bodyOf(posts[1]);
    expect(sent).toMatchObject({ title: "Research assistantship in retrieval", posting_type: "RESEARCH_ASSISTANTSHIP", required_skills: ["Python", "PyTorch"], positions_available: 1, work_mode: "ONSITE" });
    expect(sent.opening_terms).toMatchObject({ hours_per_week: 20, accepts_applications: false });
  });

  it("an edit sends only what changed, and nothing when nothing did", async () => {
    const posting = makePosting(4, { title: "RA: benchmark curation", summary: "Curate benchmarks." });
    mine = [posting];
    params = { id: posting.id };
    extra = (path, init) => (init.method === "PATCH" ? ok({ ...posting, summary: "Curate retrieval benchmarks." }) : undefined);
    serve();
    renderPage(<EditPostingPage />, `/postings/${posting.id}/edit`);

    const summary = await screen.findByLabelText(/^Summary/);
    expect(summary).toHaveValue("Curate benchmarks.");
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Nothing has changed, so there is nothing to save.")).toBeInTheDocument();
    expect(calls("PATCH", "/postings/")).toHaveLength(0);

    fireEvent.change(summary, { target: { value: "Curate retrieval benchmarks." } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith(`/postings/${posting.id}`));
    expect(calls("PATCH", `/postings/${posting.id}`)).toHaveLength(1);
    expect(bodyOf(calls("PATCH", `/postings/${posting.id}`)[0])).toEqual({ summary: "Curate retrieval benchmarks." });
  });

  it("does not offer the form for someone else's posting or an archived one", async () => {
    const theirs = makePosting(5, { is_owner: false });
    const archived = makePosting(6, { status: "ARCHIVED" });
    mine = [theirs, archived];
    serve();
    params = { id: theirs.id };
    const { unmount } = renderPage(<EditPostingPage />, `/postings/${theirs.id}/edit`);
    expect(await screen.findByRole("heading", { level: 1, name: "Only the posting’s author can edit it." })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save changes" })).not.toBeInTheDocument();
    unmount();

    params = { id: archived.id };
    renderPage(<EditPostingPage />, `/postings/${archived.id}/edit`);
    expect(await screen.findByRole("heading", { level: 1, name: "An archived posting can no longer be edited." })).toBeInTheDocument();
  });
});

// ── A posting's own page, for its author ─────────────────────────────────────

describe("a posting's page for its author", () => {
  it("manages the posting and reviews its applications with the same decisions", async () => {
    const posting = makePosting(1, { application_count: 1 });
    mine = [posting];
    applications[posting.id] = [makeApplication(1, posting)];
    params = { id: posting.id };
    serve();
    renderPage(<PostingDetailPage />, `/postings/${posting.id}`);

    const manage = (await screen.findByRole("heading", { name: "Manage this posting" })).closest("section") as HTMLElement;
    expect(within(within(manage).getByRole("group", { name: "Manage this posting" })).getAllByRole("button").map((b) => b.textContent)).toEqual(["Close", "Mark filled", "Return to draft", "Cancel posting"]);
    expect(within(manage).getByRole("link", { name: "Edit" })).toHaveAttribute("href", `/postings/${posting.id}/edit`);
    fireEvent.click(within(manage).getByRole("button", { name: "Cancel posting" }));
    const dialog = await screen.findByRole("dialog", { name: "Cancel “Posting 1”?" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(calls("POST", "/transition")).toHaveLength(0);

    const article = await screen.findByRole("article", { name: "Applicant 1" });
    expect(within(within(article).getByRole("group", { name: "Decisions on Applicant 1" })).getAllByRole("button").map((b) => b.textContent)).toEqual(["Mark under review", "Shortlist", "Not selected"]);
  });

  it("never makes a web link of an applicant's address that is not one", async () => {
    const posting = makePosting(1, { application_count: 1 });
    mine = [posting];
    applications[posting.id] = [makeApplication(1, posting, { portfolio_url: "javascript:alert(1)" })];
    params = { id: posting.id };
    serve();
    renderPage(<PostingDetailPage />, `/postings/${posting.id}`);

    const article = await screen.findByRole("article", { name: "Applicant 1" });
    expect(within(article).queryByRole("link", { name: /CV or portfolio/ })).not.toBeInTheDocument();
    expect(article).toHaveTextContent("CV or portfolio: javascript:alert(1)");
  });
});

// ── Who may see the faculty pages ─────────────────────────────────────────────

describe("authorization", () => {
  it("refuses the inbox, My postings and the editor to a student before asking for anything", async () => {
    serve("STUDENT");
    const { unmount } = renderPage(<ApplicantsPage />, "/postings/applicants");
    expect(await screen.findByRole("heading", { level: 1, name: "This page is for Faculty or Administrator accounts." })).toBeInTheDocument();
    unmount();
    const second = renderPage(<PostingsRoute />, "/postings?view=mine");
    expect(await screen.findByRole("heading", { level: 1, name: "This page is for Faculty or Administrator accounts." })).toBeInTheDocument();
    second.unmount();
    renderPage(<NewPostingPage />, "/postings/new");
    expect(await screen.findByRole("heading", { level: 1, name: "This page is for Faculty or Administrator accounts." })).toBeInTheDocument();
    expect(calls("GET", "/api/v1/postings/")).toHaveLength(0);
  });

  it("shows a student Discover without the authoring views", async () => {
    extra = (path) => (path.startsWith("/api/v1/postings?") ? ok(listOf([])) : undefined);
    serve("STUDENT");
    renderPage(<PostingsRoute />, "/postings");
    const views = await screen.findByRole("navigation", { name: "Research postings" });
    expect(within(views).getAllByRole("link").map((link) => link.textContent)).toEqual(["Discover", "My applications"]);
    expect(within(views).getByRole("link", { name: "Discover" })).toHaveAttribute("aria-current", "page");
    expect(screen.queryByRole("link", { name: "New posting" })).not.toBeInTheDocument();
  });
});
