# Manual verification

Two checks in the redesign's acceptance need a person and cannot be replaced by the automated suites:
screen readers (P11) and Lighthouse (P12). A keyboard walk, an accessibility-tree inspection or axe is not
a screen-reader check. Until someone has done these and filled in the tables, both stay **not verified**.

## Getting a stack to test

```bash
python e2e/run_e2e.py --keep --suites api
```

This starts the isolated stack (web on http://localhost:3300, API on http://localhost:8300). The demo
accounts are `demo.student@researchconnect.test`, `demo.faculty@researchconnect.test` and
`demo.admin@researchconnect.test`. Their password is `E2E_DEMO_PASSWORD` in the run's `stack.env`
(`e2e/results/<run>/stack.env`). Sign-in allows 10 attempts a minute per address. Remove the stack
afterwards with `docker compose -p rce2e down -v`.

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
| `/` | none | | | |
| `/dashboard` | `demo.student` | | | |
| `/recommendations` | `demo.student` | | | |
| `/researcher` | `demo.student` | | | |
| `/postings/applicants` | a verified faculty account with **at least two postings that have applications** | | | |

The demo faculty has one such posting, so the last row needs a second one. As `demo.faculty`, publish another
assistantship from `/postings/new`; then, as `demo.student`, apply to it.
