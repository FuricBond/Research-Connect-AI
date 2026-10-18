# P5 evidence — search and discovery

Measured on 2026-10-17 against the isolated end-to-end stack (`python e2e/run_e2e.py --keep`,
then the frontend image rebuilt after each fix below): production images of the P5 working tree on
`main`, the seeded demo accounts and the literature corpus the API suite seeds. Every number comes
from `measurements.json` in this folder. The design is in
[DESIGN_SYSTEM.md §17](../../DESIGN_SYSTEM.md#17-search-and-discovery-p5). This is the phase's own
implementation check, not the independent audit (which covers all phases once they are done).

## Suites

The final working tree, in a clean run of `python e2e/run_e2e.py` (fresh database, torn down
afterwards): **PASS** — API 69/69, browser 23/23 (18 before P5; `discovery.spec.ts` adds 5, run
as a visitor so it uses none of the sign-in budget), stack 7/7. Unit tests (Vitest): 46 files,
519 tests (449 before P5); type-check, lint and the production build exit 0.

## Requests per page load

Counted as the browser made them, without the shell's session check (`/auth/me`) and unread count
(`/notifications/unread-count`), which every signed-in page makes.

| Page | Visitor | Signed-in student |
|---|---|---|
| Search (`/?q=…`) | 1: the search | 2: the search, the reading-list lookup (after the results) |
| Changing the sort | 0 (the page in hand is reordered) | 0 |
| Opening a paper's panel | +1: five similar papers | +1 |
| Calls for papers (`/browse`) | 1: the list | 2: the list, the tracked-calls lookup |
| A call (`/calls/[id]`) | 2, together: the call (with its deadline intelligence), its risk explanation | 3: + the tracked-calls lookup |

Similar papers and Find venues make one request per paper, filter set and page. Enforced by
`tests/search-page.test.tsx`, `calls-pages.test.tsx`, `paper-tools.test.tsx` and the e2e
`discovery.spec.ts` (the call page's two requests; one search per filter change; none for a sort).

## Layout shift (CLS)

PerformanceObserver `layout-shift` (buffered, without recent input) from navigation start until
the page settled; three runs per combination as a visitor, light theme; "varied" delays every API
answer by a random 50–800 ms.

| Page, width | Before the fixes (local / varied) | After (local / varied) |
|---|---|---|
| Search 1440 | 0.0708 / 0.0708 | **0.0009 / 0.0009** |
| Search 390 | 0.1147 / 0.1147 | **0.0006 / 0.0006** |
| Calls for papers 1440 / 390 | 0.0009 / 0.0007 | 0.0009 / 0.0007 |
| A call 1440 | 0.0009 / 0.0009 | 0.0009 / 0.0009 |
| A call 390 | 0.0226 / 0.0226 | **0.0007 / 0.0007** |

The remaining 0.0006–0.0009 is the shell header's visitor controls (Sign in, Create account)
settling, as on every public page since P3.

- **Search.** The page is prerendered without the URL, so its first paint was the start page (the
  example searches and the "Begin" message); a URL with a query then replaced it with the results
  layout, which moved up 104px (1440) or 179px (390). The first paint is now only the title and the
  search box; the start page or the results are added below it once the URL is read.
- **A call.** The title face (Source Serif 4, not preloaded — P1) was first requested when the
  title arrived; a long title wrapped onto one more line when the font swapped in and moved the
  page by 35px at 390px. The loading skeleton now carries a hidden line in the title face, so the
  font loads with the first paint.

## Accessibility and layout

| Check | Result |
|---|---|
| axe: visitor and student × light and dark × 1440/768/390/320 × search start, results, Evidence panel, paper panel, filter sheet, similar papers, Find venues, its Evidence panel at the risk part, calls, a call, call not found (160 runs) | **0** violations of any impact (two fixed on the way, below) |
| Horizontal overflow, same 160 | **0** |
| 200% text at 320px: results, Evidence panel, paper panel, similar papers, Find venues and its panel, calls, a call | overflow 0, no control off screen |
| Keyboard, from the page title through the search results (41 stops) and through a call's page | every stop named, every stop with a visible 2px ring |
| Headings | one h1 per page; h2 sections; h3 cards; panels: h2 title, h3 parts, h4 groups |
| Live regions | one polite status per list ("Searching papers…", "Still searching…", "45 results"); skeletons are busy, not live; a failure after an action is an alert |

Fixed on the way: the call page's risk evidence used h4 under an h2 (axe `heading-order`,
moderate); its groups are h3 there now (h4 stays inside the Evidence panel's h3 section). The
Evidence panel named the backend's real signals (`lexical_relevance`, `topic_compatibility`,
`deadline_urgency`, `publication_freshness`) by their raw names and drew a signal with no data as
"0 out of 100"; they now read "Search terms", "Topics"… and "Not available for this item". A
first scan of the filter sheet at < 1280px flagged `color-contrast` on its description and button:
axe ran during the sheet's 200 ms fade-in, when text is part-transparent; once open, the same
elements have no violation in either theme (the scan now waits for the fade).

## Screenshots

`light/` and `dark/`: `<page>__<width>.jpg` at 1440 and 390px as a visitor — the search start,
results, the Evidence and paper panels, similar papers, Find venues with its Evidence panel at the
risk part, calls for papers and a call — and `*-text-200-percent__320.jpg` (light). Only the
seeded demo data appears.

## Known issues carried forward

- **API limits, designed around:** the search response has no authors (no AuthorList); there is no
  "paper by id" endpoint (plan Q4), so a paper's details travel in the tab and a shared
  `/similar?paper=` link from another browser shows results without the paper's title; the search
  API has no sort (Newest and Most cited reorder the page, and say so); "upcoming" also leaves out
  calls with no listed deadline (so it starts off, plan Q10); the workspace lookup reads 100 items.
- **Bundle:** `/` is 136 kB first-load JS, as at P4 (the P12 budget for a typical route is 135 kB);
  `/browse` grew from 113 to 134 kB (the shared primitives and `useApiResource`), `/similar` fell
  from 136 to 132, `/opportunities` from 140 to 139; `/calls/[id]` is 134. The panels load with
  their first opening.
- **Not deleted** (the session could not delete files): `components/discovery/{ResearchResultCard,
  SimilarResearchCard,OpportunityCard,ExplainabilityDrawer,PaginationControls,DeadlineTimeline,
  QualityBadge}.tsx` and `styles/opportunities.css` are no longer used by any page
  (`DeadlineBadge` and `RiskWarning` only by `tests/deadline-risk.test.tsx`); the discovery rules
  in `styles/globals.css` are mostly unused. To remove with P12's legacy-CSS clean-up or before.
- The Checkbox primitive (P1) puts its `hint` inside the label, so a hint becomes part of the
  control's name; P5 links its hints with `aria-describedby` instead and leaves the primitive.
- Chromium with simulated 200% text only; no Firefox/Safari, real browser zoom or screen-reader
  pass (the final audit).
