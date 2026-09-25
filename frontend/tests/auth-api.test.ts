/**
 * Phase 6.2 — the authentication API client and centralised 401 reporting.
 *
 * `fetchJson` reports a rejected session; it never redirects. The decision belongs to the
 * session provider, and keeping it there is what makes a redirect loop impossible.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  fetchResearcherProfile,
  getCurrentUser,
  login,
  register,
  setUnauthorizedHandler,
} from "../services/api";
import { storeSession } from "../services/auth";
import { PROFILE_ID, jsonResponse, makeTokenResponse, makeUser } from "./factories";

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  setUnauthorizedHandler(null);
});

describe("login", () => {
  it("posts the credentials to the backend's login route", async () => {
    fetchMock.mockResolvedValue(jsonResponse(makeTokenResponse()));

    const response = await login({ email: "ada@university.edu", password: "DemoPass123!" });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://localhost:8000/api/v1/auth/login");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(init?.body as string)).toEqual({
      email: "ada@university.edu",
      password: "DemoPass123!",
    });
    expect(response.access_token).toBe("header.payload.signature");
    expect(response.user.role).toBe("STUDENT");
  });

  it("surfaces bad credentials as a 401 ApiError", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ detail: "Invalid email or password." }, 401)
    );

    await expect(login({ email: "ada@university.edu", password: "wrong" })).rejects.toMatchObject({
      status: 401,
      detail: "Invalid email or password.",
    });
  });
});

describe("register", () => {
  it("posts to the registration route and returns a session", async () => {
    fetchMock.mockResolvedValue(jsonResponse(makeTokenResponse(), 201));

    const response = await register({
      email: "ada@university.edu",
      password: "DemoPass123!",
      full_name: "Ada Lovelace",
      role: "FACULTY",
    });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://localhost:8000/api/v1/auth/register");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(init?.body as string).role).toBe("FACULTY");
    // Registration authenticates, so no follow-up sign-in is needed.
    expect(response.access_token).not.toBe("");
  });

  it("surfaces a duplicate email as a 409", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ detail: "An account with this email already exists." }, 409)
    );

    await expect(
      register({
        email: "ada@university.edu",
        password: "DemoPass123!",
        full_name: "Ada Lovelace",
        role: "STUDENT",
      })
    ).rejects.toMatchObject({ status: 409 });
  });
});

describe("getCurrentUser", () => {
  it("reads the account from /auth/me", async () => {
    fetchMock.mockResolvedValue(jsonResponse(makeUser({ role: "ADMIN" })));

    const user = await getCurrentUser();

    expect(fetchMock.mock.calls[0][0]).toBe("http://localhost:8000/api/v1/auth/me");
    expect(user.role).toBe("ADMIN");
  });
});

describe("error detail extraction", () => {
  it("reads FastAPI's list-shaped validation body", async () => {
    // Pydantic sends a list of per-field errors, not a string; showing "[object Object]"
    // to somebody mistyping their email is not acceptable.
    fetchMock.mockResolvedValue(
      jsonResponse(
        {
          detail: [
            { loc: ["body", "email"], msg: "Invalid email address.", type: "value_error" },
            { loc: ["body", "password"], msg: "Password must be at least 8 characters.", type: "value_error" },
          ],
        },
        422
      )
    );

    await expect(
      register({ email: "nope", password: "x", full_name: "A", role: "STUDENT" })
    ).rejects.toMatchObject({
      status: 422,
      detail: "Invalid email address. Password must be at least 8 characters.",
    });
  });

  it("falls back cleanly when the body is not JSON", async () => {
    fetchMock.mockResolvedValue(new Response("<html>502</html>", { status: 502 }));

    await expect(getCurrentUser()).rejects.toMatchObject({
      status: 502,
      detail: "Request failed with status 502",
    });
  });

  it("does not describe an auth rate limit as a discovery rate limit", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        { detail: "Too many authentication attempts. Please wait and try again." },
        429
      )
    );

    const error = await login({ email: "ada@university.edu", password: "x" }).then(
      () => null,
      (err: unknown) => err as ApiError
    );

    expect(error).not.toBeNull();
    expect(error?.status).toBe(429);
    expect(error?.detail).toBe("Too many authentication attempts. Please wait and try again.");
    expect(error?.detail).not.toContain("discovery");
  });
});

describe("401 reporting", () => {
  it("reports a rejected authenticated request", async () => {
    const onUnauthorized = vi.fn();
    setUnauthorizedHandler(onUnauthorized);
    storeSession(makeTokenResponse());
    fetchMock.mockResolvedValue(jsonResponse({ detail: "Access token has expired." }, 401));

    await expect(fetchResearcherProfile(PROFILE_ID)).rejects.toBeInstanceOf(ApiError);
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
  });

  it("stays silent for a 401 on a request that carried no token", async () => {
    // An anonymous call hitting a protected route is not a lost session.
    const onUnauthorized = vi.fn();
    setUnauthorizedHandler(onUnauthorized);
    fetchMock.mockResolvedValue(jsonResponse({ detail: "Authentication required." }, 401));

    await expect(fetchResearcherProfile(PROFILE_ID)).rejects.toBeInstanceOf(ApiError);
    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  it("stays silent when a sign-in attempt is rejected", async () => {
    // Otherwise a mistyped password would clear the credentials being established.
    const onUnauthorized = vi.fn();
    setUnauthorizedHandler(onUnauthorized);
    storeSession(makeTokenResponse());
    fetchMock.mockResolvedValue(jsonResponse({ detail: "Invalid email or password." }, 401));

    await expect(login({ email: "ada@university.edu", password: "wrong" })).rejects.toBeInstanceOf(
      ApiError
    );
    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  it("stays silent for a 403, which is an authorization answer and not a lost session", async () => {
    const onUnauthorized = vi.fn();
    setUnauthorizedHandler(onUnauthorized);
    storeSession(makeTokenResponse());
    fetchMock.mockResolvedValue(jsonResponse({ detail: "Forbidden." }, 403));

    await expect(fetchResearcherProfile(PROFILE_ID)).rejects.toMatchObject({ status: 403 });
    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  it("stops reporting once the handler is removed", async () => {
    const onUnauthorized = vi.fn();
    setUnauthorizedHandler(onUnauthorized);
    setUnauthorizedHandler(null);
    storeSession(makeTokenResponse());
    fetchMock.mockResolvedValue(jsonResponse({ detail: "Access token has expired." }, 401));

    await expect(fetchResearcherProfile(PROFILE_ID)).rejects.toBeInstanceOf(ApiError);
    expect(onUnauthorized).not.toHaveBeenCalled();
  });
});
