import type { Config } from "tailwindcss";

/**
 * Tailwind generates only the utility classes that components actually use. Preflight, the global
 * reset, is off so the rest of the app keeps its own CSS.
 *
 * P12: the legacy palette is gone, and with it every colour utility: no component uses one, and
 * colour comes only from the design tokens (styles/tokens.css). A colour class now generates nothing.
 * New code uses CSS Modules and --rc-* tokens.
 */

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  corePlugins: {
    preflight: false,
  },
  // `dark:` follows the application's theme, never the OS on its own.
  darkMode: ["selector", '[data-theme="dark"]'],
  theme: {
    colors: {},
    // Cards are flat; only floating surfaces (menus, dialogs) cast a shadow.
    boxShadow: {
      none: "none",
      sm: "none",
      DEFAULT: "none",
      md: "none",
      lg: "none",
      xl: "var(--rc-shadow-dialog)",
      "2xl": "var(--rc-shadow-dialog)",
      inner: "none",
    },
    // Chips 4 · controls 6 · cards 8 · dialogs 12.
    borderRadius: {
      none: "0",
      sm: "var(--rc-radius-sm)",
      DEFAULT: "var(--rc-radius-sm)",
      md: "var(--rc-radius-md)",
      lg: "var(--rc-radius-lg)",
      xl: "var(--rc-radius-lg)",
      "2xl": "var(--rc-radius-xl)",
      "3xl": "var(--rc-radius-xl)",
      full: "var(--rc-radius-full)",
    },
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
