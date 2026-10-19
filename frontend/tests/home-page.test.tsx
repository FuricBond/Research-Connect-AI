/**
 * P4 — the signed-in home (`/dashboard`, FRONTEND_REDESIGN_PLAN.md §8).
 *
 * Student modules: Needs attention (calls due ≤ 14 days with status and next step, offers and
 * applications, a profile nudge, the "Get started" checklist for a new account), Upcoming (30
 * days: call deadlines and calendar milestones), Recommended for you, Postings that fit you,
 * Reading progress. Faculty: Needs your decision, Your open postings, Upcoming deadlines,
 * Recommended papers. Each section loads and fails on its own.
 *
 * Requests are counted here, as fetch sees them: at most seven per page load (the dashboard's
 * own; the shell's session check is not one of them), each made once, none for another role.
 * (P0.3's home tests — deadlines in the window, soonest first; the applications line; faculty
 * see postings; administrators reach administration first; a failed section retries — are kept
 * below in their P4 form.)
 */

import React from "react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn(), back: vi.fn(), forward: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/dashboard",
  useSearchParams: () => new URLSearchParams(),
}));

import DashboardPage from "../app/dashboard/page";
import { SessionProvider, useSession } from "../components/auth/SessionProvider";
import { heldApiResources } from "../hooks/useApiResource";
import { clearActiveIdentity, storeSession } from "../services/auth";
import type { PlatformRole } from "../types/auth";
import type { ApplicationStatus, PostingStatus, ResearchPosting } from "../types/posting";
import type { UnifiedResearcherContext } from "../types/research_intelligence";
import type { WorkspaceItem, WorkspaceStatus } from "../types/workspace";
import { upcomingDeadlines } from "../utils/workspace";
import { PROFILE_ID, USER_ID, jsonResponse, makeTokenResponse, makeUser } from "./factories";
import { installDialogPolyfill } from "./shell-support";

const DAY = 86_400_000;
const inDays = (days: number) => new Date(Date.now() + days * DAY).toISOString();

/* ── Fixtures ─────────────────────────────────────────────────────────────── */

function tracked(title: string, days: number | null, status: WorkspaceStatus = "PLANNING"): WorkspaceItem {
  return {
    id: `ws-${title}`,
    user_id: USER_ID,
    opportunity_id: `op-${title}`,
    status,
    priority: "HIGH",
    tags: [],
    notes: null,
    created_at: "2026-09-20T10:00:00+00:00",
    updated_at: "2026-09-21T10:00:00+00:00",
    status_updated_at: "2026-09-21T10:00:00+00:00",
    archived_at: null,
    allowed_transitions: [],
    opportunity: {
      id: `op-${title}`,
      title,
      opportunity_type: "CONFERENCE",
      delivery_mode: "OFFLINE",
      status: "ACTIVE",
      submission_deadline: days === null ? null : inDays(days),
      is_predatory_flag: false,
    },
  };
}

const ITEMS = [
  tracked("Workshop due in three days", 3.4),
  tracked("Conference due next month", 45),
  tracked("Accepted already", 2, "ACCEPTED"),
  tracked("Call with no deadline", null),
  tracked("Symposium due in ten days", 10.2, "APPLIED"),
  tracked("Journal due in three weeks", 21, "CONSIDERING"),
];

const workspace = (items: WorkspaceItem[] = ITEMS) => ({
  items,
  total_count: items.length,
  active_count: items.length,
  archived_count: 0,
  counts_by_status: {},
  counts_by_priority: {},
});

function calendarEvent(id: string, title: string, days: number, extra: Record<string, unknown> = {}) {
  return {
    id,
    calendar_id: "cal-1",
    title,
    event_type: "RESEARCH_MILESTONE",
    start_datetime: inDays(days),
    all_day: true,
    is_canonical_projection: false,
    provenance_metadata: {},
    status: "ACTIVE",
    created_at: "2026-09-20T10:00:00+00:00",
    ...extra,
  };
}

