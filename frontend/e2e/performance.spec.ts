import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { expect, test, type Browser, type Page, type Request } from "@playwright/test";
import { API_URL, DEMO, DEMO_PASSWORD, signInThroughTheForm } from "./support";

/**
 * P12 — the budgets a build cannot show (docs/design/audit/performance-baseline.md §5), on the live
 * stack, one fresh page per load: layout shift at most 0.02, no request made twice, no page error,
 * route-specific API requests within budget, fonts actually downloaded within budget, one preload. The
 * JavaScript and CSS budgets are checked on the build itself (scripts/check-bundle-budget.mjs).
 *
 * What each load really cost is written to test-results/performance-report-<role>.json: API requests split
 * into the shell's and the route's, parallel and sequential; every font file and JavaScript file with
 * the bytes it took on the wire.
 *
 * Four sign-ins: one per role, one for the deferred parts.
 */
const CLS_BUDGET = 0.02;
const WIDTHS = [1440, 768, 390];
/** Route-specific API requests: the shell's two are counted and reported apart (Decision 3). */
const REQUESTS_BUDGET = 8;
const REQUEST_BUDGETS: Record<string, number> = { "/dashboard": 7, "/researcher": 6 };
/** Font files actually downloaded by one page, every subset and style it used (Decision 4), in bytes. */
const FONT_BUDGET = 100_000;
const SHELL_REQUESTS = [/\/api\/v1\/auth\/me$/, /\/api\/v1\/notifications\?limit=3$/];

interface LoadReport {
  role: string;
  path: string;
  width: number;
  cls: number;
  shellRequests: number;
  routeRequests: number;
  totalRequests: number;
  sequentialRequests: string[];
  fonts: { file: string; bytes: number }[];
  fontBytes: number;
  fontPreloads: number;
  scriptFiles: number;
  scriptBytes: number;
}
const REPORT = path.join(__dirname, "..", "test-results", "performance-report.json");
const report: LoadReport[] = [];

const ROUTES: Record<"visitor" | "student" | "faculty" | "admin", string[]> = {
  visitor: ["/", "/login", "/register", "/browse", "/postings", "/similar", "/opportunities"],
  student: [
    "/dashboard", "/?q=information%20retrieval", "/recommendations", "/researcher", "/researcher/preferences", "/supervisors", "/peers",
    "/workspace", "/submissions", "/reading-list", "/calendar", "/notifications", "/settings", "/postings/applications",
  ],
  faculty: ["/dashboard", "/postings?view=mine", "/postings/new", "/postings/applicants"],
  admin: ["/admin", "/admin/users", "/admin/research-data"],
};

async function measured(page: Page, target: string) {
  await page.addInitScript(() => {
    (window as unknown as { __cls: number }).__cls = 0;
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries() as unknown as { hadRecentInput: boolean; value: number }[]) {
        if (!entry.hadRecentInput) (window as unknown as { __cls: number }).__cls += entry.value;
      }
    }).observe({ type: "layout-shift", buffered: true });
  });
  const requests: string[] = [];
  const errors: string[] = [];
  const timings = new Map<Request, { url: string; started: number; finished?: number }>();
  const transfers: { request: Request; kind: "font" | "script" }[] = [];
  page.on("request", (request) => {
    if (request.url().startsWith(API_URL) && request.method() !== "OPTIONS") timings.set(request, { url: request.url().slice(API_URL.length), started: Date.now() });
    if (request.method() === "GET" && request.url().startsWith(API_URL)) requests.push(request.url().slice(API_URL.length));
    if (/\.woff2(\?|$)/.test(request.url())) transfers.push({ request, kind: "font" });
    else if (request.resourceType() === "script") transfers.push({ request, kind: "script" });
  });
  page.on("requestfinished", (request) => {
    const timing = timings.get(request);
    if (timing) timing.finished = Date.now();
  });
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto(target);
  await page.waitForLoadState("networkidle");
  await expect(page.locator('main [aria-busy="true"]')).toHaveCount(0, { timeout: 30_000 });
  await page.waitForTimeout(500);
  const cls = await page.evaluate(() => (window as unknown as { __cls: number }).__cls);
  const fontPreloads = await page.locator('link[rel="preload"][as="font"]').count();

  const api = [...timings.values()];
  const isShell = (url: string) => SHELL_REQUESTS.some((pattern) => pattern.test(url));
  const route = api.filter((timing) => !isShell(timing.url));
  // Sequential: it only started once another of the route's requests had answered.
  const sequential = route.filter((timing) => route.some((other) => other !== timing && other.finished !== undefined && other.finished <= timing.started));
  const sized = await Promise.all(
    transfers.map(async ({ request, kind }) => ({ kind, file: new URL(request.url()).pathname.split("/").pop() ?? "", bytes: (await request.sizes().catch(() => ({ responseBodySize: 0 }))).responseBodySize }))
  );
  const fonts = sized.filter((entry) => entry.kind === "font");
  const scripts = sized.filter((entry) => entry.kind === "script");
  return {
    cls,
    repeated: requests.filter((url, index) => requests.indexOf(url) !== index),
    errors,
    shellRequests: api.length - route.length,
    routeRequests: route.length,
    sequentialRequests: sequential.map((timing) => timing.url.split("?")[0]),
    fonts: fonts.map(({ file, bytes }) => ({ file, bytes })),
    fontBytes: fonts.reduce((sum, entry) => sum + entry.bytes, 0),
    fontPreloads,
    scriptFiles: scripts.length,
    scriptBytes: scripts.reduce((sum, entry) => sum + entry.bytes, 0),
  };
}

