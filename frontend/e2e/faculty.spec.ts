import { expect, test, type Page, type Request } from "@playwright/test";
import { API_URL, DEMO, DEMO_PASSWORD, newPassword, primaryNav, signInThroughTheForm, uniqueEmail, watch } from "./support";

/**
 * P9 — the faculty experience against the live API (FRONTEND_REDESIGN_PLAN.md §14): an applicant
 * applies (through the API) to the seeded assistantship; the demo faculty member finds them in the
 * applicant inbox, decides in pipeline order, and "Not selected" asks before anything is sent;
 * then writes a draft in the editor (checked before sending, saved once), edits one field (only
 * that field is sent) and cancels it (asked first). The faculty pages fit every width.
 *
 * Two sign-ins: the applicant's registration and the faculty member's sign-in. The backend allows
 * ten a minute per address and the specs before this one (auth, dashboard) use most of them, so
 * this one starts with a fresh minute; otherwise its two would push the specs after it over.
 */
const POSTING = "Research assistantship in retrieval benchmarking";
const WIDTHS = [1440, 1024, 768, 390, 320];

/** The API requests made while `act` runs, as "METHOD /path". */
async function requestsDuring(page: Page, act: () => Promise<unknown>, settle = true): Promise<{ list: string[]; bodies: Map<string, unknown> }> {
  const list: string[] = [];
  const bodies = new Map<string, unknown>();
  const record = (request: Request) => {
    const url = request.url();
    if (!url.startsWith(API_URL)) return;
    const entry = `${request.method()} ${url.slice(API_URL.length).split("?")[0]}`;
    list.push(entry);
    const body = request.postData();
    if (body) bodies.set(entry, JSON.parse(body));
  };
  page.on("request", record);
  await act();
  if (settle) await page.waitForLoadState("networkidle");
  page.off("request", record);
  return { list, bodies };
}

