# Performance baseline (before any redesign work)

Measured on 2026-10-06, commit `bd34264`, Windows 11 laptop, `next build` (Next.js 15.5.25)
and the production server in the Compose `frontend` container, API on localhost.
**Network was local, so timings are best-case; use them only to compare before/after on the
same machine.** Lighthouse was not run (it is not installed and the audit adds no tools); P12
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

| Metric | Baseline | Budget |
|---|---|---|
| Shared first-load JS | 103 kB | ≤ 110 kB (+7 kB for the UI primitives) |
| Largest route first-load JS | 167 kB (`/researcher`) | ≤ 140 kB |
| Typical route first-load JS | 112–129 kB | ≤ 135 kB |
| CSS (gzip) | 24.4 kB | ≤ 28 kB, then lower as legacy CSS is deleted |
| Fonts (WOFF2) | 0 | ≤ 100 kB, 1 preloaded file |
| CLS (any route, local) | ≤ 0.067 | ≤ 0.02 |
| API requests on load | ≤ 25 | ≤ 8 per route (dashboard ≤ 7, profile ≤ 6) |
| Duplicate requests | unread-count ×2 | 0 |
| Lighthouse (DevTools, mobile preset) | not measured | Performance ≥ 90, Accessibility ≥ 95, Best practices ≥ 95 |
