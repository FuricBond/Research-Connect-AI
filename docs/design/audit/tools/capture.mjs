// Design audit capture: screenshots, axe, focus, overflow and runtime metrics for every
// important route and role on a LOCAL production build (default http://localhost:3000).
//
// Usage (from the repository root, after `npx playwright install chromium` in frontend/):
//   AUDIT_STUDENT_EMAIL=… AUDIT_STUDENT_PASSWORD=… AUDIT_FACULTY_EMAIL=… AUDIT_FACULTY_PASSWORD=…
//   AUDIT_ADMIN_EMAIL=… AUDIT_ADMIN_PASSWORD=… AUDIT_POSTING_ID=<uuid> AUDIT_WORKSPACE_ITEM_ID=<uuid>
//   node docs/design/audit/tools/capture.mjs            (ONLY=public,student to limit roles)
// Use test accounts on a local stack only. Session state is written to the OS temp folder and
// deleted immediately; nothing here prints a token or password. Names and emails on the admin
// user table are masked in screenshots.
import { createRequire } from "node:module";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const REPO = path.resolve(path.dirname(new URL(import.meta.url).pathname).replace(/^\/([A-Za-z]:)/, "$1"), "../../../..");
const require = createRequire(path.join(REPO, "frontend/package.json"));
const { chromium } = require("playwright");
const AXE = require.resolve("axe-core/axe.min.js");

const HERE = os.tmpdir();
const WEB = process.env.AUDIT_WEB_URL ?? "http://localhost:3000";
const API = process.env.AUDIT_API_URL ?? "http://localhost:8000";
const AUDIT_DIR = path.join(REPO, "docs/design/audit");
const OUT = path.join(AUDIT_DIR, "screenshots");
const env = (k) => { const v = process.env[k]; if (!v) throw new Error(`set ${k}`); return v; };
const accounts = Object.fromEntries(["student", "faculty", "admin"].map((r) => [r, { email: env(`AUDIT_${r.toUpperCase()}_EMAIL`), password: env(`AUDIT_${r.toUpperCase()}_PASSWORD`) }]));
const ids = { posting: env("AUDIT_POSTING_ID"), workspace_item: env("AUDIT_WORKSPACE_ITEM_ID") };
const ONLY = process.env.ONLY ? new Set(process.env.ONLY.split(",")) : null;

const VP = {
  "1440": { width: 1440, height: 900, touch: false },
  "1280": { width: 1280, height: 800, touch: false },
  "1024": { width: 1024, height: 768, touch: false },
  "768": { width: 768, height: 1024, touch: true },
  "390": { width: 390, height: 844, touch: true },
  "360": { width: 360, height: 800, touch: true },
};
const ALL = Object.keys(VP);
const KEY = ["1440", "390"];
const AXE_VPS = new Set(["1440", "390"]);

// ── Interactions used by some captures ──────────────────────────────────────
async function search(page) {
  await page.getByRole("searchbox", { name: "Search research literature" }).fill("graph neural networks explainability");
  await page.getByRole("button", { name: "Submit search" }).click();
  await page.locator(".research-card").first().waitFor({ timeout: 30000 });
}
async function openWhy(page) {
  await search(page);
  await page.getByRole("button", { name: /why this rank/i }).first().click();
  await page.locator(".drawer-overlay").waitFor({ timeout: 10000 });
  await page.waitForTimeout(500);
}
async function findSimilar(page) {
  await search(page);
  await page.getByRole("button", { name: /find similar research/i }).first().click();
  await page.waitForURL("**/similar", { timeout: 15000 });
}
async function matchVenues(page) {
  await search(page);
  await page.getByRole("button", { name: /match calls/i }).first().click();
  await page.waitForURL("**/opportunities", { timeout: 15000 });
}

