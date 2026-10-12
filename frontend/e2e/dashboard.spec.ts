import { expect, test, type Page } from "@playwright/test";
import { API_URL, DEMO, DEMO_PASSWORD, signInThroughTheForm, watch } from "./support";

/**
 * P4 — the signed-in home against the live API (FRONTEND_REDESIGN_PLAN.md §8): signing in lands
 * on /dashboard; each role's modules render without a failure; a page load makes at most seven
 * of the dashboard's own requests (the shell's session check and unread count are not the
 * dashboard's); a reload makes the same ones; nothing scrolls sideways on a phone.
 *
 * Two sign-ins (the backend allows 10 a minute per address; this file runs early, well before
 * the workflow test's sign-ins).
 */

const SHELL_REQUESTS = ["/api/v1/auth/me", "/api/v1/notifications/unread-count"];

/** Loads /dashboard afresh and returns the API requests it made, without the shell's. */
async function dashboardRequests(page: Page, load: () => Promise<unknown>): Promise<string[]> {
  const made: string[] = [];
  const record = (request: { url(): string; method(): string }) => {
    const url = request.url();
    if (!url.startsWith(API_URL)) return;
    const path = url.slice(API_URL.length).split("?")[0];
    if (!SHELL_REQUESTS.includes(path)) made.push(`${request.method()} ${path}`);
  };
  page.on("request", record);
  await load();
  await page.waitForLoadState("networkidle");
  await expect(page.locator('main [aria-busy="true"]')).toHaveCount(0);
  page.off("request", record);
  return made;
}

async function expectModules(page: Page, names: string[]) {
  for (const name of names) {
    const region = page.getByRole("region", { name, exact: true });
    await expect(region, name).toBeVisible();
    await expect(region.getByText(/could not be loaded|could not be found|could not be worked out/), `${name} failed`).toHaveCount(0);
  }
}

test("a student's home: the five modules, at most seven requests, the same on reload", async ({ page }) => {
  const network = watch(page);
  await signInThroughTheForm(page, DEMO.student, DEMO_PASSWORD);
  // Signing in with no destination lands on the home.
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole("heading", { level: 1, name: /^Welcome back/ })).toBeVisible();

  const modules = ["Needs attention", "Upcoming (next 30 days)", "Recommended for you", "Postings that fit you", "Reading progress"];
  const first = await dashboardRequests(page, () => page.goto("/dashboard"));
  await expectModules(page, modules);
  expect(first.length, first.join("\n")).toBeLessThanOrEqual(7);
  expect(new Set(first).size, `a request was made twice:\n${first.join("\n")}`).toBe(first.length);
  expect(first.some((r) => r.endsWith("/api/v1/postings/fit-scores"))).toBe(true);

  const reloaded = await dashboardRequests(page, () => page.reload());
  expect(reloaded.sort()).toEqual([...first].sort());
  await expectModules(page, modules);

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/dashboard");
  await expect(page.locator('main [aria-busy="true"]')).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
  network.expectClean();
});

test("a faculty member's home: the four modules and at most seven requests, none of a student's", async ({ page }) => {
  const network = watch(page);
  await signInThroughTheForm(page, DEMO.faculty, DEMO_PASSWORD);
  await expect(page).toHaveURL(/\/dashboard$/);

  const made = await dashboardRequests(page, () => page.goto("/dashboard"));
  await expectModules(page, ["Needs your decision", "Your open postings", "Upcoming deadlines", "Recommended papers"]);
  expect(made.length, made.join("\n")).toBeLessThanOrEqual(7);
  for (const studentOnly of ["/fit-scores", "/applications/mine/summary", "/recommendations/unified", "/calendar", "/reading-list"]) {
    expect(made.some((r) => r.includes(studentOnly)), `${studentOnly} requested for faculty`).toBe(false);
  }
  // The seeded faculty member has two open postings.
  await expect(page.getByRole("region", { name: "Your open postings" }).getByRole("listitem")).toHaveCount(2);

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/dashboard");
  await expect(page.locator('main [aria-busy="true"]')).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
  network.expectClean();
});
