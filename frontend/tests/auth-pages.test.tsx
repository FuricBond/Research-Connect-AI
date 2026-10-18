/**
 * P3 — authentication and the public pages: sign in, registration, Settings → Account, the
 * signed-out landing's line, not-found and the loading state.
 *
 * What the forms must keep (FRONTEND_REDESIGN_PLAN.md §23): the field labels and ids the e2e
 * suite and password managers rely on, the autocomplete attributes, readable errors with
 * role="alert", and the `next` redirect. What P3 adds: a button that is never greyed out, each
 * problem explained at its field with focus moved there, fields that stay focusable while the
 * request runs, and a password field whose show/hide toggle is not a second label.
 */

import React from "react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

const replace = vi.fn();
let pathname = "/login";
let search = new URLSearchParams();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, push: vi.fn(), back: vi.fn(), forward: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => pathname,
  useSearchParams: () => search,
}));

import LoginPage from "../app/login/page";
import RegisterPage from "../app/register/page";
import SettingsRoute from "../app/settings/page";
import NotFound from "../app/not-found";
import Loading from "../app/loading";
import { SessionProvider } from "../components/auth/SessionProvider";
import { RequireAuth } from "../components/auth/RequireAuth";
import { DiscoverySearch } from "../components/pages/DiscoverySearch";
import { getStoredIdentity } from "../services/auth";
import { jsonResponse, makeTokenResponse, makeUser } from "./factories";
import { settingsRoutes } from "./p8-fixtures";
import { installDialogPolyfill, serveShell } from "./shell-support";

beforeAll(installDialogPolyfill);

beforeEach(() => {
  replace.mockClear();
  pathname = "/login";
  search = new URLSearchParams();
  window.history.replaceState(null, "", "/");
});

function renderWithSession(page: React.ReactNode) {
  return render(<SessionProvider>{page}</SessionProvider>);
}

/** A visitor's browser whose sign-in / registration request is answered by `answer`. */
function serveAuth(path: "/api/v1/auth/login" | "/api/v1/auth/register", answer: (init?: RequestInit) => Promise<Response>) {
  return serveShell(null, { other: (url, init) => (url.endsWith(path) ? answer(init) : undefined) });
}

function calls(fetchMock: ReturnType<typeof serveShell>, path: string) {
  return fetchMock.mock.calls.filter(([url]) => String(url).endsWith(path));
}

