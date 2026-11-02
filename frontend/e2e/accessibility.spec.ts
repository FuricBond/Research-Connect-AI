import { readFileSync } from "node:fs";
import { expect, test, type Browser, type BrowserContextOptions, type Page } from "@playwright/test";
import { API_URL, DEMO, DEMO_PASSWORD, accountMenu, signInThroughTheForm } from "./support";

/**
 * P11 — accessibility, reflow and motion across the application (FRONTEND_REDESIGN_PLAN.md §17 and
 * §22 P11, DESIGN_SYSTEM.md §11 and §12.5).
 *
 * axe-core (the copy eslint-plugin-jsx-a11y installs, injected as the audit tool injects it) runs
 * on every main route of each role and on the overlays those routes open, in the light and the dark
 * theme, at 1440px and at 390px with touch: any serious or critical violation fails, and the page
 * must have the theme asked for and no hydration error. At 320px every route fits: the page does
 * not scroll sideways and nothing visible reaches past the edge outside a region that scrolls or
 * clips on its own (WCAG 1.4.10), also when names and titles hold a word no line can fit. With reduced motion asked for, nothing moves and every state
 * change still happens; without it, the motion tokens apply.
 *
 * Three sign-ins, one per role, each reused through its storage state.
 */
const AXE_SOURCE = readFileSync(require.resolve("axe-core/axe.min.js"), "utf8");
const AXE_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"];
const THEMES = ["light", "dark"] as const;
const VIEWPORTS = [
  { width: 1440, height: 900, touch: false },
  { width: 390, height: 844, touch: true },
] as const;
const QUERY = "/?q=information%20retrieval";

type Theme = (typeof THEMES)[number];
type Role = "visitor" | "student" | "faculty" | "admin";
type Ids = { posting: string; call: string; item: string; own: string };
/** A page and, optionally, what to do on it first; `act` returns false when the state does not exist at this width. */
type Check = { path: string; state?: string; act?: (page: Page) => Promise<void | false> };

// ── States beyond a page load ────────────────────────────────────────────────

