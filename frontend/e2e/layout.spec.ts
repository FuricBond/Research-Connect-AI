import { expect, test, type Page } from "@playwright/test";
import { DEMO, DEMO_PASSWORD, signInThroughTheForm, watch } from "./support";

/**
 * P0.1 / P0.2 / P0.6 — no page scrolls sideways and no destination is lost, at desktop,
 * tablet and phone widths.
 *
 * Before P0 the navigation's hidden "unread" text escaped the bar and made every signed-in page
 * 2,420px wide, only 2–6 of 13 tabs were visible, and the calendar and workspace cards ran off
 * narrow screens. A failure here names the page and width.
 */
const WIDTHS = [1440, 1280, 1024, 768, 390, 360, 320];
const PAGES = ["/dashboard", "/", "/workspace", "/reading-list", "/calendar", "/notifications", "/postings", "/researcher", "/similar", "/browse"];

/** Every destination a signed-in student has (utils/navigation.ts). */
const STUDENT_DESTINATIONS = [
  "Home",
  "Literature Search",
  "Browse All Calls",
  "Research Postings",
  "Similar Research",
  "Opportunity Matcher",
  "Opportunity Workspace",
  "Submissions",
  "Reading List",
  "Research Calendar",
  "Find Peers",
  "Find a Supervisor",
  "Researcher Profile",
  "Notifications",
];

async function horizontalOverflow(page: Page): Promise<number> {
  return page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
}

test("pages fit the screen and every destination stays reachable", async ({ page }) => {
  test.setTimeout(240_000);
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

      // Every destination is either in the bar or, after opening the menu, in the menu.
      await page.goto("/dashboard");
      const nav = page.getByRole("navigation", { name: "Main" });
      const menuButton = nav.getByRole("button", { name: /^(More|Menu)$/ });
      await menuButton.click();
      await expect(menuButton).toHaveAttribute("aria-expanded", "true");
      expect(await horizontalOverflow(page), `the open menu at ${width}px scrolls sideways`).toBeLessThanOrEqual(0);
      for (const name of STUDENT_DESTINATIONS) {
        const link = nav.getByRole("link", { name: new RegExp(`^${name}`) });
        await expect(link, `${name} at ${width}px`).toHaveCount(1);
        await expect(link, `${name} at ${width}px`).toBeVisible();
      }
      await page.keyboard.press("Escape");
      await expect(menuButton).toHaveAttribute("aria-expanded", "false");
      await expect(menuButton).toBeFocused();
    });
  }

  network.expectClean();
});
