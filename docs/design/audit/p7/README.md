# P7 evidence — research workflow

Measured on 2026-10-18 against the isolated end-to-end stack (`python e2e/run_e2e.py --keep`, the
frontend image rebuilt after each fix below): production images of the P7 working tree on `main`,
the seeded demo student (Chromium through Playwright). Every number comes from
`measurements.json` in this folder. The design is in
[DESIGN_SYSTEM.md §19](../../DESIGN_SYSTEM.md#19-research-workflow-p7). This is the phase's own
implementation check, not the independent audit (which covers all phases once they are done).

## Suites

The final working tree, in a clean run of `python e2e/run_e2e.py` (fresh database, torn down
afterwards, `e2e/results/20261018T125350Z`): **PASS** — API 69/69, browser 23/23, stack 7/7. The first run of the P7 tree (`e2e/results/20261018T112850Z`, kept)
passed the API (69/69) and stack (7/7) suites and failed two browser tests — both described under
"Fixed on the way"; after the fixes the browser suite passed on the kept stack (23/23, four reruns
as later fixes landed). Unit tests (Vitest): 52 files, 581 tests (551 before P7), three
consecutive full runs green. Type-check, lint (no warnings) and the production build exit 0.

## Requests per page load

Counted as the browser made them, without the shell's session check (`/auth/me`) and unread count
(`/notifications/unread-count`), which every signed-in page makes; the seeded student, light theme,
1440×900, after the page settled.

| Page or action | Requests |
|---|---|
| Workspace | 2: the list and the counts |
| Workspace, a status chip | 1: the list for that status |
| Workspace item (Overview) | 1: the item (a collaborator +1: the members, for the role) |
| … open Tasks | 2: the members (for assigning) and the tasks |
| … open Submission | 3: the item's submissions, then the shown one's readiness check and documents (its history only when opened) |
| … open Members | 1: the invitations (the members came with Tasks; 2 when Members is opened first) |
| … open Activity | 1 |
| … back to a tab already opened | **0** |
| Submissions | 2: the list and the counts |
| Reading list | 1 per status and page |
| Calendar | 2: the default calendar, then its events |
| Calendar, another month or view | **0** |

Enforced by `tests/workspace-item.test.tsx` (a tab asks only for its data; reopening asks nothing;
the owner's item needs no member list) and `tests/workspace-status.test.tsx` (the counts reload
after a change).

## Layout shift (CLS)

PerformanceObserver `layout-shift` (buffered, without recent input) from navigation start until
the page settled; three runs per combination, each in a fresh page; the seeded student, light theme.

| Page | 1440 | 390 |
|---|---|---|
| Workspace | 0.0005 ×3 | 0.0001 ×3 |
| Workspace item, Overview | 0.0005 ×3 | 0.0001 ×3 |
| Workspace item, Submission (with a submission) | 0.0005 ×3 (first build 0.0469) | 0.0001 ×3 (0.0163) |
| Submissions | 0.0005 ×3 | 0.0001 ×3 |
| Calendar | 0.0005 ×3 (first build 0.022 at 390) | 0.0001 ×3 |
| Reading list | 0.0005 ×3 | 0.0001 ×3 |

What remains on every page is the P2 header: the account button widens when the name arrives.
`/workspace` at 390px measured **0.1507** in the first browser run (e2e `shell.spec`, limit 0.05);
see below.

**The measuring helper.** P6's measurement script reused one page for its three runs and added a
new observer each time, so run *n* counted every shift *n* times over (plus the observers of the
earlier pages measured in the same page). P6's CLS figures therefore overstate, never understate;
this script measures each run in a fresh page.

## Accessibility and layout

| Check | Result |
|---|---|
| axe: light and dark × 1440/768/390/360/320 × workspace, the item's five tabs, submissions, reading list, calendar (default, month, agenda, a month with call deadlines); and the states: status menu open, remove dialog, notes open, new-task dialog, invite dialog, calendar event dialog, add-milestone dialog; with a submission and saved papers: the Submission tab filled, record-version dialog, version history, submission history open, delete-submission dialog, reading list filled, remove-paper dialog (290 runs) | **0** violations of any impact |
| Horizontal overflow, the same 290 pages and states | **0** — at 360px and 320px included (QA target: workspace and calendar at 360px) |
| 200% text at 320px: workspace, item (Overview, Tasks, Submission empty and filled), submissions (empty and filled), reading list (empty and filled), calendar (agenda and month) | overflow 0, no control off screen (the item's tabs were off screen in the first build; see below) |
| Text that leaks code ("undefined", "NaN", "[object Object]"), every page and state above | none |
| Keyboard on `/workspace`, the item page and the calendar's month grid, the first 50 stops after the title | every stop named, every stop with a visible 2px ring; the tab list is one stop (arrow keys inside), the menus open with Enter/Arrow Down |
| Headings | one h1 per page; Workspace: h2 the list, h3 each call; the item: h1 the call, h2 per section of the tab, h3 inside; Reading list: h2 "All papers" (or the status), h3 each paper; Calendar: h2 the month, h3 each day of the agenda |
| Live regions | one polite status per page for changes (status moved, task added, note posted, milestone added…); failures after an action are alerts; a rolled-back status change is announced with the status it kept |

The empty states were measured on the same stack before data was added: an empty calendar in the
first pass (its pages without violations; that pass found the reading-list heading order fixed
below), then no submission yet ("Draft a submission") and an empty reading list in the second
(190 runs, 0 violations, 0 overflow). The final pass measured the filled states.

**Data added to the e2e stack for these measurements** (isolated database, deleted with the stack):
the tracked call's dates through its page's "Add dates to calendar", a milestone dated today (one
per measuring pass, hence the repeated milestone in the calendar captures), a submission draft
with one document through the Submission tab, and papers saved from Literature Search.

## Fixed on the way

- **CLS on `/workspace` at 390px (0.1507; e2e `shell.spec` failed).** The status chips gained their
  counts after the list rendered, widened, and rewrapped onto another line, pushing the search and
  the list down 38px. A hidden, unannounced placeholder now keeps each chip's width until its count
  is known (`ChipCount`; also on Submissions and the reading list). Unknown counts are still never
  shown or read as 0.
- **e2e `layout.spec` failed** (timeout): it took a workspace item from the list, but the demo
  student's workspace is empty when that spec runs first. It now saves the call it checks through
  the API (idempotent), as `pages.spec` does.
- **Calendar header** (CLS 0.022 at 390): Export and Add milestone appeared only once the calendar
  was known and pushed the page down; they are there from the first paint, disabled until then.
- **Submission tab** (CLS 0.047 at 1440 with a submission): the readiness check arrived after the
  rest of the view and pushed the status actions and the details down; the view now appears once
  its two first answers are in, with one skeleton until then.
- **Tabs at 200% text**: the item's tab list scrolled sideways inside itself, leaving four tabs out
  of view at 320px; tabs now wrap onto another line (`Tabs.module.css`).
- **Reading list heading order** (axe `heading-order`, moderate, ×10): paper titles were h3 under
  the h1; the list now has an h2.
- **Readiness wording**: the server's summary sentence ("Readiness status: NOT_READY. 0/1 …")
  repeated the facts with enum values; the tab shows the facts in words instead. The blocking issues
  and warnings are still the server's own sentences, which can name a document type in capitals.
- **Duplicate name**: the version-history dialog had two buttons named "Close"; its footer button
  is "Done".
- **Phone length of the reading list**: each paper's notes box was always open; notes are now a
  disclosure, open from the start when the paper has notes.

## Screenshots

`light/` and `dark/` — `workspace`, `workspace-status-menu`, `item` (Overview), `item-tasks`,
`item-submission`, `item-submission-filled`, `item-members`, `item-activity`, `submissions`,
`submissions-filled`, `reading-list`, `reading-list-filled`, `calendar`, `calendar-month`,
`calendar-agenda`, `calendar-month-deadline`, `calendar-event`, at 1440, 390 and (workspace, item,
calendar, filled states) 360; `reading-list-remove__390.jpg`; at 200% text and 320px:
`light/{workspace,calendar,item-submission,item-submission-filled,reading-list-filled}-text-200-percent__320.jpg`.
In the final pass the item already had its submission, so `item-submission` shows it too. The
seeded demo accounts and fictional titles only; no real person's data.

## Deferred issues (consolidated)

Carried forward, checked again in P7:

| Issue | Severity | State in P7 |
|---|---|---|
| F10: an answered `/auth/me` failure (including a 5xx) signs out; a check that never answers keeps the skeleton | Medium | Unchanged: `SessionProvider` still clears the session on any `ApiError` (only a check cancelled while leaving is ignored, P4); not touched in P7 |
| P4: notifications only in the bell (the dashboard's "latest three" waits for P8's shared list); faculty "Needs your decision" reads at most three postings; "Recommended papers" are papers similar to the newest one; reserved module heights | Low | Unchanged (dashboard not touched). P7 helps P8: a notification's `/workspace/{id}` link now opens an item shared with the reader (the old page only found the reader's own items) |
| `/supervisors` guarded without a role (authorization is the backend's) | Low | Unchanged |
| Firefox, Safari, real browser zoom, screen readers | — | Not run (below) |

New in P7:

| Issue | Severity | Evidence |
|---|---|---|
| First-load JS above the plan's "largest route ≤ 140 kB" budget (§18, a P12 acceptance budget): `/workspace/[id]` 145 kB (157 before its tabs were lazy-loaded), `/calendar` 141 kB; P6's `/recommendations` is 143 kB | Low | `next build` route table |
| The API's readiness issues and activity descriptions are its own sentences and can carry enum words ("(FULL_PAPER) is still in DRAFT status", "as CONTRIBUTOR") | Low | Captures `item-submission-filled__*`; rewriting them needs codes the API does not fully give, or a backend change |
| A status change's optional note **replaces** the submission's notes (backend `transition_status`) | Low–medium | The field says so ("If you write one, it replaces the submission's notes"); keeping both would be a backend change |
| Under a status filter, a call moved to another status stays in the list (with its new status) until the next load | Low | By design, so a row does not vanish under the pointer; the counts update at once |
| "Open" and "Collaborate" in a row's More actions are menu items that navigate, not links (no open in a new tab); the title link and next-step link are real links | Low | `WorkspaceRow.tsx` |
| Milestone times are entered in UTC (as before), not the reader's zone | Low | Add-milestone dialog ("Time (UTC)") |
| Unit tests of P5/P6 lazy panels (Evidence panel, Find venues…) can exceed the 1-second default wait on a busy machine: 8 failures in 1 of 6 full runs (cold), green in the other 5; P7's item tests wait 5 seconds for their lazy tabs | Low (test environment) | Vitest runs during P7 |
| Two older architecture notes (`docs/architecture/phase4-1-…`, `phase4-6-…`) still name the deleted page stylesheets | Low (docs) | `grep` |
| Collaboration as a second account (an editor or viewer of a shared item) is verified with unit tests on the API's answers, not in a browser with two accounts | Untested risk | `tests/workspace-item.test.tsx` "roles" |

## Not verified here

Chromium only (no Firefox or Safari run); browser zoom simulated with a 200% root font size; no
screen-reader session (names, roles, states and live regions were checked through the
accessibility tree, axe and the unit tests). Collaboration as a second account (an editor or a
viewer of a shared item) is covered by unit tests with the API's answers, not by a browser run
with two accounts. The independent audit after all phases covers these.
