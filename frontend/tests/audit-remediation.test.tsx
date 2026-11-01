/**
 * The independent audit's frontend findings, each by what a person or a screen reader meets:
 *
 *   SEC-01   an address that is not a plain web address is never an active link
 *   FUNC-01  an invitation is answered on the notifications page, by the account it was sent to
 *   FUNC-02  every task status the UI offers is one the API has
 *   FUNC-03  only a 401 ends a session; any other failed check offers another try
 *   FUNC-05  the user list's status filter, in the address
 *   FUNC-06  signing in returns to the page with its query
 *   FUNC-07  subfields in words, across disciplines
 *   FUNC-09  a research refresh alert leads to the monitor, for administrators only
 *   UI-01    one confirmation dialog: sends once, cannot be dismissed while sending
 *   A11Y-01  Save is an action that reports, not a toggle
 *   Decision 1  an unverified faculty member is told what is waiting and offered nothing it cannot do
 *   Decision 2  administrators are not offered personal research tools
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import PageError from "../app/error";
import { RequireAuth } from "../components/auth/RequireAuth";
import { LatestNotifications } from "../components/dashboard/LatestNotifications";
import { publishLatest } from "../hooks/useUnreadNotificationCount";
import { SessionProvider, SESSION_CHECK_TIMEOUT_MS, useSession } from "../components/auth/SessionProvider";
import { PendingInvitations } from "../components/notifications/PendingInvitations";
import { ApplicationCard } from "../components/postings/ApplicationCard";
import { VerificationNotice } from "../components/postings/VerificationNotice";
import { OpportunityCard } from "../components/research/OpportunityCard";
import { SaveCallButton } from "../components/research/SaveCallButton";
import { AppShell } from "../components/shell/AppShell";
import { ConfirmDialog } from "../components/ui/Dialog/ConfirmDialog";
import { Toast } from "../components/ui/Toast/Toast";
import { TASK_STATUSES } from "../components/workspace/item/TasksPanel";
import { clearActiveIdentity, getAccessToken, storeSession } from "../services/auth";
import { readUsersQuery, usersHref } from "../utils/admin";
import { accountItemsFor, navigationFor } from "../utils/navigation";
import { notificationHref } from "../utils/notifications";
import { awaitingVerification, canRecruit } from "../utils/recruiting";
import { safeExternalUrl } from "../utils/safeUrl";
import { subfieldLabel } from "../utils/subfields";
import { taskStatusMeta } from "../utils/workflowStatus";
import { jsonResponse, makeTokenResponse, makeUser } from "./factories";

const replace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, push: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/postings",
  useSearchParams: () => new URLSearchParams(),
}));

const FRONTEND = path.resolve(__dirname, "..");

beforeEach(() => {
  replace.mockClear();
});

afterEach(() => {
  clearActiveIdentity();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("SEC-01: links", () => {
  it.each([
    "javascript:alert(1)",
    "JaVaScRiPt:alert(1)",
    " javascript:alert(1)",
    "java\tscript:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "vbscript:msgbox(1)",
    "ftp://example.org/x",
    "file:///etc/passwd",
    "//evil.example/x",
    "\\\\evil.example\\x",
    "/relative",
    "example.org",
    "http:example.org",
    "https://user:secret@example.org/",
    "https://exa mple.org/",
    "",
    null,
    undefined,
  ])("%j does not become a link", (value) => {
    expect(safeExternalUrl(value)).toBeNull();
  });

  it.each(["https://example.org", "http://example.org/a?b=1#c", "HTTPS://Example.org/"])("%s stays as it was given", (value) => {
    expect(safeExternalUrl(value)).toBe(value);
  });

  it("renders a call's unsafe source as no link at all, and a safe one as a link", () => {
    const call = { id: "1", title: "A call", opportunity_type: "CONFERENCE", status: "ACTIVE" };
    const { rerender } = render(<SessionProvider><OpportunityCard call={{ ...call, website_url: "javascript:alert(1)" } as never} /></SessionProvider>);
    expect(screen.queryByRole("link", { name: /source/i })).not.toBeInTheDocument();
    rerender(<SessionProvider><OpportunityCard call={{ ...call, website_url: "https://example.org/call" } as never} /></SessionProvider>);
    expect(screen.getByRole("link", { name: /source/i })).toHaveAttribute("href", "https://example.org/call");
  });

  it("leaves no address field in the app going straight into an href", () => {
    const offenders: string[] = [];
    const walk = (dir: string) => {
      for (const name of readdirSync(dir)) {
        const file = path.join(dir, name);
        if (statSync(file).isDirectory()) walk(file);
        else if (file.endsWith(".tsx")) {
          for (const match of readFileSync(file, "utf8").matchAll(/href=\{[^}]*\b[a-zA-Z_.?]*(website_url|submission_url|external_url|portfolio_url|landing_page_url|homepage_url|source_url|license_url)\b[^}]*\}/g)) {
            if (!match[0].includes("safeExternalUrl")) offenders.push(`${path.relative(FRONTEND, file)}: ${match[0]}`);
          }
        }
      }
    };
    walk(path.join(FRONTEND, "components"));
    walk(path.join(FRONTEND, "app"));
    expect(offenders).toEqual([]);
  });
});

describe("FUNC-01: answering an invitation", () => {
  const INVITATION = {
    id: "11111111-1111-4111-8111-111111111111",
    workspace_id: "22222222-2222-4222-8222-222222222222",
    workspace_title: "Causal ML Workshop",
    inviter_name: "Olu Owner",
    role: "EDITOR",
    created_at: "2030-01-01T00:00:00Z",
    expires_at: "2030-01-08T00:00:00Z",
  };

  function serve(answer: (url: string, init?: RequestInit) => Response | Promise<Response>) {
    let invitations = [INVITATION];
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/api/v1/auth/me")) return jsonResponse(makeUser());
      if (url.endsWith("/api/v1/workspace-invitations/mine")) return jsonResponse({ invitations, shared_workspaces: [] });
      const response = await answer(url, init);
      if (response.ok) invitations = [];
      return response;
    });
    vi.stubGlobal("fetch", fetchMock);
    storeSession(makeTokenResponse());
    return fetchMock;
  }

  const renderIt = () =>
    render(
      <SessionProvider>
        <PendingInvitations />
      </SessionProvider>
    );

  it("says who invited them to what, as what, with no token in sight", async () => {
    serve(() => jsonResponse({}));
    renderIt();
    expect(await screen.findByRole("heading", { name: "Causal ML Workshop" })).toBeInTheDocument();
    expect(screen.getByText(/Olu Owner invited you to join as an editor/)).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/token|code/i);
  });

  it("accepts once, leads to the workspace, and removes the invitation", async () => {
    const fetchMock = serve(() => jsonResponse({ id: "m", role: "EDITOR" }));
    renderIt();
    fireEvent.click(await screen.findByRole("button", { name: /^Accept/ }));
    const joined = await screen.findByText(/You joined “Causal ML Workshop”/);
    expect(within(joined).getByRole("link", { name: "Open the workspace" })).toHaveAttribute("href", `/workspace/${INVITATION.workspace_id}`);
    await waitFor(() => expect(screen.queryByRole("button", { name: /^Accept/ })).not.toBeInTheDocument());
    expect(fetchMock.mock.calls.filter(([url, init]) => String(url).endsWith(`/${INVITATION.id}/accept`) && init?.method === "POST")).toHaveLength(1);
    expect(screen.getByRole("heading", { name: "Workspace invitations" })).toHaveFocus();
  });

  it("declines, and says so", async () => {
    const fetchMock = serve(() => new Response(null, { status: 204 }));
    renderIt();
    fireEvent.click(await screen.findByRole("button", { name: /^Decline/ }));
    expect(await screen.findByText(/You declined the invitation/)).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith(`/${INVITATION.id}/decline`))).toBe(true);
  });

  it.each([
    ["expired", 400, "This invitation has expired. Ask the workspace owner to send a new one."],
    ["revoked", 400, "This invitation has been revoked by the workspace owner."],
    ["already accepted", 400, "This invitation has already been accepted."],
    ["not this account's", 404, "This invitation could not be found. It may have been sent to another account."],
  ])("explains a refusal in the API's words: %s", async (_name, status, detail) => {
    serve(() => jsonResponse({ detail }, status));
    renderIt();
    fireEvent.click(await screen.findByRole("button", { name: /^Accept/ }));
    expect((await screen.findAllByText(detail)).length).toBeGreaterThan(0);
  });

  it("keeps the invitation to try again when the request itself fails", async () => {
    let attempt = 0;
    serve(() => {
      attempt += 1;
      return attempt === 1 ? jsonResponse({ detail: "boom" }, 500) : jsonResponse({ id: "m" });
    });
    renderIt();
    fireEvent.click(await screen.findByRole("button", { name: /^Accept/ }));
    expect(await screen.findByText("The invitation could not be accepted. Nothing was changed. Try again.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /^Accept/ }));
    expect(await screen.findByText(/You joined/)).toBeInTheDocument();
  });

  it("is not there at all without invitations", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => (url.endsWith("/auth/me") ? jsonResponse(makeUser()) : jsonResponse({ invitations: [], shared_workspaces: [] }))));
    storeSession(makeTokenResponse());
    renderIt();
    await waitFor(() => expect(screen.queryByRole("heading", { name: "Workspace invitations" })).not.toBeInTheDocument());
  });

  it("leads an invitation notification to where it is answered", () => {
    const item = { notification_type: "WORKSPACE_INVITATION", source_type: "WORKSPACE", source_id: INVITATION.workspace_id, metadata_json: {} } as never;
    expect(notificationHref(item)).toBe("/notifications#invitations");
  });
});

describe("FUNC-02 and the API's enums", () => {
  /** The values of `class Name(str, Enum)` in a backend model file. */
  function backendEnum(file: string, name: string): string[] {
    const source = readFileSync(path.join(FRONTEND, "../backend/app/models", file), "utf8");
    const body = new RegExp(`class ${name}\\(str, Enum\\):[\\s\\S]*?(?=\\n\\n\\n|\\nclass )`).exec(source)?.[0] ?? "";
    return [...body.matchAll(/^\s+[A-Z_]+ = "([A-Z_]+)"/gm)].map((match) => match[1]).sort();
  }

  /** The members of `export type Name = "A" | "B"` in a frontend types file. */
  function frontendUnion(name: string): string[] {
    const source = readFileSync(path.join(FRONTEND, "types/collaboration.ts"), "utf8");
    const body = new RegExp(`export type ${name} =[^;]*;`).exec(source)?.[0] ?? "";
    return [...body.matchAll(/"([A-Z_]+)"/g)].map((match) => match[1]).sort();
  }

  it.each(["TaskStatus", "TaskPriority", "InvitationStatus", "WorkspaceRole", "MemberStatus", "ActivityType"])("%s is the API's, value for value", (name) => {
    expect(frontendUnion(name)).toEqual(backendEnum("workspace_collaboration.py", name));
  });

  it("offers exactly the API's task statuses, each in words", () => {
    expect([...TASK_STATUSES].sort()).toEqual(backendEnum("workspace_collaboration.py", "TaskStatus"));
    expect(TASK_STATUSES).not.toContain("IN_REVIEW");
    expect(taskStatusMeta("REVIEW").label).toBe("In review");
    expect(taskStatusMeta("REVIEW").tone).toBe("info");
  });
});

