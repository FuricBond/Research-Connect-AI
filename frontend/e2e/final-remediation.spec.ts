import { readFileSync } from "node:fs";
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { API_URL, DEMO, DEMO_PASSWORD, MAIL_URL, newPassword, uniqueEmail } from "./support";

/**
 * Decisions B and C, in the browser against the live API and the stack's mail sink. Recruiting pages
 * refuse an administrator whatever the address, and a person answers an invitation only after
 * following a link that reached their mailbox. Sessions are placed in the browser where a sign-in is
 * not the point, because sign-ins are limited to 10 a minute per address.
 */
const AXE_SOURCE = readFileSync(require.resolve("axe-core/axe.min.js"), "utf8");
const AXE_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"];

type Session = { access_token: string; expires_at: string; user: { id: string; email: string; full_name: string; role: string; profile_id: string | null } };

const bearer = (session: Session) => ({ Authorization: `Bearer ${session.access_token}` });

async function authCall(request: APIRequestContext, path: string, data: unknown) {
  for (let attempt = 0; ; attempt += 1) {
    const response = await request.post(`${API_URL}/api/v1/auth/${path}`, { data });
    if (response.status() !== 429 || attempt >= 4) return response;
    await new Promise((resolve) => setTimeout(resolve, (Number(response.headers()["retry-after"] ?? 30) + 1) * 1000));
  }
}

async function register(request: APIRequestContext, email: string, password = newPassword()): Promise<Session> {
  const response = await authCall(request, "register", { email, password, full_name: "Browser Person", role: "STUDENT" });
  expect(response.status(), await response.text()).toBe(201);
  return response.json();
}

async function signIn(request: APIRequestContext, email: string): Promise<Session> {
  const response = await authCall(request, "login", { email, password: DEMO_PASSWORD });
  expect(response.status(), await response.text()).toBe(200);
  return response.json();
}

async function place(page: Page, session: Session) {
  await page.addInitScript((value: Session) => {
    window.localStorage.setItem("researchconnect_access_token", value.access_token);
    window.localStorage.setItem("researchconnect_token_expires_at", value.expires_at);
    window.localStorage.setItem("researchconnect_user_id", value.user.id);
    if (value.user.profile_id) window.localStorage.setItem("researchconnect_profile_id", value.user.profile_id);
  }, session);
}

/** The confirmation link, read from the mailbox as its recipient would. */
async function linkFor(request: APIRequestContext, email: string): Promise<string> {
  for (let tries = 0; tries < 50; tries += 1) {
    const mail = (await (await request.get(`${MAIL_URL}/messages?to=${encodeURIComponent(email)}`)).json()) as { subject: string; text: string }[];
    const links = mail.filter((message) => message.subject === "Confirm your email address");
    if (links.length > 0) return /http\S+\/verify-email#token=\S+/.exec(links[links.length - 1].text)![0];
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  throw new Error(`no confirmation email reached ${email}`);
}

async function ownedWorkspace(request: APIRequestContext, owner: Session): Promise<string> {
  const calls = await (await request.get(`${API_URL}/api/opportunities?page_size=5`)).json();
  const saved = await request.post(`${API_URL}/api/v1/workspace`, { headers: bearer(owner), data: { opportunity_id: calls.items[0].id } });
  expect([200, 201]).toContain(saved.status());
  return (await saved.json()).id;
}

async function seriousAxe(page: Page): Promise<string[]> {
  await page.evaluate(AXE_SOURCE);
  return page.evaluate(async (tags) => {
    type Run = { violations: { id: string; impact: string | null; nodes: { target: string[] }[] }[] };
    const run = await (window as unknown as { axe: { run: (context: Document, options: object) => Promise<Run> } }).axe.run(document, { runOnly: { type: "tag", values: tags }, resultTypes: ["violations"] });
    return run.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
  }, AXE_TAGS);
}

async function fits(page: Page): Promise<boolean> {
  return page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth);
}

