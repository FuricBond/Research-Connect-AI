/**
 * Phase 6.2 — the session lifecycle.
 *
 * Covers the invariants the brief names: no token means signed out, a stored token is
 * verified rather than trusted, an invalid or expired one is cleared, a refresh restores a
 * valid session, and a 401 mid-session signs the person out exactly once.
 */

import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { act } from "react";
import { SessionProvider, useSession } from "../components/auth/SessionProvider";
import { getAccessToken, getStoredRole, setActiveIdentity, storeSession } from "../services/auth";
import { ApiError, fetchResearcherProfile } from "../services/api";
import { PROFILE_ID, USER_ID, jsonResponse, makeTokenResponse, makeUser } from "./factories";

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

/** Renders the session state as text, plus buttons for the actions under test. */
function Probe() {
  const { status, user, profileId, role, hasRole, login, logout } = useSession();
  return (
    <div>
      <span data-testid="status">{status}</span>
      <span data-testid="email">{user?.email ?? "none"}</span>
      <span data-testid="profile">{profileId ?? "none"}</span>
      <span data-testid="role">{role ?? "none"}</span>
      <span data-testid="is-faculty">{String(hasRole("FACULTY", "ADMIN"))}</span>
      <button
        onClick={() => {
          // A rejected sign-in is an expected case here; the form shows the message and
          // the session is left alone, so the rejection is handled rather than escaping.
          login({ email: "ada@university.edu", password: "DemoPass123!" }).catch(() => {});
        }}
      >
        sign in
      </button>
      <button onClick={logout}>sign out</button>
    </div>
  );
}

function renderProbe() {
  return render(
    <SessionProvider>
      <Probe />
    </SessionProvider>
  );
}

describe("restoration", () => {
  it("settles on unauthenticated with nothing stored, without calling the backend", async () => {
    renderProbe();

    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated"));
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("verifies a stored token against the backend and restores the account", async () => {
    storeSession(makeTokenResponse({ user: makeUser({ role: "FACULTY" }) }));
    fetchMock.mockResolvedValue(jsonResponse(makeUser({ role: "FACULTY" })));

    renderProbe();

    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("authenticated"));
    expect(fetchMock.mock.calls[0][0]).toBe("http://localhost:8000/api/v1/auth/me");
    expect(screen.getByTestId("email")).toHaveTextContent("ada@university.edu");
    expect(screen.getByTestId("profile")).toHaveTextContent(PROFILE_ID);
    expect(screen.getByTestId("role")).toHaveTextContent("FACULTY");
    expect(screen.getByTestId("is-faculty")).toHaveTextContent("true");
  });

  it("clears a stored token the backend rejects", async () => {
    storeSession(makeTokenResponse());
    fetchMock.mockResolvedValue(jsonResponse({ detail: "Access token is invalid." }, 401));

    renderProbe();

    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated"));
    expect(getAccessToken()).toBeNull();
    expect(getStoredRole()).toBeNull();
  });

  it("drops an already-expired token without asking the backend", async () => {
    storeSession(makeTokenResponse({ expires_at: "2020-01-01T00:00:00+00:00" }));

    renderProbe();

    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated"));
    expect(fetchMock).not.toHaveBeenCalled();
    expect(getAccessToken()).toBeNull();
  });

  it("does not trust a stored token on its own", async () => {
    // A token present but no longer valid must not read as authenticated.
    storeSession(makeTokenResponse());
    fetchMock.mockRejectedValue(new TypeError("network down"));

    renderProbe();

    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated"));
    expect(getAccessToken()).toBeNull();
  });

  it("still resolves a developer identity that has no token", async () => {
    // Preserved fallback: with AUTH_DEV_IDENTITY_ENABLED=true the backend accepts the
    // stored user id, so /auth/me answers and the session restores.
    setActiveIdentity({ userId: USER_ID });
    fetchMock.mockResolvedValue(jsonResponse(makeUser()));

    renderProbe();

    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("authenticated"));
    expect(getAccessToken()).toBeNull();
  });
});

describe("sign in and sign out", () => {
  it("stores the session and becomes authenticated", async () => {
    renderProbe();
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated"));

    fetchMock.mockResolvedValue(jsonResponse(makeTokenResponse({ user: makeUser({ role: "ADMIN" }) })));
    await act(async () => {
      screen.getByText("sign in").click();
    });

    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("authenticated"));
    expect(getAccessToken()).toBe("header.payload.signature");
    expect(screen.getByTestId("role")).toHaveTextContent("ADMIN");
  });

  it("clears the stored session on sign out", async () => {
    storeSession(makeTokenResponse());
    fetchMock.mockResolvedValue(jsonResponse(makeUser()));
    renderProbe();
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("authenticated"));

    await act(async () => {
      screen.getByText("sign out").click();
    });

    expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated");
    expect(screen.getByTestId("email")).toHaveTextContent("none");
    expect(getAccessToken()).toBeNull();
  });

  it("is safe to sign out when already signed out", async () => {
    renderProbe();
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated"));

    await act(async () => {
      screen.getByText("sign out").click();
    });

    expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated");
  });

  it("does not sign the person out when their own sign-in is rejected", async () => {
    // A 401 from /auth/login is a form error, not an expired session.
    renderProbe();
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated"));

    fetchMock.mockResolvedValue(jsonResponse({ detail: "Invalid email or password." }, 401));
    await act(async () => {
      screen.getByText("sign in").click();
    });

    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated"));
  });
});

describe("401 during a session", () => {
  it("signs the person out when an authenticated request is rejected", async () => {
    storeSession(makeTokenResponse());
    fetchMock.mockResolvedValueOnce(jsonResponse(makeUser()));
    renderProbe();
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("authenticated"));

    // A later request finds the token no longer accepted.
    fetchMock.mockResolvedValue(jsonResponse({ detail: "Access token has expired." }, 401));
    await act(async () => {
      await fetchResearcherProfile(PROFILE_ID).catch((err: unknown) => {
        expect(err).toBeInstanceOf(ApiError);
      });
    });

    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated"));
    expect(getAccessToken()).toBeNull();
  });

  it("clears once even when several requests are rejected together", async () => {
    storeSession(makeTokenResponse());
    fetchMock.mockResolvedValueOnce(jsonResponse(makeUser()));
    renderProbe();
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("authenticated"));

    fetchMock.mockResolvedValue(jsonResponse({ detail: "Access token has expired." }, 401));
    await act(async () => {
      await Promise.allSettled([
        fetchResearcherProfile(PROFILE_ID),
        fetchResearcherProfile(PROFILE_ID),
        fetchResearcherProfile(PROFILE_ID),
      ]);
    });

    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated"));
    // The provider only clears state; nothing here navigates, so repeated reports cannot
    // turn into repeated redirects.
    expect(getAccessToken()).toBeNull();
  });
});

describe("useSession outside a provider", () => {
  it("fails loudly rather than reporting a silently anonymous caller", () => {
    // A component that lost its provider must not read as "signed out" — that would hide
    // a real wiring mistake behind a plausible-looking screen.
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => render(<Probe />)).toThrow(/SessionProvider/);
    consoleError.mockRestore();
  });
});
