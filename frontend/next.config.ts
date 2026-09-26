import type { NextConfig } from "next";

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
  // API URL is exposed as NEXT_PUBLIC_API_URL (replaces former VITE_API_URL).
  // The backend runs on localhost:8000 by default.
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
  },
};

export default nextConfig;
