import type { Config } from "tailwindcss";

/**
 * Tailwind generates only the utility classes that components actually use (the
 * personalization and unified-intelligence panels are written with them). Preflight, the
 * global reset, is off so the rest of the app keeps its own CSS.
 *
 * P1: Tailwind's own palette is replaced by the design tokens (styles/tokens.css), so these
 * panels speak the same visual language as the rest of the app and follow the light/dark
 * theme without any `dark:` classes. Every hue resolves to a semantic role:
 *   neutrals (slate, gray, zinc, neutral, stone) → surfaces, borders, text by lightness
 *   indigo, violet, purple, fuchsia, pink, teal, cyan → the one brand colour
 *   blue, sky → information · green, emerald, lime → success
 *   amber, yellow, orange → warning · red, rose → danger
 * New code uses CSS Modules and --rc-* tokens; Tailwind stays only in unmigrated components.
 */

/** A token as a Tailwind colour that still honours opacity modifiers (bg-x/10). */
const token = (name: string) => `color-mix(in srgb, var(${name}) calc(<alpha-value> * 100%), transparent)`;

const neutral = {
  50: token("--rc-bg"),
  100: token("--rc-surface-sunken"),
  200: token("--rc-border"),
  300: token("--rc-border-control"),
  400: token("--rc-text-muted"),
  500: token("--rc-text-muted"),
  600: token("--rc-text-secondary"),
  700: token("--rc-text-secondary"),
  800: token("--rc-text"),
  900: token("--rc-text"),
  950: token("--rc-text"),
};

function scale(base: string, subtle: string, border: string, strong = base) {
  return {
    50: token(subtle),
    100: token(subtle),
    200: token(border),
    300: token(border),
    400: token(base),
    500: token(base),
    600: token(base),
    700: token(strong),
    800: token(strong),
    900: token(strong),
    950: token(strong),
  };
}

const brand = { ...scale("--rc-brand", "--rc-brand-subtle", "--rc-brand-border", "--rc-brand-hover"), 800: token("--rc-brand-active"), 900: token("--rc-brand-active"), 950: token("--rc-brand-active") };
const info = scale("--rc-info", "--rc-info-subtle", "--rc-info-border");
const success = scale("--rc-success", "--rc-success-subtle", "--rc-success-border");
const warning = scale("--rc-warning", "--rc-warning-subtle", "--rc-warning-border");
const danger = scale("--rc-danger", "--rc-danger-subtle", "--rc-danger-border");

/** Same palette, but every shade of a hue reads as that hue's text colour (≥ 4.5:1). */
const textScale = (name: string) =>
  Object.fromEntries([50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950].map((s) => [s, token(name)]));
/** Light neutral text was written for the old always-dark panels: it is primary text now. */
const neutralText = { ...neutral, 50: token("--rc-text"), 100: token("--rc-text"), 200: token("--rc-text"), 300: token("--rc-text-secondary") };
/** Dark hue fills (800–950, the old dark panels' tints) become the light subtle tint. */
const tintFills = (palette: Record<number, string>, subtle: string) => ({ ...palette, 800: token(subtle), 900: token(subtle), 950: token(subtle) });
/** Dark hue edges become the subtle edge; 400–600 stay strong (selected, focus). */
const tintEdges = (palette: Record<number, string>, edge: string) => ({ ...palette, 700: token(edge), 800: token(edge), 900: token(edge), 950: token(edge) });

const families = {
  brand: { palette: brand, text: "--rc-brand-text", subtle: "--rc-brand-subtle", edge: "--rc-brand-border" },
  info: { palette: info, text: "--rc-info", subtle: "--rc-info-subtle", edge: "--rc-info-border" },
  success: { palette: success, text: "--rc-success", subtle: "--rc-success-subtle", edge: "--rc-success-border" },
  warning: { palette: warning, text: "--rc-warning", subtle: "--rc-warning-subtle", edge: "--rc-warning-border" },
  danger: { palette: danger, text: "--rc-danger", subtle: "--rc-danger-subtle", edge: "--rc-danger-border" },
} as const;

const HUES: Record<string, keyof typeof families> = {
  indigo: "brand", violet: "brand", purple: "brand", fuchsia: "brand", pink: "brand", teal: "brand", cyan: "brand",
  blue: "info", sky: "info",
  green: "success", emerald: "success", lime: "success",
  amber: "warning", yellow: "warning", orange: "warning",
  red: "danger", rose: "danger",
};
const NEUTRALS = ["slate", "gray", "zinc", "neutral", "stone"];
const BASE = { transparent: "transparent", current: "currentColor", inherit: "inherit", white: token("--rc-surface"), black: token("--rc-text") };

type Palette = Record<string, string | Record<string | number, string>>;

function palette(kind: "colors" | "text" | "fill" | "edge"): Palette {
  const out: Palette = { ...BASE };
  for (const n of NEUTRALS) out[n] = kind === "text" ? neutralText : neutral;
  for (const [hue, family] of Object.entries(HUES)) {
    const f = families[family];
    out[hue] =
      kind === "text" ? textScale(f.text) : kind === "fill" ? tintFills(f.palette, f.subtle) : kind === "edge" ? tintEdges(f.palette, f.edge) : f.palette;
  }
  return out;
}

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  corePlugins: {
    preflight: false,
  },
  theme: {
    colors: palette("colors"),
    textColor: palette("text"),
    backgroundColor: palette("fill"),
    borderColor: ({ theme }) => ({ ...palette("edge"), DEFAULT: theme("colors.gray.200", "currentColor") }),
    divideColor: palette("edge"),
    extend: {
      fontFamily: {
        sans: ["var(--rc-font-sans)"],
        serif: ["var(--rc-font-serif)"],
        mono: ["var(--rc-font-mono)"],
      },
      // No text below 12px (DESIGN_SYSTEM.md §4.2).
      fontSize: {
        xs: ["0.75rem", { lineHeight: "1rem" }],
      },
    },
  },
};

export default config;
