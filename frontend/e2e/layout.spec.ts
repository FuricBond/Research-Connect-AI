import { expect, test, type Browser, type BrowserContextOptions, type Page } from "@playwright/test";
import { DEMO, DEMO_PASSWORD, accountMenu, openNavigation, primaryNav, signInThroughTheForm, watch } from "./support";

/**
 * P0.1 / P0.2 / P0.6, carried into the P2 shell — no page scrolls sideways and no destination
 * is lost, at desktop, tablet and phone widths.
 *
 * From 1024px the navigation is a sidebar; below, it opens in a drawer from the Menu button.
 * The account's own pages are in the account menu and the notifications behind the bell.
 * A failure here names the page and width.
 */
const WIDTHS = [1440, 1280, 1024, 768, 390, 360, 320];
const PAGES = [
  "/dashboard", "/", "/workspace", "/reading-list", "/calendar", "/notifications", "/postings", "/similar", "/browse",
  // Every profile section: each has its own panels, and a section's grid once outgrew the page.
  "/researcher", "/researcher?section=interests", "/researcher?section=recommendations",
  "/researcher?section=personalization", "/researcher?section=history", "/researcher/preferences",
  "/settings/notifications",
];

/** Every destination a signed-in student has in the primary navigation (utils/navigation.ts). */
const STUDENT_DESTINATIONS = [
  "Home",
  "Literature search",
  "Calls for papers",
  "Research postings",
  "Similar research",
  "Opportunity matcher",
  "Workspace",
  "Submissions",
  "Reading list",
  "Calendar",
  "Find a supervisor",
  "Find peers",
];
const ACCOUNT_PAGES = ["Researcher profile", "Research preferences", "Notification settings"];

async function horizontalOverflow(page: Page): Promise<number> {
  return page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
}

test("pages fit the screen and every destination stays reachable", async ({ page, browser }) => {
  test.setTimeout(300_000);
  const network = watch(page);
  await signInThroughTheForm(page, DEMO.student, DEMO_PASSWORD);

  for (const width of WIDTHS) {
    await test.step(`${width}px`, async () => {
      await page.setViewportSize({ width, height: width >= 1024 ? 900 : 844 });

      for (const path of PAGES) {
        await page.goto(path);
        await page.waitForLoadState("networkidle");
        expect(await horizontalOverflow(page), `${path} at ${width}px scrolls sideways`).toBeLessThanOrEqual(0);
      }

      await page.goto("/dashboard");
      const menuButton = page.getByRole("button", { name: "Menu", exact: true });
      let nav = primaryNav(page);
      if (width >= 1024) {
        // The sidebar: always there, no Menu button.
        await expect(menuButton).toBeHidden();
      } else {
        await expect(nav).toBeHidden();
        nav = await openNavigation(page);
        await expect(menuButton).toHaveAttribute("aria-expanded", "true");
        expect(await horizontalOverflow(page), `the open drawer at ${width}px scrolls sideways`).toBeLessThanOrEqual(0);
      }
      await expect(nav.getByRole("link", { name: "Home" })).toHaveAttribute("aria-current", "page");
      for (const name of STUDENT_DESTINATIONS) {
        const link = nav.getByRole("link", { name, exact: true });
        await expect(link, `${name} at ${width}px`).toHaveCount(1);
        await expect(link, `${name} at ${width}px`).toBeVisible();
      }
      if (width < 1024) {
        await page.keyboard.press("Escape");
        await expect(menuButton).toHaveAttribute("aria-expanded", "false");
        await expect(menuButton).toBeFocused();
      }

      // The account's pages, and the bell.
      const account = accountMenu(page);
      await account.click();
      await expect(account).toHaveAttribute("aria-expanded", "true");
      expect(await horizontalOverflow(page), `the open account menu at ${width}px scrolls sideways`).toBeLessThanOrEqual(0);
      for (const name of ACCOUNT_PAGES) await expect(page.getByRole("link", { name, exact: true }), `${name} at ${width}px`).toBeVisible();
      await page.keyboard.press("Escape");
      await expect(account).toHaveAttribute("aria-expanded", "false");
      await expect(account).toBeFocused();
      await expect(page.getByRole("banner").getByRole("link", { name: /^Notifications/ })).toBeVisible();
    });
  }

  network.expectClean();

  // Reuses this test's session: the backend allows 10 sign-ins a minute per address, and the
  // browser suite's are counted.
  await test.step("the header holds together at 200% text size", async () => {
    await headerHoldsTogetherAt200(browser, await page.context().storageState());
  });
});

