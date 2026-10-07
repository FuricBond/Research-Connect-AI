/**
 * P1 — the design-system primitives (components/ui, components/research) behave and announce
 * themselves correctly: names, states, focus, and words instead of colours or enums.
 */

import React, { useState } from "react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { Button, IconButton } from "../components/ui/Button/Button";
import { PageHeader } from "../components/ui/PageHeader/PageHeader";

describe("Button", () => {
  it("is a native button that defaults to type=button", () => {
    render(<Button>Save paper</Button>);
    expect(screen.getByRole("button", { name: "Save paper" })).toHaveAttribute("type", "button");
  });

  it("keeps its name and is marked busy while loading", () => {
    render(<Button loading>Save paper</Button>);
    const button = screen.getByRole("button", { name: "Save paper" });
    expect(button).toHaveAttribute("aria-busy", "true");
  });

  it("does not act when disabled", () => {
    const onClick = vi.fn();
    render(
      <Button disabled onClick={onClick}>
        Apply
      </Button>
    );
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(onClick).not.toHaveBeenCalled();
  });

  it("names an icon-only button", () => {
    render(<IconButton label="Close" icon={<span aria-hidden="true">×</span>} />);
    expect(screen.getByRole("button", { name: "Close" })).toBeInTheDocument();
  });
});

describe("states", () => {
  it("gives a page exactly one h1", () => {
    render(<PageHeader title="Literature search" description="Find papers." />);
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });
});