async function signedIn(browser: Browser, email: string) {
  const context = await browser.newContext();
  const page = await context.newPage();
  await signInThroughTheForm(page, email, DEMO_PASSWORD);
  const state = await context.storageState();
  await context.close();
  return state;
}

/** The script files a page loads while `act` runs. */
async function scriptsDuring(page: Page, act: () => Promise<unknown>) {
  const scripts: string[] = [];
  const record = (request: { url: () => string; resourceType: () => string }) => {
    if (request.resourceType() === "script") scripts.push(request.url());
  };
  page.on("request", record);
  await act();
  await page.waitForLoadState("networkidle");
  page.off("request", record);
  return scripts;
}

test("what a page defers loads when asked for, not before, and works when it arrives", async ({ browser }) => {
  test.setTimeout(180_000);
  const failed: string[] = [];
  // A prefetch cancelled by moving on is not a missing chunk; a script that failed to arrive is.
  const noteFailure = (request: Request) => {
    if (request.failure()?.errorText !== "net::ERR_ABORTED") failed.push(request.url());
  };

  await test.step("the paper tools' part for no paper is not loaded when arriving from a paper", async () => {
    const direct = await (await browser.newContext()).newPage();
    direct.on("requestfailed", noteFailure);
    const scripts = await scriptsDuring(direct, () => direct.goto("/similar"));
    await expect(direct.getByRole("heading", { name: "Choose a paper to start" })).toBeVisible();
    const sources = await Promise.all(scripts.map(async (url) => [url, await (await direct.request.get(url)).text()] as const));
    const part = sources.filter(([, source]) => source.includes("Choose a paper to start")).map(([url]) => new URL(url).pathname);
    expect(part.length).toBeGreaterThan(0);

    const fromPaper = await (await browser.newContext()).newPage();
    fromPaper.on("requestfailed", noteFailure);
    const loaded = await scriptsDuring(fromPaper, async () => {
      await fromPaper.goto("/?q=information%20retrieval");
      await fromPaper.getByRole("link", { name: "Find similar" }).first().click({ timeout: 60_000 });
      await expect(fromPaper).toHaveURL(/\/similar\?paper=/);
    });
    await expect(fromPaper.getByRole("heading", { name: "Choose a paper to start" })).toHaveCount(0);
    expect(loaded.map((url) => new URL(url).pathname).filter((path) => part.includes(path))).toEqual([]);
  });

  await test.step("the reset confirmation loads when pressed, takes focus and hands it back", async () => {
    const context = await browser.newContext({ storageState: await signedIn(browser, DEMO.student) });
    const page = await context.newPage();
    page.on("requestfailed", noteFailure);
    const sent: string[] = [];
    page.on("request", (request) => {
      if (request.method() === "POST") sent.push(request.url());
    });
    await page.goto("/recommendations");
    await page.waitForLoadState("networkidle");
    await expect(page.getByRole("heading", { name: "Technical details" })).toBeVisible();
    const reset = page.getByRole("button", { name: "Reset what was learned" });
    const added = await scriptsDuring(page, async () => {
      await reset.focus();
      await page.keyboard.press("Enter");
      await expect(page.getByRole("dialog", { name: "Reset what was learned?" })).toBeVisible();
    });
    expect(added.length).toBeGreaterThan(0);
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(reset).toBeFocused();
    expect(sent.filter((url) => url.includes("/personalization/reset"))).toEqual([]);
    await context.close();
  });

  expect(failed.filter((url) => url.endsWith(".js"))).toEqual([]);
});

