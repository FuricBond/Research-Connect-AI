# P0 Independent Audit

Audited tree: branch `design/frontend-redesign-plan`, HEAD `23953dc` (identical to
`origin/design/frontend-redesign-plan`), clean working tree. Baseline: `bd34264` (main),
rebuilt from a clean `git archive` and measured with the same scripts. Everything below was
measured on 2026-10-07 against the running application (Compose dev stack, the three
`design.audit.*` accounts), not taken from the implementation report.

## 1. Executive verdict

**NOT CLEAR** as committed at `23953dc` (§10 lists the blockers). After the narrow
remediation in §12 the working tree re-audits **CLEAR**; that verdict holds once the
remediation is committed.

## 2. Repository state

- Branch `design/frontend-redesign-plan`, HEAD `23953dc`; the brief says P0 is not pushed,
  but both commits (`89a3bd6`, `23953dc`) are on `origin`.
- `bd34264..HEAD`: 211 files — 153 under `docs/design/`, 58 under `frontend/` (41 modified,
  17 added). No backend, database, migration, API, `package.json`/lockfile, Next/Tailwind
  config, Docker or CI change.
- Nothing required is ignored: no ignored file under `frontend/` outside build output.
  The root `.gitignore` `lib/` rule still exists but no frontend `lib/` directory remains;
  `frontend/utils/navigation.ts` is tracked.
- No `.env` file, key, token, password or e-mail address in the diff; screenshots only in
  `docs/design/audit/`.

## 3. P0 findings

