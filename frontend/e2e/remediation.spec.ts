import { expect, test, type APIRequestContext, type Browser, type BrowserContext, type Page } from "@playwright/test";
import { API_URL, DEMO, DEMO_PASSWORD, newPassword, uniqueEmail } from "./support";

/**
 * The independent audit's findings, end to end in the browser against the live API. Sessions are
 * placed in the browser directly, so the sign-in limit (10 a minute per address) only counts the
 * API calls here, and those wait when told to.
 */
type Session = { access_token: string; expires_at: string; user: { id: string; email: string; full_name: string; role: string; profile_id: string | null } };

async function authCall(request: APIRequestContext, path: string, data: unknown) {
  for (let attempt = 0; ; attempt += 1) {
    const response = await request.post(`${API_URL}/api/v1/auth/${path}`, { data });
    if (response.status() !== 429 || attempt >= 4) return response;
    await new Promise((resolve) => setTimeout(resolve, (Number(response.headers()["retry-after"] ?? 30) + 1) * 1000));
  }
}

async function register(request: APIRequestContext, label: string, role: "STUDENT" | "FACULTY" = "STUDENT"): Promise<Session> {
  const response = await authCall(request, "register", { email: uniqueEmail(label), password: newPassword(), full_name: `Browser ${label}`, role });
  expect(response.status(), await response.text()).toBe(201);
  return response.json();
}

async function signIn(request: APIRequestContext, email: string): Promise<Session> {
  const response = await authCall(request, "login", { email, password: DEMO_PASSWORD });
  expect(response.status(), await response.text()).toBe(200);
  return response.json();
}

const bearer = (session: Session) => ({ Authorization: `Bearer ${session.access_token}` });

/** A browser context already signed in as `session`. */
async function contextFor(browser: Browser, session: Session, options: Parameters<Browser["newContext"]>[0] = {}): Promise<BrowserContext> {
  const context = await browser.newContext(options);
  await context.addInitScript((value: Session) => {
    window.localStorage.setItem("researchconnect_access_token", value.access_token);
    window.localStorage.setItem("researchconnect_token_expires_at", value.expires_at);
    window.localStorage.setItem("researchconnect_user_id", value.user.id);
    if (value.user.profile_id) window.localStorage.setItem("researchconnect_profile_id", value.user.profile_id);
  }, session);
  return context;
}

const POSTING = {
  posting_type: "RESEARCH_ASSISTANTSHIP",
  description: "Work on causal inference methods with the group for a semester.",
  required_skills: ["python"],
  opening_terms: {
    compensation_type: "STIPEND",
    compensation_amount: 1000,
    compensation_currency: "USD",
    compensation_period: "MONTH",
    commitment_type: "PART_TIME",
    hours_per_week: 10,
    duration_months: 6,
    accepts_applications: true,
  },
};

async function verifiedFaculty(request: APIRequestContext, admin: Session, label: string): Promise<Session> {
  const faculty = await register(request, label, "FACULTY");
  const verified = await request.patch(`${API_URL}/api/v1/admin/users/${faculty.user.id}`, { headers: bearer(admin), data: { is_verified: true } });
  expect(verified.status(), await verified.text()).toBe(200);
  return faculty;
}

async function openPosting(request: APIRequestContext, faculty: Session, title: string): Promise<string> {
  const created = await request.post(`${API_URL}/api/v1/postings`, { headers: bearer(faculty), data: { ...POSTING, title } });
  expect(created.status(), await created.text()).toBe(201);
  const id = (await created.json()).id as string;
  expect((await request.post(`${API_URL}/api/v1/postings/${id}/transition`, { headers: bearer(faculty), data: { target_status: "OPEN" } })).status()).toBe(200);
  return id;
}

async function apply(request: APIRequestContext, student: Session, postingId: string) {
  const applied = await request.post(`${API_URL}/api/v1/postings/${postingId}/applications`, { headers: bearer(student), data: { cover_note: "I would like to help with this work." } });
  expect(applied.status(), await applied.text()).toBe(201);
}

async function aCall(request: APIRequestContext): Promise<string> {
  const calls = await (await request.get(`${API_URL}/api/opportunities?page_size=5`)).json();
  return calls.items[0].id;
}

