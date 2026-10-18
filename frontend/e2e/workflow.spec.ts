import { expect, test } from "@playwright/test";
import { API_URL, DEMO, DEMO_PASSWORD, apiLogin, apiRegister, primaryNav, signInThroughTheForm, watch } from "./support";

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
    await primaryNav(page).getByRole("link", { name: "Calls for papers" }).click();
    // P5: the page's h1 names the list (the old "Recommended opportunities" heading went).
    await expect(page.getByRole("heading", { level: 1, name: "Calls for papers" })).toBeVisible();
    await expect(page.locator(".opportunity-card").first()).toBeVisible();
    expect(await page.locator(".opportunity-card").count()).toBeGreaterThanOrEqual(5);
  });

  let savedTitle = "";
  await test.step("a personalized recommendation is saved to the workspace", async () => {
    // P6: recommendations have their own page, first under "For you".
    await primaryNav(page).getByRole("link", { name: "Recommendations" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Recommendations" })).toBeVisible();
    const card = page.locator(".opportunity-card").first();
    await expect(card).toBeVisible({ timeout: 60_000 });
    savedTitle = (await card.locator("h3").first().textContent())?.trim() ?? "";
    expect(savedTitle).not.toBe("");
    await card.getByRole("button", { name: "Save to workspace" }).click();
    await expect(card.getByRole("button", { name: "Saved to workspace" })).toBeVisible();
    // Feedback on the same recommendation is recorded, and can be undone.
    await card.getByRole("button", { name: "Helpful" }).click();
    await expect(card.getByRole("button", { name: "Helpful" })).toHaveAttribute("aria-pressed", "true");
    await card.getByRole("button", { name: "Undo" }).click();
    await expect(card.getByText("Feedback removed.")).toBeVisible();

    await primaryNav(page).getByRole("link", { name: "Workspace" }).click();
    await expect(page.locator(".workspace-card", { hasText: savedTitle })).toBeVisible();
  });

  await test.step("the researcher moves the saved call along, through its status menu", async () => {
    // P7: the menu offers the server's allowed moves; the change shows at once and persists.
    const row = page.locator(".workspace-card", { hasText: savedTitle });
    await row.getByRole("button", { name: "Status: Saved. Change status" }).click();
    await expect(row.getByRole("menuitem")).toHaveText(["Move to considering", "Move to planning", "Move to archived"]);
    await row.getByRole("menuitem", { name: "Move to planning" }).click();
    await expect(row.getByRole("button", { name: "Status: Planning. Change status" })).toBeVisible();
    await page.reload();
    await expect(page.locator(".workspace-card", { hasText: savedTitle }).getByRole("button", { name: "Status: Planning. Change status" })).toBeVisible();
  });

  await test.step("the researcher applies to an opening", async () => {
    await primaryNav(page).getByRole("link", { name: "Research postings" }).click();
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
    // P2.4: the bell is the one way in; its name carries the unread count. P8: it opens the latest
    // notifications, grouped, with "View all".
    const bell = page.getByRole("banner").getByRole("button", { name: /^Notifications, \d+ unread/ });
    await bell.click();
    await expect(page.getByRole("banner").getByRole("link", { name: /^Application shortlisted/ }).first()).toBeVisible();
    await page.getByRole("link", { name: "View all notifications" }).click();
    await expect(page).toHaveURL(/\/notifications$/);
    await expect(page.getByRole("heading", { level: 1, name: "Notifications" })).toBeVisible();
    await expect(page.getByRole("heading", { level: 2, name: /^Research postings/ })).toBeVisible();
    await expect(page.locator("body")).toContainText(POSTING);
    for (const path of ["/postings/applications", "/notifications"]) {
      await page.goto(path);
      await expect(page.locator("body")).not.toContainText(PRIVATE_NOTE);
    }
  });

  network.expectClean();
});
