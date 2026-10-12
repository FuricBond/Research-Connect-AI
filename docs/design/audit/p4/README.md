# P4 evidence — the dashboard

Measured on 2026-10-12 against the isolated end-to-end stack (`python e2e/run_e2e.py --keep`:
production images of the P4 working tree on `design/frontend-redesign-p2`, seeded demo accounts),
with the frontend rebuilt after each fix below. Every number comes from `measurements.json` in
this folder. The design is in [DESIGN_SYSTEM.md §16](../../DESIGN_SYSTEM.md#16-dashboard-p4).
This is the phase's own implementation check, not the independent audit (which covers all
phases once they are done).

## Requests per page load

Counted as the browser made them, from a fresh load of `/dashboard`, without the shell's
session check (`/auth/me`) and unread count (`/notifications/unread-count`), which every
signed-in page makes. All start together; the only dependent ones are inside their module.

| Role | Requests | Which |
|---|---|---|
| Student | **7** (every width and theme) | workspace, application summary, calendar, recommendations, open postings, fit scores (after the postings), reading list |
| Faculty (seeded: 2 open postings, one with an applicant; no papers) | **4** | workspace, own postings, that posting's application list (after the postings), newest paper (none, so no related-papers request) |
| Faculty, at most | 7 | + up to 3 application lists (after the postings) and the related papers (after the newest paper) |

Enforced by `tests/home-page.test.tsx` (exact sets per role, each once, re-render, retry, shared
resources) and `e2e/dashboard.spec.ts` (≤ 7 on the live API, the same set on reload).
With the shell's two requests, a student load is 9 API requests in all; the P12 budget table
("≤ 8 per route, dashboard ≤ 7") counts the shell too and needs reconciling then.

## Layout shift (CLS)

PerformanceObserver `layout-shift` (buffered, without recent input), from navigation start
until 0.8 s after the last module settled; three runs per combination, light and dark.
"Varied" delays every API answer by a random 50–800 ms, so modules settle in a different order
each run.

| Role, width | Before the fixes (local / varied) | After (local / varied) |
|---|---|---|
| Student 1440 | 0.039 / 0.040 | **0.006 / 0.006** |
| Student 390 | 0.039 / 0.050 | **0.009 / 0.013** |
| Faculty 1440 | 0.0005 / 0.0005 | 0.0005 / 0.0005 |
| Faculty 390 | 0.0006 / 0.0006 | 0.0006 / 0.0006 |

Before: "Needs attention" and "Recommended for you" grew past their placeholders and pushed
"Upcoming" and "Postings that fit you" down. After: each module reserves a typical answer's
height from its first paint and items are clamped (titles and reasons to two lines), so at
1440px no module changes height; at 390px only modules below the first screen still grow. The
P12 budget is ≤ 0.02. With other data (more calls due, longer titles) a module can still grow.

## Accessibility and layout

| Check | Result |
|---|---|
| axe, student and faculty × light and dark × 1440/768/390/320 (16 runs) | **0** violations of any impact (one serious `color-contrast` in dark fixed: the match value was faded to 85% opacity) |
| Horizontal overflow, same 16 | 0 |
| 200% text at 320px | overflow 0, nothing off screen (the faculty timeline overflowed by 104px before; a narrow timeline now puts the date above the title) |
| Keyboard, from the page title through the dashboard | student 16 stops, faculty 8; every stop named and with a visible 2px ring |
| Headings | one h1 (the greeting); an h2 per module; h3 inside |
| Loading | placeholders are busy and named for screen readers but not live regions (seven modules would otherwise be read out on every load) |

## Fixed on the way

- **Signed out by a quick reload (audit F10, part).** A full-page navigation while `/auth/me`
  was in flight cancelled the check, and the session provider treated the cancellation as a
  failure and cleared the session — reproduced on `/workspace → /calendar`, `/reading-list →
  /notifications` and `/dashboard → /workspace`, signed out in all six runs. The dashboard's
  timing exposed it in the browser suite (the theme test). Now a check cancelled while the page
  is being left is ignored; signed in afterwards in all six runs. Every answered failure still
  signs out, as before; the rest of F10 stays deferred.

## Screenshots

`light/` and `dark/`: `<role>-dashboard__<width>.jpg` at 1440, 390 and 320px for the seeded
student and faculty accounts, and `*-text-200-percent__320.jpg` (light). Only seeded demo data
appears.

## Known issues carried forward

- Notifications stay in the bell; the plan's "latest three" module waits for P8's shared list.
- Faculty "Needs your decision" reads at most three postings' applications (no aggregate
  endpoint, plan Q4); more postings with applications are named and linked.
- Faculty "Recommended papers" are papers similar to their newest paper (no endpoint recommends
  papers).
- Reserved heights leave space in a module with little to show (an empty account).
- `/auth/me`: a network error or 5xx while staying on the page still signs out, and a check that
  never answers keeps the skeleton (F10, deferred). `/supervisors` is guarded without a role
  (authorization, pre-existing).
- Measured in Chromium with simulated 200% text; no screen-reader pass (P11).