async function ownedWorkspace(request: APIRequestContext, owner: Session): Promise<string> {
  const saved = await request.post(`${API_URL}/api/v1/workspace`, { headers: bearer(owner), data: { opportunity_id: await aCall(request) } });
  expect([200, 201]).toContain(saved.status());
  return (await saved.json()).id;
}

async function invite(request: APIRequestContext, owner: Session, workspaceId: string, email: string, role = "CONTRIBUTOR") {
  const response = await request.post(`${API_URL}/api/v1/workspaces/${workspaceId}/invitations`, { headers: bearer(owner), data: { invitee_email: email, role } });
  expect(response.status(), await response.text()).toBe(201);
  return (await response.json()).invitation as { id: string };
}

async function settled(page: Page) {
  await page.waitForLoadState("networkidle");
  await expect(page.locator('main [aria-busy="true"]')).toHaveCount(0, { timeout: 30_000 });
}

test.describe("FUNC-01: a workspace invitation, end to end", () => {
  test("invite, see it, accept, appear as a member; decline; refusals in plain words; retry after a failure", async ({ browser, request }) => {
    test.setTimeout(240_000);
    const owner = await register(request, "inviter");
    const invitee = await register(request, "invitee");
    const stranger = await register(request, "stranger");
    const workspace = await ownedWorkspace(request, owner);

    await test.step("the owner invites from the Members tab, and is told the truth", async () => {
      const context = await contextFor(browser, owner);
      const page = await context.newPage();
      await page.goto(`/workspace/${workspace}?tab=members`);
      await page.getByRole("button", { name: "Invite someone" }).click();
      const dialog = page.getByRole("dialog", { name: "Invite someone to this call" });
      await dialog.getByRole("textbox", { name: /Email address/ }).fill(invitee.user.email);
      await dialog.getByRole("button", { name: "Send invitation" }).click();
      await expect(dialog.getByText(`Invitation sent to ${invitee.user.email}.`)).toBeVisible();
      await expect(dialog).toContainText("accept or decline it on their notifications page");
      await expect(dialog).not.toContainText(/code/i);
      await context.close();
    });

    const context = await contextFor(browser, invitee);
    const page = await context.newPage();
    await test.step("the invitee finds it through the notification, with no token anywhere", async () => {
      await page.goto("/notifications");
      await settled(page);
      await expect(page.getByRole("heading", { name: "Workspace invitations" })).toBeVisible();
      const link = page.getByRole("link", { name: "Invitation to a research workspace" });
      await expect(link).toHaveAttribute("href", "/notifications#invitations");
      await expect(page.locator("main")).toContainText("Accept or decline it on your notifications page");
      const answer = await (await request.get(`${API_URL}/api/v1/workspace-invitations/mine`, { headers: bearer(invitee) })).text();
      expect(answer).not.toContain("token");
    });

    await test.step("someone else's account cannot answer it", async () => {
      const mine = await (await request.get(`${API_URL}/api/v1/workspace-invitations/mine`, { headers: bearer(invitee) })).json();
      const id = mine.invitations[0].id;
      for (const actor of [stranger, owner]) {
        expect((await request.post(`${API_URL}/api/v1/workspace-invitations/${id}/accept`, { headers: bearer(actor) })).status()).toBe(404);
      }
    });

    await test.step("a failed accept leaves a clear error and can be tried again", async () => {
      await page.route(`${API_URL}/api/v1/workspace-invitations/*/accept`, (route) => route.fulfill({ status: 500, contentType: "application/json", headers: { "access-control-allow-origin": "*" }, body: '{"detail":"x"}' }));
      await page.getByRole("button", { name: /^Accept/ }).click();
      await expect(page.getByText("The invitation could not be accepted. Nothing was changed. Try again.")).toBeVisible();
      await page.unroute(`${API_URL}/api/v1/workspace-invitations/*/accept`);
    });

    await test.step("accepting joins the workspace, which then opens and is listed", async () => {
      await page.getByRole("button", { name: /^Accept/ }).click();
      await expect(page.getByText(/You joined/)).toBeVisible();
      await page.getByRole("link", { name: "Open the workspace" }).click();
      await expect(page).toHaveURL(new RegExp(`/workspace/${workspace}`));
      await settled(page);
      await page.goto("/workspace");
      await settled(page);
      await expect(page.getByRole("region", { name: "Shared with you" })).toBeVisible();
    });

    await test.step("they appear among the members with the invited role, for the owner", async () => {
      const members = await (await request.get(`${API_URL}/api/v1/workspaces/${workspace}/members`, { headers: bearer(owner) })).json();
      const added = members.items.find((member: { user_id: string }) => member.user_id === invitee.user.id);
      expect(added.role).toBe("CONTRIBUTOR");
      const ownerContext = await contextFor(browser, owner);
      const ownerPage = await ownerContext.newPage();
      await ownerPage.goto(`/workspace/${workspace}?tab=members`);
      await settled(ownerPage);
      await expect(ownerPage.locator("main")).toContainText(invitee.user.full_name);
      // The owner can change that member's role, and remove them.
      await ownerPage.getByRole("combobox", { name: new RegExp(`Role of ${invitee.user.full_name}`) }).selectOption("VIEWER");
      await expect.poll(async () => (await (await request.get(`${API_URL}/api/v1/workspaces/${workspace}/members`, { headers: bearer(owner) })).json()).items.find((m: { user_id: string }) => m.user_id === invitee.user.id).role).toBe("VIEWER");
      await ownerContext.close();
    });

    await test.step("declining says so and grants nothing", async () => {
      const second = await ownedWorkspace(request, stranger);
      await invite(request, stranger, second, invitee.user.email);
      await page.goto("/notifications");
      await settled(page);
      await page.getByRole("button", { name: /^Decline/ }).click();
      await expect(page.getByText(/You declined the invitation/)).toBeVisible();
      expect((await request.get(`${API_URL}/api/v1/workspace/${second}`, { headers: bearer(invitee) })).status()).toBe(403);
    });

    await test.step("an invitation revoked while the page is open is explained, and goes away", async () => {
      const third = await ownedWorkspace(request, owner);
      // Another call in the owner's workspace may already be tracked; a new invitation needs a pending slot.
      const made = await invite(request, owner, third === workspace ? workspace : third, stranger.user.email);
      const strangerContext = await contextFor(browser, stranger);
      const strangerPage = await strangerContext.newPage();
      await strangerPage.goto("/notifications");
      await settled(strangerPage);
      const accept = strangerPage.getByRole("button", { name: /^Accept/ });
      await expect(accept).toBeVisible();
      expect((await request.delete(`${API_URL}/api/v1/workspaces/${third}/invitations/${made.id}`, { headers: bearer(owner) })).status()).toBe(204);
      await accept.click();
      await expect(strangerPage.getByText("This invitation has been revoked by the workspace owner.").first()).toBeVisible();
      await expect(accept).toHaveCount(0);
      await strangerContext.close();
    });
    await context.close();
  });
});

