import type { Config } from "tailwindcss";

/**
 * Tailwind generates only the utility classes that components actually use (the
 * personalization and unified-intelligence panels are written with them). Preflight, the
 * global reset, is off so the rest of the app keeps its own CSS unchanged.
 */
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  corePlugins: {
    preflight: false,
  },
};

export default config;