const CALENDAR = {
  calendar: { id: "cal-1", user_id: USER_ID, name: "Research calendar" },
  events: [
    calendarEvent("e1", "Draft the related-work section", 5),
    // The workshop's own deadline, projected into the calendar: listed once, from the workspace.
    calendarEvent("e2", "Workshop due in three days (deadline)", 3.4, { event_type: "OPPORTUNITY_SUBMISSION", opportunity_id: "op-Workshop due in three days", is_canonical_projection: true }),
    calendarEvent("e3", "A cancelled meeting", 2, { status: "CANCELLED" }),
    calendarEvent("e4", "Camera-ready for HCI 2026", 25, { event_type: "CAMERA_READY" }),
  ],
  total_events: 4,
  upcoming_deadlines_count: 1,
  conflict_count: 0,
  extension_count: 0,
};

const CONTEXT: UnifiedResearcherContext = {
  profile_id: PROFILE_ID,
  user_id: USER_ID,
  full_name: "Priya Raghavan",
  academic_status: "POSTGRADUATE",
  identity_status: "SELF_DECLARED_ONLY",
  is_identity_ambiguous: false,
  completeness_score: 0.9,
  is_cold_start: false,
  is_partial_profile: false,
  signals: [],
  active_interests_count: 3,
  explicit_preferences_count: 0,
  inferred_preferences_count: 0,
  saved_opportunities_count: 0,
  active_submissions_count: 0,
  upcoming_tasks_count: 0,
  calendar_events_count: 0,
};

function recommendation(id: string, title: string, score: number, reason: string) {
  return {
    opportunity_id: id,
    title,
    opportunity_type: "CONFERENCE",
    submission_deadline: inDays(40),
    final_score: score,
    base_relevance_score: score,
    personalization_score: 0.2,
    workspace_context: { is_saved: false, has_active_submission: false },
    evidence_tiers: [],
    explanation: { primary_reasons: [reason] },
  };
}

const recommendations = (context: Partial<UnifiedResearcherContext> = {}, items = RECOMMENDED) => ({
  items,
  total_count: items.length,
  researcher_context: { ...CONTEXT, ...context },
  invariants_verified: true,
});

const RECOMMENDED = [
  recommendation("rec-1", "Workshop on Explainable Graph Learning", 0.72, "Matches your interest in graph neural networks."),
  recommendation("rec-2", "Symposium on Trustworthy AI", 0.48, "Close to your keywords: explainability."),
  recommendation("rec-3", "Conference on Information Retrieval", 0.31, "Shares the topic information retrieval."),
];

function posting(id: string, title: string, overrides: Partial<ResearchPosting> = {}): ResearchPosting {
  return {
    id,
    author: { profile_id: "author", full_name: "Dr Okafor", institution: null, department: null, academic_status: null },
    title,
    posting_type: "RESEARCH_ASSISTANT",
    status: "OPEN" as PostingStatus,
    summary: null,
    description: "",
    required_skills: [],
    preferred_qualifications: null,
    institution: null,
    department: null,
    location: null,
    country: null,
    work_mode: "REMOTE",
    positions_available: 1,
    application_deadline: inDays(6),
    expected_start_date: null,
    expected_end_date: null,
    contact_email: null,
    external_url: null,
    topics: [],
    opening_terms: {
      compensation_type: "UNPAID",
      compensation_amount: null,
      compensation_currency: null,
      compensation_period: null,
      commitment_type: null,
      hours_per_week: null,
      duration_months: null,
      eligibility_requirements: null,
      accepts_applications: true,
      is_structured_opening: true,
    },
    application_count: 0,
    published_at: null,
    closed_at: null,
    archived_at: null,
    status_note: null,
    created_at: "2026-09-01T10:00:00+00:00",
    updated_at: "2026-09-01T10:00:00+00:00",
    is_accepting_applications: true,
    days_until_deadline: 6,
    allowed_transitions: [],
    is_owner: false,
    viewer_application_id: null,
    viewer_application_status: null,
    ...overrides,
  } as ResearchPosting;
}

const OPEN_POSTINGS = [
  posting("p1", "RA: retrieval evaluation"),
  posting("p2", "Thesis topic: explainable GNNs"),
  posting("p3", "Internship: data engineering"),
  posting("p4", "Project: robotics lab"),
];

