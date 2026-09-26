/**
 * Phase 6.2 — what the sign-in and registration forms are allowed to say.
 *
 * Two rules: a person gets something they can act on, and nothing internal reaches the
 * screen. A 5xx body may carry a driver error or a stack trace, so its detail is never shown.
 */

import { describe, expect, it } from "vitest";
import { ApiError } from "../services/api";
import {
  describeLoginError,
  describeRegisterError,
  resolveRedirectTarget,
} from "../components/auth/authMessages";

describe("describeLoginError", () => {
  it("gives one message for both wrong password and unknown email", () => {
    // The backend equalises its timing for the same reason: neither answer should
    // disclose whether an address is registered.
    expect(describeLoginError(new ApiError(401, "Invalid email or password."))).toBe(
      "Email or password is incorrect."
    );
  });

  it("passes a validation complaint through", () => {
    expect(
      describeLoginError(new ApiError(422, "Invalid email address.", "Invalid email address."))
    ).toBe("Invalid email address.");
  });

  it("passes the rate-limit message through", () => {
    const message = "Too many authentication attempts. Please wait and try again.";
    expect(describeLoginError(new ApiError(429, message, message))).toBe(message);
  });

  it("never shows a server-side detail", () => {
    const leak = 'psycopg.OperationalError: connection to server at "db" failed';
    const shown = describeLoginError(new ApiError(500, leak, leak));

    expect(shown).not.toContain("psycopg");
    expect(shown).not.toContain("connection to server");
    expect(shown).toBe("Sign-in is unavailable right now. Please try again in a moment.");
  });

  it("explains a network failure rather than showing nothing", () => {
    expect(describeLoginError(new TypeError("Failed to fetch"))).toContain(
      "Could not reach the server"
    );
  });
});

describe("describeRegisterError", () => {
  it("names a duplicate email and points at signing in", () => {
    expect(
      describeRegisterError(new ApiError(409, "An account with this email already exists."))
    ).toContain("already exists");
  });

  it("passes a field validation message through", () => {
    const detail = "Password must be at least 8 characters.";
    expect(describeRegisterError(new ApiError(422, detail, detail))).toBe(detail);
  });

  it("never shows a server-side detail", () => {
    const leak = "IntegrityError: duplicate key value violates unique constraint";
    expect(describeRegisterError(new ApiError(503, leak, leak))).not.toContain("IntegrityError");
  });
});

describe("resolveRedirectTarget", () => {
  it("honours a same-origin path", () => {
    expect(resolveRedirectTarget("/workspace")).toBe("/workspace");
  });

  it("falls back when nothing was requested", () => {
    expect(resolveRedirectTarget(null)).toBe("/researcher");
  });

  it("refuses an absolute URL to another site", () => {
    expect(resolveRedirectTarget("https://evil.example/steal")).toBe("/researcher");
  });

  it("refuses a protocol-relative URL", () => {
    // "//evil.example" is a URL to another host, not a path on this one.
    expect(resolveRedirectTarget("//evil.example/steal")).toBe("/researcher");
  });

  it("does not send somebody back to the page they just left", () => {
    expect(resolveRedirectTarget("/login")).toBe("/researcher");
    expect(resolveRedirectTarget("/register")).toBe("/researcher");
  });
});

// ── P1-01 regression: the redirect target is decided by the URL parser ─────────────
//
// The previous guard compared string prefixes, and "/\evil.example" satisfied it while
// the browser resolved it to another host. Every case below is judged by where the value
// actually leads, so a spelling the list does not anticipate is still caught.

const ORIGIN = "http://localhost:3000";
// Built rather than typed, so no layer of escaping can quietly change these characters.
const BS = String.fromCharCode(92);
const TAB = String.fromCharCode(9);
const LF = String.fromCharCode(10);

const SAFE_TARGETS: [string, string][] = [
  ["/", "/"],
  ["/dashboard", "/dashboard"],
  ["/workspace/123", "/workspace/123"],
  ["/dashboard?foo=bar", "/dashboard?foo=bar"],
  ["/dashboard#section", "/dashboard#section"],
  ["/dashboard?foo=bar#section", "/dashboard?foo=bar#section"],
];

const UNSAFE_TARGETS: [string, string][] = [
  ["absolute https URL", "https://evil.example"],
  ["absolute http URL", "http://evil.example"],
  ["upper-case scheme", "HTTPS://EVIL.EXAMPLE/x"],
  ["protocol-relative", "//evil.example"],
  ["slash then backslash", "/" + BS + "evil.example"],
  ["double backslash", BS + BS + "evil.example"],
  ["encoded backslash", "/%5Chost"],
  ["two encoded backslashes", "/%5C%5Cevil.example"],
  ["encoded double slash", "/%2F%2Fevil.example"],
  ["single encoded slash", "/%2Fevil.example"],
  ["tab between slashes", "/" + TAB + "/host"],
  ["encoded tab between slashes", "/%09/evil.example"],
  ["newline between slashes", "/" + LF + "/evil.example"],
  ["space between slashes", "/ /host"],
  ["leading space", " //evil.example"],
  ["dot-segment collapsing to //", "/..//evil.example"],
  ["encoded dot-segment collapsing to //", "/%2e%2e//evil.example"],
  ["current-directory segment collapsing to //", "/.//evil.example"],
  ["javascript: scheme", "javascript:alert(1)"],
  ["same-origin absolute URL (refused, as before)", `${ORIGIN}/dashboard`],
  ["empty value", ""],
];

describe("resolveRedirectTarget — parser-based same-origin check (P1-01)", () => {
  it.each(SAFE_TARGETS)("accepts the internal path %s", (input, expected) => {
    expect(resolveRedirectTarget(input, ORIGIN)).toBe(expected);
  });

  it.each(UNSAFE_TARGETS)("refuses %s", (_label, input) => {
    expect(resolveRedirectTarget(input, ORIGIN)).toBe("/researcher");
  });

  it("never returns anything that leaves this origin, whatever it is given", () => {
    const every = [...SAFE_TARGETS.map(([input]) => input), ...UNSAFE_TARGETS.map(([, input]) => input)];
    for (const input of every) {
      const target = resolveRedirectTarget(input, ORIGIN);
      expect(new URL(target, ORIGIN).origin, `input ${JSON.stringify(input)}`).toBe(ORIGIN);
    }
  });

  it("returns an internal path, never an absolute or protocol-relative URL", () => {
    for (const [input] of SAFE_TARGETS) {
      const target = resolveRedirectTarget(input, ORIGIN);
      expect(target.startsWith("/")).toBe(true);
      expect(target.startsWith("//")).toBe(false);
    }
  });

  it("still refuses the sign-in pages when they carry a query or fragment", () => {
    expect(resolveRedirectTarget("/login?next=/admin", ORIGIN)).toBe("/researcher");
    expect(resolveRedirectTarget("/register#top", ORIGIN)).toBe("/researcher");
  });

  it("checks against the page's own origin when none is given", () => {
    // This is how the sign-in and registration pages call it.
    expect(window.location.origin).not.toBe("null");
    expect(resolveRedirectTarget("/workspace")).toBe("/workspace");
    expect(resolveRedirectTarget("/" + BS + "evil.example")).toBe("/researcher");
    expect(resolveRedirectTarget("/..//evil.example")).toBe("/researcher");
  });
});
