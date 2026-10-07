import localFont from "next/font/local";

/**
 * The two typefaces of the design system (docs/design/DESIGN_SYSTEM.md §4.1), self-hosted from
 * app/fonts (licence: app/fonts/OFL.txt). Nothing is fetched from a font service at build or
 * run time, so the Content-Security-Policy's `font-src 'self'` holds.
 *
 * Each family is split into a latin file (all of Latin-1: English and Western European names)
 * and a latin-ext file that the browser downloads only when a page contains a character from
 * its range (Polish, Czech, Turkish, Vietnamese… author names). In the font stacks
 * (styles/tokens.css) the latin-ext family comes first: it carries no metric-matched fallback,
 * so text the latin file covers falls through to the latin family and, while that loads, to
 * its size-adjusted local fallback — which keeps layout shift low.
 *
 * next/font only accepts literal option values, hence the repeated ranges.
 */

/** UI and body text: Source Sans 3, variable weight. Preloaded: nearly every glyph uses it. */
export const sourceSans = localFont({
  src: [{ path: "./fonts/source-sans-3-latin-wght.woff2", weight: "200 900", style: "normal" }],
  variable: "--font-source-sans",
  display: "swap",
  preload: true,
  adjustFontFallback: "Arial",
  declarations: [
    {
      prop: "unicode-range",
      value:
        "U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,U+0329,U+2000-206F,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD",
    },
  ],
});

export const sourceSansExt = localFont({
  src: [{ path: "./fonts/source-sans-3-latin-ext-wght.woff2", weight: "200 900", style: "normal" }],
  variable: "--font-source-sans-ext",
  display: "swap",
  preload: false,
  adjustFontFallback: false,
  declarations: [
    {
      prop: "unicode-range",
      value:
        "U+0100-02BA,U+02BD-02C5,U+02C7-02CC,U+02CE-02D7,U+02DD-02FF,U+0304,U+0308,U+0329,U+1D00-1DBF,U+1E00-1E9F,U+1EF2-1EFF,U+2020,U+20A0-20AB,U+20AD-20C0,U+2113,U+2C60-2C7F,U+A720-A7FF",
    },
  ],
});

/** Page titles and research-object titles: Source Serif 4 semibold. Not preloaded. */
export const sourceSerif = localFont({
  src: [
    { path: "./fonts/source-serif-4-latin-600.woff2", weight: "600", style: "normal" },
    { path: "./fonts/source-serif-4-latin-600-italic.woff2", weight: "600", style: "italic" },
  ],
  variable: "--font-source-serif",
  display: "swap",
  preload: false,
  adjustFontFallback: "Times New Roman",
  declarations: [
    {
      prop: "unicode-range",
      value:
        "U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,U+0329,U+2000-206F,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD",
    },
  ],
});

export const sourceSerifExt = localFont({
  src: [
    { path: "./fonts/source-serif-4-latin-ext-600.woff2", weight: "600", style: "normal" },
    { path: "./fonts/source-serif-4-latin-ext-600-italic.woff2", weight: "600", style: "italic" },
  ],
  variable: "--font-source-serif-ext",
  display: "swap",
  preload: false,
  adjustFontFallback: false,
  declarations: [
    {
      prop: "unicode-range",
      value:
        "U+0100-02BA,U+02BD-02C5,U+02C7-02CC,U+02CE-02D7,U+02DD-02FF,U+0304,U+0308,U+0329,U+1D00-1DBF,U+1E00-1E9F,U+1EF2-1EFF,U+2020,U+20A0-20AB,U+20AD-20C0,U+2113,U+2C60-2C7F,U+A720-A7FF",
    },
  ],
});

/** Class names that define the four font variables, for the <html> element. */
export const fontVariables = [sourceSans, sourceSansExt, sourceSerif, sourceSerifExt]
  .map((font) => font.variable)
  .join(" ");
