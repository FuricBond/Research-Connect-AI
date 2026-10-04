import { describe, expect, it } from "vitest";

import nextConfig, { buildContentSecurityPolicy, resolvePublicApiUrl, securityHeaders } from "../next.config";

/**
 * Phase 6.4 — production configuration of the frontend build. NEXT_PUBLIC_API_URL is
 * compiled into every visitor's bundle, so it must be a plain public address, and the
 * build must fail rather than ship a frontend that cannot reach the API.
 */
describe("resolvePublicApiUrl", () => {
  it("defaults to the local API when unset or blank", () => {
    expect(resolvePublicApiUrl(undefined)).toBe("http://localhost:8000");
    expect(resolvePublicApiUrl("   ")).toBe("http://localhost:8000");
  });

  it("accepts absolute http and https URLs and strips trailing slashes", () => {
    expect(resolvePublicApiUrl("http://localhost:8000/")).toBe("http://localhost:8000");
    expect(resolvePublicApiUrl("https://api.example.org//")).toBe("https://api.example.org");
    expect(resolvePublicApiUrl(" https://api.example.org ")).toBe("https://api.example.org");
  });

  it("keeps a path prefix for an API served behind a gateway", () => {
    expect(resolvePublicApiUrl("https://example.org/research-api/")).toBe("https://example.org/research-api");
  });

  it.each(["localhost:8000", "/api", "api.example.org", "not a url"])("rejects a non-absolute value: %s", (raw) => {
    expect(() => resolvePublicApiUrl(raw)).toThrow(/NEXT_PUBLIC_API_URL/);
  });

  it.each(["ftp://api.example.org", "javascript:alert(1)", "file:///etc/passwd", "ws://api.example.org"])(
    "rejects a non-http scheme: %s",
    (raw) => {
      expect(() => resolvePublicApiUrl(raw)).toThrow(/http or https|absolute http/);
    },
  );

  it("rejects embedded credentials, which would ship to every visitor", () => {
    expect(() => resolvePublicApiUrl("https://admin:secret@api.example.org")).toThrow(/credentials/);
    expect(() => resolvePublicApiUrl("https://token@api.example.org")).toThrow(/credentials/);
  });

  it("rejects a query string or fragment", () => {
    expect(() => resolvePublicApiUrl("https://api.example.org?key=abc")).toThrow(/query string or fragment/);
    expect(() => resolvePublicApiUrl("https://api.example.org#x")).toThrow(/query string or fragment/);
  });
});

describe("next.config", () => {
  it("does not advertise the framework in an X-Powered-By header", () => {
    expect(nextConfig.poweredByHeader).toBe(false);
  });

  it("compiles only the public API URL into the browser bundle's environment", () => {
    expect(Object.keys(nextConfig.env ?? {})).toEqual(["NEXT_PUBLIC_API_URL"]);
  });
});

/**
 * Fix 6/9 — security headers on every route. The app loads nothing from another origin, so the
 * policy is same-origin throughout except requests to the API.
 */
describe("security headers", () => {
  function directives(policy: string): Record<string, string> {
    return Object.fromEntries(
      policy.split("; ").map((directive) => {
        const [name, ...sources] = directive.split(" ");
        return [name, sources.join(" ")];
      })
    );
  }

  it("sends the four headers on every route", async () => {
    const rules = await nextConfig.headers!();
    expect(rules).toHaveLength(1);
    expect(rules[0].source).toBe("/:path*");
    expect(rules[0].headers.map((header) => header.key)).toEqual([
      "Content-Security-Policy",
      "X-Content-Type-Options",
      "Referrer-Policy",
      "Permissions-Policy",
    ]);
    const values = Object.fromEntries(rules[0].headers.map((header) => [header.key, header.value]));
    expect(values["X-Content-Type-Options"]).toBe("nosniff");
    expect(values["Referrer-Policy"]).toBe("strict-origin-when-cross-origin");
    expect(values["Permissions-Policy"]).toBe("camera=(), microphone=(), geolocation=()");
    // The test run is not the development server, so no eval.
    expect(values["Content-Security-Policy"]).toBe(buildContentSecurityPolicy("http://localhost:8000", false));
  });

  it("allows exactly the app's own origin plus the API for requests", () => {
    expect(directives(buildContentSecurityPolicy("https://api.example.org", false))).toEqual({
      "default-src": "'self'",
      "script-src": "'self' 'unsafe-inline'",
      "style-src": "'self' 'unsafe-inline'",
      "font-src": "'self' data:",
      "img-src": "'self' data: blob:",
      "connect-src": "'self' https://api.example.org",
      "object-src": "'none'",
      "base-uri": "'self'",
      "form-action": "'self'",
      "frame-ancestors": "'none'",
    });
  });

  it("adds 'unsafe-eval' for the development server only", () => {
    expect(directives(buildContentSecurityPolicy("http://localhost:8000", true))["script-src"]).toBe(
      "'self' 'unsafe-inline' 'unsafe-eval'"
    );
    expect(buildContentSecurityPolicy("http://localhost:8000", false)).not.toContain("unsafe-eval");
  });

  it("uses the API's origin, not its path, and loads no third-party resources", () => {
    const policy = buildContentSecurityPolicy("https://example.org/research-api", false);
    expect(directives(policy)["connect-src"]).toBe("'self' https://example.org");
    expect(policy).not.toMatch(/googleapis|gstatic|\*/);
  });

  it("builds the same headers for any valid API address", () => {
    const headers = securityHeaders(resolvePublicApiUrl("http://localhost:8300/"), false);
    expect(headers[0].value).toContain("connect-src 'self' http://localhost:8300;");
  });
});