describe("FUNC-03: when the session cannot be checked", () => {
  function Probe() {
    const { status, retryCheck } = useSession();
    return (
      <>
        <span data-testid="status">{status}</span>
        <button onClick={retryCheck}>again</button>
      </>
    );
  }

  const renderProbe = () =>
    render(
      <SessionProvider>
        <Probe />
      </SessionProvider>
    );

  it("ends the session on a genuine 401", async () => {
    storeSession(makeTokenResponse());
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({ detail: "Invalid token" }, 401)));
    renderProbe();
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated"));
    expect(getAccessToken()).toBeNull();
  });

  it.each([
    ["a 500", () => Promise.resolve(jsonResponse({ detail: "boom" }, 500))],
    ["a 503", () => Promise.resolve(jsonResponse({ detail: "down" }, 503))],
    ["no network", () => Promise.reject(new TypeError("Failed to fetch"))],
  ])("keeps the token and says so on %s", async (_name, answer) => {
    storeSession(makeTokenResponse());
    const token = getAccessToken();
    vi.stubGlobal("fetch", vi.fn(answer));
    renderProbe();
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("unavailable"));
    expect(getAccessToken()).toBe(token);
  });

  it("recovers on a retry after a temporary failure", async () => {
    storeSession(makeTokenResponse());
    let up = false;
    vi.stubGlobal("fetch", vi.fn(async () => (up ? jsonResponse(makeUser()) : jsonResponse({ detail: "down" }, 503))));
    renderProbe();
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("unavailable"));
    up = true;
    fireEvent.click(screen.getByRole("button", { name: "again" }));
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("authenticated"));
  });

  it("accepts a slow answer within the limit", async () => {
    storeSession(makeTokenResponse());
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>((resolve) => setTimeout(() => resolve(jsonResponse(makeUser())), SESSION_CHECK_TIMEOUT_MS - 1000))));
    renderProbe();
    expect(screen.getByTestId("status")).toHaveTextContent("loading");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(SESSION_CHECK_TIMEOUT_MS - 500);
    });
    expect(screen.getByTestId("status")).toHaveTextContent("authenticated");
  });

  it("stops checking when no answer ever comes", async () => {
    storeSession(makeTokenResponse());
    const token = getAccessToken();
    vi.useFakeTimers();
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (_url: string, init?: RequestInit) =>
          new Promise<Response>((_resolve, reject) => {
            init?.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
          })
      )
    );
    renderProbe();
    expect(screen.getByTestId("status")).toHaveTextContent("loading");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(SESSION_CHECK_TIMEOUT_MS + 100);
    });
    expect(screen.getByTestId("status")).toHaveTextContent("unavailable");
    expect(getAccessToken()).toBe(token);
  });

  it("does not sign out when the page is left while the check is in flight", async () => {
    storeSession(makeTokenResponse());
    let fail: (reason: unknown) => void = () => undefined;
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>((_resolve, reject) => { fail = reject; })));
    renderProbe();
    await act(async () => {
      window.dispatchEvent(new Event("beforeunload"));
      fail(new TypeError("Failed to fetch"));
    });
    expect(screen.getByTestId("status")).toHaveTextContent("loading");
    expect(getAccessToken()).not.toBeNull();
  });

  it("tells the person in the shell and offers another try, and the guard does not redirect", async () => {
    storeSession(makeTokenResponse());
    vi.stubGlobal("fetch", vi.fn(async (url: string) => (url.endsWith("/auth/me") ? jsonResponse({ detail: "down" }, 503) : jsonResponse({}))));
    render(
      <SessionProvider>
        <AppShell>
          <RequireAuth>
            <p>protected</p>
          </RequireAuth>
        </AppShell>
      </SessionProvider>
    );
    const alert = await screen.findByText(/We could not check your session/);
    expect(alert.closest('[role="alert"]')).toHaveTextContent("You have not been signed out");
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
    expect(screen.queryByText("protected")).not.toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });
});

