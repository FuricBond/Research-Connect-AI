import { describe, expect, it } from "vitest";

import nextConfig, { resolvePublicApiUrl } from "../next.config";

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
