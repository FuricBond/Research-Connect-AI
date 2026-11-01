/**
 * P12 — the budget check (scripts/check-bundle-budget.mjs) as CI runs it, on small made-up builds:
 * it fails when a route (with or without its layouts), the typical route or the shared code is over
 * budget, names what is, measures gzipped size, leaves the layouts out of First Load JS as `next
 * build` does and counts them in the second figure, and refuses to pass when there is no build to
 * measure.
 */
import { spawnSync } from "node:child_process";
import { randomBytes } from "node:crypto";
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";

const SCRIPT = path.resolve(__dirname, "../scripts/check-bundle-budget.mjs");
const dirs: string[] = [];

/** Random bytes do not compress, so a file of n kB measures about n kB gzipped. */
function build(pages: Record<string, string[]>, files: Record<string, number>, rootMainFiles = ["shared.js"]): string {
  const dir = mkdtempSync(path.join(tmpdir(), "bundle-budget-"));
  dirs.push(dir);
  mkdirSync(path.join(dir, "static"));
  for (const [name, kB] of Object.entries(files)) writeFileSync(path.join(dir, name), randomBytes(Math.round(kB * 1000)));
  writeFileSync(path.join(dir, "app-build-manifest.json"), JSON.stringify({ pages }));
  writeFileSync(path.join(dir, "build-manifest.json"), JSON.stringify({ rootMainFiles }));
  return dir;
}

function check(dir: string) {
  const run = spawnSync(process.execPath, [SCRIPT, "--dir", dir], { encoding: "utf8" });
  return { code: run.status, out: run.stdout, err: run.stderr };
}

const LAYOUT = { "/layout": ["shared.js", "shell.js", "shell.css"] };

afterEach(() => {
  for (const dir of dirs.splice(0)) rmSync(dir, { recursive: true, force: true });
});

describe("the bundle budget check", () => {
  it("passes a build within every budget and reports each route", () => {
    const { code, out } = check(build({ ...LAYOUT, "/calendar/page": ["shared.js", "page.js", "page.css"] }, { "shared.js": 100, "shell.js": 5, "shell.css": 10, "page.js": 30, "page.css": 5 }));
    expect(code).toBe(0);
    expect(out).toMatch(/\/calendar\s+130\.\d\s+135\.\d\s+15\.\d/);
    expect(out).toContain("Within budget");
  });

  it("fails when a route's First Load JS is over 140 kB, and names the route", () => {
    const { code, err } = check(build({ ...LAYOUT, "/workspace/[id]/page": ["shared.js", "page.js"], "/page": ["shared.js"] }, { "shared.js": 100, "shell.js": 1, "shell.css": 1, "page.js": 41 }));
    expect(code).toBe(1);
    expect(err).toMatch(/\/workspace\/\[id\]: First Load JS 141\.\d kB is over 140 kB/);
  });

  it("fails when a route with its layouts is over 140 kB though First Load JS is within it, and counts a chunk once", () => {
    const pages = { "/layout": ["shared.js", "shell.js"], "/a/page": ["shared.js", "page.js"] };
    const over = check(build(pages, { "shared.js": 100, "shell.js": 15, "page.js": 30 }));
    expect(over.code).toBe(1);
    expect(over.err).toMatch(/\/a: JS with layouts 145\.\d kB is over 140 kB/);
    expect(over.err).not.toContain("First Load JS");

    const shared = { "/layout": ["shared.js", "shell.js"], "/a/page": ["shared.js", "shell.js"] };
    expect(check(build(shared, { "shared.js": 100, "shell.js": 30 })).code).toBe(0);
  });

  it("does not round a route over the limit down to it", () => {
    const { code, err } = check(build({ ...LAYOUT, "/a/page": ["shared.js", "page.js"], "/page": ["shared.js"] }, { "shared.js": 100, "shell.js": 1, "shell.css": 1, "page.js": 40.3 }));
    expect(code).toBe(1);
    expect(err).toContain("/a: First Load JS");
  });

  it("fails when a route's CSS, its layouts' included, is over 28 kB", () => {
    const { code, err } = check(build({ ...LAYOUT, "/a/page": ["shared.js", "page.css"] }, { "shared.js": 100, "shell.js": 1, "shell.css": 20, "page.css": 9 }));
    expect(code).toBe(1);
    expect(err).toMatch(/\/a: CSS 29\.\d kB is over 28 kB/);
  });

  it("fails when the shared code is over 110 kB", () => {
    const { code, err } = check(build({ ...LAYOUT, "/a/page": ["shared.js"] }, { "shared.js": 111, "shell.js": 1, "shell.css": 1 }));
    expect(code).toBe(1);
    expect(err).toMatch(/shared by all: 111\.\d kB is over 110 kB/);
  });

  it("fails when the typical route is over 135 kB though each is within 140 kB", () => {
    const pages = { ...LAYOUT, "/a/page": ["shared.js", "big.js"], "/b/page": ["shared.js", "big.js"], "/c/page": ["shared.js", "big.js"] };
    const { code, err } = check(build(pages, { "shared.js": 100, "shell.js": 1, "shell.css": 1, "big.js": 38 }));
    expect(code).toBe(1);
    expect(err).toMatch(/typical route: First Load JS 138\.\d kB is over 135 kB/);
  });

  it("leaves a page that only redirects out of the typical route", () => {
    const pages = { ...LAYOUT, "/a/page": ["shared.js", "big.js"], "/settings/notifications/page": ["shared.js"], "/_not-found/page": ["shared.js"], "/workspace/[id]/submission/page": ["shared.js"] };
    const { code, err } = check(build(pages, { "shared.js": 100, "shell.js": 1, "shell.css": 1, "big.js": 38 }));
    expect(code).toBe(1);
    expect(err).toContain("typical route");
  });

  it("measures gzipped size, not size on disk", () => {
    const dir = build({ ...LAYOUT, "/a/page": ["shared.js", "page.js"] }, { "shared.js": 100, "shell.js": 1, "shell.css": 1 });
    writeFileSync(path.join(dir, "page.js"), "a".repeat(500_000));
    const { code, out } = check(dir);
    expect(code).toBe(0);
    expect(out).toMatch(/\/a\s+10\d\.\d/);
  });

  it("refuses to pass when there is no build to measure", () => {
    const dir = mkdtempSync(path.join(tmpdir(), "bundle-budget-"));
    dirs.push(dir);
    const { code, err } = check(dir);
    expect(code).toBe(2);
    expect(err).toContain("No build to measure");
  });
});