describe("FUNC-05: status filter in the address", () => {
  it("reads and writes it, and ignores what it does not know", () => {
    expect(readUsersQuery(new URLSearchParams("status=inactive&role=FACULTY&page=2"))).toMatchObject({ status: "inactive", role: "FACULTY", page: 2 });
    expect(readUsersQuery(new URLSearchParams("status=whatever")).status).toBeNull();
    expect(usersHref({ status: "unverified", q: "x" })).toBe("/admin/users?status=unverified&q=x");
  });
});

describe("FUNC-06: back to the page with its query", () => {
  it("carries the query through sign-in", async () => {
    window.history.replaceState(null, "", "/postings?view=mine");
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({}, 401)));
    render(
      <SessionProvider>
        <RequireAuth>
          <p>protected</p>
        </RequireAuth>
      </SessionProvider>
    );
    await waitFor(() => expect(replace).toHaveBeenCalledWith(`/login?next=${encodeURIComponent("/postings?view=mine")}`));
    window.history.replaceState(null, "", "/");
  });
});

describe("FUNC-07: subfields in words", () => {
  it.each([
    ["1702", "Artificial Intelligence"],
    ["1311", "Genetics"],
    ["3320", "Political Science and International Relations"],
    ["2730", "Oncology"],
  ])("%s is %s", (id, name) => {
    expect(subfieldLabel(id)).toBe(name);
  });

  it("falls back to the field, or to words, and never to the raw identifier", () => {
    expect(subfieldLabel("1799")).toBe("Other Computer Science");
    expect(subfieldLabel("9999")).toBe("Other subject area");
    expect(subfieldLabel("not-an-id")).toBe("Other subject area");
    expect(subfieldLabel("9999")).not.toContain("9999");
  });
});