const FITS = {
  fits: [
    { posting_id: "p1", score: 52, band: "Good", reasons: [{ code: "SKILLS", label: "Skills", weight: 0.4, matched: ["python"] }], gaps: [], computed_at: "" },
    { posting_id: "p2", score: 81, band: "Strong", reasons: [{ code: "TOPIC", label: "Topics", weight: 0.6, matched: ["graph neural networks"] }, { code: "SKILLS", label: "Skills", weight: 0.2, matched: [] }], gaps: [], computed_at: "" },
    { posting_id: "p3", score: 12, band: "Low", reasons: [], gaps: [], computed_at: "" },
    { posting_id: "p4", score: null, band: null, reasons: [{ code: "EXCLUDED", label: "Excluded", weight: 0, matched: [] }], gaps: [], computed_at: "" },
  ],
};

const READING = { items: [], total_count: 5, limit: 1, offset: 0, counts_by_status: { TO_READ: 2, READING: 2, DONE: 1 } };

// Faculty: four open postings with applications (one more than the three fetched), a draft and a
// closed one (never fetched).
const MINE = [
  posting("f1", "RA: benchmark curation", { application_count: 5, is_owner: true }),
  posting("f2", "Thesis: neural ranking", { application_count: 3, is_owner: true, application_deadline: inDays(40), days_until_deadline: 40 }),
  posting("f3", "Internship: annotation tools", { application_count: 2, is_owner: true, application_deadline: null, days_until_deadline: null }),
  posting("f4", "Project: query logs", { application_count: 1, is_owner: true }),
  posting("f5", "Draft: summer school", { status: "DRAFT", application_count: 4, is_owner: true }),
  posting("f6", "Closed: last year's RA", { status: "CLOSED", application_count: 2, is_owner: true }),
];

function application(id: string, status: ApplicationStatus) {
  return { id, posting_id: "x", posting_title: null, status, applicant: { profile_id: "a", full_name: "Applicant" }, status_history: [], submitted_at: "", created_at: "", updated_at: "", allowed_transitions: [] };
}

const APPLICATIONS: Record<string, ApplicationStatus[]> = {
  f1: ["SUBMITTED", "SUBMITTED", "UNDER_REVIEW", "SHORTLISTED", "REJECTED"],
  f2: ["UNDER_REVIEW"],
  f3: ["REJECTED", "ACCEPTED"],
};

const WORKS = [{ id: "work-1", title: "Explainable graph models for retrieval", publication_year: 2025, is_corresponding: true, cited_by_count: 4 }];

const SIMILAR = {
  source_work_id: "work-1",
  items: [
    { work: { id: "s1", title: "GNNExplainer revisited", publication_year: 2024, cited_by_count: 12, doi: "10.1000/gnn" }, rank: 1, combined_similarity: 0.8, semantic_similarity: 0.8, lexical_similarity: 0.5, topic_similarity: 0.6, shared_topic_ids: [], shared_topic_names: ["Graph neural networks"], retrieval_sources: [] },
    { work: { id: "s2", title: "Neural ranking with graphs", publication_year: 2023, cited_by_count: 3 }, rank: 2, combined_similarity: 0.7, semantic_similarity: 0.7, lexical_similarity: 0.4, topic_similarity: 0.5, shared_topic_ids: [], shared_topic_names: [], retrieval_sources: [] },
  ],
  total: 2,
  limit: 3,
  offset: 0,
  has_more: false,
  ranking_mode: "hybrid",
};

/* ── A fetch that names every request ─────────────────────────────────────── */

const ENDPOINTS: [string, RegExp][] = [
  ["session", /^\/api\/v1\/auth\/me$/],
  ["workspace", /^\/api\/v1\/workspace\?sort_by=deadline&sort_order=asc&limit=100$/],
  ["application-summary", /^\/api\/v1\/postings\/applications\/mine\/summary$/],
  ["calendar", /^\/api\/v1\/researchers\/[^/]+\/calendar\?start_date=[^&]+&end_date=[^&]+$/],
  ["recommendations", /^\/api\/v1\/researchers\/[^/]+\/recommendations\/unified\?limit=3$/],
  ["why", /^\/api\/v1\/researchers\/[^/]+\/recommendations\/[^/]+\/personalization$/],
  ["open-postings", /^\/api\/v1\/postings\?accepting_only=true&limit=50$/],
  ["fit-scores", /^\/api\/v1\/postings\/fit-scores$/],
  ["reading-list", /^\/api\/v1\/reading-list\?limit=1$/],
  ["my-postings", /^\/api\/v1\/postings\/mine\?limit=100$/],
  ["posting-applications", /^\/api\/v1\/postings\/[^/]+\/applications\?limit=100$/],
  ["works", /^\/api\/v1\/researchers\/[^/]+\/works\?limit=1&offset=0$/],
  ["similar", /^\/api\/v1\/discovery\/research\/[^/]+\/similar\?limit=3$/],
];

