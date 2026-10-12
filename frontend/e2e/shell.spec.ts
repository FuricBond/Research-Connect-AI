import { expect, test, type Page } from "@playwright/test";
import { DEMO, DEMO_PASSWORD, accountMenu, primaryNav, signInThroughTheForm, watch } from "./support";

/**
 * P2 — the application shell in the real app: the global search through the URL, the phone
 * controls by keyboard, the session restore on /workspace, and role-aware navigation.
 */

const overflow = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);

test("the header search opens the search page with the query in the URL, and searches once", async ({ page }) => {
  const network = watch(page);
  await signInThroughTheForm(page, DEMO.student, DEMO_PASSWORD);
  await page.goto("/workspace");

  const searches: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/api/v1/discovery/research/search")) searches.push(request.url());
  });

  const field = page.getByRole("search", { name: "Papers" }).getByRole("searchbox", { name: "Search papers" });
  await field.fill("information retrieval");
  await field.press("Enter");
  await expect(page).toHaveURL(/\/\?q=information(%20|\+)retrieval$/);
  await expect(page.getByRole("button", { name: "Why this rank?" }).first()).toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole("searchbox", { name: "Search research literature" })).toHaveValue("information retrieval");
  // The search page has its own box; the header does not repeat it there.
  await expect(page.getByRole("searchbox", { name: "Search papers" })).toHaveCount(0);
  expect(searches).toHaveLength(1);

  // The URL is the search: reload keeps it, back returns to where the person was.
  await page.reload();
  await expect(page.getByRole("button", { name: "Why this rank?" }).first()).toBeVisible({ timeout: 60_000 });
  await page.goBack();
  await expect(page).toHaveURL(/\/workspace$/);
  network.expectClean();
});

test("on a 320px phone the search sheet, navigation drawer and account menu work by keyboard", async ({ page }) => {
  const network = watch(page);
  await page.setViewportSize({ width: 320, height: 640 });
  await signInThroughTheForm(page, DEMO.student, DEMO_PASSWORD);
  await page.goto("/workspace");
  expect(await overflow(page)).toBeLessThanOrEqual(0);

  // Search sheet: the field takes focus; Escape closes it and focus goes back.
  const searchButton = page.getByRole("button", { name: "Search papers", exact: true });
  await searchButton.click();
  const sheet = page.getByRole("dialog", { name: "Search papers" });
  await expect(sheet.getByRole("searchbox", { name: "Search papers" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(sheet).toBeHidden();
  await expect(searchButton).toBeFocused();

  // Drawer: Tab stays inside it; Escape closes; focus returns to Menu.
  const menu = page.getByRole("button", { name: "Menu", exact: true });
  await menu.focus();
  await page.keyboard.press("Enter");
  const drawer = page.getByRole("dialog", { name: "Menu" });
  await expect(drawer.getByRole("link", { name: "Workspace" })).toHaveAttribute("aria-current", "page");
  for (let i = 0; i < 4; i++) {
    await page.keyboard.press("Tab");
    expect(await drawer.evaluate((node) => node.contains(document.activeElement))).toBe(true);
  }
  expect(await overflow(page)).toBeLessThanOrEqual(0);
  await page.keyboard.press("Escape");
  await expect(drawer).toBeHidden();
  await expect(menu).toBeFocused();

  // Following a link from the drawer closes it and lands on the page.
  await menu.click();
  await drawer.getByRole("link", { name: "Reading list" }).click();
  await expect(page).toHaveURL(/\/reading-list$/);
  await expect(drawer).toBeHidden();

  // Account menu: opens from the keyboard, Escape returns focus.
  const account = accountMenu(page);
  await account.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("link", { name: "Researcher profile" })).toBeVisible();
  expect(await overflow(page)).toBeLessThanOrEqual(0);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("link", { name: "Researcher profile" })).toBeHidden();
  await expect(account).toBeFocused();
  network.expectClean();
});

test("/workspace never shows the signed-out shell while the session is restored, and does not shift", async ({ page }) => {
  const network = watch(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await signInThroughTheForm(page, DEMO.student, DEMO_PASSWORD);

  await page.addInitScript(() => {
    (window as unknown as { __cls: number }).__cls = 0;
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries() as (PerformanceEntry & { value: number; hadRecentInput: boolean })[]) {
        if (!entry.hadRecentInput) (window as unknown as { __cls: number }).__cls += entry.value;
      }
    }).observe({ type: "layout-shift", buffered: true });
  });
  // Hold the session check, as a slow network would.
  let release: () => void = () => undefined;
  const held = new Promise<void>((resolve) => (release = resolve));
  await page.route("**/api/v1/auth/me", async (route) => {
    await held;
    await route.continue();
  });

  await page.goto("/workspace", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("status").filter({ hasText: "Checking your session" })).toBeAttached();
  await expect(page.getByRole("link", { name: /sign in/i })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Opportunity Workspace" })).toHaveCount(0);
  expect(page.url()).toMatch(/\/workspace$/);

  release();
  await expect(page.getByRole("heading", { name: "Opportunity Workspace" })).toBeVisible();
  await page.waitForLoadState("networkidle");
  await expect(accountMenu(page)).toBeVisible();
  const cls = await page.evaluate(() => (window as unknown as { __cls: number }).__cls);
  expect(cls, "cumulative layout shift on /workspace at 390px").toBeLessThan(0.05);
  network.expectClean();
});

test("the navigation follows the role: faculty have no supervisor search", async ({ page }) => {
  const network = watch(page);
  await signInThroughTheForm(page, DEMO.faculty, DEMO_PASSWORD);
  await page.goto("/dashboard");

  const nav = primaryNav(page);
  await expect(nav.getByRole("link", { name: "Find peers" })).toBeVisible();
  await expect(nav.getByRole("link", { name: "Find a supervisor" })).toHaveCount(0);
  await expect(nav.getByRole("link", { name: "Platform administration" })).toHaveCount(0);
  await accountMenu(page).click();
  await expect(page.getByRole("banner").getByText("Faculty account", { exact: true })).toBeVisible();
  network.expectClean();
});
