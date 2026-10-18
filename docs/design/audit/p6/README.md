# P6 evidence — personalization and profile

Measured on 2026-10-18 against the isolated end-to-end stack (`python e2e/run_e2e.py --keep`, the
frontend image rebuilt after each fix below): production images of the P6 working tree on `main`,
the seeded demo accounts (Chromium through Playwright). Every number comes from
`measurements.json` in this folder. The design is in
[DESIGN_SYSTEM.md §18](../../DESIGN_SYSTEM.md#18-personalization-and-profile-p6). This is the phase's
own implementation check, not the independent audit (which covers all phases once they are done).

## Suites

The final working tree, in a clean run of `python e2e/run_e2e.py` (fresh database, torn down
afterwards, `e2e/results/20261018T065458Z`): **PASS** — API 69/69, browser 23/23, stack 7/7. The
first run of the P6 tree failed two browser steps (P6's own new ones): the live API exposed the
contract drift described below; after the fix the browser suite passed on the kept stack, then in
the clean run. Unit tests (Vitest): 51 files, 551 tests (519 before P6). Type-check, lint (one
warning, in the untouched submission page) and the production build exit 0.

## Requests per page load

Counted as the browser made them, without the shell's session check (`/auth/me`) and unread count
(`/notifications/unread-count`), which every signed-in page makes; the seeded student, light theme,
1440×900, after the page settled.

| Page | Requests |
|---|---|
| Profile (`/researcher`) | 3 for the seeded student and faculty (the profile, its research topics, the preference record; neither demo profile is linked to a scholarly record); 4 for a linked profile (+ its publications), measured by answering the faculty's profile as linked through request interception (test only). With the shell's two: **5 and 6**, within the limit of 6 |
| Recommendations | 4: the ranking, the preference record, the personalization settings, the tracked calls |
| "Why this match?" | +1 (how preferences and activity shaped it); its Technical details +2 (evidence tiers, preference assessment) |
| Technical details, per part opened | ranking comparison 0 (the page's own), research context 1, summary 1, preferences in detail 0 (the page's own), calls considered 1, learned signals 2, calibration 1, quality 1, health and drift 3, feedback 2, history 2, settings changes 1, protection 0 |
| Find a supervisor | 1 (a faculty account: 0 — the page explains itself and asks nothing) |
| Find peers | 2: your discoverability and the matches |
| Research postings (Discover, student) | 2: the list and one batch of fits |

Enforced by `tests/researcher-profile.test.tsx` (exactly the four, nothing of the recommendations),
`recommendations-page.test.tsx` (the four, no diagnostic request until a part is opened) and
`supervisors-page.test.tsx`.

## Profile height

`/researcher` at 1440×900: **1,308px, 1.45 screens** for the seeded student, 1,190px (1.32) for the
faculty and 1,217px (1.35) linked (limit 3). Measured as `document.documentElement.scrollHeight`
after the page settled. Publications show five, then "Show all"; topics show six, then "Show all".

## Layout shift (CLS)

PerformanceObserver `layout-shift` (buffered, without recent input) from navigation start until
the page settled; three runs per combination, the seeded student, light theme.

| Page, width | First build | Final |
|---|---|---|
| Recommendations 1440 | 0.4145 / 0.4738 / 0.5330 | **0.0033 / 0.0038 / 0.0042** |
| Recommendations 390 | 0.5988 / 0.6587 / 0.7186 | **0.0006 / 0.0007 / 0.0007** |
| Profile 1440 | 0.0024 / 0.0062 / 0.0093 | **0.0011 / 0.0023 / 0.0034** |
| Profile 390 | 0.0213 / 0.0266 / 0.0319 | **0.0063 / 0.0079 / 0.0094** |

- **Recommendations.** The technical details below the list, and on phones the panel below it,
  were drawn while the list loaded and then pushed down by 25 cards. They now appear once the first
  list is in; the panel's parts appear together once both of its requests have answered; the loading
  skeleton carries a hidden line in the card title face so the font loads with the first paint. A
  re-ranking (after a change in the panel) keeps the last list on screen until the new one is in.
- **Profile.** The sections below the summary appear together once their first answers are in.

## Accessibility and layout

| Check | Result |
|---|---|
| axe: light and dark × 1440/768/390/320 × recommendations, its Evidence panel, all its technical parts open, the reset dialog, the profile, the profile being edited, Find a supervisor, Find peers, Research postings; and a faculty account on Find a supervisor (73 runs) | **0** violations of any impact |
| Horizontal overflow, the same pages and states | **0** (one fixed on the way, below) |
| 200% text at 320px: recommendations, profile, supervisors, peers, postings | overflow 0, no control off screen (three fixed on the way) |
| Text that leaks code ("undefined", "NaN", "[object Object]"), every page and state above | none |
| Keyboard on `/recommendations`, the first 60 stops after the title | every stop named, every stop with a visible 2px ring |
| Headings | one h1 per page; h2 sections (each "Because you follow …" group, Technical details, What shapes your recommendations); h3 cards and parts; h4 groups |
| Live regions | one polite status for the list ("10 calls, ranked …", "Ranking again with your change…"); feedback, removal, switches and reset confirm politely; failures after an action are alerts |

## Fixed on the way

- **Contract drift found by the live suite** (the browser suite failed twice before these): the
  frontend types for the Phase 3.8 explanation, the Phase 5.9 personalization explanation, the
  learned-signal item and the feedback source had drifted from the backend schemas. Feedback was
  sent with `source: "RECOMMENDATION_FEED"` (422; the old ranking preview sent the same), the
  explanation's `confidence` is a number (a word was expected — the page threw), its factors carry
  `title`/`description`, its negatives are `negative_signals`, and the 5.9 factors come in four
  lists with `deterministic_explanation`. The types now follow `app/schemas/…`; every field the P6
  pages read was then checked against the live responses (`humanizeEnum` no longer throws on a
  number). The old modals and summary view read the same missing fields; they now compile against
  the corrected types but are no longer used.
- **Visually hidden text escaped table scrollers**: a hidden caption or label inside `.rc-scroll-x`
  is absolutely positioned, and the scroller was not its containing block, so it widened the page
  (146–216px at 390/320 with the feedback log open). `.rc-scroll-x` is now `position: relative`.
- **200% text**: the Switch's state word ("Discoverable") could not wrap (the row now wraps), a long
  availability badge did not wrap (it does on the researcher card), and "What shapes your
  recommendations" could not break its long word (it can).
- The people pages and postings had the page header inside a container that also spaced it
  (a doubled gap); posting titles were h2 under an h2 (now h3).
- Reasons are shown without the backend's leading marks ("✓", "⚠️"), matched topics once whatever
  their case, and enum suffixes in words ("(primary expertise)").

## Screenshots

`light/` and `dark/` — `recommendations`, `recommendations-why` (the Evidence panel),
`recommendations-technical` (every part open), `researcher`, `supervisors`, `peers`, `postings`, each
at 1440 and 390; `light/recommendations-text-200-percent__320.jpg` and
`light/researcher-text-200-percent__320.jpg`. Full-page captures: the Evidence panel is a drawer
over the first screen, so the rest of the page shows below it. The seeded demo accounts only;
no real person's data.

## Not verified here

Chromium only (no Firefox or Safari run); browser zoom simulated with a 200% root font size; no
screen-reader session (names, roles and live regions were checked through the accessibility tree
and axe). The independent audit after all phases covers these.
