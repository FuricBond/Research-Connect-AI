import { createHash } from "node:crypto";
import { join, relative, sep } from "node:path";
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

/** The security headers every route answers with. The Content-Security-Policy carries a nonce per response, so it is set in middleware.ts. */
export function securityHeaders(): { key: string; value: string }[] {
  return [
    { key: "X-Content-Type-Options", value: "nosniff" },
    { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
    { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
  ];
}

/**
 * CSS module class names, in production: a short hash of the file and the name instead of
 * `Faculty_postingFilter__a1b2c`. Their maps sit in every page's JavaScript, so this is real weight
 * (audit PERF-04). The hash is of the path from the project root, so a build measures the same
 * wherever the project is checked out.
 */
function shortenCssModuleNames(rules: unknown, root: string): void {
  const getLocalIdent = (context: { resourcePath: string; resourceQuery?: string }, _name: string, exportName: string) => {
    const file = relative(root, context.resourcePath).split(sep).join("/");
    return `c${createHash("md5").update(`${file}${context.resourceQuery ?? ""}:${exportName}`).digest("base64url").slice(0, 6).replace(/-/g, "_")}`;
  };
  const visit = (node: unknown): void => {
    if (Array.isArray(node)) return node.forEach(visit);
    if (!node || typeof node !== "object") return;
    const rule = node as { oneOf?: unknown; rules?: unknown; use?: unknown; loader?: string; options?: { modules?: { getLocalIdent?: unknown } } };
    if (rule.loader?.includes("css-loader") && rule.options?.modules?.getLocalIdent) rule.options.modules.getLocalIdent = getLocalIdent;
    visit(rule.oneOf);
    visit(rule.rules);
    visit(rule.use);
  };
  visit(rules);
}

const PUBLIC_API_URL = resolvePublicApiUrl(process.env.NEXT_PUBLIC_API_URL);

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
    NEXT_PUBLIC_API_URL: PUBLIC_API_URL,
  },
  // The API client and the design system's primitives only define functions and components. Without
  // saying so webpack keeps every module of theirs on every page that imports any of them, because
  // it cannot prove that (`class ApiError extends Error`, forwardRef calls) (audit PERF-04).
  webpack(config, { dev }) {
    const root = config.context as string;
    if (!dev) shortenCssModuleNames(config.module.rules, root);
    config.module.rules.push({ include: [join(root, "services", "api"), join(root, "services", "api.ts"), join(root, "components", "ui")], test: /\.tsx?$/, sideEffects: false });
    return config;
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: securityHeaders(),
      },
    ];
  },
};

export default nextConfig;
