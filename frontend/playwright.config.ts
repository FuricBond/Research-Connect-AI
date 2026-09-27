import { defineConfig } from "@playwright/test";

/**
 * Phase 6.6 — browser end-to-end suite (frontend/e2e).
 *
 * It drives the production build served by the E2E Compose stack, so it runs from
 * `python e2e/run_e2e.py`, which starts that stack and sets E2E_WEB_URL, E2E_BROWSER_API_URL
 * and E2E_DEMO_PASSWORD. Tests run one at a time: they share a live database, and the
 * backend limits sign-in attempts per client address.
 *
 * Browser: E2E_BROWSER_CHANNEL=chrome (or msedge) uses an installed browser; otherwise run
 * `npx playwright install chromium` once for Playwright's own build.
 */
export default defineConfig({
  testDir: "./e2e",
  testMatch: "**/*.spec.ts",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 120_000,
  expect: { timeout: 20_000 },
  outputDir: "test-results",
  use: {
    baseURL: process.env.E2E_WEB_URL ?? "http://localhost:3300",
    channel: process.env.E2E_BROWSER_CHANNEL || undefined,
    headless: true,
    viewport: { width: 1280, height: 800 },
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
});
