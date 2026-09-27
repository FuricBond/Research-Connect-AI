import { expect, test } from "@playwright/test";
import { API_URL, DEMO, DEMO_PASSWORD, apiLogin, signInThroughTheForm, watch } from "./support";

/**
 * Phase 6.6 Step 16 — every page against the live API, as the seeded student. Each page must
 * render its main content with no failed API call and no page error: the check that the
 * frontend sends the payloads and reads the responses the backend actually defines.
 * The discovery chain runs on the literature corpus the API suite seeds (test_03).
 */
test("every signed-in page renders against the live API without contract errors", async ({ page, request }) => {
  // The collaboration and submission pages need a tracked opportunity (saving is idempotent).
  const student = await apiLogin(request, DEMO.student, DEMO_PASSWORD);
  const auth = { Authorization: `Bearer ${student.access_token}` };
  const listed = await (await request.get(`${API_URL}/api/opportunities?page_size=100`)).json();
  const venue = listed.items.find((o: { title: string }) => o.title === "Symposium on Human-Computer Interaction and Accessibility");
  const saved = await request.post(`${API_URL}/api/v1/workspace`, { headers: auth, data: { opportunity_id: venue.id } });
  expect([200, 201]).toContain(saved.status());

  const network = watch(page);
  await signInThroughTheForm(page, DEMO.student, DEMO_PASSWORD);

  const pages: [string, RegExp][] = [
    ["/researcher", /Researcher Interest & Expertise Intelligence/],
    ["/researcher/preferences", /Researcher Preferences Foundation/],
    ["/workspace", /Opportunity Workspace/],
    ["/submissions", /Submissions/],
    ["/calendar", /Research Calendar/],
    ["/notifications", /Notification Center/],
    ["/settings/notifications", /Notification & Reminder Preferences/],
    ["/postings", /Research Postings/],
    ["/postings/applications", /My Applications/],
    ["/peers", /Peer & Co-Author Discovery/],
    ["/browse", /Recommended opportunities/],
  ];
  for (const [path, heading] of pages) {
    await test.step(path, async () => {
      await page.goto(path);
      await expect(page.getByRole("heading", { name: heading }).first()).toBeVisible();
      await page.waitForLoadState("networkidle");
    });
  }

  await test.step("peer matches are explained", async () => {
    await page.goto("/peers");
    await expect(page.getByRole("button", { name: "How this was scored" }).first()).toBeVisible();
  });

  await test.step("literature search -> similar research -> matching venues", async () => {
    await page.goto("/");
    const box = page.getByRole("searchbox", { name: "Search research literature" });
    await box.fill("information retrieval");
    await box.press("Enter");
    await expect(page.getByRole("button", { name: "Why this rank?" }).first()).toBeVisible({ timeout: 60_000 });
    await page.getByRole("button", { name: "Find Similar Research" }).first().click();
    await expect(page.getByRole("button", { name: "Why similar?" }).first()).toBeVisible({ timeout: 60_000 });
    await page.getByRole("button", { name: /Match Calls for This Paper/i }).first().click();
    await expect(page.getByRole("button", { name: "Why matched?" }).first()).toBeVisible({ timeout: 60_000 });
  });

  await test.step("workspace collaboration and submission pages", async () => {
    await page.goto("/workspace");
    await page.locator(".workspace-card", { hasText: "Symposium on Human-Computer Interaction" })
      .getByRole("link", { name: /Collaborate/ }).click();
    await expect(page.getByRole("link", { name: /Submission Workflow/ })).toBeVisible();
    await page.getByRole("button", { name: /^Tasks/ }).click();
    await expect(page.getByRole("button", { name: /Create Task/ })).toBeVisible();
    await page.getByRole("link", { name: /Submission Workflow/ }).click();
    await expect(page.getByText(/New Submission Attempt|Create New Research Submission Draft/).first()).toBeVisible();
  });

  network.expectClean();
});
