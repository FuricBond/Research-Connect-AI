/**
 * P5 — the research objects (DESIGN_SYSTEM.md §3.2, §9): a call's card keeps deadline and risk
 * apart and never shows a raw score or enum (the P0.5 rules, now on the new card); a call's dates
 * come only from the API; the wording helpers name what the backend decided and invent nothing.
 */

import React from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn(), forward: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/browse",
  useSearchParams: () => new URLSearchParams(),
}));

import { SessionProvider } from "../components/auth/SessionProvider";
import { DeadlineMilestones, callMilestones } from "../components/research/DeadlineMilestones";
import { OpportunityCard } from "../components/research/OpportunityCard";
import { bareDoi, citationsLabel, feeLabel, plainSummary, topReasons, workTypeLabel } from "../utils/research";
import { makeCall, makeDeadline, makeExplanation } from "./p5-fixtures";

const card = (overrides: Parameters<typeof makeCall>[0] = {}) =>
  render(
    <SessionProvider>
      <OpportunityCard call={makeCall(overrides)} />
    </SessionProvider>
  );

describe("a call's card: deadline is time, risk is trust", () => {
  it("shows missing risk evidence as a neutral 'Risk not assessed', not an alert", () => {
    card({ risk_level: "INSUFFICIENT_EVIDENCE" });
    expect(screen.getByText("Risk not assessed").closest(".risk-indicator")).toHaveClass("risk-unknown");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByText(/Limited Metadata|INSUFFICIENT_EVIDENCE/)).not.toBeInTheDocument();
  });

  it("states moderate risk in words, with no raw score", () => {
    const { container } = card({ risk_level: "MODERATE_RISK", risk_score: 0.45 });
    expect(container).toHaveTextContent("Some risk signs");
    expect(container.textContent).not.toMatch(/45%|0\.45/);
  });

  it("calls a predatory flag high risk even without a level", () => {
    card({ risk_level: null, is_predatory_flag: true });
    expect(screen.getByText("High risk").closest(".risk-indicator")).toHaveClass("risk-high");
  });

  it("states a close deadline in words, and is not a live region", () => {
    const { container } = card({ deadline_intelligence: makeDeadline(3.6, { tier: "URGENT" }) });
    expect(container).toHaveTextContent("3 days left");
    expect(container.textContent).not.toMatch(/\dd left|3\.6/);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(container.querySelector(".deadline-countdown")).toHaveClass("deadline-soon");
  });

  it("says Closed for a past deadline and No deadline listed without one", () => {
    card({ deadline_intelligence: makeDeadline(-3, { status: "EXPIRED", tier: "EXPIRED" }) });
    expect(screen.getByText(/^Closed /)).toBeInTheDocument();
    render(
      <SessionProvider>
        <OpportunityCard call={makeCall({ id: "x", submission_deadline: null, deadline_intelligence: null })} />
      </SessionProvider>
    );
    expect(screen.getByText("No deadline listed")).toBeInTheDocument();
  });

  it("names the type, organiser, place and attendance in words, and its indexes", () => {
    const { container } = card({ opportunity_type: "SPECIAL_ISSUE", organizer: null, publisher: "Springer", location: "Glasgow, UK", delivery_mode: "OFFLINE", indexing: ["Scopus", " ", "DBLP"] });
    const article = within(container).getByRole("article");
    expect(article).toHaveTextContent("Special issue");
    expect(article).toHaveTextContent("Springer · Glasgow, UK · In person");
    expect(article).toHaveTextContent("Indexed in Scopus, DBLP");
    expect(article.textContent).not.toMatch(/SPECIAL_ISSUE|OFFLINE/);
  });
});

describe("a call's dates", () => {
  it("come from the deadline intelligence, in academic order", () => {
    const milestones = callMilestones(makeDeadline(10), {});
    expect(milestones.map((m) => m.label)).toEqual(["Abstract", "Paper submission", "Notification", "Camera-ready"]);
    expect(milestones[1].date).toBe("20 Oct 2026, 23:59 AoE");
  });

  it("fall back to the call's own fields, and say when there are none", () => {
    const milestones = callMilestones(null, { submission_deadline: "2026-10-20T11:59:59+00:00", camera_ready_deadline: "2026-12-11", event_start_date: "2027-01-18" });
    expect(milestones.map((m) => m.label)).toEqual(["Paper submission", "Camera-ready", "Event starts"]);
    render(<DeadlineMilestones intelligence={null} dates={{}} />);
    expect(screen.getByText("This call lists no dates.")).toBeInTheDocument();
  });

  it("say an extension and a disagreement between sources in words", () => {
    const intel = makeDeadline(10);
    const view = intel.milestone_views.SUBMISSION;
    view.latest_revision = { deadline_type: "SUBMISSION", classification: "EXTENDED", days_diff: 7.2, explanation: "", current_observation: {} as never };
    intel.milestone_views.NOTIFICATION.conflict_state = "SOURCE_CONFLICT";
    intel.milestone_views.NOTIFICATION.conflict_reason = "WikiCFP and the call page give different dates.";
    render(<DeadlineMilestones intelligence={intel} dates={{}} />);
    expect(screen.getByText("Extended by 7 days")).toBeInTheDocument();
    expect(screen.getByText("WikiCFP and the call page give different dates.")).toBeInTheDocument();
  });
});

describe("research words", () => {
  it("takes reasons from the backend's own primary factors, and makes none up", () => {
    expect(topReasons(makeExplanation())).toEqual(["Similar meaning", "Shared topics"]);
    expect(topReasons(makeExplanation({ primary_factors: [] }))).toEqual([]);
    expect(topReasons(null)).toEqual([]);
    expect(plainSummary(makeExplanation(), 3)).toBe("Ranked #3 mainly for similar meaning and shared topics.");
    expect(plainSummary(makeExplanation({ primary_factors: [] }), 3)).toBeNull();
  });

  it("names publication types, citations, DOIs and fees as people say them", () => {
    expect(workTypeLabel("article")).toBe("Journal article");
    expect(workTypeLabel("proceedings-article")).toBe("Conference paper");
    expect(workTypeLabel("peer_review")).toBe("Peer review");
    expect(workTypeLabel(null)).toBeNull();
    expect(citationsLabel(1)).toBe("1 citation");
    expect(citationsLabel(1234)).toBe("1,234 citations");
    expect(citationsLabel(null)).toBeNull();
    expect(bareDoi("https://doi.org/10.1109/5.771073")).toBe("10.1109/5.771073");
    expect(bareDoi("doi:10.1/x")).toBe("10.1/x");
    expect(feeLabel({ has_fee: false })).toBe("No fee");
    expect(feeLabel({ amount: 1200, currency: "USD" })).toBe("USD 1,200");
    expect(feeLabel({ has_fee: true })).toBe("Fee charged (amount not stated)");
    expect(feeLabel(null)).toBeNull();
  });
});