test.describe("Decision B: recruiting is for faculty", () => {
  test("an administrator asking for a recruiting page by address is refused, and nothing offers one", async ({ page, request }) => {
    const admin = await signIn(request, DEMO.admin);
    const faculty = await signIn(request, DEMO.faculty);
    const posting = await (await request.post(`${API_URL}/api/v1/postings`, {
      headers: bearer(faculty),
      data: { title: `Decision B page ${Date.now()}`, posting_type: "THESIS_TOPIC", description: "A posting that exists, so its edit page has something to refuse." },
    })).json();
    await place(page, admin);

    for (const path of ["/postings/new", "/postings?view=mine", "/postings/applicants", `/postings/${posting.id}/edit`]) {
      await test.step(path, async () => {
        await page.goto(path);
        await expect(page.getByRole("heading", { name: "This page is for Faculty accounts." })).toBeVisible();
        await expect(page.getByRole("link", { name: "Go to home" })).toBeVisible();
        expect(await seriousAxe(page)).toEqual([]);
      });
    }

    await page.goto("/postings");
    await expect(page.getByRole("heading", { name: "Research postings" })).toBeVisible();
    await expect(page.getByRole("link", { name: "New posting" })).toHaveCount(0);
    const local = page.getByRole("navigation", { name: "Research postings" });
    await expect(local.getByRole("link", { name: "Discover" })).toBeVisible();
    await expect(local.getByRole("link", { name: "My postings" })).toHaveCount(0);
    await expect(local.getByRole("link", { name: "Applicants" })).toHaveCount(0);

    // And the server says the same, whatever the page shows.
    const valid = { title: "Not allowed", posting_type: "THESIS_TOPIC", description: "A complete request, so the refusal is about who asks." };
    expect((await request.post(`${API_URL}/api/v1/postings`, { headers: bearer(admin), data: valid })).status()).toBe(403);
    expect((await request.get(`${API_URL}/api/v1/postings/mine`, { headers: bearer(admin) })).status()).toBe(403);

    // Platform administration is where it was.
    await page.goto("/admin/users");
    await expect(page.getByRole("heading", { name: "Users", level: 1 })).toBeVisible();
    await request.delete(`${API_URL}/api/v1/postings/${posting.id}`, { headers: bearer(faculty) });
  });

  test("an administrator has no personal research pages, and the pages they do have ask for none of it", async ({ page, request }) => {
    const admin = await signIn(request, DEMO.admin);
    await place(page, admin);

    for (const path of ["/postings/applications", "/supervisors", "/reading-list", "/submissions", "/workspace", "/calendar", "/researcher"]) {
      await test.step(path, async () => {
        await page.goto(path);
        await expect(page.getByRole("heading", { name: /^This page is for/ })).toBeVisible();
      });
    }

    const refused: string[] = [];
    page.on("response", (response) => {
      if (response.status() >= 400 && response.url().includes("/api/")) refused.push(`${response.status()} ${response.url()}`);
    });
    const calls = await (await request.get(`${API_URL}/api/opportunities?limit=1`)).json();
    for (const path of ["/notifications", "/settings", "/postings", "/admin", "/admin/users", "/", "/?q=retrieval", "/browse", "/similar", "/opportunities", `/calls/${calls.items[0].id}`]) {
      await page.goto(path);
      await page.waitForLoadState("networkidle");
    }
    expect(refused).toEqual([]);

    await expect(page.getByRole("button", { name: "Add dates to calendar" })).toHaveCount(0);

    await page.goto("/postings");
    await expect(page.getByRole("navigation", { name: "Research postings" }).getByRole("link", { name: "My applications" })).toHaveCount(0);

    for (const path of ["reading-list", "submissions", "workspace", "postings/applications/mine"]) {
      expect((await request.get(`${API_URL}/api/v1/${path}`, { headers: bearer(admin) })).status(), path).toBe(403);
    }
  });

  test("verified faculty still get every recruiting page", async ({ page, request }) => {
    await place(page, await signIn(request, DEMO.faculty));
    await page.goto("/postings");
    await expect(page.getByRole("link", { name: "New posting" })).toBeVisible();
    await page.goto("/postings?view=mine");
    await expect(page.getByRole("heading", { name: "This page is for Faculty accounts." })).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "My postings", level: 1 })).toBeVisible();
    await page.goto("/postings/applicants");
    await expect(page.getByRole("heading", { name: "Applicants", level: 1 })).toBeVisible();
  });
});