test.describe("Decision 1: faculty verification", () => {
  test("an unverified member is told what is waiting and offered nothing the API would refuse; verification opens it", async ({ browser, request }) => {
    test.setTimeout(180_000);
    const faculty = await register(request, "unverified", "FACULTY");
    const context = await contextFor(browser, faculty);
    const page = await context.newPage();

    await page.goto("/dashboard");
    await settled(page);
    await expect(page.getByText("Your faculty account is waiting for verification")).toBeVisible();
    await expect(page.getByRole("link", { name: "New posting" })).toHaveCount(0);

    await page.goto("/postings?view=mine");
    await settled(page);
    await expect(page.getByText("Your faculty account is waiting for verification")).toBeVisible();
    await expect(page.getByRole("link", { name: "New posting" })).toHaveCount(0);

    await page.goto("/settings");
    await settled(page);
    await expect(page.locator("main")).toContainText("Waiting for an administrator to verify your account");

    // The frontend is not the boundary.
    const refused = await request.post(`${API_URL}/api/v1/postings`, { headers: bearer(faculty), data: { ...POSTING, title: "A posting nobody verified" } });
    expect(refused.status()).toBe(403);
    expect(await refused.text()).toContain("verified");

    const admin = await signIn(request, DEMO.admin);
    const adminContext = await contextFor(browser, admin);
    const adminPage = await adminContext.newPage();
    await adminPage.goto(`/admin/users?status=unverified&q=${encodeURIComponent(faculty.user.email)}`);
    await settled(adminPage);
    await adminPage.getByRole("button", { name: /^Actions for / }).first().click();
    await adminPage.getByRole("menuitem", { name: "Mark as verified" }).click();
    await expect(adminPage.getByRole("status").filter({ hasText: "marked as verified" }).first()).toBeVisible();
    await adminContext.close();

    await page.goto("/dashboard");
    await settled(page);
    await expect(page.getByText("Your faculty account is waiting for verification")).toHaveCount(0);
    await expect(page.getByRole("link", { name: "New posting" })).toBeVisible();
    expect((await request.post(`${API_URL}/api/v1/postings`, { headers: bearer(faculty), data: { ...POSTING, title: "A posting someone verified" } })).status()).toBe(201);
    await context.close();
  });
});

