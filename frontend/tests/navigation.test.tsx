/**
 * P0.2 — the header navigation keeps every destination reachable and says where you are.
 *
 * Before P0 the navigation was one horizontal strip of up to 13 tabs: at 1440px only six were
 * visible and the rest sat off-screen with no way to tell, there was no aria-current, and the
 * screen-reader "unread" text escaped the strip and widened every page (P0.1). Now each
 * destination is either in the bar at a given width or in the "More" menu, which lists exactly
 * the ones the bar is not showing.
 */

import fs from "node:fs";
import path from "node:path";
import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";

let pathname = "/workspace";
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn(), back: vi.fn(), forward: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => pathname,
  useSearchParams: () => new URLSearchParams(),
}));

import { DiscoveryNavbar } from "../components/discovery/DiscoveryNavbar";
import { SessionProvider } from "../components/auth/SessionProvider";
import { NAV_ITEMS, menuGroups, navigationFor } from "../utils/navigation";
import { clearActiveIdentity, storeSession } from "../services/auth";
import type { PlatformRole } from "../types/auth";
import { jsonResponse, makeTokenResponse, makeUser } from "./factories";

function signIn(role: PlatformRole | null) {
  if (role === null) {
    clearActiveIdentity();
  } else {
    storeSession(makeTokenResponse({ user: makeUser({ role }) }));
  }
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      if (url.endsWith("/api/v1/auth/me")) return Promise.resolve(jsonResponse(makeUser({ role: role ?? "STUDENT" })));
      if (url.includes("/notifications/unread-count")) return Promise.resolve(jsonResponse({ unread_count: 4 }));
      return Promise.resolve(jsonResponse({ detail: `unexpected ${url}` }, 404));
    })
  );
}

function renderNavbar() {
  return render(
    <SessionProvider>
      <DiscoveryNavbar />
    </SessionProvider>
  );
}

beforeEach(() => {
  pathname = "/workspace";
});

afterEach(() => {
  clearActiveIdentity();
});

describe("navigation model", () => {
  const labels = (role: PlatformRole | null) => navigationFor(role, "/").map((item) => item.label);

  it("shows each role its own destinations and hides the rest", () => {
    expect(labels("STUDENT")).toContain("Find a Supervisor");
    expect(labels("FACULTY")).not.toContain("Find a Supervisor");
    expect(labels("ADMIN")).toContain("Administration");
    expect(labels("STUDENT")).not.toContain("Administration");
    expect(labels("FACULTY")).not.toContain("Administration");
  });

  it("offers a visitor only the public discovery pages", () => {
    expect(labels(null).sort()).toEqual(
      ["Browse All Calls", "Literature Search", "Opportunity Matcher", "Research Postings", "Similar Research"].sort()
    );
  });

  it("never loses a destination: each is either in the bar at some width or in the menu", () => {
    for (const role of ["STUDENT", "FACULTY", "ADMIN", null] as const) {
      const items = navigationFor(role, "/");
      const inMenu = new Set(menuGroups(items).flatMap((group) => group.items.map((item) => item.href)));
      for (const item of items) {
        // "always" items are in the bar at every width; every other one must be in the menu,
        // which shows it for the widths where the bar does not.
        expect(item.placement === "always" || inMenu.has(item.href), `${role} ${item.label}`).toBe(true);
      }
    }
  });

  it("marks exactly one destination as the current page", () => {
    const active = navigationFor("STUDENT", "/workspace/abc/submission").filter((item) => item.active);
    expect(active.map((item) => item.label)).toEqual(["Opportunity Workspace"]);
    const settings = navigationFor("STUDENT", "/settings/notifications").filter((item) => item.active);
    expect(settings.map((item) => item.label)).toEqual(["Notifications"]);
  });

  it("knows every route a destination stands for", () => {
    // A destination added to the app but not to the navigation would be undiscoverable.
    const hrefs = NAV_ITEMS.map((item) => item.href);
    for (const route of ["/", "/browse", "/postings", "/similar", "/opportunities", "/workspace", "/submissions", "/reading-list", "/calendar", "/peers", "/supervisors", "/researcher", "/admin", "/notifications", "/dashboard"]) {
      expect(hrefs, route).toContain(route);
    }
  });
});

