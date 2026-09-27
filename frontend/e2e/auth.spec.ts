import { expect, test } from "@playwright/test";
import { newPassword, uniqueEmail, watch } from "./support";

/**
 * Phase 6.6 Step 15 — the browser authentication lifecycle against the production build:
 * landing page, protected-route redirect, registration, authenticated navigation, logout,
 * and signing back in to the page that was asked for.
 */
test("a visitor registers, navigates, signs out and signs back in", async ({ page }) => {
  const network = watch(page);
  const email = uniqueEmail("auth");
  const password = newPassword();

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
    await expect(page.getByRole("button", { name: /sign out/i })).toBeVisible();
    await expect(page.getByText("Browser Researcher").first()).toBeVisible();
    const stored = await page.evaluate(() => Object.keys(window.localStorage).join(","));
    expect(stored).not.toBe("");
  });

  await test.step("authenticated navigation reaches protected pages", async () => {
    await page.getByRole("link", { name: /^Opportunity Workspace/ }).first().click();
    await expect(page).toHaveURL(/\/workspace$/);
    await expect(page.getByRole("heading", { name: "Opportunity Workspace" })).toBeVisible();
  });

  await test.step("signing out ends the session in this browser", async () => {
    await page.getByRole("button", { name: /sign out/i }).click();
    await expect(page.getByRole("link", { name: /sign in/i }).first()).toBeVisible();
    await page.goto("/workspace");
    await expect(page).toHaveURL(/\/login\?next=%2Fworkspace/);
  });

  await test.step("signing in returns to the page that was asked for", async () => {
    await page.getByLabel(/email/i).fill(email);
    await page.getByLabel(/password/i).fill(password);
    await page.getByRole("button", { name: /sign in/i }).click();
    await expect(page).toHaveURL(/\/workspace$/);
    await expect(page.getByRole("heading", { name: "Opportunity Workspace" })).toBeVisible();
  });

  await test.step("a wrong password is refused with a readable message", async () => {
    await page.getByRole("button", { name: /sign out/i }).click();
    await page.goto("/login");
    await page.getByLabel(/email/i).fill(email);
    await page.getByLabel(/password/i).fill(`${password}-wrong`);
    await page.getByRole("button", { name: /sign in/i }).click();
    await expect(page.getByRole("alert").or(page.locator(".auth-error")).first()).toBeVisible();
    await expect(page).toHaveURL(/\/login/);
  });

  // The one refused login above is expected; nothing else may fail.
  network.failures.splice(0, network.failures.length, ...network.failures.filter((f) => !f.startsWith("401 POST /api/v1/auth/login")));
  network.expectClean();
});