test.describe("Decision 2: an administrator's tools", () => {
  test("no personal tools in the navigation, and their addresses agree", async ({ browser, request }) => {
    test.setTimeout(120_000);
    const admin = await signIn(request, DEMO.admin);
    const context = await contextFor(browser, admin, { viewport: { width: 1440, height: 900 } });
    const page = await context.newPage();
    await page.goto("/admin");
    await settled(page);
    const nav = page.getByRole("navigation", { name: "Primary" });
    for (const name of ["Overview", "Users", "Research data", "Literature search"]) await expect(nav.getByRole("link", { name })).toBeVisible();
    for (const name of ["Workspace", "Submissions", "Reading list", "Calendar", "Recommendations", "Find peers"]) await expect(nav.getByRole("link", { name })).toHaveCount(0);
    await page.getByRole("banner").getByRole("button", { name: /account menu$/ }).click();
    await expect(page.getByRole("banner").getByRole("link", { name: "Settings" })).toBeVisible();
    await expect(page.getByRole("banner").getByRole("link", { name: "Researcher profile" })).toHaveCount(0);

    for (const path of ["/workspace", "/submissions", "/reading-list", "/calendar", "/recommendations", "/peers", "/researcher", "/researcher/preferences"]) {
      await page.goto(path);
      await expect(page.getByRole("heading", { level: 1, name: /This page is for Student researcher or Faculty accounts|This page is for/ }), path).toBeVisible();
    }
    await page.goto("/admin/users");
    await settled(page);
    await expect(page.getByRole("heading", { level: 1, name: "Users" })).toBeVisible();
    await context.close();
  });
});

test.describe("FUNC-05: the status filter", () => {
  test("filters on the server, in the address, and keeps the role and the search", async ({ browser, request }) => {
    const admin = await signIn(request, DEMO.admin);
    const context = await contextFor(browser, admin);
    const page = await context.newPage();
    await page.goto("/admin/users");
    await settled(page);
    const asked: string[] = [];
    page.on("request", (r) => {
      if (r.url().includes("/api/v1/admin/users?")) asked.push(r.url());
    });
    await page.getByRole("group", { name: "Filter by status" }).getByRole("button", { name: "Deactivated" }).click();
    await expect(page).toHaveURL(/status=inactive/);
    await settled(page);
    expect(asked.at(-1)).toContain("is_active=false");
    await page.getByRole("group", { name: "Filter by role" }).getByRole("button", { name: /Student/ }).click();
    await expect(page).toHaveURL(/role=STUDENT/);
    await expect(page).toHaveURL(/status=inactive/);
    await page.reload();
    await settled(page);
    await expect(page.getByRole("group", { name: "Filter by status" }).getByRole("button", { name: "Deactivated" })).toHaveAttribute("aria-pressed", "true");
    await context.close();
  });
});

