/**
 * P1 — the design system is enforced by tests, not by memory (DESIGN_SYSTEM.md §12).
 *
 * Colour lives only in styles/tokens.css; components use semantic tokens; there is one theme
 * mechanism (data-theme), no OS-following `dark:` classes, no text below 12px, no gradients;
 * and every text/control colour pair in both themes meets WCAG 2.2 AA, computed from the
 * token file itself so a palette change cannot quietly break contrast.
 */

import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const FRONTEND = path.resolve(__dirname, "..");
/** File text with LF line endings, whatever the checkout uses (a Windows checkout has CRLF). */
const read = (file: string) => fs.readFileSync(file, "utf8").replace(/\r\n?/g, "\n");

function walk(dir: string, test: (file: string) => boolean, out: string[] = []): string[] {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(full, test, out);
    else if (test(full)) out.push(full);
  }
  return out;
}

const rel = (file: string) => path.relative(FRONTEND, file).replace(/\\/g, "/");
const tsx = [...walk(path.join(FRONTEND, "app"), (f) => /\.tsx?$/.test(f)), ...walk(path.join(FRONTEND, "components"), (f) => /\.tsx?$/.test(f))];
const stylesheets = walk(path.join(FRONTEND, "styles"), (f) => f.endsWith(".css"));
const modules = [...walk(path.join(FRONTEND, "app"), (f) => f.endsWith(".module.css")), ...walk(path.join(FRONTEND, "components"), (f) => f.endsWith(".module.css"))];

/** Source without comments, so a hex in a comment is not counted. */
const code = (source: string) => source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:"'`])\/\/.*$/gm, "$1");
const COLOUR = /#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?\b(?![\w-])|\b(?:rgba?|hsla?)\(/g;
const colours = (file: string) => code(read(file)).match(COLOUR) ?? [];

/** Inline style objects in legacy components: may only go down as pages migrate. */
const INLINE_STYLE_LIMIT = 825; // P6: the old profile page's inline styles went with it (P4: 859; P3: 860; 869 before)