test("an application to a posting with one very long word in its title fits 320px", async ({ browser, request }) => {
  const faculty = await signIn(request, DEMO.faculty);
  const student = await register(request, uniqueEmail("long-title"));
  const created = await request.post(`${API_URL}/api/v1/postings`, {
    headers: bearer(faculty),
    data: {
      title: `Long ${"x".repeat(120)}`,
      posting_type: "RESEARCH_ASSISTANTSHIP",
      description: "A posting whose title has one word no line can fit.",
      required_skills: ["python"],
      opening_terms: { compensation_type: "STIPEND", compensation_amount: 1000, compensation_currency: "USD", compensation_period: "MONTH", commitment_type: "PART_TIME", hours_per_week: 10, duration_months: 6, accepts_applications: true },
    },
  });
  expect(created.status(), await created.text()).toBe(201);
  const postingId = (await created.json()).id;
  expect((await request.post(`${API_URL}/api/v1/postings/${postingId}/transition`, { headers: bearer(faculty), data: { target_status: "OPEN" } })).status()).toBe(200);
  expect((await request.post(`${API_URL}/api/v1/postings/${postingId}/applications`, { headers: bearer(student), data: { cover_note: "Hello" } })).status()).toBe(201);

  const context = await browser.newContext({ viewport: { width: 320, height: 720 } });
  const page = await context.newPage();
  await place(page, student);
  await page.goto("/postings/applications");
  await expect(page.getByRole("heading", { name: /^Long x+/ })).toBeVisible();
  expect(await fits(page)).toBe(true);
  await context.close();
  await request.post(`${API_URL}/api/v1/postings/${postingId}/transition`, { headers: bearer(faculty), data: { target_status: "CLOSED" } });
});

