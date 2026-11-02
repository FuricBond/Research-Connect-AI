# Performance baseline (before any redesign work)

Measured on 2026-10-06, commit `bd34264`, Windows 11 laptop, `next build` (Next.js 15.5.25)
and the production server in the Compose `frontend` container, API on localhost.
**Network was local, so timings are best-case; use them only to compare before/after on the
same machine.** Lighthouse was not run for this baseline (it is not installed and the audit adds no tools); P12
runs it from Chrome DevTools on the same routes.

## 1. Build output (first-load JavaScript)

| Route | Route JS | First load JS |
|---|---|---|
| Shared by all | — | **103 kB** (`1255-…` 46.4 kB, `4bd1b696-…` 54.2 kB, other 2.1 kB) |
| `/` | 5.82 kB | 128 kB |
| `/admin` | 4.93 kB | 119 kB |
| `/browse` | 2.24 kB | 112 kB |
| `/calendar` | 7.86 kB | 121 kB |
| `/login` | 3.19 kB | 117 kB |
| `/notifications` | 6.93 kB | 123 kB |
| `/opportunities` | 6.59 kB | 129 kB |
| `/peers` | 3.57 kB | 121 kB |
| `/postings` | 7.37 kB | 121 kB |
| `/postings/[id]` | 4.45 kB | 122 kB |
| `/postings/applications` | 2.42 kB | 120 kB |
| `/reading-list` | 5.01 kB | 119 kB |
| `/register` | 4.05 kB | 118 kB |
| **`/researcher`** | **53.5 kB** | **167 kB** |
| `/researcher/preferences` | 8.63 kB | 122 kB |
| `/settings/notifications` | 6.51 kB | 122 kB |
| `/similar` | 2.96 kB | 125 kB |
| `/submissions` | 1.8 kB | 118 kB |
| `/supervisors` | 4.01 kB | 121 kB |
| `/workspace` | 5 kB | 121 kB |
| `/workspace/[id]` | 5.89 kB | 123 kB |
| `/workspace/[id]/submission` | 9.51 kB | 126 kB |

All routes are `○ static` except the three dynamic ones; every page is a Client Component
that fetches after hydration.

## 2. CSS and fonts

- CSS: 10 files, **151,144 bytes** raw, **24,441 bytes** gzip (all global stylesheets are
  bundled; Tailwind contributes only used utilities).
- Fonts: **none downloaded** (`Inter` is declared but not loaded; OS fonts render).
- Images: none (icons are inline SVG from lucide-react).

## 3. Runtime (1440×900, warm cache, local API)

| Route state | LCP ms | CLS | API requests on load | Notes |
|---|---|---|---|---|
| public `/` | 160 | 0.001 | 0 | |
| public `/login` | 88 | 0.001 | 0 | |
| public `/browse` | 144 | 0.001 | 1 | 63 cards, no pagination |
| public `/postings` | 44 | 0.001 | 1 | |
| student search results | 44 | 0.001 | 4 | search + saved lookup |
| student `/postings` | 44 | 0.020 | 4 | |
| student `/postings/[id]` | 184 | **0.056** | 4 | fit panel pushes content |
| student `/postings/applications` | 108 | 0.029 | 4 | |
| student `/supervisors` | 108 | 0 | 3 | |
| student `/peers` | 96 | **0.066** | 4 | settings card loads late |
| student `/workspace` | 172 | **0.067** | 4 | cards replace spinner |
| student `/workspace/[id]` | 536 | 0 | **7** | members, tasks, invitations, activity in sequence |
| student submission | 476 | 0 | 4 | |
| student `/submissions` | 124 | 0.027 | 4 | |
| student `/reading-list` | 100 | 0.001 | 3 | |
| student `/calendar` | 104 | 0.004 | 4 | |
| student `/notifications` | 168 | 0.003 | 5 | **`unread-count` requested twice** (duplicate navbar) |
| student `/settings/notifications` | 112 | 0.002 | 6 | **`unread-count` twice** |
| student `/researcher` | 172 | 0.001 | **25** | 25,378px tall page |
| faculty `/researcher` | 184 | 0.001 | **25** | |
| admin `/admin` | 104 | 0.050 | 4 | freshness + users |

Steady state: every signed-in tab polls `GET /notifications/unread-count` every 30 s
(twice on the two notification pages).

No API errors (4xx/5xx) and no console errors on any route except the expected 404 resource
on the not-found page.

## 4. Observations that matter for the redesign

1. The JavaScript budget is healthy (≈ 120 kB first load); `/researcher` is the outlier
   (+46 kB) because it mounts ten large panels at once.
2. Layout shift comes from content replacing spinners; skeletons sized like the final
   content remove it.
3. Request fan-out: `/researcher` (25) and `/workspace/[id]` (7, partly sequential) are the
   heaviest. The proposed dashboard must stay within a budget (≤ 7 parallel requests).
4. There is no client cache: navigating back re-fetches everything.
5. Fonts will be the main *new* cost; budget ≤ 100 kB WOFF2 total, only the UI sans
   preloaded.

## 5. Budgets for the redesign (P12 acceptance)

