/**
 * Phase 5.14 — saving a paper from literature search to the reading list.
 *
 * The Save button posts the work id to `POST /api/v1/reading-list` with the session's bearer
 * token, then shows the saved state. It is not rendered for a signed-out visitor, who has no list
 * to save to.
 */

import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { SaveToReadingListButton } from "../components/reading-list/SaveToReadingListButton";
import { SessionProvider, useSession } from "../components/auth/SessionProvider";
import { storeSession } from "../services/auth";
import { headersOf, jsonResponse, makeTokenResponse, makeUser } from "./factories";

const WORK_ID = "wk000000-0000-4000-8000-000000000001";
const ITEM_ID = "rl000000-0000-4000-8000-000000000001";

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn((url: string) => {
    if (url.endsWith("/api/v1/auth/me")) return Promise.resolve(jsonResponse(makeUser()));
    if (url.endsWith("/api/v1/reading-list")) {
      return Promise.resolve(jsonResponse({ id: ITEM_ID, work_id: WORK_ID, status: "TO_READ" }, 201));
    }
    return Promise.resolve(jsonResponse({ detail: `unexpected request ${url}` }, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
});

/** Shows the session status, so a test can wait until the session has been resolved. */
function SessionStatus() {
  const { status } = useSession();
  return <span data-testid="session-status">{status}</span>;
}

function renderButton(props: Partial<React.ComponentProps<typeof SaveToReadingListButton>> = {}) {
  return render(
    <SessionProvider>
      <SessionStatus />
      <SaveToReadingListButton workId={WORK_ID} {...props} />
    </SessionProvider>
  );
}

function readingListPosts() {
  return fetchMock.mock.calls.filter(
    ([url, init]) => String(url).endsWith("/api/v1/reading-list") && (init as RequestInit)?.method === "POST"
  );
}

describe("SaveToReadingListButton", () => {
  it("posts the work id with the bearer token and shows the saved state", async () => {
    storeSession(makeTokenResponse());
    const onSaved = vi.fn();
    renderButton({ onSaved });

    fireEvent.click(await screen.findByRole("button", { name: "Save to reading list" }));

    expect(await screen.findByRole("button", { name: "Saved to reading list" })).toBeInTheDocument();
    const posts = readingListPosts();
    expect(posts).toHaveLength(1);
    expect(JSON.parse(String((posts[0][1] as RequestInit).body))).toEqual({ work_id: WORK_ID });
    expect(headersOf(posts[0])["Authorization"]).toBe("Bearer header.payload.signature");
    expect(onSaved).toHaveBeenCalledWith(WORK_ID, ITEM_ID);
  });

  it("starts in the saved state without posting when the work is already saved", async () => {
    storeSession(makeTokenResponse());
    renderButton({ isSaved: true });

    const button = await screen.findByRole("button", { name: "Saved to reading list" });
    fireEvent.click(button);

    expect(readingListPosts()).toHaveLength(0);
  });

  it("is not rendered for a signed-out visitor", async () => {
    renderButton();

    await waitFor(() => expect(screen.getByTestId("session-status")).toHaveTextContent("unauthenticated"));
    expect(screen.queryByRole("button", { name: /reading list/i })).not.toBeInTheDocument();
    expect(readingListPosts()).toHaveLength(0);
  });
});
