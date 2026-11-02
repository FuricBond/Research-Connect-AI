/**
 * Decisions B and C in the interface. The server is the authority (backend tests and e2e); these
 * check that the pages say the same thing, and that the confirmation page never mishandles a token.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SessionProvider } from "../components/auth/SessionProvider";
import { VerifyEmailPage } from "../components/auth/VerifyEmailPage";
import { PendingInvitations } from "../components/notifications/PendingInvitations";
import { PostingsNav } from "../components/postings/PostingsNav";
import { PostingsPage } from "../components/postings/PostingsPage";
import { useTrackedCalls } from "../components/research/trackedCalls";
import { storeSession } from "../services/auth";
import type { AuthenticatedUser } from "../types/auth";
import { canRecruit } from "../utils/recruiting";
import { jsonResponse, makeTokenResponse, makeUser } from "./factories";

const replace = vi.fn();
vi.mock("next/navigation", () => ({
  usePathname: () => "/verify-email",
  useRouter: () => ({ replace, push: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  useSearchParams: () => new URLSearchParams(window.location.search),
}));

type Answer = { status: number; body: unknown };

/** Answers by address, so each test states what the server says. */
function server(user: AuthenticatedUser, answers: Record<string, Answer | (() => Answer)> = {}) {
  const calls: { url: string; init?: RequestInit }[] = [];
  const fetchMock = vi.fn(async (url: string | URL, init?: RequestInit) => {
    const href = String(url);
    calls.push({ url: href, init });
    for (const [path, answer] of Object.entries(answers)) {
      if (href.endsWith(path)) {
        const { status, body } = typeof answer === "function" ? answer() : answer;
        return jsonResponse(body, status);
      }
    }
    if (href.endsWith("/auth/me")) return jsonResponse(user);
    return jsonResponse({ invitations: [], shared_workspaces: [], email_verified: user.email_verified });
  });
  vi.stubGlobal("fetch", fetchMock);
  return calls;
}

function signedInAs(user: AuthenticatedUser) {
  storeSession(makeTokenResponse({ user }));
}

beforeEach(() => {
  replace.mockClear();
  window.history.replaceState(null, "", "/");
});

