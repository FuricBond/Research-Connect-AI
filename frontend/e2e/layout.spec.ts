import { expect, test, type Page } from "@playwright/test";
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

test("pages fit the screen and every destination stays reachable", async ({ page }) => {
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
});