// [name, path, viewports, action?, opts]
const PLAN = {
  public: [
    ["search-landing", "/", ALL],
    ["login", "/login", ALL],
    ["register", "/register", KEY],
    ["browse-calls", "/browse", KEY],
    ["postings", "/postings", KEY],
    ["similar-no-selection", "/similar", ["1440"]],
    ["not-found", "/this-page-does-not-exist", ["1440"]],
    ["protected-redirect", "/workspace", ["1440"]],
  ],
  student: [
    ["similar-no-selection", "/similar", ["1440", "390"], null, { clearSelection: true }],
    ["opportunity-matcher-no-selection", "/opportunities", ["1440"], null, { clearSelection: true }],
    ["search-results", "/", ALL, search],
    ["search-why-this-drawer", "/", KEY, openWhy],
    ["similar-research", "/", KEY, findSimilar],
    ["opportunity-matcher", "/", KEY, matchVenues],
    ["browse-calls", "/browse", KEY],
    ["postings", "/postings", ALL],
    ["posting-detail", `/postings/${ids.posting}`, KEY],
    ["my-applications", "/postings/applications", KEY],
    ["supervisors", "/supervisors", KEY],
    ["peers", "/peers", KEY],
    ["workspace", "/workspace", ALL],
    ["workspace-item", `/workspace/${ids.workspace_item}`, KEY],
    ["workspace-submission", `/workspace/${ids.workspace_item}/submission`, KEY],
    ["submissions", "/submissions", KEY],
    ["reading-list", "/reading-list", ALL],
    ["calendar", "/calendar", ALL],
    ["notifications", "/notifications", ALL],
    ["notification-settings", "/settings/notifications", KEY],
    ["researcher-profile", "/researcher", KEY],
    ["researcher-preferences", "/researcher/preferences", KEY],
    ["admin-denied", "/admin", ["1440"]],
  ],
  faculty: [
    ["postings-mine", "/postings", KEY],
    ["posting-manage", `/postings/${ids.posting}`, KEY],
    ["notifications", "/notifications", KEY],
    ["researcher-profile", "/researcher", ["1440"]],
    ["workspace-empty", "/workspace", ["1440"]],
    ["supervisors-denied", "/supervisors", ["1440"]],
  ],
  admin: [
    ["admin-console", "/admin", ALL, null, { mask: [".auth-admin-name", ".auth-admin-email"] }],
    ["notifications", "/notifications", ["1440"]],
    ["search-landing", "/", ["1440"]],
  ],
};

const PERF_INIT = () => {
  window.__rc = { lcp: 0, cls: 0 };
  try {
    new PerformanceObserver((l) => { for (const e of l.getEntries()) window.__rc.lcp = e.startTime; })
      .observe({ type: "largest-contentful-paint", buffered: true });
    new PerformanceObserver((l) => { for (const e of l.getEntries()) if (!e.hadRecentInput) window.__rc.cls += e.value; })
      .observe({ type: "layout-shift", buffered: true });
  } catch {}
};

async function settle(page) {
  await page.waitForLoadState("networkidle", { timeout: 15000 }).catch(() => {});
  await page.waitForFunction(() => !document.querySelector(".auth-pending, .loading-state, .notifications-loading, .postings-loading"), null, { timeout: 20000 }).catch(() => {});
  await page.waitForTimeout(700);
}

async function signIn(context, creds) {
  const page = await context.newPage();
  await page.goto(`${WEB}/login`);
  await page.getByLabel(/email/i).fill(creds.email);
  await page.getByLabel(/password/i).fill(creds.password);
  await page.getByRole("button", { name: /^sign in$/i }).click();
  await page.getByRole("button", { name: /sign out/i }).waitFor({ timeout: 20000 });
  await page.close();
}

async function focusAudit(page) {
  const steps = [];
  await page.evaluate(() => { document.activeElement && document.activeElement.blur(); window.scrollTo(0, 0); });
  await page.mouse.click(1, 1).catch(() => {});
  for (let i = 0; i < 14; i++) {
    await page.keyboard.press("Tab");
    steps.push(await page.evaluate(() => {
      const el = document.activeElement;
      if (!el || el === document.body) return null;
      const cs = getComputedStyle(el);
      const visible = (cs.outlineStyle !== "none" && parseFloat(cs.outlineWidth) > 0) || (cs.boxShadow && cs.boxShadow !== "none");
      const name = (el.getAttribute("aria-label") || el.textContent || el.getAttribute("placeholder") || "").trim().replace(/\s+/g, " ").slice(0, 40);
      return { tag: el.tagName.toLowerCase(), name, visible, outline: `${cs.outlineStyle} ${cs.outlineWidth}`, shadow: cs.boxShadow.slice(0, 40) };
    }));
  }
  return steps;
}

async function runAxe(page) {
  await page.addScriptTag({ path: AXE });
  return page.evaluate(async () => {
    const r = await window.axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"] } });
    return r.violations.map((v) => ({ id: v.id, impact: v.impact, tags: v.tags.filter((t) => t.startsWith("wcag")), help: v.help, nodes: v.nodes.length, sample: v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(" | ").slice(0, 300) }));
  });
}