### P0.1 Horizontal overflow — FAIL (as committed)
- The root cause (the unread badge's visually hidden text without a positioned ancestor) is
  genuinely fixed: `position: relative` on the tabs; `html`/`body` are `overflow-x: visible`
  in every state; the diff adds no `overflow: hidden`/`clip`.
- The report's set (15 student pages × 7 widths) reproduces exactly: **105/105 before →
  0/105 after**.
- A broader sweep (4 roles, 43 routes, 1440/1280/1024/768/390/360/320 = 301 states):
  **226/301 before → 16/301 after**. Still overflowing: `/researcher?section=personalization`
  (+216 px at 768, +481 at 390, +551 at 320), `?section=history` (+37 at 768, +415 at 390),
  `?section=interests` (+55 at 390, +125 at 320), `?section=recommendations` (+28 at 320),
  `/researcher/preferences` (+14 at 390, +84 at 320), `/workspace/[id]/submission` (+18 at 320).
- Root cause of the large ones is P0's own `.profile-section-body { display: grid }` with an
  implicit `auto` track (grid blowout); injecting `grid-template-columns: minmax(0, 1fr)`
  removes it. Without that, the pre-P0 single profile page overflowed by only 38 px at 390
  once the nav bug is removed, so this is a regression. The remainder are older component
  rules (`minmax(360px, 1fr)` / `minmax(320px, 1fr)` card grids, header rows whose
  Refresh button cannot wrap, a submission header button).
- Scoped scrollers that remain are intentional and reachable: reminder rules table and admin
  tables (labelled, focusable regions), workspace status tabs and signal filters (contain
  focusable buttons).

### P0.2 Navigation — PASS
- 4 roles × 7 widths: every role-appropriate destination is reachable exactly once (bar or
  More/Menu), none lost, none duplicated, no bar item overlaps or truncates; role gating
  identical to `bd34264` (Find a Supervisor student-only, Administration admin-only).
- `aria-current="page"` on the current destination; More is highlighted when the current
  page is inside it; one `nav[aria-label="Main"]` and one `main` per page.
- Menu: `aria-expanded`/`aria-controls`; Escape closes and returns focus to the button;
  outside click closes; choosing a link navigates and closes; Tab reaches the button
  (4–9 stops), Enter opens, Tab enters the menu; focus outline visible throughout.
- Tap targets ≥ 40 px (44 px under 768). Minor: on phones the open menu runs ~43 px below
  the fold (internal scroll plus page scroll) — non-blocking.

### P0.3 Signed-in home — PASS
- Student, faculty and admin land on `/dashboard`; a reload stays there; signed-out
  `/dashboard` → `/login?next=%2Fdashboard`.
- Content matches the API: the student's four deadlines equal an independent recomputation
  (open items due ≤ 30 days, same order and statuses); faculty and admin show the honest
  empty state; application/posting lines come from the existing summaries; no invented data.
- Every home link opens a real page. Requests: student 5, faculty 5, admin 4 (≤ 3 page + 2
  shell), all existing endpoints.

### P0.4 Profile decomposition — FAIL (regression)
- Five sections, deep-linkable; reload keeps the section; back/forward correct.
- Default section: **3 requests (25 before), 932 px tall (26,373 px before)**; interests 5,
  recommendations 7, personalization 15, history 7. All 72 headings of the old page exist in
  some section — no panel lost. No "Phase x" text on any section.
- **Regression:** saving a profile edit no longer recomputes research intelligence. Before:
  `PATCH` → `GET …/research-intelligence?refresh=true`. After: `PATCH` only, and the
  interests section then loads `?refresh=false`, which returns the persisted (pre-edit)
  interests that recommendations are built on.
- Raw values remain in deeper sections (personalization diagnostics such as
  "Insufficient data for RISK_TIER=INSUFFICIENT_EVIDENCE", "Personalization health is
  INSUFFICIENT_DATA"; `CALL_FOR_PAPERS` in recommendations; `NOT_INTERESTED` filter option);
  the report overstated this cleanup. Label maps are P1 (`lib/status`); non-blocking.

### P0.5 Risk / deadline / unknown — FAIL (clarity)
- Deadline: clock icon and words ("Due 9 Oct 2026 · 3 days left", "Closed 15 Aug 2026"),
  no raw decimals anywhere; orange only when ≤ 7 days, background when ≤ 2.
- Risk: shield icons and words; red reserved for high risk; never a number.
- Unknown: "Risk not assessed", grey with a dashed border and a question-shield — neutral.
- Colour is never the only signal (icon + wording differ).
- Date handling: the backend stores date-only call deadlines as 23:59 AoE = 11:59:59 UTC
  next day (329 of 341 stored deadlines); P0's `DeadlineCountdown` shows the AoE date
  (correct) but without saying AoE, so the home page reads "Due 7 Oct 2026 · 1 day left" on
  7 Oct, and the same call reads "Due 9 Oct" on the workspace but "Due 10 Oct 2026 UTC" on
  venue matching (older badge). Blocking: the deadline text contradicts itself.
- Non-blocking: when the backend fails to compute a risk explanation, the workspace card
  falls back to `risk_score` (default 0.00) and shows "Low risk".

### P0.6 Mobile — FAIL (as committed)
- Calendar, workspace, notifications, settings, admin, home, nav, Similar and Opportunities
  fit at 768/390/360/320 with usable controls; dialogs and the "Why this rank?" drawer fit.
- The profile sections and preferences page do not (see P0.1).

### P0.7 Similar / Opportunity — FAIL (accessibility)
- No paper, signed out: both tools show a title, why a paper is needed and a link to
  Literature Search; no request; nothing selected.
- From search: the chosen result is the paper used; reload, back/forward and switching to
  the other tool keep it.
- Signed in: five reading-list papers offered; the chosen one is used and survives reload.
- **Defect:** after "Use this paper", keyboard focus falls to `<body>` (the button unmounts).

## 4. Accessibility

20 comparable states (rules per state; nodes in brackets):

| Impact | Before | After |
|---|---|---|
| critical | 18 (68) | 0 (0) |
| serious | 22 (1,366) | 16 (282) |
| moderate | 26 (32) | 6 (8) |

All 26 audited states including home and the open menu: 0 critical, 18 serious, 6 moderate.
Remaining serious = colour contrast in the existing palette; moderate = heading order.
P0-caused: **heading-order on the Research interests section** (h1 → h3 when no intelligence
exists; on the old page an h2 preceded it) and the focus loss in P0.7. No violation targets
an element P0 added.

## 5. Performance

- Requests: home 5/5/4; profile default 25 → 3; notifications 4 with one unread-count call
  (two before); notification settings 5, one unread-count.
- First-load JS: shared 103 → 103 kB; `/dashboard` 121 kB (new); `/opportunities`
  129 → 134; `/similar` 125 → 130; `/researcher` 167 → 169; `/workspace` 121 → 123;
  `/notifications` 123 → 121; `/settings/notifications` 123 → 120. No material regression.

## 6. Test results (final tree `23953dc`)

| Check | Result |
|---|---|
| Typecheck | pass |
| Lint | 0 errors, 4 warnings (baseline 5; all 4 pre-existing) |
| Vitest | 32 files, 293 passed, 0 failed, 0 skipped (one `act()` warning, stubbed-404 console noise) |
| Browser Playwright (E2E run `20261007T040134Z`) | 4 passed |
| API E2E | 69 passed, 0 failed, 0 skipped (7 deselected by design) |
| Stack E2E | 7 passed; startup 20.9 s; log scan passed |
| Production build | pass |

## 7. Regression review

- Roles, routes and API contracts: unchanged; no route broken, no permission lost.
- Changed tests were changed for genuine behaviour changes (landing page, navbar placement,
  menu, sections), but coverage shrank: the browser suite no longer loads the profile's
  default, personalization or history sections (before, one step loaded every panel and
  failed on any API error), and the layout spec checks only the default section — which is
  how the section overflow escaped.
- Functional regression: profile save → stale research intelligence (P0.4).

## 8. Scope review

No P1 work: no tokens imported (`tokens.draft.css` unused, no `--rc-*`), no fonts, no
`components/ui`, no Tailwind/Next config, no dark-mode change, no new dependency. Small
supporting code (indicators, nav model, `utils/date|risk|workspace`) is P0-necessary.

## 9. Findings

| ID | Severity | Finding | Evidence | Required before P1? |
|----|----------|---------|----------|---------------------|
| A1 | REGRESSION | Profile sections scroll sideways (grid blowout in `.profile-section-body`) | personalization +481 px @390, history +415 @390; fix verified by injection | Yes |
| A2 | P0 BLOCKER | Remaining page overflow on profile routes and submission page at 320–390 | interests +22 @390, preferences +14 @390/+84 @320, submission +18 @320 | Yes |
| A3 | REGRESSION | Profile save no longer refreshes research intelligence | network: `refresh=true` before, `refresh=false` after | Yes |
| A4 | REGRESSION | heading-order on Research interests (h1 → h3) | axe, new vs baseline | Yes |
| A5 | P0 BLOCKER | Focus lost after choosing a reading-list paper | `document.activeElement === body` | Yes |
| A6 | P0 BLOCKER | AoE date shown without "AoE"; contradicts countdown and other surfaces | "Due 7 Oct 2026 · 1 day left" on 7 Oct | Yes |
| A7 | REGRESSION | E2E no longer covers profile default/personalization/history; layout spec misses sections | `pages.spec.ts`, `layout.spec.ts` | Yes |
| A8 | P0 NON-BLOCKING | Workspace risk fallback can show "Low risk" for an unassessed venue | `app/workspace/page.tsx` risk fallback | No (cheap fix) |
| A9 | P0 NON-BLOCKING | Raw enums in personalization/recommendations/history; personalization 15 requests | text scan | No (P1/P6) |
| A10 | P0 NON-BLOCKING | Phone menu runs ~43 px below the fold | menu bottom 887 @844 | No (P2) |
| A11 | P0 NON-BLOCKING | Home lists "Applied" calls under Needs attention | home content | No (P4) |
| A12 | P0 NON-BLOCKING | Vitest noise (`act()` warning, 404 console output) | test log | No |
| A13 | P1 | Phase labels outside the profile (notifications subtitle, calendar provenance, explainability drawer) | text scan | No |
| A14 | P1 | Colour contrast (282 nodes), pre-existing heading order, no skip link | axe | No |
| A15 | INFO | Brief says unpushed; P0 is on origin | git | No |

## 10. Required remediation

A1–A7 (A8 fixed alongside: one line, same acceptance criterion).

## 11. Final verdict

NOT CLEAR — P0 requires remediation before P1.

## 12. Re-audit after remediation (uncommitted working tree on `23953dc`)

Fixes, each limited to its finding (20 files, +179/−31, no new dependency, no backend change):

| ID | Fix |
|----|-----|
| A1 | `styles/profile.css`: `.profile-section-body { grid-template-columns: minmax(0, 1fr) }` |
| A2 | Card grids `minmax(min(Npx, 100%), 1fr)` (preferences view and page, personalization summary); header and action rows wrap (preferences, recommendation history, recommendations search, submission header, research-interest filter tabs); add-row inputs `min-width: 0` (preferences page) |
| A3 | `app/researcher/page.tsx`: a profile save recomputes research intelligence at once (`refresh=true`), as before the split |
| A4 | Research-interests empty state is an `h2`; its hint now points to the Profile section instead of "above" |
| A5 | Similar Research / Opportunity Matcher: after "Use this paper", focus moves to the chosen paper's title |
| A6 | `DeadlineCountdown` adds "AoE" when the date is an AoE date (`isAoeDeadline` shares `formatDeadlineDate`'s rule) |
| A7 | `pages.spec` opens all five profile sections; `layout.spec` covers every section, the preferences page and notification settings |
| A8 | Workspace card uses only the risk assessment; no `risk_score` fallback to "Low risk" |

Re-measured:

- Overflow: dev stack **0/301** (16 before remediation); `html`/`body` still
  `overflow-x: visible`. With the E2E demo data: student 21 pages × 768/390/360/320 and
  faculty 10 pages × the same widths plus home at 390 — 0 overflow. The intermediate E2E run
  (`20261007T045957Z`) caught one data-dependent case the audit accounts could not show
  (interest-tier filter tabs, +14 px at 360); fixed and verified on that stack.
- Navigation 28/28 role × width combinations pass; home 5/5/4 requests; profile default
  3 requests; back/forward and reload unchanged.
- Profile save: `PATCH` → `GET …/research-intelligence?refresh=true`; the interests section
  then does not re-read it.
- Deadlines read "Due 7 Oct 2026 AoE · 1 day left"; focus lands on the chosen paper's `h2`.
- axe, 20 comparable states: critical 18 → 0, serious 22 → 16, moderate 26 → 5 (nodes
  68 → 0, 1,366 → 282, 32 → 7); all 26 states 0 / 18 / 5; no violation on a P0 element and no
  rule present in any state that the baseline did not already have.
- Typecheck pass; lint 0 errors, 4 pre-existing warnings; Vitest 32 files, **298 passed**,
  0 failed, 0 skipped; production build pass (shared 103 kB, `/researcher` 169 kB).
- E2E run `20261007T052741Z` on the final tree: startup 20.4 s; API **69 passed**; browser
  **4 passed** (layout spec now 16 pages × 7 widths); stack **7 passed**; RESULT PASS.

Still open, none blocking P1: A9 (raw enums in deeper profile panels → P1 status maps /
P6), A10 (phone menu height → P2), A11 (Applied calls under Needs attention → P4), A12
(test noise), A13–A14 (phase labels elsewhere, contrast, skip link → P1), and the older
venue-matching badge showing the same deadline as "10 Oct 2026 UTC" (the deadline
intelligence loses the AoE zone; backend, outside P0).

## Final verdict (remediated working tree)

CLEAR — P0 is independently verified and ready for P1.