type Answer = (path: string, init?: RequestInit) => Response | Promise<Response>;
let requests: { name: string; path: string; init?: RequestInit }[] = [];

function serve(role: PlatformRole, answers: Partial<Record<string, Answer>> = {}, user = makeUser({ role, full_name: "Priya Raghavan" })) {
  requests = [];
  storeSession(makeTokenResponse({ user }));
  const defaults: Record<string, Answer> = {
    session: () => jsonResponse(user),
    workspace: () => jsonResponse(workspace()),
    "application-summary": () => jsonResponse({ total: 2, active: 2, by_status: { UNDER_REVIEW: 1, SUBMITTED: 1 } }),
    calendar: () => jsonResponse(CALENDAR),
    recommendations: () => jsonResponse(recommendations()),
    why: () => jsonResponse({}, 404),
    "open-postings": () => jsonResponse({ postings: OPEN_POSTINGS, total: 4, limit: 50, offset: 0 }),
    "fit-scores": () => jsonResponse(FITS),
    "reading-list": () => jsonResponse(READING),
    "my-postings": () => jsonResponse({ postings: MINE, total: MINE.length, limit: 100, offset: 0 }),
    "posting-applications": (path) => {
      const id = path.split("/")[4];
      return jsonResponse({ applications: (APPLICATIONS[id] ?? []).map((status, i) => application(`${id}-${i}`, status)), total: 0, limit: 100, offset: 0 });
    },
    works: () => jsonResponse(WORKS),
    similar: () => jsonResponse(SIMILAR),
  };
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      const path = url.replace(/^https?:\/\/[^/]+/, "");
      const [name] = ENDPOINTS.find(([, pattern]) => pattern.test(path)) ?? [`unexpected ${path}`];
      requests.push({ name, path, init });
      const answer = answers[name] ?? defaults[name];
      return Promise.resolve(answer ? answer(path, init) : jsonResponse({ detail: "unexpected" }, 404));
    })
  );
}

/** The dashboard's own requests: everything but the shell's session check. */
const dashboardRequests = () => requests.filter((r) => r.name !== "session").map((r) => r.name);

function renderHome() {
  return render(
    <SessionProvider>
      <DashboardPage />
    </SessionProvider>
  );
}

const region = (name: string) => screen.getByRole("region", { name });
/** Waits until no section is still loading. */
const settled = () => waitFor(() => expect(document.querySelectorAll('[aria-busy="true"]')).toHaveLength(0));

beforeAll(installDialogPolyfill);
beforeEach(() => clearActiveIdentity());
afterEach(() => clearActiveIdentity());

/* ── Tests ────────────────────────────────────────────────────────────────── */

describe("upcomingDeadlines", () => {
  it("keeps open calls due within the window, soonest first", () => {
    expect(upcomingDeadlines(ITEMS, 14).map(({ item }) => item.opportunity.title)).toEqual(["Workshop due in three days", "Symposium due in ten days"]);
  });
});

