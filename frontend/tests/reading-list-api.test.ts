/**
 * Phase 5.14 — reading list API helpers.
 *
 * The BibTeX download cannot be a plain link: the export needs the caller's credentials, and a
 * link (like the calendar .ics export) sends no Bearer token. It is fetched with the auth
 * headers, saved through an object URL as `reading-list.bib`, and a 401 is reported to the
 * session exactly as `fetchJson` reports one.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  downloadReadingListBibtex,
  lookupReadingList,
  removeReadingListItem,
  setUnauthorizedHandler,
} from "../services/api";
import { storeSession } from "../services/auth";
import { headersOf, jsonResponse, makeTokenResponse } from "./factories";

const ITEM_ID = "rl000000-0000-4000-8000-000000000001";

let fetchMock: ReturnType<typeof vi.fn>;
let createObjectURL: ReturnType<typeof vi.fn>;
let revokeObjectURL: ReturnType<typeof vi.fn>;
let clicked: { href: string; download: string }[];
const originalCreateObjectURL = URL.createObjectURL;
const originalRevokeObjectURL = URL.revokeObjectURL;

beforeEach(() => {
  storeSession(makeTokenResponse());
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  createObjectURL = vi.fn(() => "blob:reading-list");
  revokeObjectURL = vi.fn();
  URL.createObjectURL = createObjectURL as unknown as typeof URL.createObjectURL;
  URL.revokeObjectURL = revokeObjectURL as unknown as typeof URL.revokeObjectURL;
  clicked = [];
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
    clicked.push({ href: this.href, download: this.download });
  });
});

afterEach(() => {
  URL.createObjectURL = originalCreateObjectURL;
  URL.revokeObjectURL = originalRevokeObjectURL;
  setUnauthorizedHandler(null);
});

describe("downloadReadingListBibtex", () => {
  it("fetches the export with the bearer token and saves it as reading-list.bib", async () => {
    fetchMock.mockResolvedValue(new Response("@article{x,\n}\n", { status: 200 }));

    await downloadReadingListBibtex({ itemIds: ["a", "b"], status: "DONE" });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url] = fetchMock.mock.calls[0];
    const requested = new URL(String(url));
    expect(requested.pathname).toBe("/api/v1/reading-list/export.bib");
    expect(requested.searchParams.getAll("item_ids")).toEqual(["a", "b"]);
    expect(requested.searchParams.get("status")).toBe("DONE");
    expect(headersOf(fetchMock.mock.calls[0])).toEqual({ Authorization: "Bearer header.payload.signature" });

    expect(createObjectURL).toHaveBeenCalledWith(expect.any(Blob));
    expect(clicked).toEqual([{ href: "blob:reading-list", download: "reading-list.bib" }]);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:reading-list");
    // The temporary anchor is removed again.
    expect(document.querySelector("a[download]")).toBeNull();
  });

  it("exports the whole list when nothing is chosen", async () => {
    fetchMock.mockResolvedValue(new Response("", { status: 200 }));

    await downloadReadingListBibtex();

    expect(new URL(String(fetchMock.mock.calls[0][0])).search).toBe("");
  });

  it("reports a 401 to the session and saves nothing", async () => {
    const onUnauthorized = vi.fn();
    setUnauthorizedHandler(onUnauthorized);
    fetchMock.mockResolvedValue(jsonResponse({ detail: "Token has expired." }, 401));

    const error = await downloadReadingListBibtex().catch((err: unknown) => err);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(401);
    expect((error as ApiError).detail).toBe("Token has expired.");
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
    expect(createObjectURL).not.toHaveBeenCalled();
  });

  it("throws the backend's message for another user's item without ending the session", async () => {
    const onUnauthorized = vi.fn();
    setUnauthorizedHandler(onUnauthorized);
    fetchMock.mockResolvedValue(
      jsonResponse({ detail: "Forbidden: the export includes another user's reading list item." }, 403)
    );

    await expect(downloadReadingListBibtex({ itemIds: [ITEM_ID] })).rejects.toMatchObject({
      status: 403,
      detail: "Forbidden: the export includes another user's reading list item.",
    });
    expect(onUnauthorized).not.toHaveBeenCalled();
  });
});

describe("reading list helpers", () => {
  it("removes an item with DELETE and resolves to nothing on 204", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));

    await expect(removeReadingListItem(ITEM_ID)).resolves.toBeUndefined();

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(new RegExp(`/api/v1/reading-list/${ITEM_ID}$`));
    expect((init as RequestInit).method).toBe("DELETE");
    expect(headersOf(fetchMock.mock.calls[0])["Authorization"]).toBe("Bearer header.payload.signature");
  });

  it("looks up saved works, and asks nothing for an empty list", async () => {
    await expect(lookupReadingList([])).resolves.toEqual({ saved: {} });
    expect(fetchMock).not.toHaveBeenCalled();

    fetchMock.mockResolvedValue(jsonResponse({ saved: { w1: ITEM_ID } }));
    await expect(lookupReadingList(["w1", "w2"])).resolves.toEqual({ saved: { w1: ITEM_ID } });
    expect(new URL(String(fetchMock.mock.calls[0][0])).searchParams.getAll("work_ids")).toEqual(["w1", "w2"]);
  });
});
