/**
 * Phase 6.7 (Fix 5/9) — signing out revokes the token, and the password can be changed.
 *
 *  - Sign out asks the backend to revoke the account's tokens first (POST /auth/logout with
 *    the Bearer token), then clears the stored session even if that request fails.
 *  - The settings page changes the password: mismatched entries never reach the API, a wrong
 *    current password shows the backend's message, and on success this browser keeps working
 *    with the fresh token the backend returns (the old one is revoked).
 */

import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn(), back: vi.fn(), forward: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/settings/notifications",
  useSearchParams: () => new URLSearchParams(),
}));

import NotificationSettingsRoute from "../app/settings/notifications/page";
import { AuthMenu } from "../components/auth/AuthMenu";
import { SessionProvider } from "../components/auth/SessionProvider";
import { getStoredIdentity, storeSession } from "../services/auth";
import { PROFILE_ID, headersOf, jsonResponse, makeTokenResponse, makeUser } from "./factories";

let fetchMock: ReturnType<typeof vi.fn>;

function calls(path: string) {
  return fetchMock.mock.calls.filter(([url]) => String(url).endsWith(path));
}

beforeEach(() => {
  storeSession(makeTokenResponse());
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

describe("sign out", () => {
  function renderMenu(logoutResponse: () => Promise<Response>) {
    fetchMock.mockImplementation((url: string) => {
      if (url.endsWith("/api/v1/auth/me")) return Promise.resolve(jsonResponse(makeUser()));
      if (url.endsWith("/api/v1/auth/logout")) return logoutResponse();
      return Promise.resolve(jsonResponse({ detail: `unexpected request ${url}` }, 404));
    });
    return render(
      <SessionProvider>
        <AuthMenu />
      </SessionProvider>
    );
  }

  it("revokes the token on the backend, then clears the session", async () => {
    renderMenu(() => Promise.resolve(new Response(null, { status: 204 })));

    fireEvent.click(await screen.findByRole("button", { name: /Sign out/ }));

    expect(await screen.findByRole("link", { name: /Sign in/ })).toBeInTheDocument();
    const [logoutCall] = calls("/api/v1/auth/logout");
    expect((logoutCall[1] as RequestInit).method).toBe("POST");
    expect(headersOf(logoutCall).Authorization).toBe("Bearer header.payload.signature");
    expect(getStoredIdentity().token).toBeNull();
  });

  it("still signs this browser out when the backend cannot be reached", async () => {
    renderMenu(() => Promise.reject(new TypeError("Failed to fetch")));

    fireEvent.click(await screen.findByRole("button", { name: /Sign out/ }));

    expect(await screen.findByRole("link", { name: /Sign in/ })).toBeInTheDocument();
    expect(calls("/api/v1/auth/logout")).toHaveLength(1);
    expect(getStoredIdentity().token).toBeNull();
  });

  it("still signs out when the token was already revoked", async () => {
    renderMenu(() => Promise.resolve(jsonResponse({ detail: "Access token has been revoked." }, 401)));

    fireEvent.click(await screen.findByRole("button", { name: /Sign out/ }));

    expect(await screen.findByRole("link", { name: /Sign in/ })).toBeInTheDocument();
    expect(getStoredIdentity().token).toBeNull();
  });
});

describe("change password", () => {
  const PREFERENCES = {
    id: "np000000-0000-4000-8000-000000000001",
    profile_id: PROFILE_ID,
    email_enabled: true,
    in_app_enabled: true,
    deadline_reminders_enabled: true,
    extension_notifications_enabled: true,
    conflict_notifications_enabled: true,
    calendar_event_reminders_enabled: true,
    posting_match_alerts_enabled: false,
    posting_match_min_score: 60,
    created_at: "2026-10-01T10:00:00+00:00",
    updated_at: "2026-10-01T10:00:00+00:00",
  };

  function renderSettings(changeResponse: () => Promise<Response>) {
    fetchMock.mockImplementation((url: string) => {
      if (url.endsWith("/api/v1/auth/me")) return Promise.resolve(jsonResponse(makeUser()));
      if (url.endsWith("/api/v1/notifications/preferences")) return Promise.resolve(jsonResponse(PREFERENCES));
      if (url.includes("/api/v1/notifications/rules")) return Promise.resolve(jsonResponse({ rules: [], total: 0 }));
      if (url.endsWith("/api/v1/auth/change-password")) return changeResponse();
      return Promise.resolve(jsonResponse({}, 200));
    });
    return render(
      <SessionProvider>
        <NotificationSettingsRoute />
      </SessionProvider>
    );
  }

  async function fill(current: string, next: string, confirm: string) {
    fireEvent.change(await screen.findByLabelText("Current password"), { target: { value: current } });
    fireEvent.change(screen.getByLabelText(/^New password/), { target: { value: next } });
    fireEvent.change(screen.getByLabelText("Confirm new password"), { target: { value: confirm } });
    fireEvent.click(screen.getByRole("button", { name: "Change password" }));
  }

  it("keeps this browser signed in with the fresh token", async () => {
    renderSettings(() =>
      Promise.resolve(jsonResponse(makeTokenResponse({ access_token: "fresh.token.after-change" })))
    );

    await fill("old-password", "a-new-password", "a-new-password");

    expect(await screen.findByRole("status")).toHaveTextContent("Password changed");
    const [call] = calls("/api/v1/auth/change-password");
    expect(JSON.parse(String((call[1] as RequestInit).body))).toEqual({
      current_password: "old-password",
      new_password: "a-new-password",
    });
    expect(headersOf(call).Authorization).toBe("Bearer header.payload.signature");
    expect(getStoredIdentity().token).toBe("fresh.token.after-change");
    expect(screen.getByLabelText("Current password")).toHaveValue("");
  });

  it("refuses mismatched new passwords without calling the API", async () => {
    renderSettings(() => Promise.resolve(jsonResponse({}, 200)));

    await fill("old-password", "a-new-password", "a-different-one");

    expect(await screen.findByRole("alert")).toHaveTextContent("The new passwords do not match.");
    expect(calls("/api/v1/auth/change-password")).toHaveLength(0);
  });

  it("shows the backend's message for a wrong current password and keeps the session", async () => {
    renderSettings(() => Promise.resolve(jsonResponse({ detail: "Current password is incorrect." }, 400)));

    await fill("wrong-password", "a-new-password", "a-new-password");

    expect(await screen.findByRole("alert")).toHaveTextContent("Current password is incorrect.");
    await waitFor(() => expect(screen.getByRole("button", { name: "Change password" })).toBeEnabled());
    expect(getStoredIdentity().token).toBe("header.payload.signature");
  });
});
