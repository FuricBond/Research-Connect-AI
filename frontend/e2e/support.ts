import { expect, type APIRequestContext, type Page } from "@playwright/test";

/** Shared helpers for the Phase 6.6 browser suite. */

export const API_URL = process.env.E2E_BROWSER_API_URL ?? "http://localhost:8300";
export const DEMO_PASSWORD = process.env.E2E_DEMO_PASSWORD ?? "";
export const DEMO = {
  faculty: "demo.faculty@researchconnect.test",
  student: "demo.student@researchconnect.test",
};

export function uniqueEmail(label: string): string {
  return `e2e.browser.${label}.${Math.random().toString(36).slice(2, 10)}@example.test`;
}

export function newPassword(): string {
  return `E2e-${Math.random().toString(36).slice(2)}${Math.random().toString(36).slice(2, 8)}`;
}

/**
 * Records every API response the page receives and every uncaught page error, so a test
 * fails on a frontend/backend contract break (a 4xx/5xx the UI caused, or a crash) even
 * when the page still looks fine.
 */
export function watch(page: Page) {
  const failures: string[] = [];
  page.on("response", (response) => {
    const url = response.url();
    if (url.startsWith(API_URL) && response.status() >= 400) {
      failures.push(`${response.status()} ${response.request().method()} ${url.slice(API_URL.length)}`);
    }
  });
  page.on("pageerror", (error) => failures.push(`page error: ${error.message}`));
  return {
    failures,
    expectClean: () => expect(failures, failures.join("\n")).toEqual([]),
  };
}

export async function apiLogin(request: APIRequestContext, email: string, password: string) {
  const response = await request.post(`${API_URL}/api/v1/auth/login`, { data: { email, password } });
  expect(response.status(), await response.text()).toBe(200);
  return (await response.json()) as { access_token: string; user: { id: string; profile_id: string } };
}

export async function apiRegister(request: APIRequestContext, label: string) {
  const email = uniqueEmail(label);
  const password = newPassword();
  const response = await request.post(`${API_URL}/api/v1/auth/register`, {
    data: { email, password, full_name: `Browser ${label}`, role: "STUDENT" },
  });
  expect(response.status(), await response.text()).toBe(201);
  return { email, password };
}

export async function signInThroughTheForm(page: Page, email: string, password: string) {
  await page.goto("/login");
  await page.getByLabel(/email/i).fill(email);
  await page.getByLabel(/password/i).fill(password);
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page.getByRole("button", { name: /sign out/i })).toBeVisible();
}