describe("FUNC-09: where a research refresh alert leads", () => {
  const alert = { notification_type: "SYSTEM", source_type: "SYSTEM", source_id: null, metadata_json: { run_tag: "r1" } } as never;

  it("goes to the monitor for an administrator, and nowhere for anyone else", () => {
    expect(notificationHref(alert, "ADMIN")).toBe("/admin/research-data");
    expect(notificationHref(alert, "STUDENT")).toBeNull();
    expect(notificationHref(alert, "FACULTY")).toBeNull();
    expect(notificationHref(alert)).toBeNull();
  });

  it("gives another system notification no destination", () => {
    expect(notificationHref({ notification_type: "SYSTEM", source_type: "SYSTEM", source_id: null, metadata_json: {} } as never, "ADMIN")).toBeNull();
  });
});

describe("UI-01: confirming", () => {
  function Harness({ onConfirm, onClose = vi.fn() }: { onConfirm: () => Promise<boolean>; onClose?: () => void }) {
    const [open, setOpen] = useState(false);
    const [failure, setFailure] = useState<string | null>(null);
    return (
      <>
        <button onClick={() => setOpen(true)}>open</button>
        {open && (
          <ConfirmDialog
            title="Delete this?"
            confirmLabel="Delete"
            failure={failure}
            onClose={() => {
              onClose();
              setOpen(false);
            }}
            onConfirm={async () => {
              const agreed = await onConfirm();
              if (!agreed) setFailure("It could not be deleted.");
              return agreed;
            }}
          >
            <p>This cannot be undone.</p>
          </ConfirmDialog>
        )}
      </>
    );
  }

  /** jsdom has no modal behaviour: `cancel` is what Escape fires on a real dialog. */
  const escape = () => fireEvent(document.querySelector("dialog") as HTMLDialogElement, new Event("cancel", { cancelable: true }));

  beforeEach(() => {
    HTMLDialogElement.prototype.showModal = function () {
      this.setAttribute("open", "");
    };
    HTMLDialogElement.prototype.close = function () {
      this.removeAttribute("open");
      this.dispatchEvent(new Event("close"));
    };
  });

  it("sends once however often it is pressed, then closes", async () => {
    let agree: (value: boolean) => void = () => undefined;
    const onConfirm = vi.fn(() => new Promise<boolean>((resolve) => { agree = resolve; }));
    render(<Harness onConfirm={onConfirm} />);
    fireEvent.click(screen.getByRole("button", { name: "open" }));
    const confirm = screen.getByRole("button", { name: "Delete" });
    fireEvent.click(confirm);
    fireEvent.click(confirm);
    fireEvent.click(confirm);
    expect(onConfirm).toHaveBeenCalledTimes(1);
    await act(async () => agree(true));
    await waitFor(() => expect(screen.queryByText("This cannot be undone.")).not.toBeInTheDocument());
  });

  it("sends nothing on Cancel, Close or Escape while idle", () => {
    const onConfirm = vi.fn(async () => true);
    render(<Harness onConfirm={onConfirm} />);
    for (const dismiss of [() => fireEvent.click(screen.getByRole("button", { name: "Cancel" })), () => fireEvent.click(screen.getByRole("button", { name: "Close" })), escape]) {
      fireEvent.click(screen.getByRole("button", { name: "open" }));
      expect(screen.getByText("This cannot be undone.")).toBeInTheDocument();
      dismiss();
      expect(screen.queryByText("This cannot be undone.")).not.toBeInTheDocument();
    }
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("cannot be dismissed while the change is being sent", async () => {
    let agree: (value: boolean) => void = () => undefined;
    const onClose = vi.fn();
    render(<Harness onClose={onClose} onConfirm={() => new Promise<boolean>((resolve) => { agree = resolve; })} />);
    fireEvent.click(screen.getByRole("button", { name: "open" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    escape();
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    fireEvent.click(document.querySelector("dialog") as HTMLDialogElement);
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByText("This cannot be undone.")).toBeInTheDocument();
    await act(async () => agree(false));
    expect(await screen.findByText("It could not be deleted.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete" })).toBeEnabled();
    expect(onClose).not.toHaveBeenCalled();
  });
});

describe("Toast", () => {
  it("speaks politely, stays while held, and leaves after 5 seconds", () => {
    vi.useFakeTimers();
    const onDismiss = vi.fn();
    render(<Toast message="Saved." onDismiss={onDismiss} action={<button>Undo</button>} />);
    expect(screen.getByRole("status")).toHaveAttribute("aria-live", "polite");
    fireEvent.pointerEnter(screen.getByText("Saved.").parentElement as HTMLElement);
    act(() => vi.advanceTimersByTime(10_000));
    expect(onDismiss).not.toHaveBeenCalled();
    fireEvent.pointerLeave(screen.getByText("Saved.").parentElement as HTMLElement);
    act(() => vi.advanceTimersByTime(5_000));
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it("has its region ready before there is a message", () => {
    render(<Toast message={null} onDismiss={vi.fn()} />);
    expect(screen.getByRole("status")).toBeEmptyDOMElement();
  });
});

describe("A11Y-01: Save", () => {
  it("is a named action, not a toggle, and reports once", async () => {
    storeSession(makeTokenResponse());
    vi.stubGlobal("fetch", vi.fn(async (url: string) => (url.endsWith("/auth/me") ? jsonResponse(makeUser()) : jsonResponse({ id: "w" }))));
    render(
      <SessionProvider>
        <SaveCallButton opportunityId="11111111-1111-4111-8111-111111111111" />
      </SessionProvider>
    );
    const save = await screen.findByRole("button", { name: "Save to workspace" });
    expect(save).not.toHaveAttribute("aria-pressed");
    fireEvent.click(save);
    const saved = await screen.findByRole("button", { name: "Saved to workspace" });
    expect(saved).not.toHaveAttribute("aria-pressed");
    expect(screen.getByRole("status")).toHaveTextContent("Saved to your workspace.");
  });
});

describe("Decision 1: faculty verification", () => {
  it("decides who may recruit as the API does", () => {
    expect(canRecruit(makeUser({ role: "FACULTY", is_verified: true }))).toBe(true);
    expect(canRecruit(makeUser({ role: "FACULTY", is_verified: false }))).toBe(false);
    expect(canRecruit(makeUser({ role: "ADMIN", is_verified: false }))).toBe(true);
    expect(canRecruit(makeUser({ role: "STUDENT", is_verified: true }))).toBe(false);
    expect(canRecruit(null)).toBe(false);
    expect(awaitingVerification(makeUser({ role: "FACULTY", is_verified: false }))).toBe(true);
    expect(awaitingVerification(makeUser({ role: "STUDENT", is_verified: false }))).toBe(false);
  });

  it("says what is waiting and who does it", () => {
    render(<VerificationNotice />);
    expect(screen.getByText("Your faculty account is waiting for verification")).toBeInTheDocument();
    expect(screen.getByText(/An administrator needs to verify your account/)).toBeInTheDocument();
  });
});

describe("Decision 2: an administrator's tools", () => {
  const labels = (role: "ADMIN" | "STUDENT" | "FACULTY") => navigationFor(role).flatMap((section) => section.items.map((item) => item.href));
  const PERSONAL = ["/workspace", "/submissions", "/reading-list", "/calendar", "/recommendations", "/peers"];

  it("leaves personal research tools out of the administrator's navigation and account menu", () => {
    for (const href of PERSONAL) expect(labels("ADMIN")).not.toContain(href);
    expect(accountItemsFor("ADMIN").map((item) => item.href)).toEqual(["/settings"]);
  });

  it("keeps platform administration, and discovery", () => {
    for (const href of ["/admin", "/admin/users", "/admin/research-data", "/", "/browse", "/postings"]) expect(labels("ADMIN")).toContain(href);
  });

  it("keeps the tools for students and faculty", () => {
    for (const role of ["STUDENT", "FACULTY"] as const) {
      for (const href of PERSONAL) expect(labels(role)).toContain(href);
      expect(accountItemsFor(role).map((item) => item.href)).toEqual(["/researcher", "/researcher/preferences", "/settings"]);
    }
  });

  it.each(["app/workspace/page.tsx", "app/workspace/[id]/page.tsx", "app/submissions/page.tsx", "app/reading-list/page.tsx", "app/calendar/page.tsx", "app/recommendations/page.tsx", "app/peers/page.tsx", "app/researcher/page.tsx", "app/researcher/preferences/page.tsx"])(
    "%s agrees at its address",
    (file) => {
      expect(readFileSync(path.join(FRONTEND, file), "utf8")).toContain('roles={["STUDENT", "FACULTY"]}');
    }
  );

  it("shows an administrator no Save on a call", async () => {
    storeSession(makeTokenResponse({ user: makeUser({ role: "ADMIN" }) }));
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(makeUser({ role: "ADMIN" }))));
    render(
      <SessionProvider>
        <SaveCallButton opportunityId="11111111-1111-4111-8111-111111111111" />
        <RequireAuth>
          <p>loaded</p>
        </RequireAuth>
      </SessionProvider>
    );
    await screen.findByText("loaded");
    expect(screen.queryByRole("button", { name: /save/i })).not.toBeInTheDocument();
  });
});

describe("FUNC-04: research preferences", () => {
  const PROFILE = { id: "p1", user_id: "u1" };
  const STRUCTURED = {
    raw_preferences: [],
    funding: { funding_required: false, min_funding_amount: null, currency: "USD" },
    academic: { academic_level: null, career_stage: null },
    summary: { has_conflicts: false },
    completeness: { percentage: 20 },
  };

  it("has a plain heading, no developer words, and no inline styles in its source", async () => {
    storeSession(makeTokenResponse());
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url.endsWith("/auth/me")) return jsonResponse(makeUser());
        if (url.includes("/preferences/structured")) return jsonResponse(STRUCTURED);
        return jsonResponse(PROFILE);
      })
    );
    const { PreferencesPage } = await import("../components/preferences/PreferencesPage");
    render(
      <SessionProvider>
        <RequireAuth>
          <PreferencesPage />
        </RequireAuth>
      </SessionProvider>
    );
    expect(await screen.findByRole("heading", { level: 1, name: "Research preferences" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Kinds of opportunity" })).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/Foundation|3-state|\[[A-Z_]+\]/);
    const source = readFileSync(path.join(FRONTEND, "components/preferences/PreferencesPage.tsx"), "utf8");
    expect(source).not.toContain("style={{");
    expect(readFileSync(path.join(FRONTEND, "app/researcher/preferences/page.tsx"), "utf8")).not.toContain("style={{");
  });

  it("offers the same retry when it cannot load", async () => {
    storeSession(makeTokenResponse());
    let up = false;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url.endsWith("/auth/me")) return jsonResponse(makeUser());
        if (!up) return jsonResponse({ detail: "down" }, 500);
        return url.includes("/preferences/structured") ? jsonResponse(STRUCTURED) : jsonResponse(PROFILE);
      })
    );
    const { PreferencesPage } = await import("../components/preferences/PreferencesPage");
    render(
      <SessionProvider>
        <RequireAuth>
          <PreferencesPage />
        </RequireAuth>
      </SessionProvider>
    );
    const retry = await screen.findByRole("button", { name: "Try again" });
    up = true;
    fireEvent.click(retry);
    expect(await screen.findByRole("heading", { name: "Kinds of opportunity" })).toBeInTheDocument();
  });
});

