/**
 * P6 — the researcher card shared by Find a supervisor and Find peers (DESIGN_SYSTEM.md §9
 * ResearcherCard). It keeps every guarantee the Phase 5.13 supervisor card had: the server's tier
 * and score, shared topics, matching papers with year, similarity and a DOI link, open postings
 * linking to the posting, nothing undisclosed shown, and the signal breakdown on request.
 */

import React from "react";
import { describe, expect, it } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";

import { ResearcherCard } from "../components/people/ResearcherCard";
import type { PeerProfile } from "../types/peer";
import type { MatchingPaper, OpenPostingRef } from "../types/supervisor";

const POSTING_ID = "po000000-0000-4000-8000-000000000001";

const person = (overrides: Partial<PeerProfile> = {}): PeerProfile => ({
  profile_id: "fa000000-0000-4000-8000-000000000001",
  full_name: "Dr. Grace Hopper",
  institution: null,
  department: null,
  academic_status: "FACULTY",
  contact_email: null,
  collaboration_status: "OPEN_TO_ENQUIRIES",
  collaboration_interests: [],
  collaboration_note: null,
  ...overrides,
});

const papers: MatchingPaper[] = [
  { work_id: "w1", title: "Neural ranking models", publication_year: 2024, similarity: 0.91, shared_topics: ["ranking"], doi: "10.1000/ranking", landing_page_url: "https://example.org/ranking" },
  { work_id: "w2", title: "Query logs at scale", publication_year: 2022, similarity: 0.47, shared_topics: [], doi: null, landing_page_url: null },
];
const postings: OpenPostingRef[] = [{ posting_id: POSTING_ID, title: "Thesis: evaluating neural rankers", posting_type: "THESIS_TOPIC", application_deadline: null }];

function renderCard(overrides: Partial<PeerProfile> = {}) {
  return render(
    <ResearcherCard
      person={person(overrides)}
      score={0.62}
      tier="STRONG"
      confidence={0.8}
      reasons={["You share research topics: information retrieval, ranking.", "Two of their recent papers are close to yours.", "They are taking students."]}
      sharedTopics={["information-retrieval", "ranking", "evaluation", "query-logs"]}
      papers={papers}
      postings={postings}
      signals={[
        { key: "TOPIC_FIT", label: "Shared topics", rawScore: 0.8, contribution: 0.28, explanation: "You share research topics: information retrieval, ranking." },
        { key: "SEMANTIC_FIT", label: "Closeness in meaning", rawScore: 0, contribution: 0, explanation: "Your interests could not be embedded, so this match is scored on research topics only." },
      ]}
    />
  );
}

describe("ResearcherCard", () => {
  it("shows the name, availability, the tier in the API's words with its value, and the strongest reasons", () => {
    renderCard();
    const card = screen.getByRole("article", { name: "Dr. Grace Hopper" });
    expect(within(card).getByRole("heading", { level: 3, name: "Dr. Grace Hopper" })).toBeInTheDocument();
    expect(card).toHaveTextContent("Faculty");
    expect(card).toHaveTextContent("Open to enquiries");
    expect(card).toHaveTextContent("Strong match · 62%");
    expect(card).toHaveTextContent("You share research topics: information retrieval, ranking.");
    expect(card).toHaveTextContent("Two of their recent papers are close to yours.");
  });

  it("shows at most three shared topics, the rest under How this was scored", () => {
    renderCard();
    const shared = screen.getByRole("list", { name: "Topics you share with Dr. Grace Hopper" });
    expect(within(shared).getAllByRole("listitem")).toHaveLength(3);
    expect(shared).toHaveTextContent("information retrieval");
    expect(screen.getByText(/and 1 more/)).toBeInTheDocument();
  });

  it("lists matching papers with year, similarity and a link only where there is one", () => {
    renderCard();
    const link = screen.getByRole("link", { name: "Neural ranking models (opens in new tab)" });
    expect(link).toHaveAttribute("href", "https://doi.org/10.1000/ranking");
    expect(link.closest("li")).toHaveTextContent("Neural ranking models (opens in new tab) (2024) · 91% similar");
    const plain = screen.getByText(/Query logs at scale/).closest("li")!;
    expect(plain).toHaveTextContent("Query logs at scale (2022) · 47% similar");
    expect(within(plain).queryByRole("link")).not.toBeInTheDocument();
  });

  it("links open postings to the posting page", () => {
    renderCard();
    const link = screen.getByRole("link", { name: "Thesis: evaluating neural rankers" });
    expect(link).toHaveAttribute("href", `/postings/${POSTING_ID}`);
    expect(link.closest("li")).toHaveTextContent("Thesis Topic");
  });

  it("never renders an undisclosed email or institution", () => {
    const { container } = renderCard();
    expect(container.querySelector('a[href^="mailto:"]')).toBeNull();
    expect(container).not.toHaveTextContent("@");
    expect(container).not.toHaveTextContent(/unknown/i);
  });

  it("shows a disclosed email and institution", () => {
    renderCard({ institution: "Open University", department: "Computer Science", contact_email: "grace@open.edu" });
    expect(screen.getByText("Faculty · Open University · Computer Science")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "grace@open.edu" })).toHaveAttribute("href", "mailto:grace@open.edu");
  });

  it("keeps the signal breakdown behind How this was scored", () => {
    const { container } = renderCard();
    const details = container.querySelector("details")!;
    expect(details).not.toHaveAttribute("open");
    fireEvent.click(within(details).getByText("How this was scored"));

    const table = within(details).getByRole("table");
    expect(within(table).getByText("Shared topics")).toBeInTheDocument();
    expect(within(table).getByText("Closeness in meaning")).toBeInTheDocument();
    expect(table).toHaveTextContent("+0.280");
    expect(table).toHaveTextContent("scored on research topics only");
    expect(details).toHaveTextContent("Confidence 80%");
    expect(details).toHaveTextContent("They are taking students.");
  });
});
