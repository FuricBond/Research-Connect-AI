/**
 * Phase 5.15 — a student's fit on research postings.
 *
 *  - PostingCard shows "82% fit · Strong" and the top reason only when a fit is given.
 *  - The postings list makes one batch call for a student in Discover mode, none for other
 *    roles, and still lists the postings when that call fails.
 *  - The posting page shows "Your fit" with the missing skills to a student who is not the
 *    author, and never asks for it for the author.
 */

import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

const params = { id: "po000000-0000-4000-8000-000000000001" };

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn(), back: vi.fn(), forward: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/postings",
  useSearchParams: () => new URLSearchParams(),
  useParams: () => params,
}));

import { PostingCard } from "../components/postings/PostingCard";
import PostingsPage from "../app/postings/page";
import PostingDetailPage from "../app/postings/[id]/page";
import { SessionProvider } from "../components/auth/SessionProvider";
import { storeSession } from "../services/auth";
import type { PlatformRole } from "../types/auth";
import type { PostingFit, ResearchPosting } from "../types/posting";
import { jsonResponse, makeTokenResponse, makeUser } from "./factories";

function makePosting(overrides: Partial<ResearchPosting> = {}): ResearchPosting {
  return {
    id: params.id,
    author: {
      profile_id: "fa000000-0000-4000-8000-000000000001",
      full_name: "Dr. Amara Okafor",
      institution: "Test University",
      department: "Computer Science",
      academic_status: "FACULTY",
    },
    title: "Doctoral position in neural information retrieval",
    posting_type: "PROJECT",
    status: "OPEN",
    summary: null,
    description: "We are seeking a doctoral researcher to work on dense retrieval models.",
    required_skills: ["Python", "PyTorch"],
    preferred_qualifications: null,
    institution: "Test University",
    department: "Computer Science",
    location: null,
    country: null,
    work_mode: "ONSITE",
    positions_available: 1,
    application_deadline: null,
    expected_start_date: null,
    expected_end_date: null,
    contact_email: null,
    external_url: null,
    topics: [],
    opening_terms: {
      compensation_type: "UNSPECIFIED",
      compensation_amount: null,
      compensation_currency: null,
      compensation_period: null,
      commitment_type: null,
      hours_per_week: null,
      duration_months: null,
      eligibility_requirements: null,
      accepts_applications: false,
      is_structured_opening: false,
    },
    application_count: 0,
    published_at: "2026-10-01T10:00:00+00:00",
    closed_at: null,
    archived_at: null,
    status_note: null,
    created_at: "2026-10-01T10:00:00+00:00",
    updated_at: "2026-10-01T10:00:00+00:00",
    is_accepting_applications: true,
    days_until_deadline: null,
    allowed_transitions: [],
    is_owner: false,
    viewer_application_id: null,
    viewer_application_status: null,
    ...overrides,
  };
}

function makeFit(overrides: Partial<PostingFit> = {}): PostingFit {
  return {
    posting_id: params.id,
    score: 82,
    band: "Strong",
    reasons: [
      { code: "TOPIC", label: "Shares your research topics: Information Retrieval", weight: 0.5, matched: ["Information Retrieval"] },
      { code: "SKILLS", label: "You have recorded 1 of its 2 required skills", weight: 0.3, matched: ["Python"] },
    ],
    gaps: ["PyTorch"],
    computed_at: "2026-10-03T12:00:00+00:00",
    ...overrides,
  };
}

let fetchMock: ReturnType<typeof vi.fn>;

function serve(role: PlatformRole, routes: { fits?: () => Promise<Response>; posting?: ResearchPosting } = {}) {
  storeSession(makeTokenResponse({ user: makeUser({ role }) }));
  fetchMock.mockImplementation((url: string) => {
    if (url.endsWith("/api/v1/auth/me")) return Promise.resolve(jsonResponse(makeUser({ role })));
    if (url.endsWith("/api/v1/postings/fit-scores")) {
      return routes.fits ? routes.fits() : Promise.resolve(jsonResponse({ fits: [makeFit()] }));
    }
    if (url.endsWith(`/api/v1/postings/${params.id}/fit`)) return Promise.resolve(jsonResponse(makeFit()));
    if (url.includes("/api/v1/postings?")) {
      return Promise.resolve(jsonResponse({ postings: [makePosting()], total: 1, limit: 50, offset: 0 }));
    }
    if (url.endsWith(`/api/v1/postings/${params.id}`)) {
      return Promise.resolve(jsonResponse(routes.posting ?? makePosting()));
    }
    return Promise.resolve(jsonResponse({ detail: `unexpected request ${url}` }, 404));
  });
}