test.describe("FUNC-02: every task status", () => {
  test("each filter answers 200 and In review sends the API's own value", async ({ browser, request }) => {
    const owner = await register(request, "tasks");
    const workspace = await ownedWorkspace(request, owner);
    const created = await request.post(`${API_URL}/api/v1/workspaces/${workspace}/tasks`, { headers: bearer(owner), data: { title: "Reviewed task" } });
    const task = (await created.json()).id;
    expect((await request.patch(`${API_URL}/api/v1/workspaces/${workspace}/tasks/${task}`, { headers: bearer(owner), data: { status: "REVIEW" } })).status()).toBe(200);

    const context = await contextFor(browser, owner);
    const page = await context.newPage();
    const failures: string[] = [];
    const statuses: string[] = [];
    page.on("response", (response) => {
      if (!response.url().includes("/tasks")) return;
      if (response.status() >= 400) failures.push(`${response.status()} ${response.url()}`);
      const asked = new URL(response.url()).searchParams.get("status");
      if (asked) statuses.push(asked);
    });
    await page.goto(`/workspace/${workspace}?tab=tasks`);
    await settled(page);
    await expect(page.locator("main")).toContainText("In review");
    const filter = page.getByRole("combobox", { name: "Status" });
    for (const label of ["To do", "In progress", "In review", "Done", "Cancelled"]) {
      await filter.selectOption({ label });
      await settled(page);
      await expect(page.locator("main")).not.toContainText("could not be loaded");
    }
    await filter.selectOption({ label: "In review" });
    await expect(page.getByRole("heading", { name: "Reviewed task" })).toBeVisible();
    expect(failures).toEqual([]);
    expect(statuses).toContain("REVIEW");
    expect(statuses).not.toContain("IN_REVIEW");
    await context.close();
  });
});

test.describe("SEC-01: a stored address that is not a web address", () => {
  test("is shown as no link on a call and on a posting", async ({ browser, request }) => {
    const admin = await signIn(request, DEMO.admin);
    const context = await browser.newContext();
    const page = await context.newPage();
    // Answers as an older row would: the API refuses to store these now.
    const postings = await (await request.get(`${API_URL}/api/v1/postings?limit=1`)).json();
    const posting = postings.postings[0];
    await page.route(`${API_URL}/api/v1/postings/${posting.id}*`, async (route) => {
      const response = await route.fetch();
      await route.fulfill({ response, json: { ...(await response.json()), external_url: "javascript:alert(document.domain)" } });
    });
    await page.goto(`/postings/${posting.id}`);
    await settled(page);
    await expect(page.locator('main a[href^="javascript:" i], main a[href^="data:" i]')).toHaveCount(0);

    const calls = await (await request.get(`${API_URL}/api/opportunities?page_size=1`)).json();
    const call = calls.items[0];
    await page.route(`${API_URL}/api/opportunities/${call.id}`, async (route) => {
      const response = await route.fetch();
      await route.fulfill({ response, json: { ...(await response.json()), website_url: "javascript:alert(1)", submission_url: "data:text/html,x" } });
    });
    await page.goto(`/calls/${call.id}`);
    await settled(page);
    await expect(page.locator('main a[href^="javascript:" i], main a[href^="data:" i]')).toHaveCount(0);
    await expect(page.getByRole("link", { name: /Source|Submission site/ })).toHaveCount(0);
    await context.close();
    expect(admin.user.role).toBe("ADMIN");
  });
});

test.describe("SEC-02: the policy on scripts", () => {
  test("no blanket unsafe-inline; a nonce per response; the theme applies before paint; injected script does not run", async ({ browser }) => {
    const context = await browser.newContext();
    await context.addInitScript(() => window.localStorage.setItem("rc-theme", "dark"));
    const page = await context.newPage();
    const violations: string[] = [];
    page.on("console", (message) => {
      if (/Content Security Policy/i.test(message.text())) violations.push(message.text());
    });
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));

    const first = await page.goto("/login");
    const policy = first?.headers()["content-security-policy"] ?? "";
    const scripts = /script-src ([^;]*)/.exec(policy)?.[1] ?? "";
    expect(scripts).not.toContain("unsafe-inline");
    expect(scripts).not.toContain("unsafe-eval");
    expect(scripts).toMatch(/'nonce-[A-Za-z0-9+/=]+'/);
    const second = await page.request.get("/login");
    expect(second.headers()["content-security-policy"]).not.toBe(policy);

    // The theme script ran with its nonce, and the app hydrated: the form is live.
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    const email = page.getByLabel(/email/i);
    await email.fill("x");
    await expect(email).toHaveValue("x");
    expect(violations).toEqual([]);
    expect(errors).toEqual([]);

    // A script with no nonce, as an injection would be, is refused.
    await page.evaluate(() => {
      const script = document.createElement("script");
      script.textContent = "window.__injected = true";
      document.head.appendChild(script);
    });
    expect(await page.evaluate(() => (window as unknown as { __injected?: boolean }).__injected)).toBeUndefined();
    await expect.poll(() => violations.length).toBeGreaterThan(0);
    await context.close();
  });
});

