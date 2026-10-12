# P2 evidence — the application shell

Measured on 2026-10-12 with local production builds (`next build` + `next start`) against the
Compose dev backend and the synthetic `design.audit.*` accounts. **Before** is commit `2b4a21c`
(P1 final, built in a temporary worktree); **after** is the P2 working tree on
`design/frontend-redesign-p2`. Every number comes from `measurements.json` in this folder.
The design of the shell is in [DESIGN_SYSTEM.md §14](../../DESIGN_SYSTEM.md#14-application-shell-p2).

## Shell audit (280 page loads + 56 open states)

4 roles (visitor, student, faculty, admin) × light and dark × 1440, 1280, 1024, 768, 390, 360
and 320px × 2–9 routes each; then the account menu, the visitor's Appearance menu, the
navigation drawer and the search sheet opened at 1440, 390 and 320px.

| Check | Result |
|---|---|
| Page-level horizontal overflow | **0 of 280** loads, **0 of 56** open states |
| Primary navigations displayed | exactly 1 from 1024px; 0 below until the drawer opens |
| Banner / main landmarks per page | 1 / 1 |
| Duplicate `id`s | none |
| `h1` per page | 1 |
| `aria-current="page"` links in the displayed navigation (from 1024px) | 1, except where another shell control is the current page's link: `/notifications` (the bell), `/researcher` and `/settings/notifications` (the account menu), and `/login` (none) |
| Header height | 56px at every width |
| `/auth/me` per load | 1 with a stored session, 0 without |
| Unread-count requests per load | 1 signed in, 0 for a visitor |
| axe critical / serious | **0 / 0** (136 runs) |
| axe moderate | 20 hits, all in page content and identical on the baseline build: `heading-order` (the search page's landing `h4`; the posting cards' `h3` on reading list, supervisors and applications) and `landmark-unique` (supervisor cards' sections) |
| Theme | `data-theme` matched the chosen theme on every load; "Match system theme" followed the OS (dark → dark, light → light) |

## `/workspace` session restore (P2.7)

| CLS | Before | After |
|---|---|---|
| 390px | 0.221 / 0.229 | **0.000 / 0.000** |
| 1440px | 0.038 / 0.038 | **0.000 / 0.000** |

Before: the first paint showed the visitor's navigation and a small "Checking your session" box;
the signed-in navigation, then the page, then the five stat cards (one per line on a phone)
arrived in turn and pushed the filters and list below the fold. Most of the shift was the stat
strip arriving after the data, not the session check itself. After: until `/auth/me` answers,
the navigation shows placeholder rows, the header reserves the account controls' room and the
page shows a page-shaped skeleton with the status "Checking your session…"; the workspace then
renders its stat strip with placeholders until its numbers arrive, and its tab counts read "–"
rather than a false "0". Same four requests as before (session, unread count, workspace,
summary); nothing protected is requested or shown before the session is known.

## Performance (same machine and data, two cold loads each)

| | Before | After |
|---|---|---|
| Shared first-load JS | 103 kB | 103 kB |
| Route first-load JS | 103–172 kB | 103–172 kB (unchanged on every route; page JS +0 to +0.3 kB, `/` +0.3 kB for the URL query) |
| CSS, all chunks (gzip) | 36.4 kB | 37.3 kB (+0.9) |
| CSS loaded by a route (gzip) | 17.2–23.7 kB | 23.3–25.6 kB: the shell's primitives (button, field, dialog, skeleton) now load with the layout on every page; one shared, cached file |
| API requests per route | — | unchanged on all 7 routes measured |
| LCP (local) | 48–168 ms | 40–172 ms (within run-to-run noise) |
| CLS, other routes | ≤ 0.041 | ≤ 0.053; `/dashboard` varies by run on both builds (0.004–0.053 before, 0.002–0.09 after) with the same source: a home module growing as its data arrives. The shell's own shifts measure 0.000. |

The unread count is now state of the bell alone, so its 30-second refresh re-renders the bell,
not the whole navigation (before, the count lived in the navigation bar).

## Screenshots

`light/` and `dark/`: `<state>__<width>.jpg` at 1440, 390 and 320px — public search, student
home, student workspace, faculty postings, admin overview, notifications, account menu open,
the visitor's Appearance menu open, navigation drawer open (phones), global search (header field
from 768px, search sheet below), search results opened from the URL, and `/workspace` while the
session is being restored. Only the synthetic `design.audit.*` accounts and the seeded demo
records appear; the administration page's accounts table is masked.

## Known issues carried forward

- The moderate axe findings above (heading levels in page content), for the page rebuilds.
- The home page's "Continue your work" tiles and several page titles still use the old names
  ("Browse All Calls", "Opportunity Workspace") while the navigation says "Calls for papers" and
  "Workspace" — terminology cleanup belongs to the page phases.
- `/dashboard` CLS varies with the order its modules' data arrives (P3/P4).
- Search filters and pagination are not yet in the URL (P5); only the query is.
