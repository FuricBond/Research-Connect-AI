/**
 * P2.1–P2.3 — one application shell: a primary navigation grouped by task (the sidebar from
 * 1024px, a drawer below), role-aware, with the current page exposed as aria-current="page".
 *
 * Replaces the P0 bridge (one bar of tabs plus a "More" menu, AppHeader and DiscoveryNavbar).
 * Hiding a destination is a convenience: the pages stay guarded and the backend authorises.
 */

import fs from "node:fs";
import path from "node:path";
import React from "react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

let pathname = "/workspace";
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn(), back: vi.fn(), forward: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => pathname,
  useSearchParams: () => new URLSearchParams(),
}));

import { SessionProvider } from "../components/auth/SessionProvider";
import { AppShell } from "../components/shell/AppShell";
import { Drawer } from "../components/ui/Dialog/Dialog";
import { ACCOUNT_ITEMS, NAV_SECTIONS, SHELL_HREFS, currentHref, navigationFor } from "../utils/navigation";
import { clearActiveIdentity } from "../services/auth";
import type { PlatformRole } from "../types/auth";
import { installDialogPolyfill, requestsTo, serveShell } from "./shell-support";

function renderShell() {
  return render(
    <SessionProvider>
      <AppShell>
        <p>Page content</p>
      </AppShell>
    </SessionProvider>
  );
}

beforeAll(installDialogPolyfill);

beforeEach(() => {
  pathname = "/workspace";
});

afterEach(() => {
  clearActiveIdentity();
  vi.unstubAllGlobals();
});

describe("navigation model", () => {
  const labels = (role: PlatformRole | null) => navigationFor(role).flatMap((section) => section.items.map((item) => item.label));

  it("shows each role its own destinations and hides the rest", () => {
    expect(labels("STUDENT")).toContain("Find a supervisor");
    expect(labels("FACULTY")).not.toContain("Find a supervisor");
    expect(labels("ADMIN")).not.toContain("Find a supervisor");
    expect(labels("ADMIN")).toContain("Platform administration");
    expect(labels("STUDENT")).not.toContain("Platform administration");
    expect(labels("FACULTY")).not.toContain("Platform administration");
    // Every signed-in role keeps the destinations it had before P2.
    for (const role of ["STUDENT", "FACULTY", "ADMIN"] as const) {
      for (const label of ["Home", "Literature search", "Calls for papers", "Research postings", "Workspace", "Reading list", "Calendar", "Find peers"]) {
        expect(labels(role), `${role} ${label}`).toContain(label);
      }
    }
  });

  it("offers a visitor only the public discovery pages", () => {
    // P5: similar papers and venue matching left the navigation; they are actions on a paper.
    expect(labels(null).sort()).toEqual(["Calls for papers", "Literature search", "Research postings"].sort());
  });

  it("lists the paper-based tools nowhere: they work from a chosen paper (P5, plan §7, §10)", () => {
    const listed = [...NAV_SECTIONS.flatMap((section) => section.items), ...ACCOUNT_ITEMS].map((item) => item.href);
    expect(listed).not.toContain("/similar");
    expect(listed).not.toContain("/opportunities");
  });

  it("groups destinations by task, in a fixed order", () => {
    // P6: "People" became "For you", with the recommendations first (plan §6).
    expect(navigationFor("STUDENT").map((section) => section.label)).toEqual([undefined, "Discover", "My research", "For you"]);
    expect(navigationFor("ADMIN").map((section) => section.label)).toEqual([undefined, "Discover", "My research", "For you", "Administration"]);
    expect(navigationFor(null).map((section) => section.label)).toEqual(["Discover"]);
  });

  it("keeps notifications out of the lists: the bell is the one way in", () => {
    const listed = [...NAV_SECTIONS.flatMap((section) => section.items), ...ACCOUNT_ITEMS].map((item) => item.href);
    expect(listed).not.toContain("/notifications");
    expect(SHELL_HREFS.filter((href) => href === "/notifications")).toHaveLength(1);
  });

  it("names the one shell link that stands for the current page: the most specific", () => {
    expect(currentHref("/")).toBe("/");
    expect(currentHref("/workspace/abc/submission")).toBe("/workspace");
    expect(currentHref("/postings/applications")).toBe("/postings");
    expect(currentHref("/researcher")).toBe("/researcher");
    expect(currentHref("/researcher/preferences")).toBe("/researcher/preferences");
    // P3: the account menu's Settings stands for the account settings and the pages beneath them.
    expect(currentHref("/settings")).toBe("/settings");
    expect(currentHref("/settings/notifications")).toBe("/settings");
    expect(currentHref("/notifications")).toBe("/notifications");
    expect(currentHref("/login")).toBeNull();
    // "/" is the search page only, not every page.
    expect(currentHref("/browse")).toBe("/browse");
    // P5: a call's page belongs to the calls; the paper tools to the search they are reached from.
    expect(currentHref("/calls/2b0e0b5c-8d1f-4c55-9f0a-7a1d3c9e4f21")).toBe("/browse");
    expect(currentHref("/similar")).toBe("/");
    expect(currentHref("/opportunities")).toBe("/");
    expect(currentHref("/similarity")).toBeNull();
  });

  it("covers every page of the app, and links only to pages that exist", () => {
    const appDir = path.join(__dirname, "../app");
    const routes: string[] = [];
    (function walk(dir: string) {
      for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
        const full = path.join(dir, entry.name);
        if (entry.isDirectory()) walk(full);
        else if (entry.name === "page.tsx") {
          const route = "/" + path.relative(appDir, dir).split(path.sep).filter(Boolean).join("/");
          routes.push(route === "/." ? "/" : route);
        }
      }
    })(appDir);
    expect(routes.length).toBeGreaterThan(20);

    // Sign-in and registration are reached from the header's account controls.
    const reachedFromAccountControls = ["/login", "/register"];
    for (const route of routes) {
      if (reachedFromAccountControls.includes(route)) continue;
      expect(currentHref(route.replace(/\[[^\]]+\]/g, "x")), route).not.toBeNull();
    }
    for (const href of SHELL_HREFS) expect(routes, href).toContain(href);
  });
});