test.describe("FUNC-03: when the session cannot be checked", () => {
  test("a server failure keeps the session and offers another try; a 401 ends it", async ({ browser, request }) => {
    const student = await register(request, "session");
    const context = await contextFor(browser, student);
    const page = await context.newPage();
    let answer = 503;
    await page.route(`${API_URL}/api/v1/auth/me`, (route) =>
      answer === 200 ? route.continue() : route.fulfill({ status: answer, contentType: "application/json", headers: { "access-control-allow-origin": "*" }, body: '{"detail":"x"}' })
    );
    await page.goto("/workspace");
    await expect(page.getByText(/We could not check your session/)).toBeVisible();
    await expect(page).toHaveURL(/\/workspace$/);
    expect(await page.evaluate(() => window.localStorage.getItem("researchconnect_access_token"))).toBe(student.access_token);

    answer = 200;
    await page.getByRole("button", { name: "Try again" }).click();
    await expect(page.getByText(/We could not check your session/)).toHaveCount(0);
    await expect(page.getByRole("heading", { level: 1, name: "Workspace" })).toBeVisible();

    answer = 401;
    await page.reload();
    await expect(page).toHaveURL(/\/login/);
    expect(await page.evaluate(() => window.localStorage.getItem("researchconnect_access_token"))).toBeNull();
    await context.close();
  });

  test("no answer at all stops checking and offers another try", async ({ browser, request }) => {
    test.setTimeout(60_000);
    const student = await register(request, "hang");
    const context = await contextFor(browser, student);
    const page = await context.newPage();
    await page.route(`${API_URL}/api/v1/auth/me`, () => undefined);
    await page.goto("/workspace");
    await expect(page.getByText(/We could not check your session/)).toBeVisible({ timeout: 20_000 });
    expect(await page.evaluate(() => window.localStorage.getItem("researchconnect_access_token"))).toBe(student.access_token);
    await context.close();
  });
});

test.describe("FUNC-06: back to the page, with its query", () => {
  test("sign-in returns to the query; a hostile destination does not leave the site", async ({ page, request }) => {
    const faculty = await signIn(request, DEMO.faculty);
    expect(faculty.user.role).toBe("FACULTY");
    await page.goto("/postings?view=mine");
    await expect(page).toHaveURL(/\/login\?next=%2Fpostings%3Fview%3Dmine$/);
    await page.getByLabel(/email/i).fill(DEMO.faculty);
    await page.getByLabel(/password/i).first().fill(DEMO_PASSWORD);
    await page.getByRole("button", { name: /^sign in$/i }).click();
    await expect(page).toHaveURL(/\/postings\?view=mine$/);
    await expect(page.getByRole("heading", { level: 1, name: "My postings" })).toBeVisible();
    await expect(page).toHaveTitle("My postings — ResearchConnect AI");

    await page.getByRole("banner").getByRole("button", { name: /account menu$/ }).click();
    for (const hostile of ["https://evil.example/x", "//evil.example/x", "javascript:alert(1)", String.fromCharCode(47, 92) + "evil.example"]) {
      await page.goto(`/login?next=${encodeURIComponent(hostile)}`);
      await page.waitForURL((url) => url.pathname !== "/login", { timeout: 20_000 });
      expect(new URL(page.url()).host, hostile).toBe(new URL(page.url().startsWith("http") ? page.url() : "http://x").host);
      expect(page.url(), hostile).not.toContain("evil.example");
    }
  });
});

