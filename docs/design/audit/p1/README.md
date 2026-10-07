# P1 evidence — the Scholarly Ledger design system

Measured on 2026-10-07 against the Compose dev stack (production build, the
`design.audit.*` accounts). **Before** is commit `41d2d8f` (P0 final); **after** is the P1
working tree. Every number below comes from `measurements.json` in this folder or from the
commands named next to it.

## Results

20 states — public search and its "Why this rank?" drawer, registration form, signed-in home
(loaded, loading and failed), profile, profile edit form, recommendations and its "Why this
recommendation?" dialog, personalization, workspace, Similar Research and the Opportunity
Matcher with a paper chosen, notifications, notification settings, calendar, faculty postings,
an empty workspace, admin.

| Measure (20 states × 1440 and 390px) | Before, light | Before, dark (OS) | After, light | After, dark |
|---|---|---|---|---|
| axe critical (rule hits / elements) | 4 / 4 | 4 / 4 | **0 / 0** | **0 / 0** |
| axe serious | 34 / 962 | 34 / 1,006 | **0 / 0** | **0 / 0** |
| axe moderate | 12 / 14 | 12 / 14 | **0 / 0** | **0 / 0** |
| colour-contrast elements | 960 | 1,004 | **0** | **0** |
| "islands" (large panels in the opposite theme) | 215 | 240 | **0** | **0** |
| page-level horizontal overflow, 360 and 320px | 1 of 40 | — | **0 of 40** | **0 of 40** |

Before, "dark" meant the OS in dark mode: the page stayed light while Tailwind panels turned
dark (the half-dark problem). After, the app has one theme at a time, chosen by the person
(light, dark or system) and applied before first paint.

Every list that shows a call's deadline or venue risk now uses the canonical indicators
(home, workspace, recommendations, the candidate and ranking previews, submissions, the
submission banner and the explanation drawer). Before, the recommendations list printed
"Risk: INSUFFICIENT EVIDENCE" in green and the candidate preview called an unassessed venue
"Low Risk"; `frontend/tests/canonical-indicators.test.tsx` now guards both. The personalization
section had two h1s; its profile card is now an h2 under the section's h1, and each of the 28
main pages checked (public, student, faculty, admin) has exactly one h1.

The P0 suites still pass on the P1 build: page overflow 0 of 301 states (4 roles, 43
routes, 7 widths), navigation 28 of 28 role × width combinations, home 5/5/4 requests with
the four expected deadlines, profile default section 3 requests, back/forward and reload,
both paper flows, focus on the chosen paper, the profile-save refresh, and the
"Why this rank?" drawer and "Why this recommendation?" dialog fitting a 390px screen.

## Styling metrics (`frontend/app`, `components`, `styles`)

| | Before | After |
|---|---|---|
| Hex colour literals in CSS / TSX | 671 / 463 | 60 (all in `tokens.css`) / **0** |
| `rgb()`/`hsl()` in CSS / TSX | 80 / 83 | 12 (tokens, `color-mix`) / **0** |
| Distinct colours | 144 | 54 (the token palette) |
| Tailwind `dark:` classes | 409 | **0** |
| Tailwind arbitrary values | 117 | 5 |
| `--rc-*` token uses | 0 | 1,940 |
| Text below 12px | 272 (62 CSS, 99 inline, 111 Tailwind) | **0** |
| Gradients | 9 | **0** |
| All-caps labels (`text-transform: uppercase`) | 100 | **0** |
| Inline `style={{…}}` objects | 900 | 869 (ratchet in `tests/design-tokens.test.ts`) |

## Performance

| | Before (`41d2d8f`) | After |
|---|---|---|
| Shared first-load JS | 103 kB | 103 kB |
| Route first-load JS | 113–169 kB | 113–171 kB (+2 to +7 kB on most routes: primitives, indicators and the theme switcher) |
| CSS, all chunks (gzip) | 31.2 kB | 36.5 kB |
| CSS loaded by a route (gzip) | 15.6–18.0 kB | 20.7–23.7 kB (tokens for both themes +2.4 kB, primitive modules 3.3 kB; shared and cached across routes) |
| Fonts downloaded on a typical page | 0 (OS font) | 50.9 kB (Source Sans latin, preloaded; Source Serif latin) |
| CLS `/dashboard` 1440 / 390 | 0.077 / 0.266 | **0.019–0.025 / 0.061** (the deadline list growing past its three-row skeleton) |
| CLS `/workspace` 1440 / 390 | 0.037 / 0.224 | 0.038 / 0.229 (unchanged; see known issues) |
| CLS other measured routes | ≤ 0.026 | ≤ 0.030 |
| LCP (local, cold) | 48–188 ms | 48–208 ms (two runs) |

Fonts: six WOFF2 files, 169 kB committed; the latin-ext files (97.5 kB) download only when a
page contains characters outside Latin-1.

## Screenshots

`after/light`, `after/dark`: every state above at 1440 and 390px (`<state>__<width>.jpg`).
`before/light`, `before/dark`: the same states at 1440px, for comparison. No screenshot shows
another person's data (the admin accounts table is below the fold).

## Known issues carried forward

- `/workspace` shifts layout at 390px (CLS 0.22, identical before P1): the page's content
  briefly gives way to the sign-in check after first paint. A session-restoration issue for P2.
- Legacy components still use Tailwind hue names (`indigo`, `emerald` …) and inline styles;
  they now resolve to the tokens, and are replaced when their pages are migrated.
- On phones, the stat-card rows of notifications, workspace and calendar stack one per line and
  push the page's content below the fold; those pages also keep their own headers rather than
  `PageHeader`. Both belong to the page rebuilds (P2 onward).
- Product-level items outside P1: primary buttons on every search card, two clear buttons in
  the search box, raw sub-scores ("Semantic 73%"), personalization diagnostics wording and stat
  cards — P5 (search) and P6 (personalization).
