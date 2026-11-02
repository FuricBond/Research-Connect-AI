# Manual verification

Two checks in the redesign's acceptance need a person and cannot be replaced by the automated suites:
screen readers (P11) and Lighthouse (P12). A keyboard walk, an accessibility-tree inspection or axe is not
a screen-reader check. Until someone has done these and filled in the tables, both stay **not verified**.

**Status, 2026-11-02: Lighthouse verified by hand (table below). NVDA not verified: the owner stopped before any workflow was run. VoiceOver not verified:
skipped by the owner's decision, because no Apple device is available.**

## Getting a stack to test

```bash
python e2e/run_e2e.py --keep --suites api
```

This starts the isolated stack (web on http://localhost:3300, API on http://localhost:8300). The demo
accounts are `demo.student@researchconnect.test`, `demo.faculty@researchconnect.test` and
`demo.admin@researchconnect.test`. Their password is `E2E_DEMO_PASSWORD` in the run's `stack.env`
(`e2e/results/<run>/stack.env`). Sign-in allows 10 attempts a minute per address. Remove the stack
afterwards with `docker compose -p rce2e down -v`.

The stack sends no real email. What reached a mailbox is at `http://localhost:8325/messages?to=<address>`: that is
where a confirmation link comes from in the workflows below. The demo accounts are already confirmed.

To see a failure on purpose: browser DevTools, Network tab, right-click the request, **Block request URL**,
then repeat the step.

## Screen readers

Do every workflow twice: **NVDA with Firefox or Chrome on Windows**, and **VoiceOver with Safari on macOS**.
Use the keyboard only, with the screen off or not looked at where that is practical.

For each step write down what was **actually spoken**. "Understandable by ear" means someone who cannot see
the screen knows what the control does, what state it is in, what just happened and where they are.

### What to listen for at every step

| Thing | What should happen |
|---|---|
| Control name and state | The name says what it does; a button holding focus while busy says it is busy |
| Dialog opening | The dialog's title is read, focus lands on the title, Tab stays inside |
| Dialog closing | Focus returns to the control that opened it, and that control is announced |
| Status messages | Read without moving focus ("Saved to your reading list.") |
| Errors | Read as soon as they appear, and they say what to do next |
| Focus location | Never lost to the top of the page after an action |

### Workflows

**1. Search → save** (`demo.student`). Open `/`. Type `information retrieval`, press Enter. Move to the first
result. Press **Save to reading list**.
Listen for: the results count; the button's name changing to "Saved to reading list" once, with no "pressed"
or "toggle" wording (audit A11Y-01); the "Saved to your reading list." status.
Failure: block `POST /api/v1/reading-list`; listen for "Could not save to your reading list. Try again."

**2. Workspace status change** (`demo.student`). Open `/workspace`. On a call, open **Status: Saved. Change
status**, choose **Move to planning**.
Listen for: the menu and its items; "Saving…" while focus stays put; the new status on the button; focus
handed to the new menu button.
Failure: block the status request; listen for "could not be moved… It is still Saved."

**3. Apply** (`demo.student`). Open `/postings`, tick **Accepting applications**, open an opening, press
**Apply now**, write a note, send it.
Listen for: the form's labels and hints; the confirmation; the page's new status.
Failure: block the application request; the note stays and the error is read. Applying twice: "You have
already applied to this opening."

**4. Applicant decision** (`demo.faculty`). Open `/postings/applicants`. On an applicant, press **Shortlist**,
then **Not selected**.
Listen for: the applicant's card named by the person; the dialog's title and consequence; that Escape does
nothing while the decision is being sent (audit UI-01) and closes it when idle; focus returning to the card.
Failure: block the transition request; the dialog stays open and reads the reason.

**5. Admin role change** (`demo.admin`). Open `/admin/users`. Open **Role of …** on a test account, choose
**Faculty**, confirm.
Listen for: the menu; the dialog naming the person and the consequence; the toast with **Undo**, read once
politely and staying while focus is in it; focus returning.
Failure: changing the last administrator is refused and the dialog reads why.

**6. Sign-in and session recovery** (`demo.student`). Open `/postings?view=mine` signed out. Sign in; submit the form
empty first.
Listen for: each field's error, and focus moving to the first; the page you are taken to after signing in.
Failure: block `GET /api/v1/auth/me` and reload; listen for the message that your session could not be checked, that
you were not signed out, and for **Try again**.

**7. Workspace invitation, from unconfirmed to accepted** (a new account, plus `demo.student` to invite). As
`demo.student`, on a workspace's **Members** tab, invite a new address. Register that address in another browser.
Open `/notifications`, press **Send the confirmation email**. Open the link from the mailbox above, then return to
`/notifications` and accept.
Listen for: the section saying invitations appear once you confirm the address, and naming no workspace or person; "We
sent a link to …", read once, with focus staying on the button; "Your email address is confirmed." with its link; the
invitation's workspace, inviter and role; "You joined …" with focus on the section's heading.
Failure: open the link while signed in to a different account; listen for the refusal, which says the link does not
confirm this account's address, and for the offer of a new email.

**8. Recruiting workflow** (`demo.faculty`). Open `/postings/new`, submit it empty, then complete it and publish. Open
`/postings?view=mine`, then the posting's **Edit**.
Listen for: the form's errors and where focus goes; the status after publishing; the status menu's items.
Failure: as `demo.admin`, open `/postings/new` and `/postings/applicants` by address; listen for "This page is for Faculty
accounts." and the way home.

**9. Notifications and settings** (`demo.student`). Open the bell, then `/notifications`; mark one read. Open `/settings`,
turn an email alert off and on, change the theme.
Listen for: the unread count changing; each switch's name and state; the password form's errors.
Failure: block the preferences request; listen for the failure and that the switch went back.

**10. Administration** (`demo.admin`). On `/admin` read the health and the counts. On `/admin/users`, filter by status,
search, then verify an unverified faculty account and press **Undo** on the toast. Open `/admin/research-data`.
Listen for: results counts as filters change; the toast read once; tables read with their headers.
Failure: block `GET /api/v1/admin/users`; listen for the failure and **Try again**.

### Record

| Workflow | Screen reader and browser, versions | Date, tester | Step | What was spoken | Pass or problem |
|---|---|---|---|---|---|
| | | | | | |

## Lighthouse

Not installed in the project, and nothing downloads it. **Chrome DevTools has it built in**, so nothing needs
installing.

1. Start the stack as above: it runs a production build.
2. Open Chrome, DevTools (F12), **Lighthouse** tab. Mode **Navigation**, device **Mobile** (the default
   preset), categories **Performance**, **Accessibility**, **Best practices**. Use a clean profile with no
   extensions.
3. Sign in first in that same tab: Lighthouse keeps the session with **Clear storage** unticked (the gear in
   the Lighthouse tab).
4. Run it on these pages, saving each report as JSON:

| Page | Account | Performance ≥ 90 | Accessibility ≥ 95 | Best practices ≥ 95 |
|---|---|---|---|---|
| `/` | none | 100 | 100 | 100 |
| `/dashboard` | `demo.student` | 100 | 100 | 100 |
| `/recommendations` | `demo.student` | 100 | 100 | 100 |
| `/researcher` | `demo.student` | 100 | 100 | 100 |
| `/postings/applicants` | a verified faculty account with **at least two postings that have applications** | 100 | 100 | 100 |

Measured 2026-11-02 by the project owner, in Chrome 156, mobile preset with simulated throttling, on the
local stack. Local serving makes these best-case: a deployed site can score lower. The Accessibility score covers only
what a tool can check, so it does not replace the screen-reader workflows above. Reports were kept as screenshots, not JSON.

The demo faculty has one such posting, so the last row needs a second one. As `demo.faculty`, publish another
assistantship from `/postings/new`; then, as `demo.student`, apply to it.