/**
 * A page with names like "Erdős" or "Łukasz": the browser also downloads the Latin-Ext files, which is
 * what can push a page over the font budget (Decision 4). Over budget today, and known: the budget needs
 * smaller Latin-Ext files, which means re-subsetting them. `test.fail` keeps it visible here: this test
 * starts failing the suite the day the page fits, so the note cannot outlive the problem.
 */
for (const [name, italic] of [["upright text", false], ["italic text too", true]] as const) {
  test(`fonts actually downloaded by a page that needs Latin-Ext, ${name}`, async ({ browser }) => {
    test.fail(true, "Known: 128.8 kB (169.4 kB with italics) against 100 kB. The Latin-Ext files are unmodified Fontsource subsets.");
    const context = await browser.newContext();
    const page = await context.newPage();
    const responses: Promise<{ file: string; bytes: number }>[] = [];
    page.on("response", (response) => {
      if (/\.woff2(\?|$)/.test(response.url())) responses.push(response.body().then((body) => ({ file: new URL(response.url()).pathname.split("/").pop() ?? "", bytes: body.length })));
    });
    await page.goto("/login");
    await page.waitForLoadState("networkidle");
    await page.evaluate((withItalic) => {
      const add = (tag: string, text: string, family: string, style = "normal") => {
        const element = document.createElement(tag);
        element.textContent = text;
        element.style.fontFamily = family;
        element.style.fontStyle = style;
        document.body.append(element);
      };
      add("p", "Łukasz Erdős, ordinary text", "var(--rc-font-sans)");
      add("p", "Erdős and Łukasz, a paper title", "var(--rc-font-serif)");
      if (withItalic) add("p", "Erdős and Łukasz, in a heading", "var(--rc-font-serif)", "italic");
      return document.fonts.ready;
    }, italic);
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(500);
    const fonts = await Promise.all(responses);
    const fontBytes = fonts.reduce((sum, font) => sum + font.bytes, 0);
    mkdirSync(path.dirname(REPORT), { recursive: true });
    writeFileSync(REPORT.replace(".json", `-latin-ext-${italic ? "italic" : "upright"}.json`), JSON.stringify({ fonts, fontBytes }, null, 1));
    await context.close();
    expect(fontBytes).toBeLessThanOrEqual(FONT_BUDGET);
  });
}

for (const role of ["visitor", "student", "faculty", "admin"] as const) {
  test(`${role}: pages do not shift, repeat a request or fail as they load`, async ({ browser }) => {
    test.setTimeout(420_000);
    const storageState = role === "visitor" ? undefined : await signedIn(browser, DEMO[role]);
    for (const width of WIDTHS) {
      const touch = width < 1024;
      for (const target of ROUTES[role]) {
        await test.step(`${target} at ${width}px`, async () => {
          // A context of its own: an empty cache is a first visit, so the transfers are real.
          const context = await browser.newContext({ viewport: { width, height: width >= 1024 ? 900 : 844 }, isMobile: touch, hasTouch: touch, storageState });
          const page = await context.newPage();
          const { cls, repeated, errors, shellRequests, routeRequests, sequentialRequests, fonts, fontBytes, fontPreloads, scriptFiles, scriptBytes } = await measured(page, target);
          expect.soft(cls, `${target} at ${width}px: layout shift`).toBeLessThanOrEqual(CLS_BUDGET);
          expect.soft(repeated, `${target} at ${width}px: requests made twice`).toEqual([]);
          expect.soft(errors, `${target} at ${width}px: page errors`).toEqual([]);
          expect.soft(routeRequests, `${target} at ${width}px: the route's own API requests`).toBeLessThanOrEqual(REQUEST_BUDGETS[target] ?? REQUESTS_BUDGET);
          expect.soft(fontBytes, `${target} at ${width}px: fonts downloaded`).toBeLessThanOrEqual(FONT_BUDGET);
          expect.soft(fontPreloads, `${target} at ${width}px: font preloads`).toBeLessThanOrEqual(1);
          report.push({ role, path: target, width, cls, shellRequests, routeRequests, totalRequests: shellRequests + routeRequests, sequentialRequests, fonts, fontBytes, fontPreloads, scriptFiles, scriptBytes });
          await context.close();
        });
      }
    }
    mkdirSync(path.dirname(REPORT), { recursive: true });
    // Every role's test adds to the file: a failed test restarts the worker, and this array with it.
    writeFileSync(REPORT.replace(".json", `-${role}.json`), JSON.stringify(report.filter((load) => load.role === role), null, 1));
  });
}
