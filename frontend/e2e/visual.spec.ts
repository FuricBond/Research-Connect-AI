import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { expect, test, type Browser, type BrowserContextOptions, type Page } from "@playwright/test";
import { API_URL, DEMO, DEMO_PASSWORD, signInThroughTheForm } from "./support";

/**
 * P12 — the look, locked (FRONTEND_REDESIGN_PLAN.md §24): 15 routes × 1440/768/390 × light/dark, in the
 * e2e stack with the demo data, Chromium only. Run by `python e2e/run_e2e.py --suites visual` (not in
 * GitHub CI: it needs the stack); add `--update-visual` to re-baseline, and accept a change only with
 * a reason. Baselines are per platform: they were taken on Windows and do not apply elsewhere.
 *
 * The demo data's dates are relative to when it was seeded. So the page's clock is fixed, and every
 * date in an API answer is moved by the same distance and set to noon: "in 30 days" and "15 Feb 2030"
 * read the same on any day this runs. Run against a stack seeded within the last few hours. Postings
 * published together and recommendations with equal scores tie, and their order then follows each
 * seed's random ids, so ties are put in title order.
 *
 * A failed comparison restarts Playwright's worker, and with it this file's setup: the sessions are
 * kept on disk (git-ignored, throwaway accounts on a throwaway stack) or the sign-in limit would stop
 * the screens after the first difference from being compared at all.
 */
const NOW = new Date("2030-01-15T12:00:00.000Z");
const WIDTHS = [1440, 768, 390];
const THEMES = ["light", "dark"] as const;
const DAY = 86_400_000;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}(?:T[\d:.]+(?:Z|[+-]\d{2}:?\d{2})?)?$/;
const CLOCK_TIME = /^\d{2}:\d{2}:\d{2}$/;
const SESSIONS = path.join(__dirname, "..", "test-results", "visual-sessions.json");

type Role = "visitor" | "student" | "faculty" | "admin";
type State = Awaited<ReturnType<typeof signedIn>>;
type Ranked = { rank: number; final_score: number; opportunity: { title: string } };

/** Fixed by name so the address, not a generated id, says which screen it is. */
const SCREENS: { name: string; role: Role; path: () => string }[] = [
  { name: "search-landing", role: "visitor", path: () => "/" },
  { name: "sign-in", role: "visitor", path: () => "/login" },
  { name: "calls-for-papers", role: "visitor", path: () => "/browse" },
  { name: "postings", role: "visitor", path: () => "/postings" },
  { name: "dashboard", role: "student", path: () => "/dashboard" },
  { name: "search-results", role: "student", path: () => "/?q=information%20retrieval" },
  { name: "recommendations", role: "student", path: () => "/recommendations" },
  { name: "workspace", role: "student", path: () => "/workspace" },
  { name: "workspace-item", role: "student", path: () => `/workspace/${itemId}` },
  { name: "calendar", role: "student", path: () => "/calendar" },
  { name: "profile", role: "student", path: () => "/researcher" },
  { name: "my-postings", role: "faculty", path: () => "/postings?view=mine" },
  { name: "applicants", role: "faculty", path: () => "/postings/applicants" },
  { name: "notifications", role: "faculty", path: () => "/notifications" },
  { name: "administration", role: "admin", path: () => "/admin" },
];

let itemId = "";
const states: Partial<Record<Role, State>> = {};

/** Moves an API answer's dates by `by` milliseconds, each to noon of its day. */
function moved(value: unknown, by: number): unknown {
  if (Array.isArray(value)) return value.map((entry) => moved(entry, by));
  if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).map(([key, entry]) => [key, moved(entry, by)]));
  if (typeof value === "string" && CLOCK_TIME.test(value)) return "12:00:00"; // a deadline's time, sent on its own
  if (typeof value !== "string" || !ISO_DATE.test(value)) return value;
  const shifted = Math.floor((new Date(value).getTime() + by) / DAY) * DAY + DAY / 2;
  const iso = new Date(shifted).toISOString();
  return value.length === 10 ? iso.slice(0, 10) : iso;
}

async function signedIn(browser: Browser, email: string) {
  const context = await browser.newContext();
  const page = await context.newPage();
  await signInThroughTheForm(page, email, DEMO_PASSWORD);
  const state = await context.storageState();
  await context.close();
  return state;
}

const token = (state: State) => state.origins.flatMap((origin) => origin.localStorage).find((entry) => entry.name === "researchconnect_access_token")?.value ?? "";

