/**
 * P0.5 — deadline (time) and venue risk (trust) are different things and look different.
 *
 * Before P0 a workspace card read "Deadline: 10/10/2026 (3.7978d remaining)" next to a red
 * "Risk: INSUFFICIENT_EVIDENCE"; urgent deadlines used the same red as high risk; and missing
 * evidence looked like a warning. Now deadlines are time words with a clock, risk is words with
 * a shield, and missing evidence is a neutral "Risk not assessed".
 */

import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn(), back: vi.fn(), forward: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/workspace",
  useSearchParams: () => new URLSearchParams(),
}));

import WorkspacePageRoute from "../app/workspace/page";
import { SessionProvider } from "../components/auth/SessionProvider";
import { DeadlineBadge } from "../components/discovery/DeadlineBadge";
import { RiskWarning } from "../components/discovery/RiskWarning";
import { DeadlineCountdown } from "../components/indicators/DeadlineCountdown";
import { RiskIndicator } from "../components/indicators/RiskIndicator";
import { clearActiveIdentity, storeSession } from "../services/auth";
import type { OpportunityDeadline } from "../types/opportunity";
import type { WorkspaceItem, WorkspaceListResponse } from "../types/workspace";
import { deadlineTone, describeTimeLeft, humanizeEnum } from "../utils/date";
import { riskPresentation } from "../utils/risk";
import { USER_ID, jsonResponse, makeTokenResponse, makeUser } from "./factories";

function deadlineIntel(days: number, overrides: Partial<{ status: string; tier: string }> = {}): OpportunityDeadline {
  return {
    reference_time: "2026-10-06T00:00:00Z",
    primary_milestone: "SUBMISSION",
    primary_view: {
      canonical_deadline: { local_date: "2026-10-10", timezone_name: "UTC", utc_deadline: "2026-10-10T11:59:00Z" },
      canonical_assessment: {
        deadline_type: "SUBMISSION",
        reference_time: "2026-10-06T00:00:00Z",
        status: overrides.status ?? "UPCOMING",
        urgency_tier: overrides.tier ?? "URGENT",
        urgency_score: 0.8,
        days_remaining: days,
        confidence: 1,
        explanation: "",
      },
    },
    milestone_views: {},
    summary: "",
    overall_urgency_tier: overrides.tier ?? "URGENT",
    has_extension: false,
    has_conflict: false,
    primary_reason: "",
  } as unknown as OpportunityDeadline;
}

describe("time left in words", () => {
  it.each([
    [3.7978, "3 days left"],
    [1, "1 day left"],
    [1.99, "1 day left"],
    [0.5, "12 hours left"],
    [0.04, "Due within the hour"],
    [-0.2, "Closed"],
  ])("%s days -> %s", (days, text) => {
    expect(describeTimeLeft(days)).toBe(text);
  });

  it("says nothing without a value", () => {
    expect(describeTimeLeft(null)).toBeNull();
    expect(describeTimeLeft(undefined)).toBeNull();
  });

  it("grades urgency by time only", () => {
    expect(deadlineTone(1.5)).toBe("urgent");
    expect(deadlineTone(5)).toBe("soon");
    expect(deadlineTone(20)).toBe("open");
    expect(deadlineTone(-1)).toBe("passed");
    expect(deadlineTone(null, "EXPIRED")).toBe("passed");
    expect(deadlineTone(null, "MISSING")).toBe("unknown");
    expect(deadlineTone(20, "UPCOMING", "CRITICAL")).toBe("urgent");
  });

  it("writes enum values in sentence case", () => {
    expect(humanizeEnum("CAMERA_READY")).toBe("Camera ready");
    expect(humanizeEnum("APPLIED")).toBe("Applied");
  });
});

describe("risk presentation", () => {
  it("treats missing or insufficient evidence as neutral, never as a warning", () => {
    for (const level of ["INSUFFICIENT_EVIDENCE", null, undefined, "UNKNOWN"]) {
      const risk = riskPresentation(level);
      expect(risk.tone, String(level)).toBe("unknown");
      expect(risk.label).toBe("Risk not assessed");
    }
  });

  it("names each assessed level in words", () => {
    expect(riskPresentation("HIGH_RISK").label).toBe("High risk");
    expect(riskPresentation("MODERATE_RISK").label).toBe("Some risk signs");
    expect(riskPresentation("LOW_RISK").label).toBe("Low risk");
    expect(riskPresentation("LOW_RISK", { isPredatory: true }).tone).toBe("high");
  });
});

describe("indicators", () => {
  it("states a deadline in time words with no raw float", () => {
    const { container } = render(<DeadlineCountdown deadline="2026-10-10" daysRemaining={3.7978} />);
    expect(container.textContent).toMatch(/^Due .+ · 3 days left$/);
    expect(container.textContent).not.toContain("3.79");
    expect(container.firstElementChild).toHaveClass("deadline-soon");
  });

  it("says when there is no deadline instead of inventing urgency", () => {
    const { container } = render(<DeadlineCountdown deadline={null} />);
    expect(container.textContent).toBe("No deadline listed");
    expect(container.firstElementChild).toHaveClass("deadline-unknown");
  });

  it("styles risk apart from deadlines, with a neutral unknown", () => {
    const { container: unknown } = render(<RiskIndicator level="INSUFFICIENT_EVIDENCE" />);
    expect(unknown.textContent).toBe("Risk not assessed");
    expect(unknown.firstElementChild).toHaveClass("risk-indicator", "risk-unknown");
    expect(unknown.firstElementChild?.className).not.toMatch(/deadline/);

    const { container: high } = render(<RiskIndicator level="HIGH_RISK" />);
    expect(high.textContent).toBe("High risk");
    expect(high.firstElementChild).toHaveClass("risk-high");
  });
});

