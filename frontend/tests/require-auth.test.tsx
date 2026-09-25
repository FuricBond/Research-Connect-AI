/**
 * Phase 6.2 — route protection.
 *
 * The guard is UX, not a security boundary, so what matters here is that it never shows
 * protected content to the wrong person, never shows it before the session is known, and
 * redirects exactly once.
 */

import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

const replace = vi.fn();
let pathname = "/researcher";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, push: vi.fn(), back: vi.fn(), forward: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => pathname,
  useSearchParams: () => new URLSearchParams(),
}));

import { RequireAuth } from "../components/auth/RequireAuth";
import { SessionProvider } from "../components/auth/SessionProvider";
import { storeSession } from "../services/auth";
import { jsonResponse, makeTokenResponse, makeUser } from "./factories";

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  replace.mockClear();
  pathname = "/researcher";
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

function renderGuarded(roles?: readonly ("STUDENT" | "FACULTY" | "ADMIN")[]) {
  return render(
    <SessionProvider>
      <RequireAuth roles={roles}>
        <p>Protected content</p>
      </RequireAuth>
    </SessionProvider>
  );
}

describe("while the session is being restored", () => {
  it("renders neither the content nor a redirect", async () => {
    storeSession(makeTokenResponse());
    // A request that never settles keeps the provider in its loading state.
    fetchMock.mockReturnValue(new Promise(() => {}));

    renderGuarded();

    expect(screen.queryByText("Protected content")).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Checking your session");
    expect(replace).not.toHaveBeenCalled();
  });
});

describe("signed out", () => {
  it("redirects to sign in and carries the intended destination", async () => {
    renderGuarded();

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login?next=%2Fresearcher"));
    expect(screen.queryByText("Protected content")).not.toBeInTheDocument();
  });

  it("redirects only once", async () => {
    renderGuarded();

    await waitFor(() => expect(replace).toHaveBeenCalled());
    // A second redirect for the same state is how a loop starts.
    expect(replace).toHaveBeenCalledTimes(1);
  });

  it("omits the destination when it is the site root", async () => {
    pathname = "/";
    renderGuarded();

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
  });
});

describe("signed in", () => {
  it("renders the protected content", async () => {
    storeSession(makeTokenResponse());
    fetchMock.mockResolvedValue(jsonResponse(makeUser()));

    renderGuarded();

    await waitFor(() => expect(screen.getByText("Protected content")).toBeInTheDocument());
    expect(replace).not.toHaveBeenCalled();
  });
});

describe("role gating", () => {
  it("withholds the page from an account without the required role", async () => {
    storeSession(makeTokenResponse({ user: makeUser({ role: "STUDENT" }) }));
    fetchMock.mockResolvedValue(jsonResponse(makeUser({ role: "STUDENT" })));

    renderGuarded(["ADMIN"]);

    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(screen.queryByText("Protected content")).not.toBeInTheDocument();
    // A wrong role is not a missing session, so it must not bounce them to sign in.
    expect(replace).not.toHaveBeenCalled();
  });

  it("admits an account that holds the required role", async () => {
    storeSession(makeTokenResponse({ user: makeUser({ role: "ADMIN" }) }));
    fetchMock.mockResolvedValue(jsonResponse(makeUser({ role: "ADMIN" })));

    renderGuarded(["ADMIN"]);

    await waitFor(() => expect(screen.getByText("Protected content")).toBeInTheDocument());
  });

  it("admits any listed role", async () => {
    storeSession(makeTokenResponse({ user: makeUser({ role: "FACULTY" }) }));
    fetchMock.mockResolvedValue(jsonResponse(makeUser({ role: "FACULTY" })));

    renderGuarded(["FACULTY", "ADMIN"]);

    await waitFor(() => expect(screen.getByText("Protected content")).toBeInTheDocument());
  });

  it("does not let the client grant itself a role the backend did not give", async () => {
    // The stored role is a cache for presentation. What the backend returns from
    // /auth/me is what the guard honours.
    storeSession(makeTokenResponse({ user: makeUser({ role: "ADMIN" }) }));
    fetchMock.mockResolvedValue(jsonResponse(makeUser({ role: "STUDENT" })));

    renderGuarded(["ADMIN"]);

    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(screen.queryByText("Protected content")).not.toBeInTheDocument();
  });
});