async function screenPage(browser: Browser, options: BrowserContextOptions, theme: string) {
  const context = await browser.newContext({ ...options, locale: "en-GB", timezoneId: "UTC" });
  await context.addInitScript(
    ({ value, expires }) => {
      window.localStorage.setItem("rc-theme", value);
      // The session is checked by the server on its own clock; here it must outlive the fixed one.
      if (window.localStorage.getItem("researchconnect_token_expires_at")) window.localStorage.setItem("researchconnect_token_expires_at", expires);
    },
    { value: theme, expires: new Date(NOW.getTime() + 30 * DAY).toISOString() }
  );
  const by = NOW.getTime() - Date.now();
  await context.route(`${API_URL}/**`, async (route) => {
    if (route.request().method() !== "GET") return route.continue();
    const response = await route.fetch();
    if (!(response.headers()["content-type"] ?? "").includes("json")) return route.fulfill({ response });
    const answer = moved(await response.json(), by) as { postings?: { title: string }[]; recommendations?: Ranked[] };
    answer.postings?.sort((a, b) => a.title.localeCompare(b.title));
    answer.recommendations?.sort((a, b) => Number((b.final_score - a.final_score).toFixed(6)) || a.opportunity.title.localeCompare(b.opportunity.title));
    answer.recommendations?.forEach((entry, index) => (entry.rank = index + 1));
    return route.fulfill({ response, body: JSON.stringify(answer) });
  });
  const page = await context.newPage();
  await page.clock.setFixedTime(NOW);
  return { context, page };
}

async function settled(page: Page) {
  await page.waitForLoadState("networkidle");
  await expect(page.locator('main [aria-busy="true"]')).toHaveCount(0, { timeout: 30_000 });
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(300);
}

test.beforeAll(async ({ browser, request }) => {
  test.setTimeout(120_000);
  if (existsSync(SESSIONS)) Object.assign(states, JSON.parse(readFileSync(SESSIONS, "utf8")));
  for (const role of ["student", "faculty", "admin"] as const) states[role] ??= await signedIn(browser, DEMO[role]);
  mkdirSync(path.dirname(SESSIONS), { recursive: true });
  writeFileSync(SESSIONS, JSON.stringify(states));

  const auth = (role: Role) => ({ Authorization: `Bearer ${token(states[role] as State)}` });
  const calls = await (await request.get(`${API_URL}/api/opportunities?page_size=100`)).json();
  const call = calls.items.find((entry: { title: string }) => entry.title === "Symposium on Human-Computer Interaction and Accessibility");
  const saved = await request.post(`${API_URL}/api/v1/workspace`, { headers: auth("student"), data: { opportunity_id: call.id } });
  expect([200, 201]).toContain(saved.status());
  itemId = (await saved.json()).id;

  // One applicant, always the same one, on the demo faculty's opening. On a reused stack they exist.
  const mine = await (await request.get(`${API_URL}/api/v1/postings/mine?limit=100`, { headers: auth("faculty") })).json();
  const opening = mine.postings.find((posting: { title: string }) => posting.title === "Research assistantship in retrieval benchmarking");
  const registered = await request.post(`${API_URL}/api/v1/auth/register`, {
    data: { email: "visual.applicant@example.test", password: `E2e-${Math.random().toString(36).slice(2)}${Math.random().toString(36).slice(2, 8)}`, full_name: "Visual Applicant", role: "STUDENT" },
  });
  if (registered.status() === 201) {
    const applicant = await registered.json();
    const applied = await request.post(`${API_URL}/api/v1/postings/${opening.id}/applications`, {
      headers: { Authorization: `Bearer ${applicant.access_token}` },
      data: { cover_note: "I build retrieval evaluation pipelines and would like to help.", contact_email: "visual.applicant@example.test" },
    });
    expect(applied.status(), await applied.text()).toBe(201);
  }
});

for (const screen of SCREENS) {
  for (const theme of THEMES) {
    test(`${screen.name}, ${theme}`, async ({ browser }) => {
      test.setTimeout(240_000);
      for (const width of WIDTHS) {
        await test.step(`${width}px`, async () => {
          const touch = width < 1024;
          const { context, page } = await screenPage(browser, { viewport: { width, height: width >= 1024 ? 900 : width >= 768 ? 1024 : 844 }, isMobile: touch, hasTouch: touch, storageState: states[screen.role] }, theme);
          await page.goto(screen.path());
          await settled(page);
          await expect.soft(page).toHaveScreenshot(`${screen.name}-${theme}-${width}.png`, { fullPage: true, animations: "disabled", caret: "hide" });
          await context.close();
        });
      }
    });
  }
}
