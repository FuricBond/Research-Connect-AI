/**
 * P1 — the design-system primitives (components/ui, components/research) behave and announce
 * themselves correctly: names, states, focus, and words instead of colours or enums.
 */

import React, { useState } from "react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { Button, IconButton } from "../components/ui/Button/Button";
import { Checkbox, RadioGroup, Select, Switch, TextArea, TextInput } from "../components/ui/Field/Field";
import { Dialog, Drawer } from "../components/ui/Dialog/Dialog";
import { EmptyState, SkeletonList } from "../components/ui/State/State";
import { PriorityLabel, StatusBadge } from "../components/ui/Badge/Badge";
import { PageHeader } from "../components/ui/PageHeader/PageHeader";
import { MatchScore, matchBand } from "../components/research/MatchScore";
import { applicationStatusMeta, postingStatusMeta, workspaceStatusMeta } from "../utils/status";

// jsdom has <dialog> but not showModal()/close(): give it the browser's behaviour.
beforeAll(() => {
  const proto = HTMLDialogElement.prototype as HTMLDialogElement & { showModal?: () => void; close?: () => void };
  proto.showModal = function showModal(this: HTMLDialogElement) {
    this.setAttribute("open", "");
  };
  proto.close = function close(this: HTMLDialogElement) {
    this.removeAttribute("open");
    this.dispatchEvent(new Event("close"));
  };
});

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

describe("form fields", () => {
  it("label every control, link hints and errors, and mark invalid input", () => {
    render(
      <>
        <TextInput label="ORCID iD" hint="For example 0000-0002-1825-0097." error="That is not an ORCID iD." defaultValue="x" />
        <Select label="Career stage" defaultValue="PHD">
          <option value="PHD">PhD</option>
        </Select>
        <TextArea label="Research summary" />
      </>
    );
    const orcid = screen.getByLabelText("ORCID iD");
    expect(orcid).toHaveAttribute("aria-invalid", "true");
    expect(orcid).toHaveAccessibleDescription("For example 0000-0002-1825-0097. That is not an ORCID iD.");
    expect(screen.getByRole("combobox", { name: "Career stage" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Research summary" })).toBeInTheDocument();
  });

  it("names checkboxes and groups radios under a legend", () => {
    function Radios() {
      const [value, setValue] = useState("light");
      return (
        <RadioGroup
          legend="Theme"
          name="theme"
          value={value}
          onChange={setValue}
          options={[
            { value: "light", label: "Light" },
            { value: "dark", label: "Dark" },
          ]}
        />
      );
    }
    render(
      <>
        <Checkbox label="Include closed calls" />
        <Radios />
      </>
    );
    expect(screen.getByRole("checkbox", { name: "Include closed calls" })).toBeInTheDocument();
    const group = screen.getByRole("group", { name: "Theme" });
    fireEvent.click(within(group).getByRole("radio", { name: "Dark" }));
    expect(within(group).getByRole("radio", { name: "Dark" })).toBeChecked();
  });

  it("gives a switch its label and state, and toggles it", () => {
    function Toggle() {
      const [on, setOn] = useState(false);
      return <Switch label="Email reminders" description="Sent the day before a deadline." checked={on} onChange={setOn} />;
    }
    render(<Toggle />);
    const control = screen.getByRole("switch", { name: "Email reminders" });
    expect(control).toHaveAttribute("aria-checked", "false");
    expect(control).toHaveAccessibleDescription("Sent the day before a deadline.");
    fireEvent.click(control);
    expect(control).toHaveAttribute("aria-checked", "true");
  });
});

function DialogHarness({ kind }: { kind: "dialog" | "drawer" }) {
  const [open, setOpen] = useState(false);
  const Surface = kind === "dialog" ? Dialog : Drawer;
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        Open details
      </button>
      <Surface open={open} onClose={() => setOpen(false)} title="Why this result?" description="How it was ranked.">
        <button type="button">Inside</button>
      </Surface>
    </>
  );
}

describe.each(["dialog", "drawer"] as const)("%s", (kind) => {
  it("is named by its title, takes focus, closes on Escape and returns focus", () => {
    render(<DialogHarness kind={kind} />);
    const trigger = screen.getByRole("button", { name: "Open details" });
    trigger.focus();
    fireEvent.click(trigger);

    const surface = screen.getByRole("dialog", { name: "Why this result?" });
    expect(surface).toHaveAccessibleDescription("How it was ranked.");
    expect(screen.getByRole("heading", { name: "Why this result?" })).toHaveFocus();
    expect(document.documentElement.style.overflow).toBe("hidden");

    // Escape fires the dialog's `cancel` event.
    fireEvent(surface, new Event("cancel", { cancelable: true }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
    expect(document.documentElement.style.overflow).toBe("");
  });

  it("closes from its named close button", () => {
    render(<DialogHarness kind={kind} />);
    fireEvent.click(screen.getByRole("button", { name: "Open details" }));
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});

describe("states", () => {
  it("says what is empty, why, and what to do", () => {
    render(<EmptyState title="No saved papers yet" description="Papers you save appear here." actions={<a href="/">Search papers</a>} />);
    expect(screen.getByRole("heading", { name: "No saved papers yet" })).toBeInTheDocument();
    expect(screen.getByText("Papers you save appear here.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Search papers" })).toBeInTheDocument();
  });

  it("marks loading placeholders busy with one spoken status", () => {
    const { container } = render(<SkeletonList rows={3} label="Loading results" />);
    expect(container.firstElementChild).toHaveAttribute("aria-busy", "true");
    expect(screen.getAllByRole("status")).toHaveLength(1);
    expect(screen.getByRole("status")).toHaveTextContent("Loading results");
  });

  it("gives a page exactly one h1", () => {
    render(<PageHeader title="Literature search" description="Find papers." />);
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });
});

describe("status semantics", () => {
  it("shows words, never enum values", () => {
    render(
      <>
        <StatusBadge meta={applicationStatusMeta("UNDER_REVIEW")} />
        <StatusBadge meta={applicationStatusMeta("REJECTED")} />
        <StatusBadge meta={workspaceStatusMeta("PLANNING")} />
        <StatusBadge meta={postingStatusMeta("CANCELLED")} />
        <StatusBadge meta={workspaceStatusMeta("SOMETHING_NEW")} />
      </>
    );
    for (const word of ["Under review", "Not selected", "Planning", "Cancelled", "Something new"]) {
      expect(screen.getByText(word)).toBeInTheDocument();
    }
    expect(document.body.textContent).not.toMatch(/[A-Z]{2,}_[A-Z]+/);
  });

  it("never colours a rejection as an error", () => {
    expect(applicationStatusMeta("REJECTED").tone).not.toBe("danger");
    expect(workspaceStatusMeta("REJECTED").tone).not.toBe("danger");
  });

  it("states priority as a word, not a colour", () => {
    render(<PriorityLabel priority="HIGH" />);
    expect(screen.getByText("High priority")).toBeInTheDocument();
  });

  it("presents a match as a band word with the exact value in text", () => {
    render(<MatchScore score={0.62} />);
    expect(screen.getByText(/Good match/)).toHaveTextContent("Good match · 62%");
    expect(matchBand(71)).toBe("strong");
    expect(matchBand(45)).toBe("good");
    expect(matchBand(30)).toBe("partial");
    expect(matchBand(10)).toBe("weak");
  });
});