describe("venue matching: risk banner and deadline badge", () => {
  it("shows missing evidence as a quiet neutral line, not an alert", () => {
    render(<RiskWarning riskLevel="INSUFFICIENT_EVIDENCE" onViewRiskDetails={() => undefined} />);
    expect(screen.getByText("Risk not assessed")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByText(/Limited Metadata Available/)).not.toBeInTheDocument();
  });

  it("states moderate risk without a raw score", () => {
    const { container } = render(<RiskWarning riskLevel="MODERATE_RISK" riskScore={0.45} />);
    expect(container.textContent).toContain("Some risk signs");
    expect(container.textContent).not.toMatch(/45%|0\.45/);
  });

  it("states a close deadline in words and is not a live region when static", () => {
    const { container } = render(<DeadlineBadge deadlineIntelligence={deadlineIntel(3.6)} showInspectButton={false} />);
    expect(container.textContent).toContain("3 days left");
    expect(container.textContent).not.toMatch(/\dd left/);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("says Closed for an expired deadline", () => {
    const { container } = render(
      <DeadlineBadge deadlineIntelligence={deadlineIntel(-3, { status: "EXPIRED", tier: "EXPIRED" })} />
    );
    expect(container.textContent).toContain("Closed");
    expect(container.textContent).not.toContain("Expired (");
  });
});

describe("workspace cards", () => {
  const item: WorkspaceItem = {
    id: "ws000000-0000-4000-8000-000000000009",
    user_id: USER_ID,
    opportunity_id: "op000000-0000-4000-8000-000000000009",
    status: "APPLIED",
    priority: "MEDIUM",
    tags: [],
    notes: null,
    created_at: "2026-09-20T10:00:00+00:00",
    updated_at: "2026-09-21T10:00:00+00:00",
    status_updated_at: "2026-09-21T10:00:00+00:00",
    archived_at: null,
    allowed_transitions: ["ACCEPTED", "ARCHIVED"],
    opportunity: {
      id: "op000000-0000-4000-8000-000000000009",
      title: "IEEE Conference on Machine Learning",
      opportunity_type: "CONFERENCE",
      delivery_mode: "OFFLINE",
      status: "ACTIVE",
      submission_deadline: "2026-10-10T11:59:00Z",
      is_predatory_flag: false,
      deadline_intelligence: deadlineIntel(3.7978),
      risk_explanation: { risk_level: "INSUFFICIENT_EVIDENCE" } as never,
    },
  };
  const list: WorkspaceListResponse = {
    items: [item],
    total_count: 1,
    active_count: 1,
    archived_count: 0,
    counts_by_status: { APPLIED: 1 },
    counts_by_priority: { MEDIUM: 1 },
  };

  beforeEach(() => {
    storeSession(makeTokenResponse());
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (url.endsWith("/api/v1/auth/me")) return Promise.resolve(jsonResponse(makeUser()));
        if (url.endsWith("/api/v1/workspace/summary")) return Promise.resolve(jsonResponse(list));
        if (url.includes("/api/v1/workspace?")) return Promise.resolve(jsonResponse(list));
        return Promise.resolve(jsonResponse({ detail: `unexpected ${url}` }, 404));
      })
    );
  });

  afterEach(() => clearActiveIdentity());

  it("shows the deadline in words and unknown risk as neutral", async () => {
    const { container } = render(
      <SessionProvider>
        <WorkspacePageRoute />
      </SessionProvider>
    );

    expect(await screen.findByText("IEEE Conference on Machine Learning")).toBeInTheDocument();
    const card = container.querySelector(".workspace-card")!;
    expect(card.textContent).toContain("3 days left");
    expect(card.textContent).not.toContain("3.7978");
    expect(card.textContent).not.toContain("INSUFFICIENT_EVIDENCE");
    expect(card.querySelector(".risk-unknown")?.textContent).toBe("Risk not assessed");
    expect(card.querySelector(".deadline-countdown")).not.toBeNull();
  });

  it("names statuses, priorities and transitions in words", async () => {
    render(
      <SessionProvider>
        <WorkspacePageRoute />
      </SessionProvider>
    );

    // Wait for the card itself (the status filter tabs render first).
    const title = await screen.findByText("IEEE Conference on Machine Learning");
    const card = within(title.closest(".workspace-card") as HTMLElement);
    expect(card.getByText("Applied")).toBeInTheDocument();
    expect(card.getByText("Medium priority")).toBeInTheDocument();
    expect(card.getByRole("button", { name: "Move to Accepted" })).toBeInTheDocument();
    expect(card.getByRole("combobox", { name: /Priority for IEEE Conference/ })).toBeInTheDocument();
    expect(card.queryByText("APPLIED")).not.toBeInTheDocument();
  });
});
