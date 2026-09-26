import type { NextConfig } from "next";

const DEFAULT_API_URL = "http://localhost:8000";

/**
 * Phase 6.4 — the API address compiled into the browser bundle. It is public by
 * definition, so it must be a plain absolute http(s) URL: no credentials, query or
 * fragment. A trailing slash is removed so request paths join cleanly. An invalid value
 * fails the build instead of shipping a frontend that cannot reach the API.
 */
export function resolvePublicApiUrl(raw: string | undefined): string {
  const value = (raw ?? DEFAULT_API_URL).trim() || DEFAULT_API_URL;
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    throw new Error(`NEXT_PUBLIC_API_URL must be an absolute http(s) URL, got ${JSON.stringify(value)}`);
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new Error(`NEXT_PUBLIC_API_URL must use http or https, got ${JSON.stringify(url.protocol)}`);
  }
  if (url.username || url.password) {
    throw new Error("NEXT_PUBLIC_API_URL must not contain credentials: it is compiled into the public bundle");
  }
  if (url.search || url.hash) {
    throw new Error("NEXT_PUBLIC_API_URL must not contain a query string or fragment");
  }
  return value.replace(/\/+$/, "");
}

const nextConfig: NextConfig = {
  // Container builds set NEXT_OUTPUT=standalone to emit a self-contained server
  // (.next/standalone/server.js) carrying only the dependencies it uses. Every other build
  // keeps the default output, so `next start` behaves exactly as before.
  output: process.env.NEXT_OUTPUT === "standalone" ? "standalone" : undefined,
  // The standalone server carries this configuration inline, so the TypeScript compiler
  // that file tracing pulls in for next.config.ts is never loaded at runtime. Keeping it
  // out leaves the runtime image free of build tooling.
  outputFileTracingExcludes: {
    "*": ["node_modules/typescript/**"],
  },
  // No X-Powered-By header: the framework in use is nobody's business (Phase 6.4).
  poweredByHeader: false,
  // API URL is exposed as NEXT_PUBLIC_API_URL (replaces former VITE_API_URL).
  // The backend runs on localhost:8000 by default.
  env: {
    NEXT_PUBLIC_API_URL: resolvePublicApiUrl(process.env.NEXT_PUBLIC_API_URL),
  },
};

export default nextConfig;
