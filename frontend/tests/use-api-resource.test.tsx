/**
 * P4 — useApiResource: one request per resource however many components use it, answers that
 * always belong to the current key, a classified error with no server text, retry on request,
 * and nothing kept after the last user unmounts or for another account.
 */

import React, { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn(), back: vi.fn(), forward: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/dashboard",
  useSearchParams: () => new URLSearchParams(),
}));

import { SessionProvider, useSession } from "../components/auth/SessionProvider";
import { heldApiResources, useApiResource, type ApiResource } from "../hooks/useApiResource";
import { ApiError } from "../services/api";
import { clearActiveIdentity, storeSession } from "../services/auth";
import { jsonResponse, makeTokenResponse, makeUser } from "./factories";

/** A loader whose answers the test releases one by one. */
function controllable<T>() {
  const pending: { resolve: (value: T) => void; reject: (error: unknown) => void; signal: AbortSignal; key: string }[] = [];
  const load = vi.fn((key: string, signal: AbortSignal) => new Promise<T>((resolve, reject) => pending.push({ resolve, reject, signal, key })));
  return { load, pending };
}

function Probe({ name, resource }: { name: string; resource: ApiResource<{ items: string[] }> }) {
  return (
    <p data-testid={name}>
      {resource.status}
      {resource.data ? `:${resource.data.items.join(",")}` : ""}
      {resource.error ? `:${resource.error.kind}:${resource.error.status}` : ""}
      {`:r${resource.retries}`}
    </p>
  );
}

function Consumer({ name, resourceKey, load }: { name: string; resourceKey: string | null; load: (key: string, signal: AbortSignal) => Promise<{ items: string[] }> }) {
  const resource = useApiResource(resourceKey, (signal) => load(resourceKey!, signal), { isEmpty: (d) => d.items.length === 0 });
  return (
    <>
      <Probe name={name} resource={resource} />
      <button onClick={resource.retry}>retry {name}</button>
    </>
  );
}

function SessionState() {
  return <p data-testid="session">{useSession().status}</p>;
}

/** Renders inside a signed-in session (the hook scopes resources to the account) and waits for it. */
async function signedIn(ui: React.ReactNode, user = makeUser()) {
  storeSession(makeTokenResponse({ user }));
  vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(jsonResponse(user))));
  const view = render(
    <SessionProvider>
      <SessionState />
      {ui}
    </SessionProvider>
  );
  await waitFor(() => expect(screen.getByTestId("session")).toHaveTextContent("authenticated"));
  return view;
}

const text = (name: string) => screen.getByTestId(name).textContent;

beforeEach(() => clearActiveIdentity());
afterEach(async () => {
  clearActiveIdentity();
});