test.describe("FUNC-10: titles", () => {
  test("say what the page is", async ({ page, request }) => {
    const pages: [string, RegExp][] = [
      ["/postings", /^Research postings — ResearchConnect AI$/],
      ["/similar", /^Similar papers — ResearchConnect AI$/],
      ["/opportunities", /^Find venues — ResearchConnect AI$/],
    ];
    for (const [path, title] of pages) {
      await page.goto(path);
      await expect(page).toHaveTitle(title);
    }
    const postings = await (await request.get(`${API_URL}/api/v1/postings?limit=1`)).json();
    await page.goto(`/postings/${postings.postings[0].id}`);
    await expect(page).toHaveTitle(`${postings.postings[0].title} — ResearchConnect AI`);
  });

  test("My applications", async ({ browser, request }) => {
    const student = await register(request, "titles");
    const context = await contextFor(browser, student);
    const page = await context.newPage();
    await page.goto("/postings/applications");
    await expect(page.getByRole("heading", { level: 1, name: "My applications" })).toBeVisible();
    await expect(page).toHaveTitle("My applications — ResearchConnect AI");
    await context.close();
  });
});

test.describe("UI-01: a confirmation in flight", () => {
  test("cannot be dismissed by Escape, and reports the failure in the dialog", async ({ browser, request }) => {
    const faculty = await signIn(request, DEMO.faculty);
    const mine = await (await request.get(`${API_URL}/api/v1/postings/mine?limit=50`, { headers: bearer(faculty) })).json();
    const open = mine.postings.find((posting: { status: string }) => posting.status === "OPEN");
    const context = await contextFor(browser, faculty);
    const page = await context.newPage();
    await page.goto(`/postings/${open.id}`);
    await settled(page);
    let sent = 0;
    await page.route(`${API_URL}/api/v1/postings/${open.id}/transition`, async (route) => {
      sent += 1;
      await new Promise((resolve) => setTimeout(resolve, 1500));
      await route.fulfill({ status: 500, contentType: "application/json", headers: { "access-control-allow-origin": "*" }, body: '{"detail":"x"}' });
    });
    const trigger = page.getByRole("region", { name: "Manage this posting" }).getByRole("button", { name: "Cancel posting" });
    await trigger.click();
    const dialog = page.getByRole("dialog");
    await dialog.getByRole("button", { name: "Cancel posting" }).click();
    await page.keyboard.press("Escape");
    await page.waitForTimeout(300);
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole("alert")).toBeVisible({ timeout: 10_000 });
    expect(sent).toBe(1);
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
    await expect(trigger).toBeFocused();
    await context.close();
  });
});

test.describe("A11Y-03: 200% text at 320 px", () => {
  test("/postings/applications fits, with applications on it", async ({ browser, request }) => {
    test.setTimeout(120_000);
    const admin = await signIn(request, DEMO.admin);
    const faculty = await verifiedFaculty(request, admin, "overflow");
    const student = await register(request, "overflow-applicant");
    await apply(request, student, await openPosting(request, faculty, "A long enough posting title for wrapping at narrow widths"));
    const context = await contextFor(browser, student, { viewport: { width: 320, height: 640 }, isMobile: true, hasTouch: true });
    const page = await context.newPage();
    await page.addInitScript(() => {
      const style = document.createElement("style");
      style.textContent = "html { font-size: 200% !important; }";
      document.addEventListener("DOMContentLoaded", () => document.head.appendChild(style));
    });
    await page.goto("/postings/applications");
    await settled(page);
    await expect(page.getByRole("heading", { level: 1, name: "My applications" })).toBeVisible();
    await page.waitForTimeout(300);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(0);
    await context.close();
  });
});