function requested(part: string): string[] {
  return fetchMock.mock.calls.map(([url]) => String(url)).filter((url) => url.includes(part));
}

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

describe("PostingCard fit", () => {
  it("shows the score, band and top reason when a fit is given", () => {
    render(<PostingCard posting={makePosting()} fit={makeFit()} />);

    const badge = screen.getByLabelText("Your fit");
    expect(badge).toHaveTextContent("82% fit · Strong");
    expect(badge).toHaveTextContent("Shares your research topics: Information Retrieval");
  });

  it("shows nothing without a fit or without a score", () => {
    const { rerender } = render(<PostingCard posting={makePosting()} />);
    expect(screen.queryByLabelText("Your fit")).not.toBeInTheDocument();

    rerender(<PostingCard posting={makePosting()} fit={makeFit({ score: null, band: null })} />);
    expect(screen.queryByLabelText("Your fit")).not.toBeInTheDocument();
  });
});

describe("postings list", () => {
  function renderList() {
    return render(
      <SessionProvider>
        <PostingsPage />
      </SessionProvider>
    );
  }

  it("asks for every listed posting's fit in one call for a student", async () => {
    serve("STUDENT");
    renderList();

    expect(await screen.findByLabelText("Your fit")).toHaveTextContent("82% fit · Strong");
    const calls = fetchMock.mock.calls.filter(([url]) => String(url).endsWith("/fit-scores"));
    expect(calls).toHaveLength(1);
    expect(JSON.parse(String((calls[0][1] as RequestInit).body))).toEqual({ posting_ids: [params.id] });
  });

  it("does not ask for fit for other roles", async () => {
    serve("FACULTY");
    renderList();

    expect(await screen.findByRole("link", { name: makePosting().title })).toBeInTheDocument();
    expect(requested("/fit-scores")).toEqual([]);
    expect(screen.queryByLabelText("Your fit")).not.toBeInTheDocument();
  });

  it("still lists the postings when the fit call fails", async () => {
    serve("STUDENT", { fits: () => Promise.resolve(jsonResponse({ detail: "boom" }, 500)) });
    renderList();

    expect(await screen.findByRole("link", { name: makePosting().title })).toBeInTheDocument();
    await waitFor(() => expect(requested("/fit-scores")).toHaveLength(1));
    expect(screen.queryByLabelText("Your fit")).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

describe("posting page fit", () => {
  function renderDetail() {
    return render(
      <SessionProvider>
        <PostingDetailPage />
      </SessionProvider>
    );
  }

  it("shows Your fit with the skills to strengthen for a student", async () => {
    serve("STUDENT");
    renderDetail();

    const heading = await screen.findByRole("heading", { name: "Your fit" });
    const section = heading.closest("section") as HTMLElement;
    expect(section).toHaveTextContent("82% fit · Strong");
    expect(section).toHaveTextContent("You have recorded 1 of its 2 required skills: Python");
    expect(section).toHaveTextContent("To strengthen your application");
    expect(section).toHaveTextContent("PyTorch");
  });

  it("is hidden for the posting's author, who is never scored", async () => {
    serve("STUDENT", { posting: makePosting({ is_owner: true }) });
    renderDetail();

    expect(await screen.findByRole("heading", { name: makePosting().title })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Your fit" })).not.toBeInTheDocument();
    expect(requested(`/postings/${params.id}/fit`)).toEqual([]);
  });

  it("is not requested for other roles", async () => {
    serve("FACULTY");
    renderDetail();

    expect(await screen.findByRole("heading", { name: makePosting().title })).toBeInTheDocument();
    expect(requested(`/postings/${params.id}/fit`)).toEqual([]);
  });
});