describe("sign in", () => {
  it("keeps the labels, ids and autocomplete the e2e suite and password managers use", async () => {
    serveAuth("/api/v1/auth/login", () => Promise.resolve(jsonResponse({}, 500)));
    renderWithSession(<LoginPage />);

    expect(await screen.findByRole("heading", { level: 1, name: "Sign in" })).toBeInTheDocument();
    const email = screen.getByLabelText("Email");
    expect(email).toHaveAttribute("id", "login-email");
    expect(email).toHaveAttribute("type", "email");
    expect(email).toHaveAttribute("autocomplete", "email");
    const password = screen.getByLabelText("Password");
    expect(password).toHaveAttribute("id", "login-password");
    expect(password).toHaveAttribute("type", "password");
    expect(password).toHaveAttribute("autocomplete", "current-password");
    // The show/hide toggle is named by its own text, so /password/i still finds one field.
    expect(screen.getAllByLabelText(/password/i)).toHaveLength(1);
    // Never a pale, disabled button before the form is filled (audit P2-9).
    expect(screen.getByRole("button", { name: "Sign in" })).toBeEnabled();
  });

  it("explains a missing entry at its field and moves focus there, without a request", async () => {
    const fetchMock = serveAuth("/api/v1/auth/login", () => Promise.resolve(jsonResponse({}, 500)));
    renderWithSession(<LoginPage />);

    fireEvent.click(await screen.findByRole("button", { name: "Sign in" }));

    const email = screen.getByLabelText("Email");
    expect(email).toHaveAttribute("aria-invalid", "true");
    expect(email).toHaveAccessibleDescription("Enter your email address.");
    expect(email).toHaveFocus();
    expect(screen.getByLabelText("Password")).toHaveAccessibleDescription("Enter your password.");
    expect(calls(fetchMock, "/api/v1/auth/login")).toHaveLength(0);

    // Correcting a field clears its message.
    fireEvent.change(email, { target: { value: "ada@example.test" } });
    expect(email).not.toHaveAttribute("aria-invalid");
  });

  it("shows the backend's refusal as an alert and leaves the form usable", async () => {
    serveAuth("/api/v1/auth/login", () => Promise.resolve(jsonResponse({ detail: "Invalid email or password." }, 401)));
    renderWithSession(<LoginPage />);

    fireEvent.change(await screen.findByLabelText("Email"), { target: { value: "ada@example.test" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "wrong-password" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Email or password is incorrect.");
    expect(screen.getByLabelText("Email")).not.toHaveAttribute("readonly");
    expect(screen.getByRole("button", { name: "Sign in" })).not.toHaveAttribute("aria-busy");
    expect(replace).not.toHaveBeenCalled();
  });

  it("keeps the fields focusable while signing in, then opens the page that was asked for", async () => {
    search = new URLSearchParams("next=/workspace");
    let answer: (response: Response) => void = () => undefined;
    const fetchMock = serveAuth("/api/v1/auth/login", () => new Promise<Response>((resolve) => (answer = resolve)));
    renderWithSession(<LoginPage />);

    fireEvent.change(await screen.findByLabelText("Email"), { target: { value: "  Ada@Example.TEST " } });
    const password = screen.getByLabelText("Password");
    fireEvent.change(password, { target: { value: "correct-password" } });
    password.focus();
    fireEvent.submit(password.closest("form")!);

    // Busy, read-only, not disabled: keyboard focus stays where it was.
    const button = screen.getByRole("button", { name: "Sign in" });
    expect(button).toHaveAttribute("aria-busy", "true");
    expect(password).toHaveAttribute("readonly");
    expect(password).not.toBeDisabled();
    expect(password).toHaveFocus();
    expect(JSON.parse(String((calls(fetchMock, "/api/v1/auth/login")[0][1] as RequestInit).body))).toEqual({
      email: "ada@example.test",
      password: "correct-password",
    });

    await act(async () => answer(jsonResponse(makeTokenResponse())));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/workspace"));
    expect(getStoredIdentity().token).toBe("header.payload.signature");
    // The form gives way while the page opens.
    expect(screen.getByRole("status")).toHaveTextContent("You're signed in. Opening your page…");
    expect(screen.queryByLabelText("Email")).not.toBeInTheDocument();
  });

  it("sends somebody already signed in on, without showing them the form", async () => {
    search = new URLSearchParams("next=/reading-list");
    serveShell("STUDENT");
    renderWithSession(<LoginPage />);

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/reading-list"));
    expect(screen.queryByRole("button", { name: "Sign in" })).not.toBeInTheDocument();
  });

  it("shows the password on request, and says whether it is shown", async () => {
    serveAuth("/api/v1/auth/login", () => Promise.resolve(jsonResponse({}, 500)));
    renderWithSession(<LoginPage />);

    const toggle = await screen.findByRole("button", { name: "Show password" });
    const password = screen.getByLabelText("Password");
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    expect(toggle).toHaveAttribute("aria-controls", "login-password");
    fireEvent.click(toggle);
    expect(password).toHaveAttribute("type", "text");
    expect(toggle).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(toggle);
    expect(password).toHaveAttribute("type", "password");
  });

  it("links to registration, keeping where the person was going", async () => {
    search = new URLSearchParams("next=/workspace");
    serveAuth("/api/v1/auth/login", () => Promise.resolve(jsonResponse({}, 500)));
    renderWithSession(<LoginPage />);

    expect(await screen.findByRole("link", { name: "Create an account" })).toHaveAttribute("href", "/register?next=%2Fworkspace");
  });
});

describe("registration", () => {
  async function fill(values: Partial<Record<"name" | "email" | "password" | "confirm", string>>) {
    if (values.name !== undefined) fireEvent.change(await screen.findByLabelText("Full name"), { target: { value: values.name } });
    if (values.email !== undefined) fireEvent.change(screen.getByLabelText("Email"), { target: { value: values.email } });
    if (values.password !== undefined) fireEvent.change(screen.getByLabelText("Password"), { target: { value: values.password } });
    if (values.confirm !== undefined) fireEvent.change(screen.getByLabelText("Confirm password"), { target: { value: values.confirm } });
  }

  it("keeps the ids, autocomplete and self-service roles", async () => {
    serveAuth("/api/v1/auth/register", () => Promise.resolve(jsonResponse({}, 500)));
    renderWithSession(<RegisterPage />);

    expect(await screen.findByRole("heading", { level: 1, name: "Create an account" })).toBeInTheDocument();
    expect(screen.getByLabelText("Full name")).toHaveAttribute("id", "register-name");
    expect(screen.getByLabelText("Email")).toHaveAttribute("id", "register-email");
    expect(screen.getByLabelText("Password")).toHaveAttribute("id", "register-password");
    expect(screen.getByLabelText("Password")).toHaveAttribute("autocomplete", "new-password");
    expect(screen.getByLabelText("Confirm password")).toHaveAttribute("id", "register-confirm");
    const role = screen.getByLabelText("Account type");
    expect(role).toHaveAttribute("id", "register-role");
    // ADMIN is granted by an administrator, never chosen here.
    expect(within(role).getAllByRole("option").map((o) => (o as HTMLOptionElement).value)).toEqual(["STUDENT", "FACULTY"]);
    expect(screen.getByRole("button", { name: "Create account" })).toBeEnabled();
  });

  it("explains every missing entry at its field and focuses the first, without a request", async () => {
    const fetchMock = serveAuth("/api/v1/auth/register", () => Promise.resolve(jsonResponse({}, 500)));
    renderWithSession(<RegisterPage />);

    fireEvent.click(await screen.findByRole("button", { name: "Create account" }));

    expect(screen.getByLabelText("Full name")).toHaveAccessibleDescription("Enter your full name.");
    expect(screen.getByLabelText("Full name")).toHaveFocus();
    expect(screen.getByLabelText("Email")).toHaveAccessibleDescription(/Enter your email address\./);
    expect(screen.getByLabelText("Password")).toHaveAccessibleDescription(/Enter a password\./);
    expect(screen.getByLabelText("Confirm password")).toHaveAccessibleDescription("Enter the password again.");
    expect(calls(fetchMock, "/api/v1/auth/register")).toHaveLength(0);
  });

  it("applies the backend's password rules before a round trip", async () => {
    const fetchMock = serveAuth("/api/v1/auth/register", () => Promise.resolve(jsonResponse({}, 500)));
    renderWithSession(<RegisterPage />);
    const submit = async () => fireEvent.click(await screen.findByRole("button", { name: "Create account" }));

    await fill({ name: "Ada Lovelace", email: "not-an-email", password: "short", confirm: "short" });
    await submit();
    expect(screen.getByLabelText("Email")).toHaveAccessibleDescription(/Enter an email address like name@university\.edu\./);
    expect(screen.getByLabelText("Email")).toHaveFocus();
    expect(screen.getByLabelText("Password")).toHaveAccessibleDescription(/Password must be at least 8 characters\./);

    await fill({ email: "ada@example.test", password: " spaced-out ", confirm: " spaced-out " });
    await submit();
    expect(screen.getByLabelText("Password")).toHaveAccessibleDescription(/must not start or end with a space/);

    await fill({ password: "é".repeat(40), confirm: "é".repeat(40) });
    await submit();
    expect(screen.getByLabelText("Password")).toHaveAccessibleDescription(/at most 72 bytes/);

    await fill({ password: "a-long-enough-password", confirm: "another-password" });
    await submit();
    expect(screen.getByLabelText("Confirm password")).toHaveAccessibleDescription("The two passwords do not match.");
    expect(screen.getByLabelText("Confirm password")).toHaveFocus();
    expect(calls(fetchMock, "/api/v1/auth/register")).toHaveLength(0);
  });

  it("creates the account with what was entered and opens the page that was asked for", async () => {
    search = new URLSearchParams("next=/postings");
    const fetchMock = serveAuth("/api/v1/auth/register", () =>
      Promise.resolve(jsonResponse(makeTokenResponse({ user: makeUser({ role: "FACULTY" }) }), 201))
    );
    renderWithSession(<RegisterPage />);

    await fill({ name: "  Ada Lovelace ", email: "Ada@Example.TEST", password: "a-long-enough-password", confirm: "a-long-enough-password" });
    fireEvent.change(screen.getByLabelText("Account type"), { target: { value: "FACULTY" } });
    fireEvent.change(screen.getByLabelText("Institution (optional)"), { target: { value: "Analytical Engine College" } });
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/postings"));
    expect(JSON.parse(String((calls(fetchMock, "/api/v1/auth/register")[0][1] as RequestInit).body))).toEqual({
      full_name: "Ada Lovelace",
      email: "ada@example.test",
      password: "a-long-enough-password",
      role: "FACULTY",
      institution_name: "Analytical Engine College",
    });
  });

  it("says when the email is already registered", async () => {
    serveAuth("/api/v1/auth/register", () => Promise.resolve(jsonResponse({ detail: "Email already registered." }, 409)));
    renderWithSession(<RegisterPage />);

    await fill({ name: "Ada Lovelace", email: "ada@example.test", password: "a-long-enough-password", confirm: "a-long-enough-password" });
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("An account with this email already exists. Try signing in instead.");
    expect(replace).not.toHaveBeenCalled();
  });

  it("names each password toggle after its field", async () => {
    serveAuth("/api/v1/auth/register", () => Promise.resolve(jsonResponse({}, 500)));
    renderWithSession(<RegisterPage />);

    expect(await screen.findByRole("button", { name: "Show password" })).toHaveAttribute("aria-controls", "register-password");
    expect(screen.getByRole("button", { name: "Show password confirmation" })).toHaveAttribute("aria-controls", "register-confirm");
  });
});

describe("settings", () => {
  it("has the account, notification and appearance sections, with a way to each", async () => {
    pathname = "/settings";
    serveShell("FACULTY", { other: settingsRoutes({}) });
    renderWithSession(<SettingsRoute />);

    expect(await screen.findByRole("heading", { level: 1, name: "Settings" })).toBeInTheDocument();
    const account = screen.getByRole("region", { name: "Account" });
    expect(within(account).getByText("Ada Lovelace")).toBeInTheDocument();
    expect(within(account).getByText(makeUser().email)).toBeInTheDocument();
    expect(within(account).getByText("Faculty")).toBeInTheDocument();
    expect(within(account).getByRole("form", { name: "Change password" })).toBeInTheDocument();
    // P8: the notification settings and the theme are sections of this page.
    const toc = screen.getByRole("navigation", { name: "On this page" });
    expect(within(toc).getAllByRole("link").map((link) => link.getAttribute("href"))).toEqual(["#account", "#notifications", "#appearance"]);
    const notifications = screen.getByRole("region", { name: "Notifications" });
    expect(notifications).toHaveAttribute("id", "notifications");
    expect(await within(notifications).findByRole("switch", { name: "Email alerts" })).toBeInTheDocument();
    const appearance = screen.getByRole("region", { name: "Appearance" });
    expect(within(appearance).getByRole("group", { name: "Colour theme" })).toBeInTheDocument();
  });

  it("is for signed-in accounts: a visitor is sent to sign in and back", async () => {
    pathname = "/settings";
    serveShell(null);
    renderWithSession(<SettingsRoute />);

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login?next=%2Fsettings"));
    expect(screen.queryByRole("form", { name: "Change password" })).not.toBeInTheDocument();
  });
});

describe("guard states", () => {
  it("offers the way home when an account may not see a page", async () => {
    serveShell("STUDENT");
    renderWithSession(
      <RequireAuth roles={["ADMIN"]}>
        <p>Protected content</p>
      </RequireAuth>
    );

    const denial = await screen.findByRole("alert");
    expect(within(denial).getByRole("heading", { level: 1 })).toHaveTextContent("This page is for Administrator accounts.");
    expect(within(denial).getByRole("link", { name: "Go to home" })).toHaveAttribute("href", "/dashboard");
  });
});

describe("the signed-out landing", () => {
  it("tells a visitor what searching needs and what an account adds", async () => {
    pathname = "/";
    serveShell(null);
    renderWithSession(<DiscoverySearch />);

    const intro = await screen.findByText(/Searching is open to everyone\./);
    expect(within(intro).getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login");
    expect(within(intro).getByRole("link", { name: "create an account" })).toHaveAttribute("href", "/register");
    expect(screen.getByRole("searchbox", { name: "Search research literature" })).toBeInTheDocument();
  });

  it("does not repeat it to a signed-in account", async () => {
    pathname = "/";
    serveShell("STUDENT");
    renderWithSession(<DiscoverySearch />);

    expect(await screen.findByText("Begin your literature search")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText(/Searching is open to everyone\./)).not.toBeInTheDocument());
  });
});

describe("not found and loading", () => {
  it("names the missing page in the page's one heading and leads back to search", () => {
    render(<NotFound />);
    expect(screen.getByRole("heading", { level: 1, name: "Page not found" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to search" })).toHaveAttribute("href", "/");
  });

  it("announces loading once, in plain words", () => {
    render(<Loading />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading…");
  });
});