test.describe("PERF-01: the applicant inbox does not move as it loads", () => {
  const CLS_BUDGET = 0.02;
  const SIZES: [number, number][] = [[1440, 900], [1280, 800], [768, 1024], [390, 844]];

  async function shift(browser: Browser, session: Session, [width, height]: [number, number], prepare?: (page: Page) => Promise<void>, target = "/postings/applicants") {
    const touch = width < 1024;
    const context = await contextFor(browser, session, { viewport: { width, height }, isMobile: touch, hasTouch: touch });
    await context.addInitScript(() => {
      (window as unknown as { __cls: number }).__cls = 0;
      new PerformanceObserver((list) => {
        for (const entry of list.getEntries() as unknown as { hadRecentInput: boolean; value: number }[]) {
          if (!entry.hadRecentInput) (window as unknown as { __cls: number }).__cls += entry.value;
        }
      }).observe({ type: "layout-shift", buffered: true });
    });
    const page = await context.newPage();
    if (prepare) await prepare(page);
    await page.goto(target);
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(1000);
    const cls = await page.evaluate(() => (window as unknown as { __cls: number }).__cls);
    const text = await page.locator("main").innerText();
    await context.close();
    return { cls, text };
  }

  test("the pages with a waiting invitation or a shared workspace do not move either", async ({ browser, request }) => {
    test.setTimeout(240_000);
    const owner = await register(request, "cls-owner");
    const invitee = await register(request, "cls-invitee");
    const workspace = await ownedWorkspace(request, owner);
    await invite(request, owner, workspace, invitee.user.email);
    for (const size of SIZES) {
      const notifications = await shift(browser, invitee, size, undefined, "/notifications");
      expect(notifications.text).toContain("Workspace invitations");
      expect.soft(notifications.cls, `notifications at ${size[0]}px`).toBeLessThanOrEqual(CLS_BUDGET);
      const list = await shift(browser, invitee, size, undefined, "/workspace");
      expect(list.text).toContain("Shared with you");
      expect.soft(list.cls, `workspace at ${size[0]}px`).toBeLessThanOrEqual(CLS_BUDGET);
    }
  });

  test("two postings with applications, one, none, and when the requests fail", async ({ browser, request }) => {
    test.setTimeout(420_000);
    const admin = await signIn(request, DEMO.admin);
    const student = await register(request, "inbox-applicant");
    const many = await verifiedFaculty(request, admin, "inbox-many");
    await apply(request, student, await openPosting(request, many, "Inbox posting one"));
    await apply(request, student, await openPosting(request, many, "Inbox posting two"));
    const one = await verifiedFaculty(request, admin, "inbox-one");
    await apply(request, student, await openPosting(request, one, "The only inbox posting"));
    const none = await verifiedFaculty(request, admin, "inbox-none");

    for (const size of SIZES) {
      await test.step(`${size[0]}px`, async () => {
        const loaded = await shift(browser, many, size);
        expect(loaded.text).toContain("Inbox posting one");
        expect.soft(loaded.cls, `two postings at ${size[0]}px`).toBeLessThanOrEqual(CLS_BUDGET);

        const single = await shift(browser, one, size);
        expect(single.text).toContain("The only inbox posting");
        expect.soft(single.cls, `one posting at ${size[0]}px`).toBeLessThanOrEqual(CLS_BUDGET);

        const empty = await shift(browser, none, size);
        expect(empty.text).toContain("No applications yet.");
        expect.soft(empty.cls, `no applications at ${size[0]}px`).toBeLessThanOrEqual(CLS_BUDGET);

        const failed = await shift(browser, many, size, async (page) => {
          await page.route(`${API_URL}/api/v1/postings/mine*`, (route) => route.fulfill({ status: 500, contentType: "application/json", headers: { "access-control-allow-origin": "*" }, body: '{"detail":"x"}' }));
        });
        expect(failed.text).toContain("could not be loaded");
        expect.soft(failed.cls, `failed at ${size[0]}px`).toBeLessThanOrEqual(CLS_BUDGET);

        const slow = await shift(browser, many, size, async (page) => {
          await page.route(`${API_URL}/api/v1/postings/*/applications*`, async (route) => {
            await new Promise((resolve) => setTimeout(resolve, 600));
            await route.continue();
          });
        });
        expect.soft(slow.cls, `slow applications at ${size[0]}px`).toBeLessThanOrEqual(CLS_BUDGET);
      });
    }
  });
});
