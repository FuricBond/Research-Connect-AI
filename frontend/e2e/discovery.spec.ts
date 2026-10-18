import { expect, test, type Page } from "@playwright/test";
import { API_URL, watch } from "./support";

/**
 * P5 — search and discovery in the real app, as a visitor (every page here is public, so this
 * file signs nobody in and costs nothing from the sign-in budget): the whole search lives in the
 * address through reload, back and forward; the paper and Evidence panels are dialogs that hand
 * focus back; calls for papers keep their filters into a call's page and back; a call's page asks
 * for two things and says "not found" for an id it cannot use; nothing scrolls sideways on a phone.
 * The literature corpus is the one the API suite seeds (test_03).
 */

const overflow = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);

/** The API requests a page makes (path and query), from now until `stop()`. */
function record(page: Page) {
  const made: string[] = [];
  const listener = (request: { url(): string }) => {
    const url = request.url();
    if (url.startsWith(API_URL)) made.push(url.slice(API_URL.length));
  };
  page.on("request", listener);
  return { made, stop: () => page.off("request", listener) };
}

test("the search keeps its query, filters and page in the address through reload, back and forward", async ({ page }) => {
  const network = watch(page);
  await page.goto("/?q=information%20retrieval");
  await expect(page.getByRole("button", { name: /^Why this result\?/ }).first()).toBeVisible({ timeout: 60_000 });

  const searches = record(page);
  // The suite's 1280px viewport shows the filter rail (below 1280px the filters are in a sheet).
  await page.getByRole("complementary", { name: "Filters" }).getByLabel("Open access only").check();
  await expect(page).toHaveURL(/\/\?q=information%20retrieval&oa=1$/);
  await expect(page.getByRole("heading", { level: 2, name: /results?$/ })).toBeVisible({ timeout: 60_000 });
  expect(searches.made.filter((url) => url.includes("/discovery/research/search"))).toHaveLength(1);
  expect(searches.made.find((url) => url.includes("/discovery/research/search"))).toContain("is_oa=true");

  // Sorting reorders the page in hand: no request.
  await page.getByLabel("Sort").selectOption("cited");
  await expect(page).toHaveURL(/&sort=cited$/);
  expect(searches.made.filter((url) => url.includes("/discovery/research/search"))).toHaveLength(1);
  searches.stop();

  await page.reload();
  await expect(page.getByLabel("Sort")).toHaveValue("cited");
  await expect(page.getByRole("searchbox", { name: "Search research literature" })).toHaveValue("information retrieval");
  await expect(page.getByRole("complementary", { name: "Filters" }).getByLabel("Open access only")).toBeChecked();

  await page.goBack();
  await expect(page).toHaveURL(/\/\?q=information%20retrieval&oa=1$/);
  await expect(page.getByLabel("Sort")).toHaveValue("relevance");
  await page.goBack();
  await expect(page).toHaveURL(/\/\?q=information%20retrieval$/);
  await expect(page.getByRole("complementary", { name: "Filters" }).getByLabel("Open access only")).not.toBeChecked();
  await page.goForward();
  await expect(page.getByRole("complementary", { name: "Filters" }).getByLabel("Open access only")).toBeChecked();
  network.expectClean();
});

