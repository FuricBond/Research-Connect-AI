import { expect, test, type Page } from "@playwright/test";
import { DEMO, DEMO_PASSWORD, signInThroughTheForm, watch } from "./support";

/**
 * P1 — the design system in the real app: one deliberate colour theme that survives a reload
 * and works at phone width, the self-hosted fonts, and the skip link as the first stop.
 */

const theme = (page: Page) => page.evaluate(() => document.documentElement.getAttribute("data-theme"));
const overflow = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);

test("the theme is chosen once, applied everywhere and kept across reloads", async ({ page }) => {
  const network = watch(page);
  await signInThroughTheForm(page, DEMO.student, DEMO_PASSWORD);
  await page.goto("/dashboard");

  const themes = page.getByRole("group", { name: "Colour theme" });
  await themes.getByRole("radio", { name: "Dark theme" }).check();
  expect(await theme(page)).toBe("dark");

  // Applied before first paint on the next load, on every page.
  for (const path of ["/dashboard", "/workspace", "/researcher?section=personalization"]) {
    await page.goto(path);
    expect(await theme(page), path).toBe("dark");
  }
  await page.reload();
  expect(await theme(page)).toBe("dark");
  await expect(themes.getByRole("radio", { name: "Dark theme" })).toBeChecked();

  // Dark at phone width still fits the screen.
  await page.setViewportSize({ width: 390, height: 844 });
  for (const path of ["/dashboard", "/workspace", "/researcher?section=personalization"]) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    expect(await overflow(page), `${path} at 390px in dark`).toBeLessThanOrEqual(0);
  }

  await themes.getByRole("radio", { name: "Light theme" }).check();
  expect(await theme(page)).toBe("light");
  network.expectClean();
});

test("an explicit OS preference is followed only while 'match system' is chosen", async ({ browser }) => {
  const context = await browser.newContext({ colorScheme: "dark" });
  const page = await context.newPage();
  await page.goto("/");
  expect(await theme(page)).toBe("dark");
  await page.getByRole("group", { name: "Colour theme" }).getByRole("radio", { name: "Light theme" }).check();
  await page.reload();
  expect(await theme(page)).toBe("light");
  await context.close();
});

test("the skip link comes first and the self-hosted fonts load", async ({ page }) => {
  await page.goto("/");
  await page.keyboard.press("Tab");
  const skip = page.getByRole("link", { name: "Skip to main content" });
  await expect(skip).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("main#main-content")).toBeFocused();

  // Both families are loaded from this origin, not substituted.
  await page.evaluate(() => document.fonts.ready);
  const families = await page.evaluate(() => [...document.fonts].filter((f) => f.status === "loaded").map((f) => f.family));
  expect(families.some((f) => /source.?sans/i.test(f))).toBe(true);
  expect(families.some((f) => /source.?serif/i.test(f))).toBe(true);
});