const pause = (page: Page) => page.waitForTimeout(250);
const appearance: Check["act"] = async (page) => {
  await page.getByRole("button", { name: "Appearance" }).click();
  await expect(page.getByRole("group", { name: "Colour theme" })).toBeVisible();
};
const accountPanel: Check["act"] = async (page) => {
  await accountMenu(page).click();
  await expect(page.getByRole("button", { name: /sign out/i })).toBeVisible();
};
const bellPanel: Check["act"] = async (page) => {
  await page.getByRole("banner").getByRole("button", { name: /^Notifications/ }).click();
  await expect(page.getByRole("link", { name: "View all notifications" })).toBeVisible();
  await page.waitForLoadState("networkidle");
};
const drawer: Check["act"] = async (page) => {
  if ((page.viewportSize()?.width ?? 0) >= 1024) return false; // the sidebar is always there
  await page.getByRole("button", { name: "Menu", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "Menu" })).toBeVisible();
  await pause(page);
};
const results = (page: Page) => expect(page.getByRole("button", { name: /^Why this result\?/ }).first()).toBeVisible({ timeout: 60_000 });
const paperPanel: Check["act"] = async (page) => {
  await results(page);
  const title = page.locator(".paper-card").first().getByRole("heading").getByRole("button");
  const name = (await title.textContent())?.trim() ?? "";
  await title.click();
  await expect(page.getByRole("dialog", { name })).toBeVisible();
  await settled(page);
};
const evidence: Check["act"] = async (page) => {
  await results(page);
  await page.getByRole("button", { name: /^Why this result\?/ }).first().click();
  await expect(page.getByRole("dialog", { name: "Why this result?" })).toBeVisible();
  await pause(page);
};
const filterSheet: Check["act"] = async (page) => {
  if ((page.viewportSize()?.width ?? 0) >= 1280) return false; // the filter rail is on the page
  await results(page);
  await page.getByRole("button", { name: /^Filters/ }).first().click();
  await expect(page.getByRole("dialog", { name: /^Filters/ })).toBeVisible();
  await pause(page);
};
const paperTool = (link: "Find similar" | "Find venues", address: RegExp): Check["act"] => async (page) => {
  await results(page);
  await page.getByRole("link", { name: link }).first().click();
  await expect(page).toHaveURL(address);
  await settled(page);
};
const statusMenu: Check["act"] = async (page) => {
  await page.getByRole("button", { name: /^Status/ }).first().click();
  await expect(page.getByRole("menu").first()).toBeVisible();
};
const roleDialog: Check["act"] = async (page) => {
  await page.getByRole("button", { name: /^Role of .*: Student researcher\. Change the role$/ }).first().click();
  await page.getByRole("menuitem", { name: "Faculty" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await pause(page);
};

const fieldErrors: Check["act"] = async (page) => {
  await page.getByRole("button", { name: /create account/i }).click();
  await expect(page.locator('[aria-invalid="true"]').first()).toBeVisible();
};
/** The page when the server fails one request: the error state, in this theme. The route ends with the check. */
const failing = (pattern: string): Check["act"] => async (page) => {
  await page.route(pattern, (route) =>
    route.fulfill({
      status: 500,
      contentType: "application/json",
      headers: { "access-control-allow-origin": new URL(page.url()).origin, "access-control-allow-credentials": "true" },
      body: JSON.stringify({ detail: "Failed for this check" }),
    })
  );
  await page.reload();
  await settled(page);
  await expect(page.getByRole("button", { name: "Try again" }).first()).toBeVisible();
};

function checks(role: Role, ids: Ids): Check[] {
  switch (role) {
    case "visitor":
      return [
        { path: "/" }, { path: "/", state: "appearance", act: appearance }, { path: "/login" }, { path: "/register" }, { path: "/register", state: "field errors", act: fieldErrors },
        { path: "/browse" }, { path: `/calls/${ids.call}` }, { path: "/postings" }, { path: `/postings/${ids.posting}` },
        { path: "/similar" }, { path: "/opportunities" }, { path: "/settings" }, { path: "/no-such-page" },
        { path: QUERY, state: "paper panel", act: paperPanel }, { path: "/", state: "navigation drawer", act: drawer },
      ];
    case "student":
      return [
        { path: "/dashboard" }, { path: "/dashboard", state: "account menu", act: accountPanel }, { path: "/dashboard", state: "notifications", act: bellPanel },
        { path: "/dashboard", state: "navigation drawer", act: drawer },
        { path: QUERY }, { path: QUERY, state: "paper panel", act: paperPanel }, { path: QUERY, state: "evidence", act: evidence },
        { path: QUERY, state: "filters", act: filterSheet },
        { path: QUERY, state: "similar papers", act: paperTool("Find similar", /\/similar\?paper=/) },
        { path: QUERY, state: "venues", act: paperTool("Find venues", /\/opportunities\?paper=/) },
        { path: "/recommendations" }, { path: "/researcher" }, { path: "/researcher/preferences" }, { path: "/supervisors" }, { path: "/peers" },
        { path: "/workspace" }, { path: "/workspace", state: "status menu", act: statusMenu }, { path: "/workspace", state: "failed", act: failing("**/api/v1/workspace?*") },
        ...["", "?tab=tasks", "?tab=submission", "?tab=members", "?tab=activity"].map((tab) => ({ path: `/workspace/${ids.item}${tab}` })),
        { path: "/submissions" }, { path: "/reading-list" }, { path: "/calendar" }, { path: "/notifications" }, { path: "/settings" }, { path: "/verify-email" },
        { path: "/postings" }, { path: `/postings/${ids.posting}` }, { path: "/postings/applications" }, { path: "/browse" }, { path: `/calls/${ids.call}` },
        { path: "/admin" },
      ];
    case "faculty":
      return [
        { path: "/dashboard" }, { path: "/postings?view=mine" }, { path: "/postings/new" }, { path: `/postings/${ids.own}` }, { path: `/postings/${ids.own}/edit` },
        { path: "/postings/applicants" }, { path: "/researcher" }, { path: "/supervisors" }, { path: "/notifications" }, { path: "/settings" }, { path: "/workspace" },
      ];
    case "admin":
      return [
        { path: "/admin" }, { path: "/admin/users" }, { path: "/admin/users", state: "role change", act: roleDialog }, { path: "/admin/users", state: "failed", act: failing("**/api/v1/admin/users?*") }, { path: "/admin/research-data" },
        { path: "/notifications" }, { path: "/settings" },
      ];
  }
}

// ── Helpers ──────────────────────────────────────────────────────────────────

async function settled(page: Page) {
  await page.waitForLoadState("networkidle");
  await expect(page.locator('main [aria-busy="true"]')).toHaveCount(0, { timeout: 30_000 });
  await pause(page);
}

type AxeRun = { passes: unknown[]; incomplete: unknown[]; inapplicable: unknown[]; violations: { id: string; impact: string | null; help: string; nodes: { target: string[] }[] }[] };

/**
 * The serious and critical axe violations on the page, one line each, and how many rules axe
 * evaluated — so a scan that did not run is never read as a clean one.
 */
async function axe(page: Page): Promise<{ serious: string[]; rules: number }> {
  // Not a script tag: the Content-Security-Policy rightly refuses an inline script without its nonce.
  await page.evaluate(AXE_SOURCE);
  return page.evaluate(async (tags) => {
    const run = await (window as unknown as { axe: { run: (context: Document, options: object) => Promise<AxeRun> } }).axe.run(document, {
      runOnly: { type: "tag", values: tags },
      resultTypes: ["violations"],
    });
    return {
      rules: run.passes.length + run.incomplete.length + run.inapplicable.length + run.violations.length,
      serious: run.violations
        .filter((v) => v.impact === "serious" || v.impact === "critical")
        .map((v) => `${v.id} (${v.impact}, ${v.nodes.length}): ${v.help} — ${v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(" | ")}`),
    };
  }, AXE_TAGS);
}

/** What reaches past the right or left edge at this width, outside a region that scrolls or clips, and how many boxes were measured. */
async function overflow(page: Page): Promise<{ found: string[]; measured: number }> {
  return page.evaluate(() => {
    const width = document.documentElement.clientWidth;
    const found: string[] = [];
    const sideways = document.documentElement.scrollWidth - width;
    if (sideways > 0) found.push(`the page scrolls sideways by ${sideways}px`);
    const inside = (rect: DOMRect) => rect.left >= -1 && rect.right <= width + 1;
    const contained = (el: Element) => {
      for (let parent = el.parentElement; parent && parent !== document.body; parent = parent.parentElement) {
        if (/^(auto|scroll|hidden|clip)$/.test(getComputedStyle(parent).overflowX)) return inside(parent.getBoundingClientRect());
      }
      return false;
    };
    for (const el of document.body.querySelectorAll("*")) {
      const rect = el.getBoundingClientRect();
      if (!rect.width || !rect.height || inside(rect)) continue;
      if (getComputedStyle(el).visibility === "hidden" || el.closest(".rc-visually-hidden, .rc-skip-link")) continue;
      if (contained(el)) continue;
      const text = (el.textContent ?? "").trim().replace(/\s+/g, " ").slice(0, 40);
      found.push(`<${el.tagName.toLowerCase()}> "${text}" spans ${Math.round(rect.left)}–${Math.round(rect.right)}px`);
      if (found.length > 5) break;
    }
    return { found, measured: document.body.querySelectorAll("*").length };
  });
}

/** A word no line can hold (a long address, a URL) on the end of the names, titles and places in an answer. */
const LONG_WORD = "Supercalifragilisticexpialidocious".repeat(4);
const PEOPLES_WORDS = new Set(["title", "full_name", "display_name", "name", "email", "contact_email", "institution", "department", "venue", "venue_name", "journal", "location", "display_label", "preference_value", "posting_title", "opportunity_title"]);
function stretched(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(stretched);
  if (!value || typeof value !== "object") return value;
  return Object.fromEntries(Object.entries(value).map(([key, entry]) => [key, typeof entry === "string" && entry && PEOPLES_WORDS.has(key) ? `${entry} ${LONG_WORD}` : stretched(entry)]));
}

const HYDRATION = /hydrat|Minified React error #(418|423|425)\b/i;

async function signedIn(browser: Browser, email: string) {
  const context = await browser.newContext();
  const page = await context.newPage();
  await signInThroughTheForm(page, email, DEMO_PASSWORD);
  const state = await context.storageState();
  await context.close();
  return state;
}

function token(state: Awaited<ReturnType<typeof signedIn>>) {
  return state.origins.flatMap((origin) => origin.localStorage).find((entry) => entry.name === "researchconnect_access_token")?.value ?? "";
}

/** A page in a fresh context with the theme stored before the first script runs. */
async function themedPage(browser: Browser, theme: Theme, options: BrowserContextOptions) {
  const context = await browser.newContext(options);
  await context.addInitScript((value) => {
    try {
      window.localStorage.setItem("rc-theme", value);
    } catch {
      // Storage blocked: the theme script then follows the system.
    }
  }, theme);
  const page = await context.newPage();
  const hydration: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error" && HYDRATION.test(message.text())) hydration.push(message.text().slice(0, 200));
  });
  page.on("pageerror", (error) => {
    if (HYDRATION.test(error.message)) hydration.push(error.message.slice(0, 200));
  });
  return { context, page, hydration };
}