describe("DiscoveryNavbar", () => {
  it("exposes the current page with aria-current and never as visible 'Active' text", async () => {
    signIn("STUDENT");
    renderNavbar();

    const current = await screen.findByRole("link", { name: "Opportunity Workspace" });
    expect(current).toHaveAttribute("aria-current", "page");
    expect(screen.queryByText("Active")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Literature Search" })).not.toHaveAttribute("aria-current");
  });

  it("opens and closes the More menu from the keyboard and lists the remaining destinations", async () => {
    signIn("STUDENT");
    renderNavbar();

    const more = await screen.findByRole("button", { name: /More|Menu/ });
    expect(more).toHaveAttribute("aria-expanded", "false");
    // The menu is not in the accessibility tree until it is opened.
    expect(screen.queryByRole("link", { name: "Researcher Profile" })).not.toBeInTheDocument();

    fireEvent.click(more);
    expect(more).toHaveAttribute("aria-expanded", "true");
    const menu = document.getElementById(more.getAttribute("aria-controls")!)!;
    for (const label of ["Researcher Profile", "Reading List", "Research Calendar", "Submissions", "Find Peers", "Find a Supervisor"]) {
      expect(within(menu).getByRole("link", { name: label })).toBeInTheDocument();
    }
    expect(within(menu).getByRole("group", { name: "My research" })).toBeInTheDocument();

    fireEvent.keyDown(document, { key: "Escape" });
    expect(more).toHaveAttribute("aria-expanded", "false");
    expect(more).toHaveFocus();
  });

  it("keeps the unread count on the Notifications link, outside the menu", async () => {
    signIn("STUDENT");
    renderNavbar();

    const link = await screen.findByRole("link", { name: /Notifications\s*4 unread/ });
    expect(link).toHaveAttribute("href", "/notifications");
  });

  it("lists Administration only for an administrator", async () => {
    signIn("ADMIN");
    pathname = "/admin";
    renderNavbar();

    fireEvent.click(await screen.findByRole("button", { name: /More|Menu/ }));
    const admin = await screen.findByRole("link", { name: "Administration" });
    expect(admin).toHaveAttribute("aria-current", "page");
  });

  it("shows a visitor no account destinations and asks nothing about notifications", async () => {
    signIn(null);
    pathname = "/";
    renderNavbar();

    expect(await screen.findByRole("link", { name: "Literature Search" })).toHaveAttribute("aria-current", "page");
    expect(screen.queryByRole("link", { name: /Notifications/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Home" })).not.toBeInTheDocument();
    await waitFor(() => expect(fetch).not.toHaveBeenCalledWith(expect.stringContaining("unread-count"), expect.anything()));
  });
});

describe("navigation styles (P0.1 root cause)", () => {
  const css = fs.readFileSync(path.join(__dirname, "../styles/globals.css"), "utf8");

  function rule(selector: string): string {
    const start = css.indexOf(`${selector},`) >= 0 ? css.indexOf(`${selector},`) : css.indexOf(`${selector} {`);
    expect(start, selector).toBeGreaterThanOrEqual(0);
    return css.slice(start, css.indexOf("}", start));
  }

  it("contains the visually hidden unread text inside its tab", () => {
    // Without a positioned ancestor the absolutely positioned hidden text escaped the bar and
    // made every signed-in page 2,420px wide.
    expect(rule(".discovery-nav-tab")).toMatch(/position:\s*relative/);
    expect(rule(".discovery-nav-menu-link")).toMatch(/position:\s*relative/);
  });

  it("does not make the bar a horizontal scroller", () => {
    expect(rule(".discovery-nav-tabs")).not.toMatch(/overflow-x:\s*auto/);
  });
});
