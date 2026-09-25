import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

/**
 * Phase 6.2 — test runner for the authentication layer.
 *
 * Added because the session, header and 401 invariants are unit-level guarantees: a
 * browser walkthrough can show that signing in works, but not that a bearer token and
 * X-User-ID are never sent together, or that malformed stored state is ignored.
 */
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    include: ["tests/**/*.test.{ts,tsx}"],
    restoreMocks: true,
  },
  resolve: {
    alias: { "@": path.resolve(__dirname, ".") },
  },
});