async function capture(context, role, [name, route, vps, action, opts = {}]) {
  const page = await context.newPage();
  await page.addInitScript(PERF_INIT);
  if (opts.clearSelection) await page.addInitScript(() => { try { sessionStorage.clear(); } catch {} });
  const consoleErrors = [];
  const apiCalls = [];
  const failures = [];
  page.on("console", (m) => { if (m.type() === "error") consoleErrors.push(m.text().slice(0, 200)); });
  page.on("pageerror", (e) => consoleErrors.push("pageerror: " + e.message.slice(0, 200)));
  page.on("request", (r) => { if (r.url().startsWith(API)) apiCalls.push(`${r.method()} ${r.url().slice(API.length).split("?")[0]}`); });
  page.on("response", (r) => { if (r.url().startsWith(API) && r.status() >= 400) failures.push(`${r.status()} ${r.request().method()} ${r.url().slice(API.length).split("?")[0]}`); });

  const results = [];
  const first = VP[vps[0]];
  await page.setViewportSize({ width: first.width, height: first.height });
  const t0 = Date.now();
  await page.goto(WEB + route, { waitUntil: "load" });
  await settle(page);
  if (action) { await action(page); await settle(page); }
  const metrics = await page.evaluate(() => {
    const nav = performance.getEntriesByType("navigation")[0];
    const js = performance.getEntriesByType("resource").filter((e) => e.name.endsWith(".js") || e.initiatorType === "script");
    return { lcp: Math.round(window.__rc?.lcp || 0), cls: +(window.__rc?.cls || 0).toFixed(3), dcl: Math.round(nav?.domContentLoadedEventEnd || 0), load: Math.round(nav?.loadEventEnd || 0), jsFiles: js.length, jsKB: Math.round(js.reduce((s, e) => s + (e.transferSize || e.encodedBodySize || 0), 0) / 1024) };
  });
  const dupes = Object.entries(apiCalls.reduce((m, c) => ((m[c] = (m[c] || 0) + 1), m), {})).filter(([, n]) => n > 1).map(([c, n]) => `${c} x${n}`);
  const base = { role, name, route, finalUrl: page.url().replace(WEB, ""), wallMs: Date.now() - t0, metrics, apiCalls: apiCalls.length, dupes, failures: [...new Set(failures)], consoleErrors: [...new Set(consoleErrors)].slice(0, 5) };

  let focus = null;
  for (const vp of vps) {
    const v = VP[vp];
    await page.setViewportSize({ width: v.width, height: v.height });
    await page.waitForTimeout(400);
    const dims = await page.evaluate(() => ({ h: document.documentElement.scrollHeight, sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth }));
    const dir = path.join(OUT, role);
    fs.mkdirSync(dir, { recursive: true });
    const file = path.join(dir, `${name}__${vp}.jpg`);
    const maxH = v.width >= 1024 ? 2600 : 3600;
    await page.screenshot({ path: file, type: "jpeg", quality: 62, fullPage: true, mask: (opts.mask || []).map((s) => page.locator(s)), maskColor: "#cbd5e1", clip: { x: 0, y: 0, width: v.width, height: Math.min(dims.h, maxH) } });
    const entry = { ...base, vp, file: path.relative(AUDIT_DIR, file).replace(/\\/g, "/"), pageHeight: dims.h, horizontalOverflowPx: Math.max(0, dims.sw - dims.cw) };
    if (AXE_VPS.has(vp)) entry.axe = await runAxe(page).catch((e) => [{ id: "axe-error", impact: "n/a", help: String(e).slice(0, 120), nodes: 0 }]);
    if (vp === "1440" && !action) focus = focus || (await focusAudit(page).catch(() => null));
    if (focus && vp === "1440") entry.focus = focus;
    results.push(entry);
    process.stdout.write(`  ${role}/${name}@${vp} h=${dims.h} overflow=${entry.horizontalOverflowPx}\n`);
  }
  await page.close();
  return results;
}

const browser = await chromium.launch();
const all = [];
for (const role of Object.keys(PLAN)) {
  if (ONLY && !ONLY.has(role)) continue;
  const contexts = {};
  for (const touch of [false, true]) {
    contexts[touch] = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1, isMobile: touch, hasTouch: touch, locale: "en-GB", timezoneId: "Asia/Kolkata", colorScheme: "light" });
  }
  if (role !== "public") {
    await signIn(contexts[false], accounts[role]);
    const state = path.join(HERE, `.state-${role}.json`);
    await contexts[false].storageState({ path: state });
    await contexts[true].close();
    contexts[true] = await browser.newContext({ storageState: state, viewport: { width: 390, height: 844 }, deviceScaleFactor: 1, isMobile: true, hasTouch: true, locale: "en-GB", timezoneId: "Asia/Kolkata", colorScheme: "light" });
    fs.unlinkSync(state);
  }
  for (const item of PLAN[role]) {
    const [name, route, vps, action, opts] = item;
    const desk = vps.filter((v) => !VP[v].touch);
    const touch = vps.filter((v) => VP[v].touch);
    try {
      if (desk.length) all.push(...(await capture(contexts[false], role, [name, route, desk, action, opts])));
      if (touch.length) all.push(...(await capture(contexts[true], role, [name, route, touch, action, opts])));
    } catch (e) {
      console.log(`  FAILED ${role}/${name}: ${String(e).slice(0, 200)}`);
      all.push({ role, name, route, error: String(e).slice(0, 300) });
    }
  }
  for (const c of Object.values(contexts)) await c.close();
}
await browser.close();
const outFile = path.join(AUDIT_DIR, "data", ONLY ? `capture-results-${[...ONLY].join("-")}.json` : "capture-results.json");
fs.writeFileSync(outFile, JSON.stringify(all, null, 2));
console.log(`captured ${all.length} entries -> ${outFile}`);