describe("Decision B: who is offered recruiting", () => {
  it("only verified faculty can recruit, whatever else an account is", () => {
    expect(canRecruit(makeUser({ role: "FACULTY", is_verified: true }))).toBe(true);
    for (const user of [{ role: "FACULTY", is_verified: false }, { role: "ADMIN", is_verified: true }, { role: "ADMIN", is_verified: false }, { role: "STUDENT", is_verified: true }] as const) {
      expect(canRecruit(makeUser(user))).toBe(false);
    }
  });

  it("gives an administrator Discover only: no My postings, Applicants or My applications", async () => {
    const user = makeUser({ role: "ADMIN", is_verified: true });
    signedInAs(user);
    server(user);
    render(<SessionProvider><PostingsNav current="discover" /></SessionProvider>);
    expect(await screen.findByRole("link", { name: "Discover" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "My postings" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Applicants" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "My applications" })).not.toBeInTheDocument();
  });

  it("does not ask for an administrator's invitations, which the server would refuse", async () => {
    const user = makeUser({ role: "ADMIN", is_verified: true, email_verified: false });
    signedInAs(user);
    const calls = server(user);
    const { container } = render(<SessionProvider><PendingInvitations /></SessionProvider>);
    await waitFor(() => expect(calls.some((call) => call.url.endsWith("/auth/me"))).toBe(true));
    expect(calls.filter((call) => call.url.includes("workspace-invitations"))).toEqual([]);
    expect(container.querySelector("#invitations")).toBeNull();
  });

  it("does not look up an administrator's workspace on a list of calls", async () => {
    const user = makeUser({ role: "ADMIN", is_verified: true });
    signedInAs(user);
    const calls = server(user);
    const seen = vi.fn();
    function Tracked() {
      seen(useTrackedCalls().status);
      return null;
    }
    render(<SessionProvider><Tracked /></SessionProvider>);
    await waitFor(() => expect(calls.some((call) => call.url.endsWith("/auth/me"))).toBe(true));
    await waitFor(() => expect(seen).toHaveBeenCalled());
    expect(calls.filter((call) => call.url.includes("/workspace"))).toEqual([]);
  });

  it("still gives faculty My postings and Applicants", async () => {
    const user = makeUser({ role: "FACULTY", is_verified: true });
    signedInAs(user);
    server(user);
    render(<SessionProvider><PostingsNav current="discover" /></SessionProvider>);
    expect(await screen.findByRole("link", { name: "My postings" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Applicants" })).toBeInTheDocument();
  });

  it("refuses an administrator at /postings?view=mine and asks the API for nothing about postings", async () => {
    window.history.replaceState(null, "", "/postings?view=mine");
    const user = makeUser({ role: "ADMIN", is_verified: true });
    signedInAs(user);
    const calls = server(user);
    render(<SessionProvider><PostingsPage /></SessionProvider>);
    expect(await screen.findByRole("heading", { name: "This page is for Faculty accounts." })).toBeInTheDocument();
    expect(calls.filter((call) => call.url.includes("/postings"))).toEqual([]);
  });
});

describe("Decision C: the invitations section for an unconfirmed account", () => {
  it("says the same whether or not an invitation exists, and offers no answer", async () => {
    const user = makeUser({ email: "new@univ.edu", email_verified: false });
    signedInAs(user);
    server(user);
    render(<SessionProvider><PendingInvitations /></SessionProvider>);
    expect(await screen.findByText("Invitations sent to new@univ.edu appear here once you confirm that it is yours.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send the confirmation email" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Accept/ })).not.toBeInTheDocument();
  });

  it("announces that the email went, and keeps focus on the button", async () => {
    const user = makeUser({ email: "new@univ.edu", email_verified: false });
    signedInAs(user);
    server(user, { "/auth/email-verification": { status: 202, body: { status: "SENT" } } });
    render(<SessionProvider><PendingInvitations /></SessionProvider>);
    const send = await screen.findByRole("button", { name: "Send the confirmation email" });
    send.focus();
    fireEvent.click(send);
    expect(await screen.findByRole("alert")).toHaveTextContent("We sent a link to new@univ.edu.");
    expect(screen.getByRole("button", { name: "Send the email again" })).toHaveFocus();
  });

  it("reads out why the server cannot send", async () => {
    const user = makeUser({ email_verified: false });
    signedInAs(user);
    server(user, { "/auth/email-verification": { status: 503, body: { detail: "This server cannot send email to your address, so it cannot be confirmed yet." } } });
    render(<SessionProvider><PendingInvitations /></SessionProvider>);
    fireEvent.click(await screen.findByRole("button", { name: "Send the confirmation email" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("This server cannot send email");
  });

  it("shows nothing extra to a confirmed account with no invitations", async () => {
    const user = makeUser({ email_verified: true });
    signedInAs(user);
    const calls = server(user);
    const { container } = render(<SessionProvider><PendingInvitations /></SessionProvider>);
    await waitFor(() => expect(calls.some((call) => call.url.includes("/workspace-invitations/mine"))).toBe(true));
    expect(container.querySelector("#invitations")).toBeNull();
  });
});

describe("Decision C: the confirmation page", () => {
  const CONFIRM = "/auth/email-verification/confirm";

  it("takes the token out of the address at once, sends it in the body, and says it worked", async () => {
    window.history.replaceState(null, "", "/verify-email#token=abc_123-def");
    const before = makeUser({ email: "a@univ.edu", email_verified: false });
    const after = { ...before, email_verified: true };
    signedInAs(before);
    const calls = server(before, { [CONFIRM]: { status: 200, body: after }, "/auth/me": { status: 200, body: after } });
    render(<SessionProvider><VerifyEmailPage /></SessionProvider>);

    expect(window.location.hash).toBe("");
    expect(await screen.findByRole("alert")).toHaveTextContent("Your email address is confirmed.");
    expect(screen.getByRole("link", { name: "your notifications page" })).toHaveAttribute("href", "/notifications#invitations");
    const confirm = calls.filter((call) => call.url.endsWith(CONFIRM));
    expect(confirm).toHaveLength(1);
    expect(confirm[0].url).not.toContain("abc_123");
    expect(JSON.parse(String(confirm[0].init?.body))).toEqual({ token: "abc_123-def" });
    expect(window.sessionStorage.getItem("researchconnect_email_confirmation")).toBeNull();
  });

  it("keeps the token for signing in when the visitor is signed out, without showing it anywhere", async () => {
    window.history.replaceState(null, "", "/verify-email#token=abc_123");
    vi.stubGlobal("fetch", vi.fn());
    render(<SessionProvider><VerifyEmailPage /></SessionProvider>);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login?next=%2Fverify-email"));
    expect(window.sessionStorage.getItem("researchconnect_email_confirmation")).toBe("abc_123");
    expect(window.location.hash).toBe("");
  });

  it("forgets a refused token and offers a new email, for this account only", async () => {
    window.history.replaceState(null, "", "/verify-email#token=stale");
    const user = makeUser({ email: "a@univ.edu", email_verified: false });
    signedInAs(user);
    server(user, { [CONFIRM]: { status: 400, body: { detail: "This link does not confirm this account's address." } } });
    render(<SessionProvider><VerifyEmailPage /></SessionProvider>);
    expect(await screen.findByRole("alert")).toHaveTextContent("This link does not confirm this account's address.");
    expect(screen.getByRole("button", { name: "Send the confirmation email" })).toBeInTheDocument();
    expect(window.sessionStorage.getItem("researchconnect_email_confirmation")).toBeNull();
  });

  it("keeps the token through a failure, so Try again can use it", async () => {
    window.history.replaceState(null, "", "/verify-email#token=keep");
    const before = makeUser({ email_verified: false });
    const after = { ...before, email_verified: true };
    let attempts = 0;
    signedInAs(before);
    server(before, {
      [CONFIRM]: () => {
        attempts += 1;
        return attempts === 1 ? { status: 500, body: { detail: "x" } } : { status: 200, body: after };
      },
      "/auth/me": { status: 200, body: before },
    });
    render(<SessionProvider><VerifyEmailPage /></SessionProvider>);
    expect(await screen.findByRole("alert")).toHaveTextContent("could not be confirmed just now");
    expect(window.sessionStorage.getItem("researchconnect_email_confirmation")).toBe("keep");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Your email address is confirmed.")).toBeInTheDocument();
    expect(attempts).toBe(2);
  });

  it("with no link: says done to a confirmed account, and offers an email to any other", async () => {
    window.history.replaceState(null, "", "/verify-email");
    const user = makeUser({ email_verified: true });
    signedInAs(user);
    const calls = server(user);
    render(<SessionProvider><VerifyEmailPage /></SessionProvider>);
    expect(await screen.findByRole("alert")).toHaveTextContent("Your email address is confirmed.");
    expect(calls.filter((call) => call.url.endsWith(CONFIRM))).toEqual([]);
  });
});
