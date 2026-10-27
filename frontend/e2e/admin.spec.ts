import { expect, test, type Page, type Request } from "@playwright/test";
import { API_URL, DEMO, DEMO_PASSWORD, newPassword, primaryNav, signInThroughTheForm, uniqueEmail, watch } from "./support";

/**
 * P10 — the administration pages against the live API (FRONTEND_REDESIGN_PLAN.md §15): the demo
 * administrator signs in and lands on the overview (six requests, once each), reads the research
 * data monitor (the e2e stack runs without the scheduler, so the refresh is off and has never run),
 * pages through the accounts with the page in the address (back and forward included), and changes
 * a fresh account's role: dismissing the confirmation sends nothing, confirming sends one change,
 * and the new role survives a reload. The pages fit every width.
 *
 * Two sign-ins (the target's registration, the administrator's). This spec runs first, so it ends
 * by waiting for a fresh sign-in minute: the specs after it (auth, dashboard…) use most of it.
 */
const WIDTHS = [1440, 1024, 768, 390, 320];

/** The API requests made while `act` runs, as "METHOD /path?query", with their bodies. */
async function requestsDuring(page: Page, act: () => Promise<unknown>): Promise<{ list: string[]; bodies: unknown[] }> {
  const list: string[] = [];
  const bodies: unknown[] = [];
  const record = (request: Request) => {
    const url = request.url();
    if (!url.startsWith(API_URL)) return;
    list.push(`${request.method()} ${url.slice(API_URL.length)}`);
    const body = request.postData();
    if (body) bodies.push(JSON.parse(body));
  };
  page.on("request", record);
  await act();
  await page.waitForLoadState("networkidle");
  page.off("request", record);
  return { list, bodies };
}

const own = (list: string[]) => list.filter((entry) => !/\/auth\/me$|\/notifications\/unread-count$/.test(entry));

test("a visitor asking for an administration page is sent to sign in", async ({ page }) => {
  await page.goto("/admin/users");
  await expect(page).toHaveURL(/\/login\?next=%2Fadmin%2Fusers$/);
});