test("a faculty member reviews applicants in the inbox and writes, edits and cancels a posting", async ({ page, request }) => {
  test.setTimeout(300_000);
  await page.waitForTimeout(61_000); // a fresh sign-in window (see above)
  const applicantName = `Browser applicant ${Math.random().toString(36).slice(2, 8)}`;
  await test.step("an applicant applies to the seeded assistantship", async () => {
    const registered = await request.post(`${API_URL}/api/v1/auth/register`, {
      data: { email: uniqueEmail("applicant"), password: newPassword(), full_name: applicantName, role: "STUDENT" },
    });
    expect(registered.status(), await registered.text()).toBe(201);
    const { access_token } = await registered.json();
    const listed = await (await request.get(`${API_URL}/api/v1/postings?limit=100`)).json();
    const posting = listed.postings.find((p: { title: string }) => p.title === POSTING);
    expect(posting).toBeTruthy();
    const applied = await request.post(`${API_URL}/api/v1/postings/${posting.id}/applications`, {
      headers: { Authorization: `Bearer ${access_token}` },
      data: { cover_note: "I maintain retrieval evaluation pipelines and would like to help curate benchmarks." },
    });
    expect(applied.status(), await applied.text()).toBe(201);
  });

  const network = watch(page);
  await signInThroughTheForm(page, DEMO.faculty, DEMO_PASSWORD);
  // Signing in lands on the home: let its own requests finish before measuring the inbox's.
  await page.waitForLoadState("networkidle");
  await expect(page.locator('main [aria-busy="true"]')).toHaveCount(0);

  await test.step("the inbox gathers the applications, within its request cap", async () => {
    const made = await requestsDuring(page, async () => {
      await primaryNav(page).getByRole("link", { name: "Applicants" }).click();
      await expect(page.getByRole("heading", { level: 1, name: "Applicants" })).toBeVisible();
      await expect(page.locator('main [aria-busy="true"]')).toHaveCount(0);
    });
    const own = made.list.filter((r) => !r.endsWith("/auth/me") && !r.endsWith("/notifications/unread-count"));
    expect(own.filter((r) => r === "GET /api/v1/postings/mine"), own.join("\n")).toHaveLength(1);
    expect(own.filter((r) => /\/applications$/.test(r)).length, own.join("\n")).toBeLessThanOrEqual(10);
    expect(own.length, own.join("\n")).toBeLessThanOrEqual(11);
    expect(new Set(own).size, `a request was made twice:\n${own.join("\n")}`).toBe(own.length);
    await expect(page.getByRole("heading", { level: 2, name: POSTING })).toBeVisible();
  });

  const card = page.getByRole("article", { name: applicantName });
  await test.step("decisions come in pipeline order; Not selected asks first and Cancel sends nothing", async () => {
    await expect(card.getByRole("group", { name: `Decisions on ${applicantName}` }).getByRole("button")).toHaveText(["Mark under review", "Shortlist", "Not selected"]);
    const made = await requestsDuring(page, async () => {
      await card.getByRole("button", { name: "Not selected" }).click();
      const dialog = page.getByRole("dialog", { name: `Mark ${applicantName} as not selected for “${POSTING}”?` });
      await expect(dialog).toBeVisible();
      await dialog.getByRole("button", { name: "Cancel" }).click();
      await expect(dialog).toBeHidden();
      await expect(card.getByRole("button", { name: "Not selected" })).toBeFocused();
    });
    expect(made.list.filter((r) => r.startsWith("POST"))).toEqual([]);
    await expect(card).toContainText("Submitted");
  });

  await test.step("Shortlist is sent once and shown when the server agrees, and stays after a reload", async () => {
    const made = await requestsDuring(page, async () => {
      await card.getByRole("button", { name: "Shortlist" }).click();
      await expect(card).toContainText("Shortlisted");
    });
    expect(made.list.filter((r) => r.startsWith("POST"))).toHaveLength(1);
    expect([...made.bodies.values()]).toEqual([{ target_status: "SHORTLISTED", decision_reason: null, reviewer_note: null }]);
    // The button used is gone with the new status: focus moves to the applicant's name, not the page.
    await expect(card.getByRole("heading", { name: applicantName })).toBeFocused();
    await page.reload();
    await expect(page.getByRole("article", { name: applicantName })).toContainText("Shortlisted");
    await expect(page.getByRole("article", { name: applicantName }).getByRole("group", { name: /Decisions/ }).getByRole("button")).toHaveText(["Make offer", "Not selected"]);
  });

  await test.step("Not selected, confirmed, sends exactly one decision and ends the application", async () => {
    const made = await requestsDuring(page, async () => {
      await card.getByRole("button", { name: "Not selected" }).click();
      const dialog = page.getByRole("dialog");
      await dialog.getByLabel(/Message to the applicant/).fill("Thank you for applying.");
      await dialog.getByRole("button", { name: "Mark not selected" }).click();
      await expect(dialog).toBeHidden();
      await expect(card).toContainText("Not selected");
    });
    expect(made.list.filter((r) => r.startsWith("POST"))).toHaveLength(1);
    expect([...made.bodies.values()]).toEqual([{ target_status: "REJECTED", decision_reason: "Thank you for applying.", reviewer_note: null }]);
    await expect(card.getByRole("group", { name: /Decisions/ })).toHaveCount(0);
    await expect(card.getByRole("heading", { name: applicantName })).toBeFocused();
  });

  const title = `E2E draft ${Math.random().toString(36).slice(2, 8)}`;
  let postingPath = "";
  await test.step("the editor checks the form first, then saves the draft once", async () => {
    await primaryNav(page).getByRole("link", { name: "My postings" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "My postings" })).toBeVisible();
    await page.getByRole("link", { name: "New posting" }).first().click();
    await expect(page.getByRole("heading", { level: 1, name: "New posting" })).toBeVisible();

    const empty = await requestsDuring(page, async () => {
      await page.getByRole("button", { name: "Save draft" }).click();
      await expect(page.getByRole("form", { name: "New posting" }).getByRole("alert")).toContainText("Check these 2 fields before saving:");
    }, false);
    expect(empty.list.filter((r) => r.startsWith("POST"))).toEqual([]);
    await expect(page.getByLabel(/^Title/)).toBeFocused();

    await page.getByLabel(/^Title/).fill(title);
    await page.getByRole("textbox", { name: /^Description/ }).fill("A short project to test the posting editor from the browser suite.");
    await page.getByLabel(/^Required skills/).fill("Python, Evaluation");
    await expect(page.getByRole("complementary", { name: "Preview" })).toContainText(title);
    const saved = await requestsDuring(page, async () => {
      await page.getByRole("button", { name: "Save draft" }).click();
      await expect(page.getByRole("heading", { level: 1, name: title })).toBeVisible();
    });
    expect(saved.list.filter((r) => r === "POST /api/v1/postings")).toHaveLength(1);
    expect(saved.bodies.get("POST /api/v1/postings")).toMatchObject({ title, required_skills: ["Python", "Evaluation"] });
    postingPath = new URL(page.url()).pathname;
    expect(postingPath).toMatch(/^\/postings\/[0-9a-f-]{36}$/);
    await expect(page.getByRole("region", { name: "Manage this posting" }).getByRole("button", { name: "Publish" })).toBeVisible();
  });

  await test.step("an edit sends only the field that changed", async () => {
    await page.getByRole("region", { name: "Manage this posting" }).getByRole("link", { name: "Edit" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Edit posting" })).toBeVisible();
    await page.getByLabel(/^Summary/).fill("Edited from the browser suite.");
    const made = await requestsDuring(page, async () => {
      await page.getByRole("button", { name: "Save changes" }).click();
      await expect(page).toHaveURL(new RegExp(`${postingPath}$`));
      await expect(page.getByText("Edited from the browser suite.")).toBeVisible();
    });
    const patch = `PATCH /api/v1${postingPath}`;
    expect(made.list.filter((r) => r === patch)).toHaveLength(1);
    expect(made.bodies.get(patch)).toEqual({ summary: "Edited from the browser suite." });
  });

  await test.step("Cancel posting asks first: dismissing sends nothing, confirming sends one change", async () => {
    const manage = page.getByRole("region", { name: "Manage this posting" });
    const dismissed = await requestsDuring(page, async () => {
      await manage.getByRole("button", { name: "Cancel posting" }).click();
      const dialog = page.getByRole("dialog", { name: `Cancel “${title}”?` });
      await expect(dialog).toBeVisible();
      await page.keyboard.press("Escape");
      await expect(dialog).toBeHidden();
    });
    expect(dismissed.list.filter((r) => r.startsWith("POST"))).toEqual([]);

    const confirmed = await requestsDuring(page, async () => {
      await manage.getByRole("button", { name: "Cancel posting" }).click();
      await page.getByRole("dialog").getByRole("button", { name: "Cancel posting" }).click();
      await expect(page.getByRole("dialog")).toBeHidden();
      await expect(manage).toContainText("Cancelled: researchers no longer see it.");
    });
    expect(confirmed.list.filter((r) => r.startsWith("POST"))).toEqual([`POST /api/v1${postingPath}/transition`]);
    expect([...confirmed.bodies.values()]).toEqual([{ target_status: "CANCELLED", note: null }]);
    await expect(manage.getByRole("button")).toHaveText(["Archive"]);
  });

  await test.step("the faculty pages fit every width", async () => {
    const pages = ["/dashboard", "/postings?view=mine", "/postings/applicants", "/postings/new", postingPath, `${postingPath}/edit`];
    for (const width of WIDTHS) {
      await page.setViewportSize({ width, height: width >= 1024 ? 900 : 844 });
      for (const path of pages) {
        await page.goto(path);
        await page.waitForLoadState("networkidle");
        await expect(page.locator('main [aria-busy="true"]')).toHaveCount(0);
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
        expect(overflow, `${path} at ${width}px scrolls sideways`).toBeLessThanOrEqual(0);
      }
    }
  });

  network.expectClean();
});
