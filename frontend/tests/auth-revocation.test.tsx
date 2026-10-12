/**
 * Phase 6.7 (Fix 5/9) — signing out revokes the token, and the password can be changed.
 *
 *  - Sign out asks the backend to revoke the account's tokens first (POST /auth/logout with
 *    the Bearer token), then clears the stored session even if that request fails.
 *  - The settings page changes the password: mismatched entries never reach the API, a wrong
 *    current password shows the backend's message, and on success this browser keeps working
 *    with the fresh token the backend returns (the old one is revoked).
 *
 * P3: the password change moved from the notification settings to Settings → Account
 * (`/settings`), and explains each field's problem next to it; these tests follow the form.
 */

import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn(), back: vi.fn(), forward: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/settings",
  useSearchParams: () => new URLSearchParams(),
}));

import SettingsRoute from "../app/settings/page";
import { AccountMenu } from "../components/shell/AccountMenu";
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
        <AccountMenu />
      </SessionProvider>
    );
  }

  // P2.5: Sign out is in the account menu.
  async function clickSignOut() {
    fireEvent.click(await screen.findByRole("button", { name: /account menu/ }));
    fireEvent.click(screen.getByRole("button", { name: /Sign out/ }));
  }

  it("revokes the token on the backend, then clears the session", async () => {
    renderMenu(() => Promise.resolve(new Response(null, { status: 204 })));

    await clickSignOut();

    expect(await screen.findByRole("link", { name: /Sign in/ })).toBeInTheDocument();
    const [logoutCall] = calls("/api/v1/auth/logout");
    expect((logoutCall[1] as RequestInit).method).toBe("POST");
    expect(headersOf(logoutCall).Authorization).toBe("Bearer header.payload.signature");
    expect(getStoredIdentity().token).toBeNull();
  });

  it("still signs this browser out when the backend cannot be reached", async () => {
    renderMenu(() => Promise.reject(new TypeError("Failed to fetch")));

    await clickSignOut();

    expect(await screen.findByRole("link", { name: /Sign in/ })).toBeInTheDocument();
    expect(calls("/api/v1/auth/logout")).toHaveLength(1);
    expect(getStoredIdentity().token).toBeNull();
  });

  it("still signs out when the token was already revoked", async () => {
    renderMenu(() => Promise.resolve(jsonResponse({ detail: "Access token has been revoked." }, 401)));

    await clickSignOut();

    expect(await screen.findByRole("link", { name: /Sign in/ })).toBeInTheDocument();
    expect(getStoredIdentity().token).toBeNull();
  });
});

describe("change password", () => {
  function renderSettings(changeResponse: () => Promise<Response>) {
    fetchMock.mockImplementation((url: string) => {
      if (url.endsWith("/api/v1/auth/me")) return Promise.resolve(jsonResponse(makeUser()));
      if (url.endsWith("/api/v1/auth/change-password")) return changeResponse();
      return Promise.resolve(jsonResponse({ detail: `unexpected request ${url}` }, 404));
    });
    return render(
      <SessionProvider>
        <SettingsRoute />
      </SessionProvider>
    );
  }

  async function fill(current: string, next: string, confirm: string) {
    fireEvent.change(await screen.findByLabelText("Current password"), { target: { value: current } });
    fireEvent.change(screen.getByLabelText(/^New password/), { target: { value: next } });
    fireEvent.change(screen.getByLabelText("Confirm new password"), { target: { value: confirm } });
    fireEvent.click(screen.getByRole("button", { name: "Change password" }));
  }

  it("is in the account settings, not the notification settings", async () => {
    renderSettings(() => Promise.resolve(jsonResponse({}, 200)));
    expect(await screen.findByRole("heading", { level: 1, name: "Settings" })).toBeInTheDocument();
    expect(screen.getByRole("form", { name: "Change password" })).toBeInTheDocument();
    // The browser's password manager fills the right fields.
    expect(screen.getByLabelText("Current password")).toHaveAttribute("autocomplete", "current-password");
    expect(screen.getByLabelText(/^New password/)).toHaveAttribute("autocomplete", "new-password");
    expect(screen.getByLabelText("Confirm new password")).toHaveAttribute("autocomplete", "new-password");
  });

  it("keeps this browser signed in with the fresh token", async () => {
    renderSettings(() =>
      Promise.resolve(jsonResponse(makeTokenResponse({ access_token: "fresh.token.after-change" })))
    );

    await fill("old-password", "a-new-password", "a-new-password");

    expect(await screen.findByText(/Password changed/)).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Password changed. Your other sessions have been signed out.");
    const [call] = calls("/api/v1/auth/change-password");
    expect(JSON.parse(String((call[1] as RequestInit).body))).toEqual({
      current_password: "old-password",
      new_password: "a-new-password",
    });
    expect(headersOf(call).Authorization).toBe("Bearer header.payload.signature");
    expect(getStoredIdentity().token).toBe("fresh.token.after-change");
    expect(screen.getByLabelText("Current password")).toHaveValue("");
  });

  it("refuses mismatched new passwords without calling the API, and says so at the field", async () => {
    renderSettings(() => Promise.resolve(jsonResponse({}, 200)));

    await fill("old-password", "a-new-password", "a-different-one");

    expect(await screen.findByText("The new passwords do not match.")).toBeInTheDocument();
    const confirm = screen.getByLabelText("Confirm new password");
    expect(confirm).toHaveAttribute("aria-invalid", "true");
    expect(confirm).toHaveAccessibleDescription(/The new passwords do not match\./);
    expect(confirm).toHaveFocus();
    expect(calls("/api/v1/auth/change-password")).toHaveLength(0);
  });

  it("applies the registration rules to the new password before calling the API", async () => {
    renderSettings(() => Promise.resolve(jsonResponse({}, 200)));

    await fill("", "short", "short");

    expect(await screen.findByText("Enter your current password.")).toBeInTheDocument();
    expect(screen.getByText("Password must be at least 8 characters.")).toBeInTheDocument();
    // Focus goes to the first field that needs attention.
    expect(screen.getByLabelText("Current password")).toHaveFocus();
    expect(calls("/api/v1/auth/change-password")).toHaveLength(0);
  });

  it("shows the backend's message for a wrong current password and keeps the session", async () => {
    renderSettings(() => Promise.resolve(jsonResponse({ detail: "Current password is incorrect." }, 400)));

    await fill("wrong-password", "a-new-password", "a-new-password");

    expect(await screen.findByRole("alert")).toHaveTextContent("Current password is incorrect.");
    await waitFor(() => expect(screen.getByRole("button", { name: "Change password" })).toBeEnabled());
    expect(getStoredIdentity().token).toBe("header.payload.signature");
  });

  it("never shows a server error's body, and says so plainly when the server is unreachable", async () => {
    renderSettings(() => Promise.resolve(jsonResponse({ detail: "psycopg.errors.InternalError at 0x7f" }, 500)));
    await fill("old-password", "a-new-password", "a-new-password");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("We could not change the password right now.");
    expect(alert).not.toHaveTextContent("psycopg");

    fetchMock.mockImplementation((url: string) =>
      url.endsWith("/api/v1/auth/change-password") ? Promise.reject(new TypeError("Failed to fetch")) : Promise.resolve(jsonResponse(makeUser()))
    );
    fireEvent.click(screen.getByRole("button", { name: "Change password" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Could not reach the server."));
  });
});
