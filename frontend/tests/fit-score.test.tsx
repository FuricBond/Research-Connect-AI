/**
 * P6 — FitScore (DESIGN_SYSTEM.md §9): the API's band or tier word first, the exact value second,
 * the strongest reason; a partial or low fit reads as something to act on, with a link to the
 * preferences; no score is "Fit not scored", never zero.
 */

import React from "react";
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { FitScore } from "../components/research/FitScore";

describe("FitScore", () => {
  it("leads with the API's band and never re-bands the value", () => {
    const { container } = render(<FitScore score={58} band="Strong" reason="Shares your research topics" />);
    expect(container).toHaveTextContent("Strong fit · 58%");
    expect(container).toHaveTextContent("Shares your research topics");
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("turns a partial fit into an action, with the missing skills and the way to add them", () => {
    const { container } = render(<FitScore score={34} band="Partial" gaps={["PyTorch", "Docker"]} />);
    expect(container).toHaveTextContent("Partial fit · 34%");
    expect(container).toHaveTextContent("To improve it: PyTorch, Docker.");
    expect(screen.getByRole("link", { name: "Update your research preferences" })).toHaveAttribute("href", "/researcher/preferences");
  });

  it("says Fit not scored when there is nothing to compare, never 0%", () => {
    const { container } = render(<FitScore score={null} band={null} />);
    expect(container).toHaveTextContent("Fit not scored");
    expect(container).not.toHaveTextContent("0%");
  });

  it("uses the supervisor and peer tiers' own words", () => {
    const { container, rerender } = render(<FitScore score={55} tier="MODERATE" />);
    expect(container).toHaveTextContent("Moderate match · 55%");
    expect(screen.queryByRole("link")).not.toBeInTheDocument();

    rerender(<FitScore score={21} tier="EXPLORATORY" />);
    expect(container).toHaveTextContent("Exploratory · 21%");
    expect(screen.getByRole("link", { name: "Add research topics" })).toHaveAttribute("href", "/researcher/preferences");
  });
});