test.describe("Decision C: an invitation waits for a confirmed address", () => {
  test("invited, registered, held; confirmed by the emailed link; accepted", async ({ browser, page, request }) => {
    test.setTimeout(240_000);
    const owner = await register(request, uniqueEmail("own-page-owner"));
    const workspace = await ownedWorkspace(request, owner);
    const address = uniqueEmail("own-page-invitee");
    const made = await request.post(`${API_URL}/api/v1/workspaces/${workspace}/invitations`, { headers: bearer(owner), data: { invitee_email: address, role: "CONTRIBUTOR" } });
    expect(made.status(), await made.text()).toBe(201);
    expect(await made.text()).not.toContain("token");

    const password = newPassword();
    const invitee = await register(request, address, password);
    await place(page, invitee);

    await test.step("held: told what to do, and told nothing about the invitation", async () => {
      await page.goto("/notifications");
      const section = page.getByRole("region", { name: "Workspace invitations" });
      await expect(section.getByText(`Invitations sent to ${address} appear here once you confirm that it is yours.`)).toBeVisible();
      await expect(page.getByRole("button", { name: /^Accept/ })).toHaveCount(0);
      await expect(page.getByText("invited you to join")).toHaveCount(0);
      expect(await seriousAxe(page)).toEqual([]);
    });

    await test.step("asking for the email: focus stays, the result is announced, it can be asked again", async () => {
      const send = page.getByRole("button", { name: "Send the confirmation email" });
      await send.focus();
      await page.keyboard.press("Enter");
      await expect(page.getByRole("alert").filter({ hasText: `We sent a link to ${address}.` })).toBeVisible();
      const again = page.getByRole("button", { name: "Send the email again" });
      await expect(again).toBeFocused();
      expect(await seriousAxe(page)).toEqual([]);
    });

    const link = await linkFor(request, address);
    expect(link).toContain("#token=");

    await test.step("someone else's account gets nothing from the link, and the link is not used up", async () => {
      const stranger = await register(request, uniqueEmail("own-page-stranger"));
      const context = await browser.newContext();
      const other = await context.newPage();
      await place(other, stranger);
      await other.goto(link);
      await expect(other.getByRole("alert").filter({ hasText: "This link does not confirm this account's address" })).toBeVisible();
      await expect(other).toHaveURL(/\/verify-email$/);
      expect((await (await request.get(`${API_URL}/api/v1/auth/me`, { headers: bearer(stranger) })).json()).email_verified).toBe(false);
      await context.close();
    });

    await test.step("opened signed out: the token leaves the address, survives signing in, and confirms", async () => {
      const context = await browser.newContext();
      const fresh = await context.newPage();
      await fresh.goto(link);
      await expect(fresh).toHaveURL(/\/login\?next=%2Fverify-email$/);
      expect(fresh.url()).not.toContain("token");
      // The form has no retry for the sign-in limit, and the calls above spent some of this minute.
      await fresh.waitForTimeout(61_000);
      await fresh.getByLabel("Email").fill(address);
      await fresh.getByLabel("Password", { exact: true }).fill(password);
      await fresh.getByRole("button", { name: "Sign in" }).last().click();
      await expect(fresh).toHaveURL(/\/verify-email$/);
      await expect(fresh.getByRole("alert").filter({ hasText: "Your email address is confirmed." })).toBeVisible();
      expect(fresh.url()).not.toContain("token");
      expect(await fresh.evaluate(() => window.sessionStorage.getItem("researchconnect_email_confirmation"))).toBeNull();
      // Next swaps the title during a client navigation, leaving it empty for a few milliseconds.
      await expect(fresh).toHaveTitle("Confirm your email address — ResearchConnect AI");
      expect(await seriousAxe(fresh)).toEqual([]);
      await context.close();
    });

    await test.step("the invitation is now there, and accepting works with the keyboard", async () => {
      await page.goto("/notifications");
      const section = page.getByRole("region", { name: "Workspace invitations" });
      const accept = section.getByRole("button", { name: /^Accept/ });
      await accept.focus();
      await page.keyboard.press("Enter");
      await expect(section.getByRole("alert").filter({ hasText: "You joined" })).toBeVisible();
      await expect(page.getByRole("heading", { name: "Workspace invitations" })).toBeFocused();
      expect((await request.get(`${API_URL}/api/v1/workspace/${workspace}`, { headers: bearer(invitee) })).status()).toBe(200);
    });

    await test.step("a used link says so, and an account already confirmed is told it is done", async () => {
      await page.goto(link);
      await expect(page.getByRole("alert").filter({ hasText: "Your email address is confirmed." })).toBeVisible();
    });
  });

  test("the unconfirmed states fit 320px and 200% text", async ({ browser, request }) => {
    const unconfirmed = await register(request, uniqueEmail("own-page-reflow"));
    const context = await browser.newContext({ viewport: { width: 320, height: 720 } });
    const page = await context.newPage();
    await place(page, unconfirmed);
    for (const path of ["/notifications", "/settings", "/verify-email"]) {
      await test.step(path, async () => {
        await page.goto(path);
        await expect(page.getByRole("button", { name: "Send the confirmation email" })).toBeVisible();
        expect(await fits(page), `${path} at 320px`).toBe(true);
        await page.addStyleTag({ content: "html { font-size: 200% !important; }" });
        expect(await fits(page), `${path} at 200% text`).toBe(true);
        await expect(page.getByRole("button", { name: "Send the confirmation email" })).toBeVisible();
        expect(await seriousAxe(page)).toEqual([]);
      });
    }
    await context.close();
  });

  test("a refusal from the mail server is read out, and nothing is lost", async ({ page, request }) => {
    const unconfirmed = await register(request, uniqueEmail("own-page-fail"));
    await place(page, unconfirmed);
    await page.route(`${API_URL}/api/v1/auth/email-verification`, (route) =>
      route.fulfill({ status: 503, contentType: "application/json", headers: { "access-control-allow-origin": "*" }, body: JSON.stringify({ detail: "This server cannot send email to your address, so it cannot be confirmed yet. Please contact an administrator." }) })
    );
    await page.goto("/settings");
    const send = page.getByRole("button", { name: "Send the confirmation email" });
    await send.focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("alert").filter({ hasText: "This server cannot send email to your address" })).toBeVisible();
    await expect(send).toBeFocused();
  });
});