Amended by the independent audit's decisions: each budget says exactly what is measured.

| Metric | Baseline | Budget | Checked by |
|---|---|---|---|
| Shared first-load JS | 103 kB | ≤ 110 kB | `check:bundle` |
| Route JS, Next build metric | 167 kB (`/researcher`) | ≤ 140 kB | `check:bundle` |
| Route JS, layout-inclusive | not measured | ≤ 140 kB | `check:bundle` |
| Typical route JS (Next build metric) | 112–129 kB | ≤ 135 kB | `check:bundle` |
| CSS (gzip), page and layouts | 24.4 kB | ≤ 28 kB | `check:bundle` |
| Fonts actually downloaded by a page | 0 | ≤ 100 kB, 1 preloaded file | `performance.spec.ts` |
| CLS, any route and tested width, real-data states included | ≤ 0.067 | ≤ 0.02 | `performance.spec.ts`, `remediation.spec.ts` |
| Route-specific API requests on load | ≤ 25 | ≤ 8 (dashboard ≤ 7, profile ≤ 6) | `performance.spec.ts`, `dashboard.spec.ts` |
| Duplicate requests | unread-count ×2 | 0 | `performance.spec.ts` |
| Lighthouse (DevTools, mobile preset) | 100 / 100 / 100 on all 5 pages, local stack, by hand on 2026-11-02 | Performance ≥ 90, Accessibility ≥ 95, Best practices ≥ 95 | met, [MANUAL_VERIFICATION.md](../MANUAL_VERIFICATION.md) |

**JavaScript: two build metrics and one measurement** (gzip level 9, 1 kB = 1000 bytes, from
`.next/app-build-manifest.json`):

- *Next build metric*: the JavaScript listed for a route's page, the figure `next build` prints.
- *Layout-inclusive*: the same plus the chunks of the layouts above the page, each counted once. This is what
  a page needs before it can start, and `next build` leaves it out for app routes.
- *Actual browser transfer*: every script file a visit downloads, including parts loaded on demand, in bytes
  on the wire. Not a budget. `performance.spec.ts` reports it, because the two build metrics do not count code
  loaded with `next/dynamic` or `React.lazy`. Budgets are met partly by moving code out of the first load, so
  this figure is what shows how much a visit still downloads.

**Requests**: *route-specific* requests are the ones a page makes itself. The shell makes two on every
signed-in page (`GET /auth/me`, `GET /notifications?limit=3`), reported separately and as a total, never
dropped from the report. *Sequential* requests started only after another of the route's requests answered
(fit scores after the postings; a faculty member's application lists after their postings). They are reported
separately and are not budgeted.

**Fonts**: the WOFF2 files a page's browser actually downloads, in bytes on the wire, including Latin-Ext and
italic files when the page uses them. Files on disk that a page never asks for do not count. A typical Latin
page downloads about 50 kB, and `/recommendations`, which has an italic heading, about 72 kB. **A page with
text needing Latin-Ext (Erdős, Łukasz) is over budget: about 129 kB, or 169 kB with italics.** That is the
files as published: `performance.spec.ts` records it as a known failure. Meeting the budget needs smaller
Latin-Ext files, which means re-subsetting them with a tool not in this project and renaming them, since the
licence reserves the font name for unmodified files.

**CLS**: measured on real-data states, not only the demo seed: `remediation.spec.ts` builds a faculty account
with two postings with applications, one with one, one with none, and failing and slow requests, at 1440,
1280, 768 and 390 px.

### Font transfer: over budget on some pages, deferred by decision

Optimizing the fonts is **deferred by the owner's explicit decision (2026-11-02)**. It was not overlooked, and
this budget is **not met**. No font file, family name or `@font-face` declaration was changed for it.

| Page | Measured transfer | Budget | State |
|---|---|---|---|
| A typical page in Latin | about 50.3 kB | ≤ 100 kB | within budget |
| A page with italic recommendations | about 71.9 kB | ≤ 100 kB | within budget |
| A page that needs Latin-Ext (names like "Erdős") | about 128.7 kB | ≤ 100 kB | **over by about 29 kB** |
| A Latin-Ext page with italics | about 169 kB | ≤ 100 kB | **over by about 69 kB** |

The overage is accepted for now. Clearing it means smaller Latin-Ext files, which means re-subsetting them with a
new tool. `performance.spec.ts` keeps it visible with `test.fail`: that test fails loudly the day the budget is
met, so this record cannot go stale unnoticed.

### What keeps pages small

- `services/api/` holds one module per area of the API. `services/api.ts` is a barrel. Webpack keeps, per
  module, every export any route uses, so a single file put every function on every page.
- `next.config.ts` marks `services/api` and `components/ui` as side-effect free, so a barrel import pulls only
  what is used; and it shortens CSS module class names in production, whose maps sit in every page's JavaScript.
- The shell's rarely used parts load when about to be used: the navigation drawer, the search sheet, the
  bell's panel, the account panel.
- A page only an account can see loads behind its guard (`utils/preloadForSession.ts` starts it with the
  session check, so nobody waits for one and then the other). A dashboard loads per role.