test("the paper panel and the Evidence panel are dialogs that hand focus back", async ({ page }) => {
  const network = watch(page);
  await page.goto("/?q=information%20retrieval");
  const why = page.getByRole("button", { name: /^Why this result\?/ }).first();
  await expect(why).toBeVisible({ timeout: 60_000 });

  const title = page.locator(".paper-card").first().getByRole("heading").getByRole("button");
  const name = (await title.textContent())?.trim() ?? "";
  await title.click();
  const panel = page.getByRole("dialog", { name });
  await expect(panel).toBeVisible();
  await expect(panel.getByRole("heading", { level: 2 })).toBeFocused();
  await expect(panel.getByRole("heading", { name: "Similar papers" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(panel).toBeHidden();
  await expect(title).toBeFocused();

  await why.click();
  const evidence = page.getByRole("dialog", { name: "Why this result?" });
  await expect(evidence).toBeVisible();
  await expect(evidence.getByText("Technical details")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(evidence).toBeHidden();
  await expect(why).toBeFocused();
  network.expectClean();
});

test("calls for papers keep their filters into a call's page and back; the call's page asks for two things", async ({ page }) => {
  const network = watch(page);
  await page.goto("/browse?type=CONFERENCE");
  await expect(page.getByLabel("Type")).toHaveValue("CONFERENCE");
  const first = page.locator(".opportunity-card").first();
  await expect(first).toBeVisible();
  await expect(first).toContainText("Conference");

  const requests = record(page);
  await first.getByRole("heading").getByRole("link").click();
  await expect(page).toHaveURL(/\/calls\/[0-9a-f-]{36}$/);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.getByRole("heading", { level: 2, name: "Dates" })).toBeVisible();
  await expect(page.getByRole("heading", { level: 2, name: "Venue risk" })).toBeVisible();
  await page.waitForLoadState("networkidle");
  requests.stop();
  const own = requests.made.filter((url) => url.startsWith("/api/opportunities/")).map((url) => url.replace(/[0-9a-f-]{36}/, "{id}"));
  expect(own.sort()).toEqual(["/api/opportunities/{id}", "/api/opportunities/{id}/risk-explanation"]);
  await expect(page).toHaveTitle(/ — ResearchConnect AI$/);
  await expect(page.getByRole("navigation", { name: "Breadcrumb" }).getByRole("link", { name: "Calls for papers" }).first()).toHaveAttribute("href", "/browse?type=CONFERENCE");

  await page.reload();
  await expect(page.getByRole("heading", { level: 2, name: "Dates" })).toBeVisible();
  await page.goBack();
  await expect(page).toHaveURL(/\/browse\?type=CONFERENCE$/);
  await expect(page.getByLabel("Type")).toHaveValue("CONFERENCE");
  network.expectClean();
});

test("a call's page says 'not found' for an unknown call, and asks nothing for an id it cannot use", async ({ page }) => {
  await page.goto("/calls/00000000-0000-4000-8000-000000000000");
  await expect(page.getByRole("heading", { level: 1, name: "Call for papers not found" })).toBeVisible();

  const requests = record(page);
  await page.goto("/calls/not-an-id");
  await expect(page.getByRole("heading", { level: 1, name: "Call for papers not found" })).toBeVisible();
  await page.waitForLoadState("networkidle");
  requests.stop();
  expect(requests.made.filter((url) => url.startsWith("/api/opportunities"))).toEqual([]);
});

test("search results, panels and calls fit a 320px phone", async ({ page }) => {
  const network = watch(page);
  await page.setViewportSize({ width: 320, height: 640 });
  await page.goto("/?q=information%20retrieval");
  await expect(page.getByRole("button", { name: /^Why this result\?/ }).first()).toBeVisible({ timeout: 60_000 });
  expect(await overflow(page), "search results at 320px").toBeLessThanOrEqual(0);

  await page.getByRole("button", { name: /^Filters/ }).click();
  await expect(page.getByRole("dialog", { name: "Filters" })).toBeVisible();
  expect(await overflow(page), "filter sheet at 320px").toBeLessThanOrEqual(0);
  await page.keyboard.press("Escape");

  await page.getByRole("button", { name: /^Why this result\?/ }).first().click();
  await expect(page.getByRole("dialog", { name: "Why this result?" })).toBeVisible();
  expect(await overflow(page), "Evidence panel at 320px").toBeLessThanOrEqual(0);
  await page.keyboard.press("Escape");

  await page.goto("/browse");
  await expect(page.locator(".opportunity-card").first()).toBeVisible();
  expect(await overflow(page), "calls at 320px").toBeLessThanOrEqual(0);
  await page.locator(".opportunity-card").first().getByRole("heading").getByRole("link").click();
  await expect(page.getByRole("heading", { level: 2, name: "Dates" })).toBeVisible();
  expect(await overflow(page), "a call's page at 320px").toBeLessThanOrEqual(0);
  network.expectClean();
});
