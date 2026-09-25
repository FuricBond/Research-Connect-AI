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
