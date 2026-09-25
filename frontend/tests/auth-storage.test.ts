/**
 * Phase 6.2 — stored session state.
 *
 * The store is the only thing standing between a browser refresh and a lost session, so
 * these cover the awkward cases: values that no longer parse, an account without a
 * researcher profile, and a browser that refuses to store anything at all.
 */

import { describe, expect, it, vi } from "vitest";
import {
  clearActiveIdentity,
  getAccessToken,
  getActiveProfileId,
  getAuthHeaders,
  getStoredIdentity,
  getStoredRole,
  getTokenExpiry,
  isStoredSessionExpired,
  setActiveIdentity,
  storeAuthenticatedUser,
  storeSession,
} from "../services/auth";
import { PROFILE_ID, USER_ID, makeTokenResponse, makeUser } from "./factories";

const TOKEN_KEY = "researchconnect_access_token";
const EXPIRY_KEY = "researchconnect_token_expires_at";
const PROFILE_KEY = "researchconnect_active_profile_id";
const ROLE_KEY = "researchconnect_user_role";

describe("storeSession", () => {
  it("records everything a later page load needs to restore the session", () => {
    storeSession(makeTokenResponse());

    expect(getAccessToken()).toBe("header.payload.signature");
    expect(window.localStorage.getItem(EXPIRY_KEY)).toBe("2099-01-01T00:00:00+00:00");

    const identity = getStoredIdentity();
    expect(identity.userId).toBe(USER_ID);
    expect(identity.profileId).toBe(PROFILE_ID);
    expect(identity.email).toBe("ada@university.edu");
    expect(identity.name).toBe("Ada Lovelace");
    expect(identity.role).toBe("STUDENT");
  });

  it("clears a previous account's profile when the new one has none", () => {
    storeSession(makeTokenResponse());
    expect(getActiveProfileId()).toBe(PROFILE_ID);

    // A legacy account with no researcher profile must not inherit the last one's.
    storeSession(
      makeTokenResponse({
        user: makeUser({ id: "99999999-8888-7777-6666-555555555555", profile_id: null }),
      })
    );

    expect(getActiveProfileId()).toBeNull();
    expect(window.localStorage.getItem(PROFILE_KEY)).toBeNull();
  });

  it("overwrites the stored role when a different account signs in", () => {
    storeSession(makeTokenResponse());
    expect(getStoredRole()).toBe("STUDENT");

    storeAuthenticatedUser(makeUser({ role: "FACULTY" }));
    expect(getStoredRole()).toBe("FACULTY");
  });
});

describe("getStoredRole", () => {
  it("returns null for a value that is not a platform role", () => {
    window.localStorage.setItem(ROLE_KEY, "SUPERUSER");
    expect(getStoredRole()).toBeNull();
  });

  it("returns null when nothing is stored", () => {
    expect(getStoredRole()).toBeNull();
  });

  it("does not accept a lowercase spelling", () => {
    window.localStorage.setItem(ROLE_KEY, "admin");
    expect(getStoredRole()).toBeNull();
  });
});

describe("expiry handling", () => {
  it("reports no expiry when the stored value does not parse", () => {
    window.localStorage.setItem(TOKEN_KEY, "token");
    window.localStorage.setItem(EXPIRY_KEY, "not-a-date");
    expect(getTokenExpiry()).toBeNull();
  });

  it("treats an unparseable expiry as unknown rather than expired", () => {
    // The backend decides whether a token is still good; a corrupt local value must not
    // throw away a session that may well be valid.
    window.localStorage.setItem(TOKEN_KEY, "token");
    window.localStorage.setItem(EXPIRY_KEY, "not-a-date");
    expect(isStoredSessionExpired()).toBe(false);
  });

  it("is not expired when no token is stored at all", () => {
    expect(isStoredSessionExpired()).toBe(false);
  });

  it("is not expired while the recorded expiry is in the future", () => {
    storeSession(makeTokenResponse());
    expect(isStoredSessionExpired()).toBe(false);
  });

  it("is expired once the recorded expiry has passed", () => {
    storeSession(makeTokenResponse({ expires_at: "2020-01-01T00:00:00+00:00" }));
    expect(isStoredSessionExpired()).toBe(true);
  });

  it("treats the exact expiry instant as expired", () => {
    const moment = "2026-06-01T12:00:00.000Z";
    storeSession(makeTokenResponse({ expires_at: moment }));
    expect(isStoredSessionExpired(new Date(moment))).toBe(true);
  });
});

describe("clearActiveIdentity", () => {
  it("removes every stored key, including the expiry", () => {
    storeSession(makeTokenResponse());
    clearActiveIdentity();

    expect(getStoredIdentity()).toEqual({
      userId: null,
      profileId: null,
      token: null,
      email: null,
      name: null,
      role: null,
    });
    expect(window.localStorage.getItem(EXPIRY_KEY)).toBeNull();
    expect(getAuthHeaders()).toEqual({});
  });

  it("is safe to call when nothing is stored", () => {
    expect(() => clearActiveIdentity()).not.toThrow();
  });
});

describe("malformed and unavailable storage", () => {
  it("treats an empty stored string as absent", () => {
    window.localStorage.setItem(TOKEN_KEY, "");
    expect(getAccessToken()).toBeNull();
    // An empty token must not produce an "Authorization: Bearer " header.
    expect(getAuthHeaders()).toEqual({});
  });

  it("returns an empty identity when reading throws", () => {
    const getItem = vi
      .spyOn(window.localStorage, "getItem")
      .mockImplementation(() => {
        throw new DOMException("blocked", "SecurityError");
      });

    expect(getStoredIdentity()).toEqual({
      userId: null,
      profileId: null,
      token: null,
      email: null,
      name: null,
      role: null,
    });
    expect(getAuthHeaders()).toEqual({});
    getItem.mockRestore();
  });

  it("does not fail a sign-in when writing throws", () => {
    const setItem = vi.spyOn(window.localStorage, "setItem").mockImplementation(() => {
      throw new DOMException("quota", "QuotaExceededError");
    });

    expect(() => storeSession(makeTokenResponse())).not.toThrow();
    setItem.mockRestore();
  });

  it("does not throw when clearing while removal is blocked", () => {
    const removeItem = vi
      .spyOn(window.localStorage, "removeItem")
      .mockImplementation(() => {
        throw new DOMException("blocked", "SecurityError");
      });

    expect(() => clearActiveIdentity()).not.toThrow();
    removeItem.mockRestore();
  });
});

describe("setActiveIdentity", () => {
  it("leaves existing values alone when given nothing for them", () => {
    // Preserved behaviour: the developer-identity flow patches one field at a time.
    setActiveIdentity({ profileId: PROFILE_ID });
    setActiveIdentity({ name: "Ada Lovelace" });

    expect(getActiveProfileId()).toBe(PROFILE_ID);
    expect(getStoredIdentity().name).toBe("Ada Lovelace");
  });
});