/** Seconds in a computed duration list ("0.2s, 80ms" → [0.2, 0.08]). */
const seconds = (value: string) => value.split(",").map((part) => (part.trim().endsWith("ms") ? parseFloat(part) / 1000 : parseFloat(part)));

// ── The suites ───────────────────────────────────────────────────────────────

test.describe("motion", () => {
  for (const reducedMotion of ["reduce", "no-preference"] as const) {
    test(`with ${reducedMotion === "reduce" ? "reduced motion asked for nothing moves" : "no preference the motion tokens apply"}, and every state change still happens`, async ({ browser }) => {
      const context = await browser.newContext({ reducedMotion, viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
      const page = await context.newPage();
      await page.goto("/");
      await settled(page);
      const reduce = reducedMotion === "reduce";

      const tokens = await page.evaluate(() => ["instant", "fast", "base"].map((name) => getComputedStyle(document.documentElement).getPropertyValue(`--rc-duration-${name}`).trim()));
      expect(tokens).toEqual(reduce ? ["0ms", "0ms", "0ms"] : ["80ms", "140ms", "200ms"]);
      expect(await page.evaluate(() => getComputedStyle(document.documentElement).scrollBehavior)).toBe("auto");

      // The navigation drawer: it slides in only without the preference; it opens, takes focus,
      // closes on Escape and hands focus back either way.
      const menu = page.getByRole("button", { name: "Menu", exact: true });
      const transition = seconds(await menu.evaluate((el) => getComputedStyle(el).transitionDuration));
      await menu.click();
      const sheet = page.getByRole("dialog", { name: "Menu" });
      await expect(sheet).toBeVisible();
      expect(await sheet.evaluate((el) => el.contains(document.activeElement))).toBe(true);
      const slide = await sheet.evaluate((el) => ({ name: getComputedStyle(el).animationName, duration: getComputedStyle(el).animationDuration }));
      expect(slide.name).not.toBe("none");
      if (reduce) {
        expect(Math.max(...seconds(slide.duration), ...transition)).toBeLessThanOrEqual(0.00001);
      } else {
        expect(seconds(slide.duration)).toEqual([0.2]);
        expect(Math.min(...transition)).toBeGreaterThan(0);
      }
      await page.keyboard.press("Escape");
      await expect(sheet).toBeHidden();
      await expect(menu).toBeFocused();

      // A panel from the header, and a theme change, still apply at once.
      await page.getByRole("button", { name: "Appearance" }).click();
      const themes = page.getByRole("group", { name: "Colour theme" });
      await expect(themes).toBeVisible();
      await themes.getByRole("radio", { name: "Dark theme" }).check();
      expect(await page.evaluate(() => document.documentElement.dataset.theme)).toBe("dark");
      await context.close();
    });
  }
});

const ids: Ids = { posting: "", call: "", item: "", own: "" };
const states: Partial<Record<Role, Awaited<ReturnType<typeof signedIn>> | undefined>> = { visitor: undefined };

test.beforeAll(async ({ request }) => {
  const postings = await (await request.get(`${API_URL}/api/v1/postings?limit=20`)).json();
  const calls = await (await request.get(`${API_URL}/api/opportunities?page_size=5`)).json();
  ids.posting = postings.postings[0].id;
  ids.call = calls.items[0].id;
});

test("a theme chosen on the page paints it exactly as a page loaded in that theme, focus ring included", async ({ browser }) => {
  // Colours come only from the tokens, which follow data-theme: nothing may keep the old theme's.
  const SAMPLES = ["body", "header", "main", "main h1", ".opportunity-card", ".opportunity-card a", ".opportunity-card span", "main button", "main select, main input"];
  const paint = (page: Page) =>
    page.evaluate((selectors) => {
      return selectors.map((selector) => {
        const el = document.querySelector(selector);
        if (!el) return `${selector}: missing`;
        const style = getComputedStyle(el);
        return `${selector}: ${style.color} on ${style.backgroundColor}, edge ${style.borderTopColor}`;
      });
    }, SAMPLES);
  const ring = async (page: Page) => {
    // A key first, so the focus is a keyboard one: the skip link shows the ring every control uses.
    await page.keyboard.press("Shift");
    await page.getByRole("link", { name: "Skip to main content" }).focus();
    return page.evaluate(() => {
      const style = getComputedStyle(document.activeElement as Element);
      return `${style.outlineStyle} ${style.outlineColor}`;
    });
  };

  const live = await themedPage(browser, "light", { viewport: { width: 1440, height: 900 } });
  await live.page.goto("/browse");
  await settled(live.page);
  const light = await paint(live.page);
  await live.page.getByRole("button", { name: "Appearance" }).click();
  await live.page.getByRole("group", { name: "Colour theme" }).getByRole("radio", { name: "Dark theme" }).check();
  await live.page.keyboard.press("Escape");
  await live.page.waitForTimeout(500); // colour transitions (at most 150ms, legacy ones) finish
  const switched ={ paint: await paint(live.page), ring: await ring(live.page) };

  const fresh = await themedPage(browser, "dark", { viewport: { width: 1440, height: 900 } });
  await fresh.page.goto("/browse");
  await settled(fresh.page);
  expect(switched.paint.filter((line) => line.endsWith("missing"))).toEqual([]);
  expect(switched.paint).not.toEqual(light);
  expect(switched.paint).toEqual(await paint(fresh.page));
  expect(switched.ring).toBe(await ring(fresh.page));
  expect(switched.ring).toMatch(/^solid /);
  expect([...live.hydration, ...fresh.hydration]).toEqual([]);
  await live.context.close();
  await fresh.context.close();
});

for (const role of ["visitor", "student", "faculty", "admin"] as const) {
  test.describe(role, () => {
    test.beforeAll(async ({ browser, request }) => {
      if (role === "visitor" || states[role]) return;
      states[role] = await signedIn(browser, DEMO[role]);
      const auth = { Authorization: `Bearer ${token(states[role]!)}` };
      if (role === "student") {
        // A tracked call for the workspace pages, as pages.spec saves one (saving is idempotent).
        const saved = await request.post(`${API_URL}/api/v1/workspace`, { headers: auth, data: { opportunity_id: ids.call } });
        expect([200, 201]).toContain(saved.status());
        ids.item = (await saved.json()).id;
      }
      if (role === "faculty") {
        const mine = await (await request.get(`${API_URL}/api/v1/postings/mine?limit=5`, { headers: auth })).json();
        ids.own = mine.postings[0].id;
      }
    });

    for (const theme of THEMES) {
      for (const { width, height, touch } of VIEWPORTS) {
        test(`axe: no serious or critical violation, ${theme} theme, ${width}px`, async ({ browser }) => {
          test.setTimeout(900_000);
          const { context, page, hydration } = await themedPage(browser, theme, { viewport: { width, height }, isMobile: touch, hasTouch: touch, storageState: states[role] });
          for (const check of checks(role, ids)) {
            await test.step(`${check.path}${check.state ? ` (${check.state})` : ""}`, async () => {
              await page.unrouteAll();
              await page.goto(check.path);
              await settled(page);
              if (check.act && (await check.act(page)) === false) return;
              expect.soft(await page.evaluate(() => document.documentElement.dataset.theme), check.path).toBe(theme);
              const result = await axe(page);
              expect.soft(result.rules, `${check.path}: axe evaluated no rule`).toBeGreaterThan(50);
              expect.soft(result.serious, `${check.path}${check.state ? ` (${check.state})` : ""}`).toEqual([]);
            });
          }
          expect(hydration, "hydration errors").toEqual([]);
          await context.close();
        });
      }

      test(`reflow: every page fits 320px, ${theme} theme`, async ({ browser }) => {
        test.setTimeout(600_000);
        const { context, page } = await themedPage(browser, theme, { viewport: { width: 320, height: 720 }, isMobile: true, hasTouch: true, storageState: states[role] });
        for (const check of checks(role, ids)) {
          await test.step(`${check.path}${check.state ? ` (${check.state})` : ""}`, async () => {
            await page.unrouteAll();
            await page.goto(check.path);
            await settled(page);
            if (check.act && (await check.act(page)) === false) return;
            const result = await overflow(page);
            expect.soft(result.measured, `${check.path}: nothing measured`).toBeGreaterThan(20);
            expect.soft(result.found, `${check.path}${check.state ? ` (${check.state})` : ""} at 320px`).toEqual([]);
          });
        }
        await context.close();
      });
    }

    test("reflow: long names and titles wrap at 320px instead of widening the page", async ({ browser }) => {
      test.setTimeout(300_000);
      const { context, page } = await themedPage(browser, "light", { viewport: { width: 320, height: 720 }, isMobile: true, hasTouch: true, storageState: states[role] });
      await context.route(`${API_URL}/**`, async (route) => {
        if (route.request().method() !== "GET" || route.request().url().endsWith("/auth/me")) return route.continue();
        const response = await route.fetch();
        if (!(response.headers()["content-type"] ?? "").includes("json")) return route.fulfill({ response });
        return route.fulfill({ response, body: JSON.stringify(stretched(await response.json())) });
      });
      for (const check of checks(role, ids).filter((entry) => !entry.act)) {
        await test.step(check.path, async () => {
          await page.goto(check.path);
          await settled(page);
          expect.soft((await overflow(page)).found, `${check.path} with long text at 320px`).toEqual([]);
        });
      }
      await context.close();
    });
  });
}