/**
 * P2 audit (WCAG 1.4.4): with text enlarged to 200%, the header's controls do not overlap, stay
 * on screen and do not widen the page; the essential ones stay reachable — for a visitor and a
 * signed-in student, in both themes, at 320–1024px. Simulated with a 200% root font size (what a
 * larger browser text-size setting does to rem-based layouts); this is not a full WCAG
 * resize-text audit of every page.
 */
async function headerHoldsTogetherAt200(browser: Browser, studentState: BrowserContextOptions["storageState"]) {
  for (const theme of ["light", "dark"] as const) {
    for (const role of ["visitor", "student"] as const) {
      for (const width of [320, 360, 390, 768, 1024]) {
        await test.step(`${role}, ${theme}, ${width}px`, async () => {
          const context = await browser.newContext({ viewport: { width, height: 844 }, storageState: role === "student" ? studentState : undefined });
          await context.addInitScript((t) => {
            try { localStorage.setItem("rc-theme", t); } catch { /* storage blocked: the default theme */ }
            document.addEventListener("DOMContentLoaded", () => { document.documentElement.style.fontSize = "200%"; });
          }, theme);
          const page = await context.newPage();
          await page.goto(role === "student" ? "/dashboard" : "/browse");
          await page.waitForLoadState("networkidle");
          const header = await page.evaluate(() => {
            const vw = document.documentElement.clientWidth;
            const el = document.querySelector("body > div header, header")!;
            const controls = [...el.querySelectorAll<HTMLElement>("a, button, input")]
              .filter((c) => { const r = c.getBoundingClientRect(); return r.width > 0 && r.height > 0 && !c.closest("[hidden], dialog"); })
              .map((c) => ({ name: (c.getAttribute("aria-label") || c.textContent || c.getAttribute("placeholder") || "").trim(), r: c.getBoundingClientRect() }));
            const overlaps: string[] = [];
            for (let i = 0; i < controls.length; i++) for (let j = i + 1; j < controls.length; j++) {
              const a = controls[i].r, b = controls[j].r;
              const inside = (x: DOMRect, y: DOMRect) => x.left <= y.left && x.right >= y.right && x.top <= y.top && x.bottom >= y.bottom;
              if (inside(a, b) || inside(b, a)) continue; // the clear button inside the field
              if (a.left < b.right - 1 && b.left < a.right - 1 && a.top < b.bottom - 1 && b.top < a.bottom - 1) overlaps.push(`${controls[i].name} / ${controls[j].name}`);
            }
            return {
              overflow: el.scrollWidth - el.clientWidth,
              offscreen: controls.filter(({ r }) => r.left < -1 || r.right > vw + 1).map(({ name }) => name),
              overlaps,
              names: controls.map(({ name }) => name),
            };
          });
          expect(header.overflow, "the header is wider than the screen").toBeLessThanOrEqual(0);
          expect(header.offscreen, "header controls off screen").toEqual([]);
          expect(header.overlaps, "header controls overlap").toEqual([]);
          const has = (pattern: RegExp) => header.names.some((name) => pattern.test(name));
          expect(has(/^Search papers$/), "search").toBe(true);
          if (role === "visitor") {
            expect(has(/^Sign in$/), "Sign in").toBe(true);
            expect(has(/^Appearance$/), "Appearance").toBe(true);
          } else {
            expect(has(/account menu$/), "account menu").toBe(true);
            expect(has(/^Notifications/), "notifications").toBe(true);
          }
          if (width < 1024) expect(has(/^Menu$/), "Menu").toBe(true);
          await context.close();
        });
      }
    }
  }
}