test("an administrator reads the overview and the research data, and changes a role with a confirmation", async ({ page, request }) => {
  test.setTimeout(300_000);
  const name = `Browser target ${Math.random().toString(36).slice(2, 8)}`;
  const email = uniqueEmail("role-target");
  const registered = await request.post(`${API_URL}/api/v1/auth/register`, { data: { email, password: newPassword(), full_name: name, role: "STUDENT" } });
  expect(registered.status(), await registered.text()).toBe(201);

  const network = watch(page);
  await test.step("signing in lands on the overview, the administrator's home", async () => {
    await signInThroughTheForm(page, DEMO.admin, DEMO_PASSWORD);
    await expect(page).toHaveURL(/\/admin$/);
    await expect(page.getByRole("heading", { level: 1, name: "Administration" })).toBeVisible();
    const nav = primaryNav(page);
    await expect(nav.getByRole("link", { name: "Overview" })).toHaveAttribute("aria-current", "page");
    await expect(nav.getByRole("list", { name: "Administration" }).getByRole("link")).toHaveText(["Users", "Research data"]);
    await expect(nav.getByRole("link", { name: "Home" })).toHaveCount(0);
  });

  await test.step("the overview asks six things, once each, and shows the server's answers", async () => {
    const made = await requestsDuring(page, async () => {
      await page.reload();
      await expect(page.getByRole("region", { name: "System health", exact: true }).getByText("Ready", { exact: true })).toBeVisible();
      await expect(page.getByRole("region", { name: "Accounts", exact: true })).toContainText("accounts in all.");
    });
    const mine = own(made.list);
    expect(mine, mine.join("\n")).toHaveLength(6);
    expect(new Set(mine).size, `a request was made twice:\n${mine.join("\n")}`).toBe(6);
    await expect(page.getByRole("region", { name: "System health", exact: true })).toContainText("SchemaUp to date");
    // No scheduler in the e2e stack: the refresh is off, and that is what it says.
    await expect(page.getByRole("region", { name: "Research data", exact: true })).toContainText("Off");
    await expect(page.getByRole("region", { name: "Latest failed passes", exact: true })).toContainText("No research refresh has run yet");
    await expect(page.getByRole("region", { name: "Accounts", exact: true }).getByRole("link", { name: /Administrators$/ })).toHaveAttribute("href", "/admin/users?role=ADMIN");
  });

  await test.step("the research data page puts the title first and says the refresh is off", async () => {
    await primaryNav(page).getByRole("link", { name: "Research data" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Research data" })).toBeVisible();
    const facts = page.getByRole("table", { name: "Research refresh status" });
    await expect(facts.getByRole("row", { name: /Scheduled refresh/ })).toContainText("Off");
    await expect(page.getByText("No research refresh has run yet.")).toBeVisible();
  });

  await test.step("users are paged in the address, back and forward included", async () => {
    await primaryNav(page).getByRole("link", { name: "Users" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Users" })).toBeVisible();
    const summary = page.getByRole("navigation", { name: "Account pages" });
    await expect(summary, "the e2e stack holds more than 25 accounts after the API suite").toContainText(/Showing 1–25 of \d+ accounts/);
    await summary.getByRole("button", { name: "Next page" }).click();
    await expect(page).toHaveURL(/\/admin\/users\?page=2$/);
    await expect(summary).toContainText(/Showing 26–\d+ of \d+ accounts/);
    await page.goBack();
    await expect(page).toHaveURL(/\/admin\/users$/);
    await expect(summary).toContainText(/Showing 1–25 of/);
    await page.goForward();
    await expect(summary).toContainText(/Showing 26–/);
  });

  const row = page.getByRole("row").filter({ hasText: email });
  const roleButton = row.getByRole("button", { name: `Role of ${name}: Student researcher. Change the role` });
  await test.step("a search finds the account; dismissing the role change sends nothing", async () => {
    await page.getByRole("searchbox", { name: "Search by name or email" }).fill(email);
    await page.getByRole("button", { name: "Search", exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`\\?q=${encodeURIComponent(email).replace(/[.]/g, "\\.")}$`));
    await expect(page.getByRole("table").getByRole("row")).toHaveCount(2);

    const dismissed = await requestsDuring(page, async () => {
      await roleButton.click();
      await page.getByRole("menuitem", { name: "Faculty" }).click();
      const dialog = page.getByRole("dialog", { name: `Change ${name}’s role from Student researcher to Faculty?` });
      await expect(dialog).toContainText(email);
      await dialog.getByRole("button", { name: "Cancel" }).click();
      await expect(dialog).toBeHidden();
      await expect(roleButton).toBeFocused();

      await roleButton.click();
      await page.getByRole("menuitem", { name: "Faculty" }).click();
      await expect(page.getByRole("dialog")).toBeVisible();
      await page.keyboard.press("Escape");
      await expect(page.getByRole("dialog")).toBeHidden();
    });
    expect(dismissed.list.filter((entry) => entry.startsWith("PATCH"))).toEqual([]);
  });

  await test.step("confirming sends one change, the row shows the server's role, and it stays after a reload", async () => {
    const confirmed = await requestsDuring(page, async () => {
      await roleButton.click();
      await page.getByRole("menuitem", { name: "Faculty" }).click();
      await page.getByRole("dialog").getByRole("button", { name: `Make ${name.split(" ")[0]} faculty` }).click();
      await expect(page.getByRole("dialog")).toBeHidden();
      await expect(row.getByRole("button", { name: `Role of ${name}: Faculty. Change the role` })).toBeVisible();
    });
    expect(confirmed.list.filter((entry) => entry.startsWith("PATCH"))).toHaveLength(1);
    expect(confirmed.bodies).toEqual([{ role: "FACULTY" }]);
    await page.reload();
    await expect(page.getByRole("row").filter({ hasText: email }).getByRole("button", { name: `Role of ${name}: Faculty. Change the role` })).toBeVisible();
  });

  await test.step("the administration pages fit every width", async () => {
    for (const width of WIDTHS) {
      await page.setViewportSize({ width, height: width >= 1024 ? 900 : 844 });
      for (const path of ["/admin", "/admin/users", "/admin/research-data"]) {
        await page.goto(path);
        await page.waitForLoadState("networkidle");
        await expect(page.locator('main [aria-busy="true"]')).toHaveCount(0);
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
        expect(overflow, `${path} at ${width}px scrolls sideways`).toBeLessThanOrEqual(0);
      }
    }
  });

  network.expectClean();
  await page.waitForTimeout(61_000); // a fresh sign-in window for the specs after this one (see above)
});
