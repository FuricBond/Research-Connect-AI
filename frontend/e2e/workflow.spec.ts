import { expect, test } from "@playwright/test";
import { API_URL, DEMO, DEMO_PASSWORD, apiLogin, apiRegister, signInThroughTheForm, watch } from "./support";

/**
 * Phase 6.6 Step 15 — the main researcher journey through the real UI:
 * sign in -> discover -> personalized recommendation -> save -> workspace -> apply to a
 * posting -> the faculty author decides (a second identity, through the API) -> the
 * researcher sees the new status and the notification, never the reviewer's private note.
 */
const POSTING = "Research assistantship in retrieval benchmarking";
const PRIVATE_NOTE = "PRIVATE-BROWSER-NOTE";

test("a researcher discovers, saves, applies and is notified of the decision", async ({ page, request }) => {
  const network = watch(page);
  const researcher = await apiRegister(request, "journey");
  await signInThroughTheForm(page, researcher.email, researcher.password);

  await test.step("browse lists the open calls", async () => {
    await page.getByRole("link", { name: /^Browse All Calls/ }).first().click();
    await expect(page.getByRole("heading", { name: "Recommended opportunities" })).toBeVisible();
    await expect(page.locator(".opportunity-card").first()).toBeVisible();
    expect(await page.locator(".opportunity-card").count()).toBeGreaterThanOrEqual(5);
  });

  let savedTitle = "";
  await test.step("a personalized recommendation is saved to the workspace", async () => {
    await page.getByRole("link", { name: /^Researcher Profile/ }).first().click();
    await expect(page.getByRole("heading", { name: /Unified Evidence-Backed Recommendations/ })).toBeVisible();
    const save = page.getByRole("button", { name: "Save opportunity" }).first();
    await expect(save).toBeVisible();
    savedTitle = await save.evaluate((button) => {
      let node: HTMLElement | null = button as HTMLElement;
      while (node && !node.querySelector("h3")) node = node.parentElement;
      return node?.querySelector("h3")?.textContent?.trim() ?? "";
    });
    expect(savedTitle).not.toBe("");
    await save.click();
    await expect(page.getByRole("status").filter({ hasText: "Saved to workspace" })).toBeVisible();

    await page.getByRole("link", { name: /^Opportunity Workspace/ }).first().click();
    await expect(page.locator(".workspace-card", { hasText: savedTitle })).toBeVisible();
  });

  await test.step("the researcher applies to an opening", async () => {
    await page.getByRole("link", { name: /^Research Postings/ }).first().click();
    await page.getByRole("link", { name: POSTING }).first().click();
    await page.getByRole("button", { name: /apply now/i }).click();
    await page.locator("#cover-note").fill("I build retrieval evaluation pipelines and would like to help.");
    await page.getByRole("button", { name: "Submit application" }).click();
    await page.goto("/postings/applications");
    const card = page.locator("article, li, div").filter({ hasText: POSTING }).last();
    await expect(card).toContainText(/submitted/i);
  });

  await test.step("the faculty author shortlists the application", async () => {
    const faculty = await apiLogin(request, DEMO.faculty, DEMO_PASSWORD);
    const auth = { Authorization: `Bearer ${faculty.access_token}` };
    const mine = await (await request.get(`${API_URL}/api/v1/postings/mine`, { headers: auth })).json();
    const posting = mine.postings.find((p: { title: string }) => p.title === POSTING);
    const received = await (await request.get(`${API_URL}/api/v1/postings/${posting.id}/applications?limit=100`, { headers: auth })).json();
    const application = received.applications.find((a: { applicant: { full_name: string } }) =>
      a.applicant.full_name === "Browser journey");
    expect(application).toBeTruthy();
    const decided = await request.post(`${API_URL}/api/v1/postings/applications/${application.id}/transition`, {
      headers: auth, data: { target_status: "SHORTLISTED", reviewer_note: PRIVATE_NOTE },
    });
    expect(decided.status(), await decided.text()).toBe(200);
  });

  await test.step("the researcher sees the new status and the notification, not the note", async () => {
    await page.goto("/postings/applications");
    await expect(page.locator("body")).toContainText(/shortlisted/i);
    await page.getByRole("link", { name: /^Notifications/ }).first().click();
    await expect(page.getByRole("heading", { name: "Notification Center" })).toBeVisible();
    await expect(page.locator("body")).toContainText(POSTING);
    for (const path of ["/postings/applications", "/notifications"]) {
      await page.goto(path);
      await expect(page.locator("body")).not.toContainText(PRIVATE_NOTE);
    }
  });

  network.expectClean();
});
