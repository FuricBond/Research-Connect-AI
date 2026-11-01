#!/usr/bin/env node
/**
 * P12 — the JavaScript and CSS budgets (docs/design/audit/performance-baseline.md §5), checked on the
 * output of `next build`: a route over budget fails the build's job (FRONTEND_REDESIGN_PLAN.md §22).
 *
 *   npm run build && npm run check:bundle
 *
 * What is measured, gzip level 9, 1 kB = 1000 bytes, from .next/app-build-manifest.json:
 *  - First Load JS (budget 140): the JavaScript listed for a route's page. This is the figure `next
 *    build` prints in its route table.
 *  - With layouts (budget 140, Decision 5 of the audit): the page's list plus the chunks of the
 *    layouts above it, counted once each. A real visit downloads these too; `next build` leaves them
 *    out of its figure for app routes, so this is the one that says what a page needs to start.
 *  - CSS (budgeted): the stylesheets of the page and of the layouts above it.
 *
 * Neither figure counts what a page loads on demand (next/dynamic, React.lazy) or what the browser
 * prefetches. What a visit actually transfers is measured in the browser: e2e/performance.spec.ts.
 *
 * Exit codes: 0 within budget, 1 over budget, 2 no build to measure.
 */
import { existsSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { gzipSync } from "node:zlib";

const BUDGETS = {
  /** Largest route, First Load JS as `next build` prints it. */
  routeJs: 140,
  /** Largest route with the chunks of the layouts above it. */
  routeJsWithLayouts: 140,
  /** Typical route: the median of First Load JS. */
  typicalJs: 135,
  /** First Load JS shared by all. */
  sharedJs: 110,
  /** A route's CSS, layouts included. */
  routeCss: 28,
};

/** Routes that only redirect or say "not found": they would pull the typical route down. */
const NOT_TYPICAL = new Set(["/_not-found", "/settings/notifications", "/workspace/[id]/submission"]);

const kB = (bytes) => Math.round(bytes / 100) / 10;

function measure(buildDir) {
  const manifest = JSON.parse(readFileSync(join(buildDir, "app-build-manifest.json"), "utf8")).pages;
  const root = JSON.parse(readFileSync(join(buildDir, "build-manifest.json"), "utf8")).rootMainFiles ?? [];
  const sizes = new Map();
  const size = (file) => {
    if (!sizes.has(file)) sizes.set(file, gzipSync(readFileSync(join(buildDir, file)), { level: 9 }).length);
    return sizes.get(file);
  };
  const total = (files) => [...new Set(files)].reduce((sum, file) => sum + size(file), 0);
  const of = (files, extension) => (files ?? []).filter((file) => file.endsWith(extension));

  const routes = Object.keys(manifest)
    .filter((key) => key.endsWith("/page"))
    .map((key) => {
      const route = key.slice(0, -"/page".length) || "/";
      // The layouts above the page, from the root down.
      const layouts = ["/layout"];
      let path = "";
      for (const segment of route.split("/").filter(Boolean)) {
        path += `/${segment}`;
        if (manifest[`${path}/layout`]) layouts.push(`${path}/layout`);
      }
      const page = manifest[key];
      const above = layouts.flatMap((layout) => manifest[layout] ?? []);
      return {
        route,
        js: total(of(page, ".js")),
        jsWithLayouts: total([...of(page, ".js"), ...of(above, ".js")]),
        css: total([...of(page, ".css"), ...of(above, ".css")]),
      };
    })
    .sort((a, b) => b.js - a.js || a.route.localeCompare(b.route));

  const typical = routes.filter((entry) => !NOT_TYPICAL.has(entry.route)).map((entry) => entry.js).sort((a, b) => a - b);
  return { routes, shared: total(of(root, ".js")), typical: typical[Math.floor(typical.length / 2)] ?? 0 };
}

function failures({ routes, shared, typical }, budgets = BUDGETS) {
  const over = [];
  for (const { route, js, jsWithLayouts, css } of routes) {
    if (kB(js) > budgets.routeJs) over.push(`${route}: First Load JS ${kB(js)} kB is over ${budgets.routeJs} kB`);
    if (kB(jsWithLayouts) > budgets.routeJsWithLayouts) over.push(`${route}: JS with layouts ${kB(jsWithLayouts)} kB is over ${budgets.routeJsWithLayouts} kB`);
    if (kB(css) > budgets.routeCss) over.push(`${route}: CSS ${kB(css)} kB is over ${budgets.routeCss} kB`);
  }
  if (kB(typical) > budgets.typicalJs) over.push(`typical route: First Load JS ${kB(typical)} kB is over ${budgets.typicalJs} kB`);
  if (kB(shared) > budgets.sharedJs) over.push(`shared by all: ${kB(shared)} kB is over ${budgets.sharedJs} kB`);
  return over;
}

function main() {
  const at = process.argv.indexOf("--dir");
  const buildDir = resolve(at > 0 ? process.argv[at + 1] : ".next");
  if (!existsSync(join(buildDir, "app-build-manifest.json"))) {
    console.error(`No build to measure in ${buildDir}: run \`npm run build\` first.`);
    return 2;
  }
  const measured = measure(buildDir);
  console.log(`${"Route".padEnd(34)}${"First Load JS".padStart(14)}${"With layouts".padStart(14)}${"CSS".padStart(8)}`);
  for (const { route, js, jsWithLayouts, css } of measured.routes) {
    console.log(`${route.padEnd(34)}${kB(js).toFixed(1).padStart(14)}${kB(jsWithLayouts).toFixed(1).padStart(14)}${kB(css).toFixed(1).padStart(8)}`);
  }
  console.log(`\nShared by all ${kB(measured.shared)} kB (budget ${BUDGETS.sharedJs}), typical route ${kB(measured.typical)} kB (budget ${BUDGETS.typicalJs}).`);
  const over = failures(measured);
  if (over.length) {
    console.error(`\nOver budget:\n${over.map((line) => `  ${line}`).join("\n")}`);
    return 1;
  }
  console.log(`Within budget: every route's First Load JS at most ${BUDGETS.routeJs} kB, with layouts at most ${BUDGETS.routeJsWithLayouts} kB, CSS at most ${BUDGETS.routeCss} kB.`);
  return 0;
}

process.exitCode = main();
