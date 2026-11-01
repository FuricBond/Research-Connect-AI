import { NextResponse, type NextRequest } from "next/server";
import { buildContentSecurityPolicy } from "./utils/contentSecurityPolicy";

/**
 * Audit SEC-02 — a fresh nonce for every page. Next.js reads it from the request's policy and puts
 * it on its own bootstrap scripts; the root layout puts it on the theme script. No other inline
 * script runs, because `script-src` has no 'unsafe-inline'.
 */
export function middleware(request: NextRequest) {
  const nonce = btoa(crypto.randomUUID());
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  const policy = buildContentSecurityPolicy(apiUrl, nonce, process.env.NODE_ENV === "development");

  const headers = new Headers(request.headers);
  headers.set("x-nonce", nonce);
  headers.set("Content-Security-Policy", policy);

  const response = NextResponse.next({ request: { headers } });
  response.headers.set("Content-Security-Policy", policy);
  return response;
}

// Static files carry no inline script, so they need no policy of their own.
export const config = {
  matcher: [{ source: "/((?!_next/static|_next/image|favicon.ico).*)" }],
};