describe("colour lives in the token file", () => {
  it("has no colour literal in any stylesheet but styles/tokens.css", () => {
    const offenders = [...stylesheets.filter((f) => !f.endsWith("tokens.css")), ...modules]
      .map((f) => [rel(f), colours(f).length] as const)
      .filter(([, n]) => n > 0);
    expect(offenders).toEqual([]);
  });

  it("has no colour literal in any component or page", () => {
    const offenders = tsx.map((f) => [rel(f), colours(f).length] as const).filter(([, n]) => n > 0);
    expect(offenders).toEqual([]);
  });

  it("lets the inline-style count only go down", () => {
    const count = tsx.reduce((sum, f) => sum + (read(f).match(/style=\{\{/g) ?? []).length, 0);
    expect(count).toBeLessThanOrEqual(INLINE_STYLE_LIMIT);
  });
});

describe("one visual language", () => {
  it("has no Tailwind dark: classes (the tokens follow the theme)", () => {
    const offenders = tsx.filter((f) => /(^|[\s"'`])dark:[a-z]/.test(code(read(f)))).map(rel);
    expect(offenders).toEqual([]);
  });

  it("has no text below 12px", () => {
    const tiny: string[] = [];
    for (const f of tsx) {
      const src = code(read(f));
      for (const m of src.matchAll(/text-\[(\d+(?:\.\d+)?)px\]|fontSize:\s*"?(\d+(?:\.\d+)?)(px|rem)?"?/g)) {
        const px = m[1] ? Number(m[1]) : m[3] === "rem" ? Number(m[2]) * 16 : Number(m[2]);
        if (px < 12) tiny.push(`${rel(f)}: ${m[0]}`);
      }
    }
    for (const f of [...stylesheets, ...modules]) {
      for (const m of code(read(f)).matchAll(/font-size:\s*(\d*\.?\d+)(px|rem)/g)) {
        const px = m[2] === "rem" ? Number(m[1]) * 16 : Number(m[1]);
        if (px < 12) tiny.push(`${rel(f)}: ${m[0]}`);
      }
    }
    expect(tiny).toEqual([]);
  });

  it("has no gradients", () => {
    const offenders = [...tsx, ...stylesheets, ...modules].filter((f) => /gradient\(|bg-gradient-to-/.test(code(read(f)))).map(rel);
    expect(offenders).toEqual([]);
  });

  it("uses tokens for size, shape, layering and timing in module CSS", () => {
    const offenders: string[] = [];
    for (const f of modules) {
      for (const m of code(read(f)).matchAll(/(font-size|border-radius|z-index|transition-duration)\s*:\s*([^;]+);/g)) {
        if (!/var\(--rc-/.test(m[2]) && !/^(0|inherit)$/.test(m[2].trim())) offenders.push(`${rel(f)}: ${m[0]}`);
      }
    }
    expect(offenders).toEqual([]);
  });

  it("does not let the OS decide the theme anywhere but the theme script", () => {
    const offenders = [...stylesheets, ...modules].filter((f) => /prefers-color-scheme/.test(code(read(f)))).map(rel);
    expect(offenders).toEqual([]);
  });
});

/* ── Token resolution and contrast ───────────────────────────────────────── */

const TOKENS = read(path.join(FRONTEND, "styles/tokens.css"));

/**
 * The primitive, light and dark token maps of a tokens.css source. LF and CRLF sources parse the
 * same; a theme block that cannot be found is an error rather than a silently wrong block.
 */
function themesFrom(source: string) {
  const text = source.replace(/\r\n?/g, "\n");
  const block = (selectorStart: string): Record<string, string> => {
    const start = text.indexOf(selectorStart);
    if (start < 0) throw new Error(`tokens.css has no block starting ${JSON.stringify(selectorStart)}`);
    const open = text.indexOf("{", start);
    const close = text.indexOf("}", open);
    const vars: Record<string, string> = {};
    for (const m of text.slice(open + 1, close).matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) vars[m[1]] = m[2].trim();
    return vars;
  };
  const primitives = block(":root {");
  const lightOnly = block(':root,\n:root[data-theme="light"]');
  const darkOnly = block(':root[data-theme="dark"]');
  const light = { ...primitives, ...lightOnly };
  return { light, dark: { ...light, ...darkOnly }, lightOnly, darkOnly };
}

const { light, dark, lightOnly: LIGHT_ONLY, darkOnly: DARK_ONLY } = themesFrom(TOKENS);

function resolve(theme: Record<string, string>, name: string, depth = 0): string {
  const value = theme[name];
  if (value === undefined) throw new Error(`undefined token ${name}`);
  const ref = /^var\((--[\w-]+)\)$/.exec(value);
  if (ref && depth < 10) return resolve(theme, ref[1], depth + 1);
  return value;
}

function luminance(hex: string): number {
  const h = hex.replace("#", "");
  const full = h.length === 3 ? h.split("").map((c) => c + c).join("") : h;
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(full.slice(i, i + 2), 16) / 255).map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(theme: Record<string, string>, fg: string, bg: string): number {
  const a = luminance(resolve(theme, fg));
  const b = luminance(resolve(theme, bg));
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}

const TEXT = 4.5;
const UI = 3;
const PAIRS: [fg: string, bg: string, min: number][] = [
  ...["--rc-text", "--rc-text-secondary", "--rc-text-muted"].flatMap((fg) =>
    ["--rc-bg", "--rc-surface", "--rc-surface-sunken", "--rc-surface-raised", "--rc-surface-hover"].map((bg) => [fg, bg, TEXT] as [string, string, number])
  ),
  ["--rc-link", "--rc-surface", TEXT],
  ["--rc-link", "--rc-bg", TEXT],
  ["--rc-brand-text", "--rc-brand-subtle", TEXT],
  ["--rc-brand-text", "--rc-surface", TEXT],
  ["--rc-text", "--rc-surface-selected", TEXT],
  ["--rc-text-on-brand", "--rc-brand", TEXT],
  ["--rc-text-on-brand", "--rc-brand-hover", TEXT],
  ["--rc-text-on-brand", "--rc-brand-active", TEXT],
  ["--rc-text-on-brand", "--rc-danger", TEXT],
  ["--rc-text-inverse", "--rc-surface-inverse", TEXT],
  ...["info", "success", "warning", "danger"].flatMap((tone) => [
    [`--rc-${tone}`, `--rc-${tone}-subtle`, TEXT] as [string, string, number],
    [`--rc-${tone}`, "--rc-surface", TEXT] as [string, string, number],
  ]),
  ["--rc-data-deadline-fg", "--rc-surface", TEXT],
  ["--rc-data-deadline-soon-fg", "--rc-surface", TEXT],
  ["--rc-data-deadline-urgent-fg", "--rc-data-deadline-urgent-bg", TEXT],
  ["--rc-data-deadline-passed-fg", "--rc-surface", TEXT],
  ["--rc-data-risk-low-fg", "--rc-data-risk-low-bg", TEXT],
  ["--rc-data-risk-caution-fg", "--rc-data-risk-caution-bg", TEXT],
  ["--rc-data-risk-high-fg", "--rc-data-risk-high-bg", TEXT],
  ["--rc-data-risk-unknown-fg", "--rc-surface", TEXT],
  ["--rc-data-match-strong-fg", "--rc-data-match-strong-bg", TEXT],
  ["--rc-data-match-good-fg", "--rc-data-match-good-bg", TEXT],
  ["--rc-data-match-partial-fg", "--rc-data-match-partial-bg", TEXT],
  ["--rc-data-match-weak-fg", "--rc-surface", TEXT],
  ["--rc-data-app-review", "--rc-data-app-review-bg", TEXT],
  ["--rc-data-app-shortlisted", "--rc-data-app-shortlisted-bg", TEXT],
  ["--rc-data-app-offered-fg", "--rc-data-app-offered-bg", TEXT],
  ["--rc-data-app-accepted", "--rc-data-app-accepted-bg", TEXT],
  ["--rc-data-badge-count-fg", "--rc-data-badge-count-bg", TEXT],
  // Non-text: control boundaries, focus indicators, meters (WCAG 1.4.11).
  ["--rc-border-control", "--rc-surface", UI],
  ["--rc-border-control", "--rc-bg", UI],
  ["--rc-focus-ring", "--rc-surface", UI],
  ["--rc-focus-ring", "--rc-bg", UI],
  ["--rc-data-meter-fill", "--rc-surface", UI],
  ["--rc-brand", "--rc-surface", UI],
];

/** The pairs below their minimum ratio in a theme. */
function contrastFailures(theme: Record<string, string>) {
  return PAIRS.map(([fg, bg, min]) => ({ fg, bg, min, ratio: Math.round(contrast(theme, fg, bg) * 100) / 100 })).filter(
    (pair) => pair.ratio < pair.min
  );
}

describe("the checks themselves", () => {
  it("find the literals that do exist (in the token file)", () => {
    expect(colours(path.join(FRONTEND, "styles/tokens.css")).length).toBeGreaterThan(40);
  });

  it("reproduce the contrast ratios published in DESIGN_SYSTEM.md §3.4", () => {
    expect(contrast(light, "--rc-text", "--rc-surface")).toBeCloseTo(17.39, 1);
    expect(contrast(light, "--rc-text-muted", "--rc-surface")).toBeCloseTo(6.55, 1);
    expect(contrast(dark, "--rc-text", "--rc-bg")).toBeCloseTo(15.5, 1);
    expect(contrast(light, "--rc-border-control", "--rc-surface")).toBeCloseTo(3.72, 1);
  });
});

describe("token contrast (WCAG 2.2 AA)", () => {
  for (const [name, theme] of [["light", light], ["dark", dark]] as const) {
    it(`meets 4.5:1 for text and 3:1 for controls in the ${name} theme`, () => {
      expect(contrastFailures(theme)).toEqual([]);
    });
  }

  it("gives every semantic colour token a dark-theme value", () => {
    const colourish = (value: string) => /var\(--rc-p-|#|rgb|color-mix/.test(value);
    // These are deliberately the same in both themes or derive from tokens that change.
    const sameInBoth = new Set([
      "--rc-text-on-brand",
      "--rc-data-match-strong-fg",
      "--rc-data-match-weak-bg",
      "--rc-data-app-offered-fg",
      "--rc-data-badge-count-fg",
      "--rc-selected",
      "--rc-info-border",
      "--rc-success-border",
      "--rc-warning-border",
      "--rc-danger-border",
      "--rc-shadow-sticky",
    ]);
    const missing = Object.entries(LIGHT_ONLY)
      .filter(([name, value]) => colourish(value) && !sameInBoth.has(name) && !(name in DARK_ONLY))
      .map(([name]) => name);
    expect(missing).toEqual([]);
  });
});

describe("line endings (P2 audit)", () => {
  // tokens.css as a Windows checkout has it (core.autocrlf=true writes CRLF).
  const CRLF = TOKENS.replace(/\n/g, "\r\n");

  it("parses a CRLF token file exactly like the LF one", () => {
    expect(CRLF).toContain("\r\n");
    const fromCrlf = themesFrom(CRLF);
    const fromLf = themesFrom(TOKENS);
    expect(fromCrlf).toEqual(fromLf);
    expect(Object.keys(fromCrlf.lightOnly).length).toBeGreaterThan(40);
    expect(Object.keys(fromCrlf.darkOnly).length).toBeGreaterThan(40);
  });

  it("gives the same contrast results for both", () => {
    const fromCrlf = themesFrom(CRLF);
    for (const theme of ["light", "dark"] as const) {
      const ratios = (source: ReturnType<typeof themesFrom>) => PAIRS.map(([fg, bg]) => contrast(source[theme], fg, bg));
      expect(ratios(fromCrlf)).toEqual(ratios({ light, dark, lightOnly: LIGHT_ONLY, darkOnly: DARK_ONLY }));
      expect(contrastFailures(fromCrlf[theme])).toEqual([]);
    }
  });

  it("still catches a real contrast failure in a CRLF file", () => {
    // Muted text lightened to the hairline colour (about 1.3:1 on white) in the light theme.
    const broken = CRLF.replace(/(:root,\r\n:root\[data-theme="light"\][\s\S]*?--rc-text-muted:\s*)[^;]+;/, "$1var(--rc-p-ink-100);");
    expect(broken).not.toEqual(CRLF);
    const failures = contrastFailures(themesFrom(broken).light);
    expect(failures.length).toBeGreaterThan(0);
    expect(failures.every((pair) => pair.fg === "--rc-text-muted")).toBe(true);
  });

  it("reports a missing theme block instead of reading the wrong one", () => {
    expect(() => themesFrom(TOKENS.replace(':root[data-theme="dark"]', ":root[data-theme=night]"))).toThrow(/no block starting/);
  });
});