describe("primary navigation", () => {
  it("marks the current page with aria-current, once, and never with visible 'Active' text", async () => {
    serveShell("STUDENT");
    pathname = "/workspace/abc/submission";
    renderShell();

    const nav = await screen.findByRole("navigation", { name: "Primary" });
    const current = await within(nav).findByRole("link", { name: "Workspace" });
    expect(current).toHaveAttribute("aria-current", "page");
    expect(nav.querySelectorAll('[aria-current="page"]')).toHaveLength(1);
    expect(within(nav).getByRole("link", { name: "Literature search" })).not.toHaveAttribute("aria-current");
    expect(screen.queryByText("Active")).not.toBeInTheDocument();
  });

  it("labels each group, so a screen reader hears where a link belongs", async () => {
    serveShell("STUDENT");
    renderShell();

    const nav = await screen.findByRole("navigation", { name: "Primary" });
    const research = await within(nav).findByRole("list", { name: "My research" });
    for (const label of ["Workspace", "Submissions", "Reading list", "Calendar"]) {
      expect(within(research).getByRole("link", { name: label })).toBeInTheDocument();
    }
    expect(within(nav).getByRole("list", { name: "Discover" })).toBeInTheDocument();
    const forYou = within(nav).getByRole("list", { name: "For you" });
    expect(within(forYou).getAllByRole("link").map((link) => link.textContent?.trim())).toEqual(["Recommendations", "Find a supervisor", "Find peers"]);
  });

  it("gives an administrator the administration page and no supervisor search", async () => {
    serveShell("ADMIN");
    pathname = "/admin";
    renderShell();

    const nav = await screen.findByRole("navigation", { name: "Primary" });
    expect(await within(nav).findByRole("link", { name: "Platform administration" })).toHaveAttribute("aria-current", "page");
    expect(within(nav).queryByRole("link", { name: "Find a supervisor" })).not.toBeInTheDocument();
  });

  it("gives faculty neither the supervisor search nor administration", async () => {
    serveShell("FACULTY");
    renderShell();

    const nav = await screen.findByRole("navigation", { name: "Primary" });
    expect(await within(nav).findByRole("link", { name: "Find peers" })).toBeInTheDocument();
    expect(within(nav).queryByRole("link", { name: "Find a supervisor" })).not.toBeInTheDocument();
    expect(within(nav).queryByRole("link", { name: "Platform administration" })).not.toBeInTheDocument();
  });

  it("shows a visitor the public pages only and asks nothing about notifications", async () => {
    const fetchMock = serveShell(null);
    pathname = "/";
    renderShell();

    const nav = await screen.findByRole("navigation", { name: "Primary" });
    expect(await within(nav).findByRole("link", { name: "Literature search" })).toHaveAttribute("aria-current", "page");
    expect(within(nav).getAllByRole("link")).toHaveLength(3);
    expect(within(nav).queryByRole("link", { name: "Home" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^Notifications/ })).not.toBeInTheDocument();
    await act(async () => undefined);
    expect(requestsTo(fetchMock, "/notifications/unread-count")).toBe(0);
  });

  it("renders one primary navigation and the skip link's target", async () => {
    serveShell("STUDENT");
    renderShell();

    await screen.findByRole("link", { name: "Workspace" });
    expect(screen.getAllByRole("navigation", { name: "Primary" })).toHaveLength(1);
    const main = screen.getByRole("main");
    expect(main).toHaveAttribute("id", "main-content");
    expect(main).toHaveAttribute("tabindex", "-1");
    expect(within(main).getByText("Page content")).toBeInTheDocument();
    expect(document.querySelectorAll("#main-content")).toHaveLength(1);
  });
});

