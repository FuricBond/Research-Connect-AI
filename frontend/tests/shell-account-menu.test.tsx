/**
 * P2.5 — the account menu: the account's own pages, the colour theme and Sign out, behind one
 * disclosure button in the header. A visitor gets Sign in, Create account and the theme.
 */

import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

let pathname = "/dashboard";
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn(), back: vi.fn(), forward: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => pathname,
  useSearchParams: () => new URLSearchParams(),
}));

import { SessionProvider } from "../components/auth/SessionProvider";
import { AccountMenu, initials } from "../components/shell/AccountMenu";
import { AppShell } from "../components/shell/AppShell";
import { clearActiveIdentity } from "../services/auth";
import { THEME_STORAGE_KEY } from "../utils/theme";
import { jsonResponse } from "./factories";
import { serveShell } from "./shell-support";

function renderMenu() {
  return render(
    <SessionProvider>
      <p>
        <button type="button">Elsewhere on the page</button>
      </p>
      <AccountMenu />
    </SessionProvider>
  );
}

beforeEach(() => {
  pathname = "/dashboard";
  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() }))
  );
  document.documentElement.removeAttribute("data-theme");
});

afterEach(() => {
  clearActiveIdentity();
  vi.unstubAllGlobals();
});

describe("signed in", () => {
  it("is a disclosure named for the account, closed until asked", async () => {
    serveShell("STUDENT");
    renderMenu();

    const trigger = await screen.findByRole("button", { name: "Ada Lovelace, account menu" });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    const panel = document.getElementById(trigger.getAttribute("aria-controls")!)!;
    expect(panel).not.toBeVisible();
    expect(screen.queryByRole("link", { name: "Researcher profile" })).not.toBeInTheDocument();

    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(panel).toBeVisible();
    for (const label of ["Researcher profile", "Research preferences", "Notification settings"]) {
      expect(within(panel).getByRole("link", { name: label })).toBeInTheDocument();
    }
    expect(within(panel).getByText("Student researcher account")).toBeInTheDocument();
    expect(within(panel).getByRole("group", { name: "Colour theme" })).toBeInTheDocument();
    expect(within(panel).getByRole("button", { name: "Sign out" })).toBeInTheDocument();
    // A disclosure of links and controls, not an ARIA menu with nested widgets.
    expect(panel.querySelector('[role="menu"], [role="menuitem"]')).toBeNull();
  });

  it("closes on Escape and returns focus to its button", async () => {
    serveShell("STUDENT");
    renderMenu();
    const trigger = await screen.findByRole("button", { name: /account menu/ });

    fireEvent.click(trigger);
    const profile = screen.getByRole("link", { name: "Researcher profile" });
    profile.focus();
    fireEvent.keyDown(profile, { key: "Escape" });

    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(trigger).toHaveFocus();
  });

  it("closes on a click outside, and when focus moves out of it", async () => {
    serveShell("STUDENT");
    renderMenu();
    const trigger = await screen.findByRole("button", { name: /account menu/ });
    const elsewhere = screen.getByRole("button", { name: "Elsewhere on the page" });

    fireEvent.click(trigger);
    fireEvent.pointerDown(elsewhere);
    expect(trigger).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(trigger);
    const signOut = screen.getByRole("button", { name: "Sign out" });
    fireEvent.blur(signOut, { relatedTarget: elsewhere });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
  });

  it("closes when the page changes, and stays closed on coming back", async () => {
    serveShell("STUDENT");
    const view = renderMenu();
    const trigger = await screen.findByRole("button", { name: /account menu/ });
    const rerender = () =>
      view.rerender(
        <SessionProvider>
          <p>
            <button type="button">Elsewhere on the page</button>
          </p>
          <AccountMenu />
        </SessionProvider>
      );

    fireEvent.click(trigger);
    pathname = "/calendar";
    rerender();
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    pathname = "/dashboard";
    rerender();
    expect(trigger).toHaveAttribute("aria-expanded", "false");
  });

  it("marks the account page you are on", async () => {
    serveShell("STUDENT");
    pathname = "/researcher/preferences";
    renderMenu();

    fireEvent.click(await screen.findByRole("button", { name: /account menu/ }));
    expect(screen.getByRole("link", { name: "Research preferences" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Researcher profile" })).not.toHaveAttribute("aria-current");
  });

  it("changes the colour theme from the menu and remembers it", async () => {
    serveShell("STUDENT");
    const view = renderMenu();

    fireEvent.click(await screen.findByRole("button", { name: /account menu/ }));
    fireEvent.click(screen.getByRole("radio", { name: "Dark theme" }));
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");

    // A fresh page reads the stored choice back.
    view.unmount();
    renderMenu();
    fireEvent.click(await screen.findByRole("button", { name: /account menu/ }));
    expect(screen.getByRole("radio", { name: "Dark theme" })).toBeChecked();
  });

  it("is the only theme control in the shell", async () => {
    serveShell("STUDENT");
    render(
      <SessionProvider>
        <AppShell>
          <p>Page</p>
        </AppShell>
      </SessionProvider>
    );
    await screen.findByRole("button", { name: /account menu/ });
    expect(document.querySelectorAll("fieldset")).toHaveLength(1);
    expect(screen.queryByRole("group", { name: "Colour theme" })).not.toBeInTheDocument(); // closed
  });
});

describe("focus after signing out (P2 audit)", () => {
  async function signOutWith(logout: () => Promise<Response>) {
    serveShell("STUDENT", { other: (url) => (url.endsWith("/api/v1/auth/logout") ? logout() : undefined) });
    renderMenu();
    const trigger = await screen.findByRole("button", { name: /account menu/ });
    trigger.focus();
    fireEvent.click(trigger);
    const signOut = screen.getByRole("button", { name: "Sign out" });
    signOut.focus();
    fireEvent.click(signOut);
    return signOut;
  }

  it("moves to the Sign in link once the browser is signed out, not to the page body", async () => {
    let answer: (response: Response) => void = () => undefined;
    const signOut = await signOutWith(() => new Promise<Response>((resolve) => (answer = resolve)));

    // Not before the result is known: still on the (busy) Sign out button.
    expect(signOut).toHaveAttribute("aria-busy", "true");
    expect(screen.queryByRole("link", { name: "Sign in" })).not.toBeInTheDocument();

    await act(async () => answer(new Response(null, { status: 204 })));
    const signIn = await screen.findByRole("link", { name: "Sign in" });
    await waitFor(() => expect(signIn).toHaveFocus());
    expect(document.activeElement).not.toBe(document.body);
  });

  it("does the same when the server cannot be reached (this browser is signed out anyway)", async () => {
    await signOutWith(() => Promise.reject(new TypeError("Failed to fetch")));
    const signIn = await screen.findByRole("link", { name: "Sign in" });
    await waitFor(() => expect(signIn).toHaveFocus());
  });

  it("does not take focus when a visitor simply arrives", async () => {
    serveShell(null);
    renderMenu();
    const signIn = await screen.findByRole("link", { name: "Sign in" });
    expect(signIn).not.toHaveFocus();
  });
});

describe("signed out", () => {
  it("offers sign-in, registration and the theme, and nothing about an account", async () => {
    serveShell(null);
    renderMenu();

    expect(await screen.findByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login");
    expect(screen.getByRole("link", { name: "Create account" })).toHaveAttribute("href", "/register");
    expect(screen.queryByRole("button", { name: /account menu/ })).not.toBeInTheDocument();

    const appearance = screen.getByRole("button", { name: "Appearance" });
    fireEvent.click(appearance);
    expect(appearance).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("group", { name: "Colour theme" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Researcher profile" })).not.toBeInTheDocument();
  });
});

describe("while the session is being restored", () => {
  it("shows a placeholder, not the visitor's Sign in", async () => {
    serveShell("STUDENT", { pendingSession: true });
    const { container } = renderMenu();
    await act(async () => undefined);

    expect(screen.queryByRole("link", { name: "Sign in" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /account menu|Appearance/ })).not.toBeInTheDocument();
    expect(container.querySelector('[aria-hidden="true"]')).not.toBeNull();
  });
});

describe("initials", () => {
  it("takes the first and last name", () => {
    expect(initials("Ada Lovelace")).toBe("AL");
    expect(initials("Ada King Lovelace")).toBe("AL");
    expect(initials("plato")).toBe("P");
    expect(initials("  ")).toBe("?");
  });
});