describe("FUNC-11: the dashboard's notifications", () => {
  afterEach(() => publishLatest(null));

  it("reads the bell's answer and makes no request of its own", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    publishLatest({
      unread: 2,
      items: [{ id: "n1", title: "ICIRS is due in 3 days", created_at: "2030-01-01T00:00:00Z", notification_type: "DEADLINE_UPCOMING", source_type: "OPPORTUNITY", metadata_json: {} } as never],
    });
    render(<LatestNotifications />);
    const region = screen.getByRole("region", { name: "Notifications" });
    expect(region).toHaveTextContent("2 unread.");
    expect(region).toHaveTextContent("ICIRS is due in 3 days");
    expect(within(region).getByRole("link", { name: "All notifications" })).toHaveAttribute("href", "/notifications");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("says so when there is nothing, and when it could not be asked", () => {
    publishLatest({ unread: 0, items: [] });
    const { rerender } = render(<LatestNotifications />);
    expect(screen.getByText(/Nothing new/)).toBeInTheDocument();
    act(() => publishLatest({ unread: 0, items: [], failed: true }));
    rerender(<LatestNotifications />);
    expect(screen.getByText(/could not be loaded just now/)).toBeInTheDocument();
  });
});

describe("an unexpected failure on a page", () => {
  it("says so in the shell's own words, with Try again", () => {
    const reset = vi.fn();
    render(<PageError error={new Error("boom")} reset={reset} />);
    expect(screen.getByRole("heading", { level: 1, name: "This page could not be shown" })).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("boom");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(reset).toHaveBeenCalledTimes(1);
  });
});

describe("A11Y-02: an applicant's card while a change is sent", () => {
  const application = {
    id: "a1",
    posting_id: "p1",
    posting_title: "A posting",
    status: "SUBMITTED",
    allowed_transitions: ["WITHDRAWN"],
    status_history: [],
    applicant: { full_name: "Ada", academic_status: null },
    submitted_at: "2030-01-01T00:00:00Z",
    portfolio_url: "javascript:alert(1)",
    is_posting_author: true,
    contact_email: null,
    cover_note: null,
    decision_reason: null,
    reviewer_note: null,
  } as never;

  it("keeps focus on the button that is busy, and says it is unavailable", () => {
    const { rerender } = render(<ApplicationCard application={application} onTransition={vi.fn()} busy={false} />);
    const withdraw = screen.getByRole("button", { name: "Withdrawn" });
    withdraw.focus();
    rerender(<ApplicationCard application={application} onTransition={vi.fn()} busy />);
    expect(screen.getByRole("button", { name: "Withdrawn" })).toHaveFocus();
    expect(screen.getByRole("button", { name: "Withdrawn" })).toHaveAttribute("aria-disabled", "true");
    expect(document.activeElement).not.toBe(document.body);
  });

  it("never makes a link of an applicant's address that is not a web address", () => {
    render(<ApplicationCard application={application} onTransition={vi.fn()} busy={false} />);
    expect(screen.queryByRole("link", { name: "Portfolio" })).not.toBeInTheDocument();
  });
});