describe("navigation drawer (below 1024px)", () => {
  it("opens from the Menu button, holds the same navigation, and closes with Escape", async () => {
    serveShell("STUDENT");
    renderShell();

    const menu = screen.getByRole("button", { name: "Menu" });
    expect(menu).toHaveAttribute("aria-expanded", "false");
    expect(menu).toHaveAttribute("aria-haspopup", "dialog");
    await screen.findByRole("link", { name: "Workspace" });

    menu.focus();
    fireEvent.click(menu);
    expect(menu).toHaveAttribute("aria-expanded", "true");
    const drawer = screen.getByRole("dialog", { name: "Menu" });
    const drawerNav = within(drawer).getByRole("navigation", { name: "Primary" });
    expect(within(drawerNav).getByRole("link", { name: "Workspace" })).toHaveAttribute("aria-current", "page");
    expect(within(drawerNav).getByRole("link", { name: "Find a supervisor" })).toBeInTheDocument();

    // Escape is the dialog's "cancel".
    fireEvent(drawer, new Event("cancel", { cancelable: true }));
    expect(menu).toHaveAttribute("aria-expanded", "false");
    expect(drawer).not.toHaveAttribute("open");
    expect(menu).toHaveFocus();
  });

  it("has no unnamed Tab stop: Close, then the links (P2 audit)", async () => {
    serveShell("STUDENT");
    renderShell();
    await screen.findByRole("link", { name: "Workspace" });
    fireEvent.click(screen.getByRole("button", { name: "Menu" }));
    const drawer = screen.getByRole("dialog", { name: "Menu" });

    // Everything in the drawer the Tab key can reach, in document order.
    const stops = [...drawer.querySelectorAll<HTMLElement>("a[href], button, input, select, textarea, [tabindex]")].filter(
      (el) => el.tabIndex >= 0 && !el.hasAttribute("disabled")
    );
    const names = stops.map((el) => el.getAttribute("aria-label") ?? el.textContent?.trim());
    expect(names).toEqual([
      "Close",
      "Home",
      "Literature search",
      "Calls for papers",
      "Research postings",
      "Workspace",
      "Submissions",
      "Reading list",
      "Calendar",
      "Recommendations",
      "Find a supervisor",
      "Find peers",
    ]);
    // The title receives focus on open but is not a Tab stop.
    expect(drawer.querySelector("h2")).toHaveAttribute("tabindex", "-1");
  });

  it("keeps the scrollable body a Tab stop in drawers of plain text (keyboard scrolling)", () => {
    render(
      <Drawer open onClose={() => undefined} title="Why this result?">
        <p>A long explanation with no controls in it.</p>
      </Drawer>
    );
    const body = screen.getByText("A long explanation with no controls in it.").parentElement!;
    expect(body).toHaveAttribute("tabindex", "0");
  });

  it("closes when a link is followed, and when the page changes", async () => {
    serveShell("STUDENT");
    const view = renderShell();
    await screen.findByRole("link", { name: "Workspace" });
    const menu = screen.getByRole("button", { name: "Menu" });

    fireEvent.click(menu);
    const drawer = screen.getByRole("dialog", { name: "Menu" });
    const link = within(drawer).getByRole("link", { name: "Workspace" });
    // jsdom cannot load another document; the shell's own click handling is what is tested.
    link.addEventListener("click", (event) => event.preventDefault());
    fireEvent.click(link);
    expect(menu).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(menu);
    expect(menu).toHaveAttribute("aria-expanded", "true");
    pathname = "/calendar";
    view.rerender(
      <SessionProvider>
        <AppShell>
          <p>Page content</p>
        </AppShell>
      </SessionProvider>
    );
    await waitFor(() => expect(menu).toHaveAttribute("aria-expanded", "false"));

    // Coming back to the page it was opened on (the back button) does not reopen it.
    pathname = "/workspace";
    view.rerender(
      <SessionProvider>
        <AppShell>
          <p>Page content</p>
        </AppShell>
      </SessionProvider>
    );
    expect(menu).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("dialog", { name: "Menu" })).not.toBeInTheDocument();
  });
});
