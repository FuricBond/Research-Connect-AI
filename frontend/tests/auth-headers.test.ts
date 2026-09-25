/**
 * Phase 6.2 — the P0-F header invariant.
 *
 * A request must carry `Authorization: Bearer <JWT>` *or* the developer `X-User-ID`
 * header, never both. Sending both leaves the backend to choose which identity to trust,
 * which is the ambiguity the P0 fix removed. 117 API wrappers still accept a developer
 * user ID, so this is enforced centrally in `fetchJson` and pinned here.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { getAuthHeaders, setActiveIdentity, storeSession } from "../services/auth";
import {
  fetchDiscoverySettings,
  fetchResearcherProfile,
  getCurrentUser,
} from "../services/api";
import { PROFILE_ID, USER_ID, headersOf, jsonResponse, makeTokenResponse } from "./factories";

describe("getAuthHeaders", () => {
  it("sends only the bearer token when one is stored", () => {
    storeSession(makeTokenResponse());
    const headers = getAuthHeaders();

    expect(headers["Authorization"]).toBe("Bearer header.payload.signature");
    expect(headers).not.toHaveProperty("X-User-ID");
  });

  it("sends only the bearer token even when a user id is also stored", () => {
    // This is the exact state after a JWT sign-in: storeSession records both, and the
    // stored user id must not reach the wire.
    storeSession(makeTokenResponse());
    expect(window.localStorage.getItem("researchconnect_active_user_id")).toBe(USER_ID);

    expect(getAuthHeaders()).toEqual({ Authorization: "Bearer header.payload.signature" });
  });

  it("falls back to the developer header only when there is no token", () => {
    setActiveIdentity({ userId: USER_ID });
    expect(getAuthHeaders()).toEqual({ "X-User-ID": USER_ID });
  });

  it("falls back to the profile id when only that is stored", () => {
    setActiveIdentity({ profileId: PROFILE_ID });
    expect(getAuthHeaders()).toEqual({ "X-User-ID": PROFILE_ID });
  });

  it("sends nothing at all for an anonymous caller", () => {
    expect(getAuthHeaders()).toEqual({});
  });
});

describe("outgoing requests", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);
  });

  it("never puts both headers on an authenticated request", async () => {
    storeSession(makeTokenResponse());
    await getCurrentUser();

    const headers = headersOf(fetchMock.mock.calls[0]);
    expect(headers["Authorization"]).toBe("Bearer header.payload.signature");
    expect(headers).not.toHaveProperty("X-User-ID");
  });

  it("strips a wrapper's explicit X-User-ID when a token is stored", async () => {
    // Legacy wrappers such as fetchDiscoverySettings still accept a developer user ID.
    // With a token present the header must be dropped rather than sent alongside it.
    storeSession(makeTokenResponse());
    await fetchDiscoverySettings(PROFILE_ID, USER_ID);

    const headers = headersOf(fetchMock.mock.calls[0]);
    expect(headers["Authorization"]).toBe("Bearer header.payload.signature");
    expect(headers).not.toHaveProperty("X-User-ID");
  });

  it("keeps a wrapper's X-User-ID when there is no token", async () => {
    // The developer fallback must keep working exactly as before.
    await fetchDiscoverySettings(PROFILE_ID, USER_ID);

    const headers = headersOf(fetchMock.mock.calls[0]);
    expect(headers["X-User-ID"]).toBe(USER_ID);
    expect(headers).not.toHaveProperty("Authorization");
  });

  it("sends no identity header for an anonymous discovery request", async () => {
    await fetchResearcherProfile(PROFILE_ID);

    const headers = headersOf(fetchMock.mock.calls[0]);
    expect(headers).not.toHaveProperty("Authorization");
    expect(headers).not.toHaveProperty("X-User-ID");
  });

  it("does not resurrect a cleared token on the next request", async () => {
    storeSession(makeTokenResponse());
    window.localStorage.clear();
    await fetchResearcherProfile(PROFILE_ID);

    const headers = headersOf(fetchMock.mock.calls[0]);
    expect(headers).not.toHaveProperty("Authorization");
    expect(headers).not.toHaveProperty("X-User-ID");
  });
});
