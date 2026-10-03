/**
 * Phase 5.13 — one supervisor suggestion.
 *
 * The card shows the server's score, shared topics, matching recent papers with year, similarity
 * and a DOI link, and open postings linking to the posting page. A faculty member's undisclosed
 * institution or email (null from the server) is never rendered.
 */

import React from "react";
import { describe, expect, it } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";

import { SupervisorMatchCard } from "../components/supervisors/SupervisorMatchCard";
import type { SupervisorMatch } from "../types/supervisor";

const POSTING_ID = "po000000-0000-4000-8000-000000000001";

function makeMatch(overrides: Partial<SupervisorMatch> = {}): SupervisorMatch {
  return {
    supervisor: {
      profile_id: "fa000000-0000-4000-8000-000000000001",
      full_name: "Dr. Grace Hopper",
      institution: null,
      department: null,
      academic_status: "FACULTY",
      contact_email: null,
      collaboration_status: "OPEN_TO_ENQUIRIES",
      collaboration_interests: ["MENTORSHIP"],
      collaboration_note: null,
    },
    match_score: 0.62,
    tier: "STRONG",
    confidence: 0.8,
    shared_topics: ["information-retrieval", "ranking"],
    matching_papers: [
      {
        work_id: "wk000000-0000-4000-8000-000000000001",
        title: "Neural ranking models",
        publication_year: 2024,
        similarity: 0.91,
        shared_topics: ["ranking"],
        doi: "10.1000/ranking",
        landing_page_url: "https://example.org/ranking",
      },
      {
        work_id: "wk000000-0000-4000-8000-000000000002",
        title: "Query logs at scale",
        publication_year: 2022,
        similarity: 0.47,
        shared_topics: [],
        doi: null,
        landing_page_url: null,
      },
    ],
    open_postings: [
      {
        posting_id: POSTING_ID,
        title: "Thesis: evaluating neural rankers",
        posting_type: "THESIS_TOPIC",
        application_deadline: null,
      },
    ],
    signals: [
      {
        signal_type: "TOPIC_FIT",
        raw_score: 0.8,
        weight: 0.35,
        weighted_contribution: 0.28,
        evidence: ["information-retrieval", "ranking"],
        explanation: "You share research topics: information retrieval, ranking.",
      },
      {
        signal_type: "SEMANTIC_FIT",
        raw_score: 0,
        weight: 0.25,
        weighted_contribution: 0,
        evidence: [],
        explanation: "Your interests could not be embedded, so this match is scored on research topics only.",
      },
    ],
    explanation_reasons: ["You share research topics: information retrieval, ranking."],
    ...overrides,
  };
}

describe("SupervisorMatchCard", () => {
  it("shows the name, tier, fit and shared topics", () => {
    render(<SupervisorMatchCard match={makeMatch()} />);

    expect(screen.getByRole("heading", { name: "Dr. Grace Hopper" })).toBeInTheDocument();
    expect(screen.getByText("Strong match")).toBeInTheDocument();
    expect(screen.getByText("62% fit")).toBeInTheDocument();
    expect(screen.getByText("information retrieval")).toBeInTheDocument();
  });

  it("lists matching recent papers with year, similarity and a DOI link", () => {
    render(<SupervisorMatchCard match={makeMatch()} />);

    const papers = screen.getByRole("region", { name: "Matching recent papers" });
    const link = within(papers).getByRole("link", { name: "Neural ranking models" });
    expect(link).toHaveAttribute("href", "https://doi.org/10.1000/ranking");
    expect(papers).toHaveTextContent("Neural ranking models (2024) · 91% similar");
    // A paper with neither a DOI nor a landing page is listed without a link.
    expect(papers).toHaveTextContent("Query logs at scale (2022) · 47% similar");
    expect(within(papers).queryByRole("link", { name: "Query logs at scale" })).not.toBeInTheDocument();
  });

  it("links open postings to the posting page", () => {
    render(<SupervisorMatchCard match={makeMatch()} />);

    const postings = screen.getByRole("region", { name: "Open postings" });
    expect(within(postings).getByRole("link", { name: "Thesis: evaluating neural rankers" })).toHaveAttribute(
      "href",
      `/postings/${POSTING_ID}`
    );
    expect(postings).toHaveTextContent("Thesis Topic");
  });

  it("never renders an undisclosed email or institution", () => {
    const { container } = render(<SupervisorMatchCard match={makeMatch()} />);

    expect(container.querySelector('a[href^="mailto:"]')).toBeNull();
    expect(container).not.toHaveTextContent("@");
    expect(container).not.toHaveTextContent("Computer Science");
  });

  it("shows a disclosed email and institution", () => {
    const match = makeMatch();
    match.supervisor = {
      ...match.supervisor,
      institution: "Open University",
      department: "Computer Science",
      contact_email: "grace@open.edu",
    };
    render(<SupervisorMatchCard match={match} />);

    expect(screen.getByText(/Open University · Computer Science/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "grace@open.edu" })).toHaveAttribute("href", "mailto:grace@open.edu");
  });

  it("expands the signal breakdown on request", () => {
    render(<SupervisorMatchCard match={makeMatch()} />);

    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /how this was scored/i }));

    const table = screen.getByRole("table");
    expect(within(table).getByText("Shared topics")).toBeInTheDocument();
    expect(within(table).getByText("Closeness in meaning")).toBeInTheDocument();
    expect(table).toHaveTextContent("+0.280");
    expect(table).toHaveTextContent("scored on research topics only");
  });
});