describe("student home", () => {
  it("greets the student and shows the plan's five modules", async () => {
    serve("STUDENT");
    renderHome();

    expect(await screen.findByRole("heading", { level: 1, name: "Welcome back, Priya Raghavan" })).toBeInTheDocument();
    for (const name of ["Needs attention", "Upcoming (next 30 days)", "Recommended for you", "Postings that fit you", "Reading progress"]) {
      expect(region(name)).toBeInTheDocument();
    }
    // Faculty modules are not a student's, nor is writing a posting (P9).
    expect(screen.queryByRole("region", { name: "Needs your decision" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "New posting" })).not.toBeInTheDocument();
    await settled();
  });

  it("needs attention: calls due within 14 days, soonest first, with status and next step; and the applications", async () => {
    serve("STUDENT");
    renderHome();
    await settled();

    const attention = region("Needs attention");
    const calls = within(attention).getAllByRole("listitem");
    expect(calls.map((li) => li.querySelector("a")?.textContent)).toEqual(["Workshop due in three days", "Symposium due in ten days"]);
    expect(calls[0]).toHaveTextContent("3 days left");
    expect(calls[0]).toHaveTextContent("Planning");
    expect(calls[0]).toHaveTextContent("Next: finish and submit your paper");
    expect(calls[1]).toHaveTextContent("Submitted: waiting for the decision");
    expect(within(attention).queryByText("Accepted already")).not.toBeInTheDocument();
    expect(within(attention).queryByText("Journal due in three weeks")).not.toBeInTheDocument();
    expect(within(attention).getByText(/2 applications in progress \(1 under review, 1 submitted\)/)).toBeInTheDocument();
  });

  it("puts an offer first", async () => {
    serve("STUDENT", { "application-summary": () => jsonResponse({ total: 3, active: 3, by_status: { OFFERED: 1, SUBMITTED: 2 } }) });
    renderHome();
    await settled();
    expect(within(region("Needs attention")).getByText("1 offer waiting for your reply.")).toBeInTheDocument();
  });

  it("upcoming: call deadlines and calendar milestones within 30 days, in date order, each once", async () => {
    serve("STUDENT");
    renderHome();
    await settled();

    const titles = within(region("Upcoming (next 30 days)"))
      .getAllByRole("listitem")
      .map((li) => li.querySelector("a")?.textContent);
    expect(titles).toEqual(["Workshop due in three days", "Draft the related-work section", "Symposium due in ten days", "Journal due in three weeks", "Camera-ready for HCI 2026"]);
  });

  it("recommended for you: three calls, each with its match band and one reason; Why? loads only when asked", async () => {
    serve("STUDENT");
    renderHome();
    await settled();

    const section = region("Recommended for you");
    const items = within(section).getAllByRole("listitem");
    expect(items).toHaveLength(3);
    expect(items[0]).toHaveTextContent("Workshop on Explainable Graph Learning");
    expect(items[0]).toHaveTextContent("Strong match · 72%");
    expect(items[0]).toHaveTextContent("Matches your interest in graph neural networks.");
    expect(items[1]).toHaveTextContent("Good match · 48%");
    expect(dashboardRequests()).not.toContain("why");

    const why = within(items[0]).getByRole("button", { name: "Why?" });
    expect(why).toHaveAccessibleDescription("Workshop on Explainable Graph Learning");
    fireEvent.click(why);
    await waitFor(() => expect(dashboardRequests().filter((n) => n === "why")).toHaveLength(1));
  });

  it("postings that fit you: the best three by fit, scored in one batch after the postings", async () => {
    serve("STUDENT");
    renderHome();
    await settled();

    const items = within(region("Postings that fit you")).getAllByRole("listitem");
    expect(items.map((li) => li.querySelector("a")?.textContent)).toEqual(["Thesis topic: explainable GNNs", "RA: retrieval evaluation", "Internship: data engineering"]);
    expect(items[0]).toHaveTextContent("Strong fit · 81%");
    expect(items[0]).toHaveTextContent("Topics: graph neural networks");
    const fit = requests.find((r) => r.name === "fit-scores")!;
    expect(JSON.parse(String(fit.init?.body))).toEqual({ posting_ids: ["p1", "p2", "p3", "p4"] });
    expect(requests.findIndex((r) => r.name === "fit-scores")).toBeGreaterThan(requests.findIndex((r) => r.name === "open-postings"));
  });

  it("reading progress: to read, reading and done", async () => {
    serve("STUDENT");
    renderHome();
    await settled();
    const reading = region("Reading progress");
    const count = (label: string) => within(reading).getByText(label).closest("div")?.querySelector("dd")?.textContent;
    expect([count("To read"), count("Reading"), count("Done")]).toEqual(["2", "2", "1"]);
  });

  it("makes exactly its seven requests, each once, all but the fit scores at once", async () => {
    let releasePostings: () => void = () => undefined;
    serve("STUDENT", {
      "open-postings": () => new Promise<Response>((resolve) => (releasePostings = () => resolve(jsonResponse({ postings: OPEN_POSTINGS, total: 4, limit: 50, offset: 0 })))),
    });
    renderHome();
    // With the postings still unanswered: every independent request is already out, and only those.
    await waitFor(() => expect(dashboardRequests()).toHaveLength(6));
    await act(async () => undefined);
    expect(dashboardRequests().sort()).toEqual(["application-summary", "calendar", "open-postings", "reading-list", "recommendations", "workspace"]);
    await act(async () => releasePostings());
    await settled();

    const made = dashboardRequests();
    expect(made.sort()).toEqual(["application-summary", "calendar", "fit-scores", "open-postings", "reading-list", "recommendations", "workspace"]);
    expect(made.length).toBeLessThanOrEqual(7);
    // The workspace feeds two modules and is asked for once.
    expect(made.filter((n) => n === "workspace")).toHaveLength(1);
  });

  it("asks for nothing again when the page re-renders", async () => {
    serve("STUDENT");
    const view = renderHome();
    await settled();
    const before = requests.length;
    view.rerender(
      <SessionProvider>
        <DashboardPage />
      </SessionProvider>
    );
    await act(async () => undefined);
    await settled();
    expect(requests.length).toBe(before);
  });

  it("gives a new account the three-step Get started checklist", async () => {
    serve("STUDENT", {
      workspace: () => jsonResponse(workspace([])),
      "reading-list": () => jsonResponse({ ...READING, total_count: 0, counts_by_status: { TO_READ: 0, READING: 0, DONE: 0 } }),
      recommendations: () => jsonResponse(recommendations({ active_interests_count: 0, is_cold_start: true }, [])),
      "application-summary": () => jsonResponse({ total: 0, active: 0, by_status: {} }),
      calendar: () => jsonResponse({ ...CALENDAR, events: [], total_events: 0 }),
    });
    renderHome();
    await settled();

    const steps = within(region("Needs attention")).getAllByRole("listitem");
    expect(steps.map((li) => li.textContent)).toEqual(["Add your research interests", "Save a call for papers to your workspace", "Save a paper to your reading list"]);
    // P6: interests are added where preferences are edited (the profile's old section is gone).
    expect(within(steps[0]).getByRole("link")).toHaveAttribute("href", "/researcher/preferences");
    // Each section explains its own emptiness and what to do next — not a failure.
    expect(within(region("Recommended for you")).getByText("No recommendations yet.")).toBeInTheDocument();
    expect(within(region("Reading progress")).getByText("No saved papers yet.")).toBeInTheDocument();
    expect(within(region("Upcoming (next 30 days)")).getByText("Nothing is due in the next 30 days.")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("ticks the steps already done, and nudges an incomplete profile once all are", async () => {
    serve("STUDENT", { "reading-list": () => jsonResponse({ ...READING, total_count: 0, counts_by_status: { TO_READ: 0, READING: 0, DONE: 0 } }) });
    const view = renderHome();
    await settled();
    const steps = within(region("Needs attention")).getAllByRole("listitem").slice(-3);
    expect(steps.map((li) => li.textContent)).toEqual([
      "Add your research interests (done)",
      "Save a call for papers to your workspace (done)",
      "Save a paper to your reading list",
    ]);
    view.unmount();

    serve("STUDENT", { recommendations: () => jsonResponse(recommendations({ is_partial_profile: true, completeness_score: 0.45 })) });
    renderHome();
    await settled();
    const attention = region("Needs attention");
    expect(within(attention).queryByRole("heading", { name: "Get started" })).not.toBeInTheDocument();
    expect(within(attention).getByText(/Your profile is 45% complete/)).toBeInTheDocument();
  });

  it("keeps every other section working when one fails, says so plainly, and retries only that one", async () => {
    let failing = true;
    serve("STUDENT", {
      recommendations: () => (failing ? jsonResponse({ detail: "Traceback: psycopg.OperationalError" }, 500) : jsonResponse(recommendations())),
    });
    renderHome();
    await settled();

    const section = region("Recommended for you");
    expect(within(section).getByText("Your recommendations could not be loaded.")).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("psycopg");
    // The rest of the dashboard is unaffected.
    expect(within(region("Postings that fit you")).getAllByRole("listitem")).toHaveLength(3);
    expect(within(region("Needs attention")).getAllByRole("listitem").length).toBeGreaterThan(0);

    failing = false;
    const before = dashboardRequests().length;
    fireEvent.click(within(section).getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(within(section).getAllByRole("listitem")).toHaveLength(3));
    expect(dashboardRequests().slice(before)).toEqual(["recommendations"]);
  });

  it("explains a failed section and retries it (the tracked calls)", async () => {
    let failing = true;
    serve("STUDENT", { workspace: () => (failing ? jsonResponse({ detail: "boom" }, 500) : jsonResponse(workspace())) });
    renderHome();
    await settled();

    const attention = region("Needs attention");
    expect(within(attention).getByText("Your tracked calls could not be loaded.")).toBeInTheDocument();
    // The shared workspace failure is reported by both of its modules, and one retry serves both.
    expect(within(region("Upcoming (next 30 days)")).getByText("Your tracked calls could not be loaded.")).toBeInTheDocument();
    failing = false;
    fireEvent.click(within(attention).getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(within(attention).getByText("Workshop due in three days")).toBeInTheDocument());
    expect(within(region("Upcoming (next 30 days)")).getByText("Workshop due in three days")).toBeInTheDocument();
    expect(dashboardRequests().filter((n) => n === "workspace")).toHaveLength(2);
  });

  it("shows placeholders, not invented numbers, until the answers arrive", async () => {
    serve("STUDENT", { "reading-list": () => new Promise<Response>(() => {}) });
    renderHome();
    await screen.findByRole("heading", { level: 1 });
    const reading = region("Reading progress");
    expect(reading.querySelector('[aria-busy="true"]')).not.toBeNull();
    expect(reading).toHaveTextContent("Loading your reading list");
    expect(within(reading).queryByText("To read")).not.toBeInTheDocument();
    // A module's loading text is there for screen readers but not announced (the page would be read out seven times).
    expect(within(reading).queryByRole("status")).not.toBeInTheDocument();
  });
});

describe("faculty home", () => {
  it("shows the plan's four faculty modules and none of the student's", async () => {
    serve("FACULTY");
    renderHome();
    await settled();
    for (const name of ["Needs your decision", "Your open postings", "Upcoming deadlines", "Recommended papers"]) {
      expect(region(name)).toBeInTheDocument();
    }
    for (const name of ["Needs attention", "Recommended for you", "Postings that fit you", "Reading progress"]) {
      expect(screen.queryByRole("region", { name })).not.toBeInTheDocument();
    }
    // P9: the recruiting home's one main action, and its modules open the faculty pages.
    expect(screen.getByRole("link", { name: "New posting" })).toHaveAttribute("href", "/postings/new");
    expect(within(region("Needs your decision")).getByRole("link", { name: "All applicants" })).toHaveAttribute("href", "/postings/applicants");
    expect(within(region("Your open postings")).getByRole("link", { name: "Manage postings" })).toHaveAttribute("href", "/postings?view=mine");
  });

  it("needs your decision: new and under-review applications of the three busiest open postings, and the rest named", async () => {
    serve("FACULTY");
    renderHome();
    await settled();

    const section = region("Needs your decision");
    const rows = within(section).getAllByRole("listitem");
    expect(rows.map((li) => li.querySelector("a")?.textContent)).toEqual(["RA: benchmark curation", "Thesis: neural ranking"]);
    // P9: each posting opens in the applicant inbox, filtered to it.
    expect(rows[0].querySelector("a")).toHaveAttribute("href", "/postings/applicants?posting=f1");
    expect(rows[0]).toHaveTextContent("2 new · 1 under review");
    expect(rows[1]).toHaveTextContent("1 under review");
    expect(within(section).getByText(/1 more open posting has applications/)).toBeInTheDocument();
    // The three busiest open postings only: not the fourth, the draft or the closed one.
    const fetched = requests.filter((r) => r.name === "posting-applications").map((r) => r.path.split("/")[4]);
    expect(fetched.sort()).toEqual(["f1", "f2", "f3"]);
  });

  it("your open postings and upcoming deadlines (calls and postings closing within 30 days)", async () => {
    serve("FACULTY");
    renderHome();
    await settled();

    const open = within(region("Your open postings")).getAllByRole("listitem");
    expect(open.map((li) => li.querySelector("a")?.textContent)).toEqual(["RA: benchmark curation", "Thesis: neural ranking", "Internship: annotation tools", "Project: query logs"]);
    expect(open[0]).toHaveTextContent("5 applicants");
    expect(open[2]).toHaveTextContent("No application deadline");

    const upcoming = within(region("Upcoming deadlines"))
      .getAllByRole("listitem")
      .map((li) => li.textContent);
    expect(upcoming.some((t) => t?.includes("RA: benchmark curation") && t.includes("Applications close"))).toBe(true);
    expect(upcoming.some((t) => t?.includes("Thesis: neural ranking"))).toBe(false); // closes in 40 days
    expect(upcoming.some((t) => t?.includes("Workshop due in three days") && t.includes("Submission deadline"))).toBe(true);
  });

  it("recommended papers: papers similar to the newest paper, with the reason", async () => {
    serve("FACULTY");
    renderHome();
    await settled();

    const section = region("Recommended papers");
    expect(section).toHaveTextContent("Related to your paper “Explainable graph models for retrieval” (2025).");
    const papers = within(section).getAllByRole("listitem");
    expect(papers).toHaveLength(2);
    expect(within(papers[0]).getByRole("link")).toHaveAttribute("href", "https://doi.org/10.1000/gnn");
    expect(papers[0]).toHaveTextContent("Shared topics: Graph neural networks");
    expect(requests.find((r) => r.name === "similar")!.path).toContain("/research/work-1/similar");
  });

  it("makes at most seven requests, none of a student's", async () => {
    serve("FACULTY");
    renderHome();
    await settled();

    const made = dashboardRequests();
    expect(made.length).toBeLessThanOrEqual(7);
    expect(made.sort()).toEqual(["my-postings", "posting-applications", "posting-applications", "posting-applications", "similar", "workspace", "works"].sort());
    for (const studentOnly of ["application-summary", "calendar", "recommendations", "open-postings", "fit-scores", "reading-list"]) {
      expect(made).not.toContain(studentOnly);
    }
    // The postings list feeds three modules and is asked for once.
    expect(made.filter((n) => n === "my-postings")).toHaveLength(1);
  });

  it("explains the empty states of a new faculty account without failing", async () => {
    serve("FACULTY", {
      workspace: () => jsonResponse(workspace([])),
      "my-postings": () => jsonResponse({ postings: [], total: 0, limit: 100, offset: 0 }),
      works: () => jsonResponse([]),
    });
    renderHome();
    await settled();

    expect(within(region("Needs your decision")).getByText("No application is waiting for your decision.")).toBeInTheDocument();
    expect(within(region("Your open postings")).getByText("You have no open postings.")).toBeInTheDocument();
    expect(within(region("Recommended papers")).getByText("No papers of yours yet.")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    // Nothing to fetch applications or related papers for.
    expect(dashboardRequests().sort()).toEqual(["my-postings", "workspace", "works"].sort());
  });
});

describe("administrator home", () => {
  it("offers Platform administration first and makes no dashboard requests", async () => {
    serve("ADMIN");
    renderHome();
    const link = await screen.findByRole("link", { name: /Platform administration/ });
    expect(link).toHaveAttribute("href", "/admin");
    await act(async () => undefined);
    expect(dashboardRequests()).toEqual([]);
  });
});

describe("session changes", () => {
  it("keeps nothing of the account once it signs out", async () => {
    serve("STUDENT");
    function SignOut() {
      const { logout } = useSession();
      return <button onClick={logout}>sign out</button>;
    }
    render(
      <SessionProvider>
        <SignOut />
        <DashboardPage />
      </SessionProvider>
    );
    await settled();
    expect(heldApiResources()).toBeGreaterThan(0);

    fireEvent.click(screen.getByText("sign out"));
    await act(async () => undefined);
    expect(screen.queryByRole("region", { name: "Needs attention" })).not.toBeInTheDocument();
    expect(heldApiResources()).toBe(0);
  });
});
