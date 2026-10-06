# Frontend audit — summary

Audit of the ResearchConnect AI frontend as shipped on `main` at `bd34264`, performed on
2026-10-06 for the redesign plan ([../FRONTEND_REDESIGN_PLAN.md](../FRONTEND_REDESIGN_PLAN.md)).
No application code was changed.

## Contents

| File | What it contains |
|---|---|
| [route-inventory.md](route-inventory.md) | Architecture as found, route matrix (23 routes + system pages), component inventory (48 files) |
| [visual-ux-audit.md](visual-ux-audit.md) | Visual findings P0–P3 with screenshot evidence, and the UX audit |
| [design-language-audit.md](design-language-audit.md) | Every token, colour, size, spacing, radius, shadow and breakpoint in use; design-system violations |
| [accessibility-findings.md](accessibility-findings.md) | axe results, manual keyboard/dialog/landmark findings, WCAG mapping |
| [performance-baseline.md](performance-baseline.md) | Build sizes, CSS/font payload, runtime LCP/CLS/request counts, budgets |
| `screenshots/<role>/<state>__<width>.jpg` | 106 screenshots: public 21, student 68, faculty 9, admin 8 |
| `data/capture-results.json` | Raw per-page measurements: axe violations, focus stops, overflow, LCP, CLS, API calls |
| `tools/capture.mjs`, `tools/contrast.py` | The scripts that produced the screenshots, measurements and contrast table |

## How the audit was done

- **Build**: the production build served by the Compose `frontend` container
  (localhost:3000) against the local backend and the real corpus (55,799 papers, 63 open
  calls, 22 postings, 68 accounts).
- **Accounts**: three dedicated test accounts on the local database
  (`design.audit.{student,faculty,admin}.<tag>@example.test`), created through the app's own
  registration API; the admin one was promoted with one SQL `UPDATE` because no API can grant
  ADMIN. They were given realistic data through the app's API: 4 research interests, 5
  reading-list papers (to read / reading / done), 4 saved calls at different stages, 2
  calendar milestones, an open faculty posting with stipend terms and a draft, and two
  applications (one moved to "under review" by the faculty account). Passwords were generated
  and are not stored in the repository.
- **Browser**: Chromium (Playwright 1.63), light colour scheme, `en-GB`, `Asia/Kolkata`.
  Viewports 1440×900, 1280×800, 1024×768 (desktop context) and 768×1024, 390×844, 360×800
  (touch context). Key routes at all six widths, the rest at 1440 and 390.
- **Measurements**: axe-core 4.13 (WCAG 2.0–2.2 A/AA + best practice) at 1440 and 390; 14-stop
  keyboard pass at 1440; document overflow; LCP/CLS observers; every API request.
- **Privacy**: the admin user table lists real accounts, so names and emails are masked in
  the admin screenshots, and the first unmasked captures were deleted. No other screen lists
  other people's personal data; the audit accounts' own test emails appear on their pages.

### Known artefacts in the screenshots

- Screenshots are clipped at 2,600px (desktop) and 3,600px (mobile) height.
- Touch-viewport screenshots of signed-in pages often end in blank space: the horizontal
  overflow bug (P0-1) inflates the mobile layout height under emulation.
- Two student captures at 390px failed (similar research and venue matching opened from a
  result): the same overflow bug made the result-card buttons unreachable for automated taps.
  Their 1440px versions exist.
- Two extra captures (`*-os-dark__1440.jpg`) show the pages with the OS in dark mode.

## Results at a glance

| Measure | Result |
|---|---|
| Routes audited | 23 (+ `loading`, `not-found`, guard states) |
| Components audited | 48 component files, 2 hooks, `services/api.ts` (170 functions) |
| Visual/UX findings | **7 P0**, 16 P1, 12 P2, 5 P3 |
| axe | 17 critical, 45 serious, 69 moderate; 44 of 68 page states have a serious/critical issue |
| Colour contrast failures | 988 nodes on 22 routes |
| Distinct colours / font sizes / spacing values | 121 / 41 / 50 |
| Undefined CSS tokens in use | 11 (103 uses with no fallback) |
| Shared first-load JS | 103 kB (largest route 167 kB, `/researcher`) |
| Fonts loaded | none (declared `Inter` never loads) |

### Top problems

1. Signed-in pages scroll sideways whenever there are unread notifications (hidden badge text
   escapes the nav; one-line fix identified).
2. Navigation hides most destinations (6 of 13 tabs visible at 1440, 2 at 390).
3. No home view for "what needs my attention" (deadlines, applications, notifications).
4. The researcher profile is a 25,378px stack of development-phase panels.
5. Deadline and risk share red; missing risk data is shown as a red warning.
6. Mobile layouts break (calendar, workspace actions, admin tables).
7. Similar research and venue matching are tabs that lead to "no paper selected".
8. Internal phase labels and raw enum values throughout the UI.
9. Three primary colours, three explanation UIs, 41 button styles.
10. Half-dark rendering when the OS uses dark mode.

## Test data left in the local database

The three audit accounts and their data remain in the local development database so the
audit can be repeated. To retire them, deactivate them in the admin console (search
"design.audit") or ask for a cleanup script. They contain no real personal data.
