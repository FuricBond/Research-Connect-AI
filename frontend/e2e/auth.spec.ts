import { expect, test } from "@playwright/test";
import { API_URL, accountMenu, newPassword, primaryNav, signOut, uniqueEmail, watch } from "./support";

/**
 * Phase 6.6 Step 15 — the browser authentication lifecycle against the production build:
 * landing page, protected-route redirect, registration, authenticated navigation, logout,
 * and signing back in to the page that was asked for. P3: the password is changed in Settings
 * on the way, so signing back in uses the new one and the old one is refused.
 */
test("a visitor registers, navigates, signs out and signs back in", async ({ page }) => {
  const network = watch(page);
  const email = uniqueEmail("auth");
  const password = newPassword();
  const changedPassword = newPassword();

  await test.step("the landing page is public", async () => {
    await page.goto("/");
    await expect(page.getByRole("searchbox", { name: "Search research literature" })).toBeVisible();
    await expect(page.getByRole("link", { name: /sign in/i }).first()).toBeVisible();
    await expect(page.getByRole("link", { name: /create account/i }).first()).toBeVisible();
  });

  await test.step("a protected page sends a visitor to sign in", async () => {
    await page.goto("/workspace");
    await expect(page).toHaveURL(/\/login\?next=%2Fworkspace/);
  });

  await test.step("registration signs the new researcher in", async () => {
    await page.goto("/register");
    await page.locator("#register-name").fill("Browser Researcher");
    await page.locator("#register-email").fill(email);
    await page.locator("#register-password").fill(password);
    await page.locator("#register-confirm").fill(password);
    await page.locator("#register-role").selectOption("STUDENT");
    await page.getByRole("button", { name: /create account/i }).click();
    await expect(accountMenu(page)).toBeVisible();
    await expect(page.getByText("Browser Researcher").first()).toBeVisible();
    const stored = await page.evaluate(() => Object.keys(window.localStorage).join(","));
    expect(stored).not.toBe("");
  });

  await test.step("authenticated navigation reaches protected pages", async () => {
    await primaryNav(page).getByRole("link", { name: "Workspace" }).click();
    await expect(page).toHaveURL(/\/workspace$/);
    await expect(page.getByRole("heading", { name: "Opportunity Workspace" })).toBeVisible();
  });

  await test.step("leaving a page while its session check is in flight keeps this browser signed in", async () => {
    // P4: the check is slowed, and the browser leaves the page before it answers (a reload or a
    // typed address cancels it). A cancelled check is not a failed one: the next page checks again.
    await page.route(`${API_URL}/api/v1/auth/me`, async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 400));
      await route.continue();
    });
    const checking = page.waitForRequest((request) => request.url() === `${API_URL}/api/v1/auth/me`);
    await page.goto("/reading-list");
    await checking;
    await page.goto("/workspace");
    await expect(page.getByRole("heading", { name: "Opportunity Workspace" })).toBeVisible();
    await expect(accountMenu(page)).toBeVisible();
    await page.unroute(`${API_URL}/api/v1/auth/me`);
  });

  await test.step("changing the password in Settings keeps this browser signed in", async () => {
    await accountMenu(page).click();
    await page.getByRole("link", { name: "Settings", exact: true }).click();
    await expect(page).toHaveURL(/\/settings$/);
    await expect(page.getByRole("heading", { level: 1, name: "Settings" })).toBeVisible();
    await page.getByLabel("Current password", { exact: true }).fill(password);
    await page.getByLabel("New password", { exact: true }).fill(changedPassword);
    await page.getByLabel("Confirm new password", { exact: true }).fill(changedPassword);
    await page.getByRole("button", { name: "Change password" }).click();
    await expect(page.getByRole("status").filter({ hasText: "Password changed" })).toBeVisible();
    // The fresh token works: a protected page still opens.
    await primaryNav(page).getByRole("link", { name: "Workspace" }).click();
    await expect(page.getByRole("heading", { name: "Opportunity Workspace" })).toBeVisible();
  });

  await test.step("signing out ends the session in this browser", async () => {
    // By keyboard, from a protected page (P2 audit): focus lands on the Sign in link, not the body.
    await accountMenu(page).focus();
    await page.keyboard.press("Enter");
    await page.getByRole("button", { name: "Sign out" }).focus();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/login\?next=%2Fworkspace/);
    await expect(page.getByRole("banner").getByRole("link", { name: "Sign in" })).toBeFocused();
    await page.goto("/workspace");
    await expect(page).toHaveURL(/\/login\?next=%2Fworkspace/);
  });

  await test.step("signing in (with the new password) returns to the page that was asked for", async () => {
    await page.getByLabel(/email/i).fill(email);
    await page.getByLabel(/password/i).fill(changedPassword);
    await page.getByRole("button", { name: /sign in/i }).click();
    await expect(page).toHaveURL(/\/workspace$/);
    await expect(page.getByRole("heading", { name: "Opportunity Workspace" })).toBeVisible();
  });

  await test.step("a wrong password (here the old one) is refused with a readable message", async () => {
    await signOut(page);
    await page.goto("/login");
    await page.getByLabel(/email/i).fill(email);
    await page.getByLabel(/password/i).fill(password);
    await page.getByRole("button", { name: /sign in/i }).click();
    await expect(page.getByRole("alert").or(page.locator(".auth-error")).first()).toBeVisible();
    await expect(page).toHaveURL(/\/login/);
  });

  // The one refused login above is expected; nothing else may fail.
  network.failures.splice(0, network.failures.length, ...network.failures.filter((f) => !f.startsWith("401 POST /api/v1/auth/login")));
  network.expectClean();
});