describe("useApiResource", () => {
  it("shares one request between every component using the same key", async () => {
    const { load, pending } = controllable<{ items: string[] }>();
    await signedIn(
      <>
        <Consumer name="a" resourceKey="workspace" load={load} />
        <Consumer name="b" resourceKey="workspace" load={load} />
      </>
    );
    await waitFor(() => expect(load).toHaveBeenCalledTimes(1));
    expect(text("a")).toBe("loading:r0");
    await act(async () => pending[0].resolve({ items: ["x"] }));
    expect(text("a")).toBe("success:x:r0");
    expect(text("b")).toBe("success:x:r0");
    expect(load).toHaveBeenCalledTimes(1);
  });

  it("does not ask again when the page re-renders", async () => {
    const { load, pending } = controllable<{ items: string[] }>();
    function Rerendering() {
      const [, setN] = useState(0);
      return (
        <>
          <button onClick={() => setN((n) => n + 1)}>rerender</button>
          <Consumer name="a" resourceKey="workspace" load={load} />
        </>
      );
    }
    await signedIn(<Rerendering />);
    await waitFor(() => expect(load).toHaveBeenCalledTimes(1));
    await act(async () => pending[0].resolve({ items: ["x"] }));
    for (let i = 0; i < 3; i++) fireEvent.click(screen.getByText("rerender"));
    expect(text("a")).toBe("success:x:r0");
    expect(load).toHaveBeenCalledTimes(1);
  });

  it("tells an empty answer from a failure, and never shows the server's words", async () => {
    const { load, pending } = controllable<{ items: string[] }>();
    await signedIn(
      <>
        <Consumer name="empty" resourceKey="reading" load={load} />
        <Consumer name="failed" resourceKey="postings" load={load} />
        <Consumer name="offline" resourceKey="calendar" load={load} />
      </>
    );
    await waitFor(() => expect(load).toHaveBeenCalledTimes(3));
    const byKey = (key: string) => pending.find((p) => p.key === key)!;
    await act(async () => {
      byKey("reading").resolve({ items: [] });
      byKey("postings").reject(new ApiError(500, "psycopg.OperationalError at 0x7f", "psycopg.OperationalError at 0x7f"));
      byKey("calendar").reject(new TypeError("Failed to fetch"));
    });
    expect(text("empty")).toBe("empty::r0");
    expect(text("failed")).toBe("error:server:500:r0");
    expect(text("offline")).toBe("error:network:null:r0");
    expect(document.body.textContent).not.toContain("psycopg");
  });

  it("never shows the previous key's answer as the new one's, and ignores a late answer", async () => {
    const { load, pending } = controllable<{ items: string[] }>();
    function Switching() {
      const [key, setKey] = useState("calendar:october");
      return (
        <>
          <button onClick={() => setKey("calendar:november")}>next month</button>
          <Consumer name="a" resourceKey={key} load={load} />
        </>
      );
    }
    await signedIn(<Switching />);
    await waitFor(() => expect(load).toHaveBeenCalledTimes(1));

    // The key changes while October is still on its way.
    fireEvent.click(screen.getByText("next month"));
    expect(text("a")).toBe("loading:r0");
    await waitFor(() => expect(load).toHaveBeenCalledTimes(2));
    await act(async () => pending[1].resolve({ items: ["november"] }));
    expect(text("a")).toBe("success:november:r0");

    // October's answer arrives late: it was aborted when nothing needed it, and changes nothing.
    expect(pending[0].signal.aborted).toBe(true);
    await act(async () => pending[0].resolve({ items: ["october"] }));
    expect(text("a")).toBe("success:november:r0");

    // And a key that already has an answer never shows it for another key.
    fireEvent.click(screen.getByText("next month"));
    expect(text("a")).toBe("success:november:r0");
  });

  it("aborts a request nobody needs any more, and keeps nothing after the last user unmounts", async () => {
    const { load, pending } = controllable<{ items: string[] }>();
    function Toggle() {
      const [shown, setShown] = useState(true);
      return (
        <>
          <button onClick={() => setShown(false)}>leave</button>
          {shown && <Consumer name="a" resourceKey="workspace" load={load} />}
        </>
      );
    }
    await signedIn(<Toggle />);
    await waitFor(() => expect(load).toHaveBeenCalledTimes(1));
    expect(heldApiResources()).toBe(1);

    fireEvent.click(screen.getByText("leave"));
    await act(async () => undefined);
    expect(pending[0].signal.aborted).toBe(true);
    expect(heldApiResources()).toBe(0);
    // The aborted request's late answer changes nothing.
    await act(async () => pending[0].resolve({ items: ["late"] }));
    expect(heldApiResources()).toBe(0);
  });

  it("waits while its key is null (a request that needs another one's answer)", async () => {
    const { load } = controllable<{ items: string[] }>();
    await signedIn(<Consumer name="a" resourceKey={null} load={load} />);
    await act(async () => undefined);
    expect(text("a")).toBe("idle:r0");
    expect(load).not.toHaveBeenCalled();
  });

  it("retries on request, once, for everyone using the key", async () => {
    const { load, pending } = controllable<{ items: string[] }>();
    await signedIn(
      <>
        <Consumer name="a" resourceKey="workspace" load={load} />
        <Consumer name="b" resourceKey="workspace" load={load} />
      </>
    );
    await waitFor(() => expect(load).toHaveBeenCalledTimes(1));
    await act(async () => pending[0].reject(new TypeError("Failed to fetch")));
    expect(text("a")).toBe("error:network:null:r0");

    fireEvent.click(screen.getByText("retry a"));
    expect(text("b")).toBe("loading:r1");
    expect(load).toHaveBeenCalledTimes(2);
    await act(async () => pending[1].resolve({ items: ["x"] }));
    expect(text("a")).toBe("success:x:r1");
    expect(text("b")).toBe("success:x:r1");
    // No retry of its own after a failure.
    expect(load).toHaveBeenCalledTimes(2);
  });

  it("lets a retry make an earlier, slower answer void", async () => {
    const { load, pending } = controllable<{ items: string[] }>();
    await signedIn(<Consumer name="a" resourceKey="workspace" load={load} />);
    await waitFor(() => expect(load).toHaveBeenCalledTimes(1));

    // Asked again while the first answer is still on its way; the first one then arrives last.
    fireEvent.click(screen.getByText("retry a"));
    expect(load).toHaveBeenCalledTimes(2);
    await act(async () => pending[1].resolve({ items: ["fresh"] }));
    await act(async () => pending[0].resolve({ items: ["stale"] }));
    expect(text("a")).toBe("success:fresh:r1");
  });

  it("follows the account when it changes under a mounted page", async () => {
    const { load, pending } = controllable<{ items: string[] }>();
    const ada = makeUser({ id: "user-ada" });
    const grace = makeUser({ id: "user-grace", email: "grace@university.edu", full_name: "Grace Hopper" });
    function SwitchAccount() {
      const { login } = useSession();
      return <button onClick={() => void login({ email: "grace@university.edu", password: "a-good-password" })}>switch</button>;
    }
    storeSession(makeTokenResponse({ user: ada }));
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) =>
        Promise.resolve(url.endsWith("/api/v1/auth/login") ? jsonResponse(makeTokenResponse({ user: grace, access_token: "grace.token" })) : jsonResponse(ada))
      )
    );
    render(
      <SessionProvider>
        <SessionState />
        <SwitchAccount />
        <Consumer name="a" resourceKey="workspace" load={load} />
      </SessionProvider>
    );
    await waitFor(() => expect(load).toHaveBeenCalledTimes(1));
    await act(async () => pending[0].resolve({ items: ["ada's"] }));
    expect(text("a")).toBe("success:ada's:r0");

    // Another account signs in on this page without passing through "signed out".
    fireEvent.click(screen.getByText("switch"));
    await waitFor(() => expect(load).toHaveBeenCalledTimes(2));
    expect(text("a")).toBe("loading:r0");
    await act(async () => pending[1].resolve({ items: ["grace's"] }));
    expect(text("a")).toBe("success:grace's:r0");
  });

  it("keeps one account's answers from another account", async () => {
    const { load, pending } = controllable<{ items: string[] }>();
    const view = await signedIn(<Consumer name="a" resourceKey="workspace" load={load} />, makeUser({ id: "user-ada" }));
    await waitFor(() => expect(load).toHaveBeenCalledTimes(1));
    await act(async () => pending[0].resolve({ items: ["ada's"] }));
    expect(text("a")).toBe("success:ada's:r0");
    view.unmount();
    await act(async () => undefined);
    expect(heldApiResources()).toBe(0);

    // Another account in the same browser: its own request, never the first account's answer.
    await signedIn(<Consumer name="a" resourceKey="workspace" load={load} />, makeUser({ id: "user-grace", email: "grace@university.edu" }));
    expect(text("a")).not.toContain("ada's");
    await waitFor(() => expect(load).toHaveBeenCalledTimes(2));
    await act(async () => pending[1].resolve({ items: ["grace's"] }));
    expect(text("a")).toBe("success:grace's:r0");
  });

  it("asks for nothing while nobody is signed in", async () => {
    const { load } = controllable<{ items: string[] }>();
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(jsonResponse({}, 401))));
    render(
      <SessionProvider>
        <Consumer name="a" resourceKey="workspace" load={load} />
      </SessionProvider>
    );
    await act(async () => undefined);
    expect(text("a")).toBe("idle:r0");
    expect(load).not.toHaveBeenCalled();
  });
});
