/**
 * P2-02 regression — the six DELETE wrappers that used to call fetch() directly.
 *
 * They built their own headers and never asked the session for a token, so every one of
 * them answered 401 in production, and three never checked the response, so the UI
 * reported success regardless. Each must now go through the shared client: bearer token
 * attached, developer header dropped when a token exists, 401 reported to the session,
 * 403 left alone, and the Promise<void> contract unchanged.
 */

import { afterEach, beforeEach, describe, expect, expectTypeOf, it, vi } from "vitest";
import {
  ApiError,
  deleteReminderRule,
  deleteSubmission,
  deleteSubmissionDocument,
  deleteWorkspaceTask,
  removeWorkspaceItem,
  removeWorkspaceMember,
  setUnauthorizedHandler,
} from "../services/api";
import { storeSession } from "../services/auth";
import { USER_ID, headersOf, jsonResponse, makeTokenResponse } from "./factories";

const ITEM = "0a000000-0000-4000-8000-000000000001";
const SUBMISSION = "0a000000-0000-4000-8000-000000000002";
const DOCUMENT = "0a000000-0000-4000-8000-000000000003";
const RULE = "0a000000-0000-4000-8000-000000000004";
const WORKSPACE = "0a000000-0000-4000-8000-000000000005";
const MEMBER = "0a000000-0000-4000-8000-000000000006";
const TASK = "0a000000-0000-4000-8000-000000000007";
const API = "http://localhost:8000";

interface WrapperCase {
  name: string;
  /** Called with a developer user id, which a stored bearer token must override. */
  call: (userId?: string) => Promise<void>;
  path: string;
}

const CASES: WrapperCase[] = [
  { name: "removeWorkspaceItem", call: (u) => removeWorkspaceItem(ITEM, u), path: `/api/v1/workspace/${ITEM}` },
  { name: "deleteSubmission", call: (u) => deleteSubmission(SUBMISSION, u), path: `/api/v1/submissions/${SUBMISSION}` },
  {
    name: "deleteSubmissionDocument",
    call: (u) => deleteSubmissionDocument(SUBMISSION, DOCUMENT, u),
    path: `/api/v1/submissions/${SUBMISSION}/documents/${DOCUMENT}`,
  },
  { name: "deleteReminderRule", call: (u) => deleteReminderRule(RULE, u), path: `/api/v1/notifications/rules/${RULE}` },
  {
    name: "removeWorkspaceMember",
    call: (u) => removeWorkspaceMember(WORKSPACE, MEMBER, u),
    path: `/api/v1/workspaces/${WORKSPACE}/members/${MEMBER}`,
  },
  {
    name: "deleteWorkspaceTask",
    call: (u) => deleteWorkspaceTask(WORKSPACE, TASK, u),
    path: `/api/v1/workspaces/${WORKSPACE}/tasks/${TASK}`,
  },
];

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  setUnauthorizedHandler(null);
});

function respondWith(make: () => Response) {
  fetchMock.mockImplementation(() => Promise.resolve(make()));
}

describe.each(CASES)("$name", ({ call, path }) => {
  it("sends the stored bearer token, and no X-User-ID even when one is passed", async () => {
    storeSession(makeTokenResponse());
    respondWith(() => new Response(null, { status: 204 }));

    await call(USER_ID);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${API}${path}`);
    expect(init?.method).toBe("DELETE");
    expect(init?.body).toBeUndefined();
    const headers = headersOf(fetchMock.mock.calls[0]);
    expect(headers["Authorization"]).toBe("Bearer header.payload.signature");
    expect(headers).not.toHaveProperty("X-User-ID");
  });

  it("resolves to undefined on 204 No Content", async () => {
    storeSession(makeTokenResponse());
    respondWith(() => new Response(null, { status: 204 }));

    await expect(call()).resolves.toBeUndefined();
  });

  it("rejects on 401 and reports the lost session exactly once", async () => {
    const onUnauthorized = vi.fn();
    setUnauthorizedHandler(onUnauthorized);
    storeSession(makeTokenResponse());
    respondWith(() => jsonResponse({ detail: "Access token has expired." }, 401));

    await expect(call()).rejects.toMatchObject({ status: 401, detail: "Access token has expired." });
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
  });

  it("rejects on 403 without treating the caller as signed out", async () => {
    // Previously three of these resolved on 403 and the page announced a success.
    const onUnauthorized = vi.fn();
    setUnauthorizedHandler(onUnauthorized);
    storeSession(makeTokenResponse());
    respondWith(() => jsonResponse({ detail: "Forbidden: belongs to another researcher." }, 403));

    const error = await call().then(
      () => null,
      (err: unknown) => err
    );
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 403, detail: "Forbidden: belongs to another researcher." });
    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  it("keeps the developer fallback when no token is stored", async () => {
    respondWith(() => new Response(null, { status: 204 }));

    await call(USER_ID);

    const headers = headersOf(fetchMock.mock.calls[0]);
    expect(headers["X-User-ID"]).toBe(USER_ID);
    expect(headers).not.toHaveProperty("Authorization");
  });
});

describe("public contract", () => {
  it("still returns Promise<void> from every wrapper", () => {
    // Checked by the type checker, which includes this directory.
    expectTypeOf(removeWorkspaceItem).returns.toEqualTypeOf<Promise<void>>();
    expectTypeOf(deleteSubmission).returns.toEqualTypeOf<Promise<void>>();
    expectTypeOf(deleteSubmissionDocument).returns.toEqualTypeOf<Promise<void>>();
    expectTypeOf(deleteReminderRule).returns.toEqualTypeOf<Promise<void>>();
    expectTypeOf(removeWorkspaceMember).returns.toEqualTypeOf<Promise<void>>();
    expectTypeOf(deleteWorkspaceTask).returns.toEqualTypeOf<Promise<void>>();
  });
});
