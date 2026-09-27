/**
 * "Save" on a recommendation must actually put the opportunity in the workspace.
 *
 * The bar recorded a SAVED interaction and told the researcher "Saved to workspace", but
 * nothing created a workspace item, so the workspace stayed empty. Saving now records the
 * interaction and adds the opportunity (idempotent on the backend).
 */

import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { OpportunityInteractionBar } from "../components/personalization/OpportunityInteractionBar";
import { storeSession } from "../services/auth";
import { PROFILE_ID, jsonResponse, makeTokenResponse } from "./factories";

const OPPORTUNITY_ID = "op000000-0000-4000-8000-000000000001";
let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  storeSession(makeTokenResponse());
  fetchMock = vi.fn((url: string) =>
    Promise.resolve(
      url.endsWith("/api/v1/workspace")
        ? jsonResponse({ id: "ws1", opportunity_id: OPPORTUNITY_ID, status: "SAVED" }, 201)
        : jsonResponse({ id: "in1", interaction_type: "SAVED" }, 201)
    )
  );
  vi.stubGlobal("fetch", fetchMock);
});

function calls(): { url: string; method: string; body: Record<string, unknown> }[] {
  return fetchMock.mock.calls.map(([url, init]) => ({
    url: String(url),
    method: (init as RequestInit | undefined)?.method ?? "GET",
    body: JSON.parse(String((init as RequestInit | undefined)?.body ?? "{}")),
  }));
}

describe("recommendation interaction bar", () => {
  it("adds a saved opportunity to the workspace", async () => {
    render(<OpportunityInteractionBar profileId={PROFILE_ID} opportunityId={OPPORTUNITY_ID} />);

    fireEvent.click(screen.getByRole("button", { name: "Save opportunity" }));

    expect(await screen.findByText("Saved to workspace")).toBeInTheDocument();
    const made = calls();
    expect(made.some((c) => c.url.includes(`/opportunities/${OPPORTUNITY_ID}/interactions`) && c.body.interaction_type === "SAVED")).toBe(true);
    expect(made.some((c) => c.url.endsWith("/api/v1/workspace") && c.method === "POST" && c.body.opportunity_id === OPPORTUNITY_ID)).toBe(true);
  });

  it("does not touch the workspace for other feedback", async () => {
    render(<OpportunityInteractionBar profileId={PROFILE_ID} opportunityId={OPPORTUNITY_ID} />);

    fireEvent.click(screen.getByRole("button", { name: "Mark interested" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(calls().some((c) => c.url.endsWith("/api/v1/workspace"))).toBe(false);
  });
});
