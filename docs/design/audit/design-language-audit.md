# Design language audit

Every stylesheet and design token in `frontend/styles` and every `className`/`style` in
`frontend/app` and `frontend/components` was scanned at commit `bd34264`. Counts are exact
(grep over the source); "distinct" means unique values.

## 1. What exists

| Area | Found |
|---|---|
| Stylesheets | 11 files, 7,490 lines: `globals.css` 2,702 · `submission.css` 1,042 · `calendar.css` 724 · `collaboration.css` 651 · `workspace.css` 583 · `notifications.css` 572 · `postings.css` 508 · `auth.css` 411 · `peers.css` 162 · `opportunities.css` 133 · `tailwind.css` 2 |
| Tokens defined | **33** custom properties, all in `globals.css :root` (colours, 4 radii, 4 shadows, 1 font stack) |
| Tokens used but never defined | **11**: `--color-primary` (44 uses, 33 without fallback), `--bg-hover` (43 / 35), `--bg-main` (36 / 26), `--color-border` (24), `--color-text-muted` (23), `--primary-accent` (16 / 7), `--color-surface` (16), `--color-text` (5), `--bg-surface` (4), `--text-color` (2 / 2), `--bg-card-header` (2) |
| Tailwind | Utilities only, preflight off, default palette; used by 13 personalization/intelligence components |
| Inline styles | **910** `style={{…}}` objects; 9 components have **zero** class names (all inline) |
| Fonts | `Inter` named, never loaded (no `@font-face`, no `next/font`) |
| Breakpoints | **2** media queries for layout (`max-width: 768px` in globals, `860px` in submission) |
| Dark mode | none designed; `prefers-color-scheme: dark` in `peers.css` and `postings.css`; **414** Tailwind `dark:` classes |
| Reduced motion | 1 query (`auth.css`) |

The result is three coexisting design languages, one per build era:

1. **Global classes** (Phases 2, 5, 6: discovery, postings, auth, workspace) — closest to a
   system, uses most of the 33 tokens.
2. **Tailwind panels** (Phases 3–4: personalization) — default Tailwind palette: slate 576,
   gray 269, **indigo 180**, emerald 126, amber 89, **purple 83**, rose 82, blue 73 … teal 3.
3. **Inline-style views** (Phase 3.x: researcher profile, preferences, history) — hex colours
   written directly in TSX (472 hex literals in `.tsx` files).

## 2. Extracted values

**Colours.** 689 hex literals in CSS (**121 distinct**), 80 `rgb()/rgba()/hsl()` literals,
472 hex literals in TSX. Two neutral ramps compete (Tailwind *slate* `#64748b #94a3b8
#cbd5e1 #e2e8f0` and *gray* `#6b7280 #4b5563 #e5e7eb #f3f4f6`); four reds (`#dc2626 #b91c1c
#991b1b #ef4444`); seven greens (`#15803d #166534 #16a34a #10b981 #059669 #047857 #065f46`);
three blues as primaries (`#2563eb #3b82f6 #1d4ed8`); violet/indigo (`#8b5cf6 #6d28d9 #4f46e5
#4338ca`). The brand `#0f766e` appears as a literal 13 times.

Top literals: `#ffffff` 85 · `#64748b` 67 · `#e2e8f0` 57 · `#f8fafc` 29 · `#dc2626` 27 ·
`#991b1b` 25 · `#94a3b8` 25 · `#b91c1c` 24 · `#2563eb` 23 · `#ef4444` 21.

**Typography.** **41** distinct `font-size` values mixing px and rem, including near-duplicates
(`13px`, `13.5px`, `0.8125rem`, `0.82rem`, `0.84rem`, `0.85rem`, `0.86rem`, `0.875rem`,
`0.88rem`). Top: 13px (38), 12px (27), 11px (25), 0.875rem (19), 0.85rem (16), 14px (15).
Font weights: 600 (118), 700 (66), 500 (19), 650 (4), 400 (2), 800 (1). 25 uses of 11px or
smaller text.

**Spacing.** **50** distinct padding/margin/gap values: 8px (107), 6px (93), 12px (76), 16px (70),
4px (64), **10px (63)**, 24px (57), **14px (48)**, 2px (39), 20px (32), **18px (21)**, 0.6rem
(18), 3px (17), 5px (14), 0.35rem, 0.3rem, 0.15rem … — no rhythm; px and rem mixed.

**Radii.** 21 distinct values: token uses (`--radius-sm/md/lg/full`) plus 4px (29), 6px (14),
10px (9), 50% (8), 3px (7), 9999px (6), 999px (5), 8px, 12px, 24px — and fallbacks that
disagree with their own token (`var(--radius-md, 8px)` while `--radius-md` is 10px;
`var(--radius-sm, 4px)` while it is 6px).

**Shadows.** 4 tokens plus 9 literal shadows, including focus-like rings in blue
(`rgba(37,99,235,.15)`) and teal, and pulsing red rings (`pulse-border`).

**Motion.** 57 × 0.15s, 5 × 0.2s, 2 × 0.3s, plus 0.9s, 1s, 1.5s, 2s loops (`pulse`,
`pulse-border`, `spin`, `slide`, `fade`). Only one reduced-motion query.

**Z-index.** 8 unrelated values: −1, 1, 2, 10, 40, 50, 100, 1000.

**Breakpoints.** 768px and 860px only. No tablet or desktop breakpoints; layouts rely on
flex-wrap.

## 3. Duplicated and conflicting patterns

| Pattern | Count | Examples |
|---|---|---|
| Button classes | **41** | `.action-btn .primary-btn .btn-primary .posting-btn .collab-btn-primary .notifications-btn-primary .workspace-action-btn .calendar-add-btn .search-submit-btn .retry-btn …` |
| Card classes | **49** | `.research-card .opportunity-card .workspace-card .posting-card .peer-card …` |
| Badge/pill/chip/tag classes | **90** | `.nav-pill .quality-badge .citation-pill .oa-badge .posting-skill .peer-chip …` |
| Header/title classes | **73** | `.page-intro .results-header .drawer-title .preferences-section-title …` |
| Empty/error/loading classes | **23** | `.empty-state .postings-empty .workspace-empty-state .collab-empty-state .notifications-empty …` |
| Spinners vs skeletons | spinners in 20 files, skeleton in 1 | |
| "Explain this score" UIs | 3 | ExplainabilityDrawer, WhyThisRecommendationModal, RecommendationExplanationModal |

## 4. Design-system violations (to be fixed by the redesign)

| # | Violation | Severity |
|---|---|---|
| V1 | 103 property values use undefined tokens with **no fallback** (`--color-primary`, `--bg-hover`, `--bg-main`, `--primary-accent`, `--text-color`) → the intended colours/hover states never render in collaboration, submission, notifications and calendar | P1 |
| V2 | A second, undefined token namespace (`--color-*`) in `auth.css`, `peers.css`, `postings.css` survives only through fallbacks | P1 |
| V3 | Fonts declared but not loaded → OS-dependent rendering | P1 |
| V4 | Partial dark mode (2 media blocks + 414 `dark:` classes) with a light-only app | P1 |
| V5 | Three primary colours (teal, blue, indigo/purple) | P1 |
| V6 | Colour-only status in places (priority colours, match colours) | P1 (a11y) |
| V7 | 121 distinct colours, 41 font sizes, 50 spacing values, 21 radii, 8 z-indexes | P2 |
| V8 | Token fallbacks that contradict tokens (radius) | P2 |
| V9 | Page stylesheets imported across pages (reading list and supervisors import `peers.css` + `postings.css`) → change one page, break another | P2 |
| V10 | Tailwind arbitrary values: 118 (e.g. `text-[10px]`, `bg-gray-50/50`) | P2 |
| V11 | Decorative infinite animations (`pulse`, `pulse-border`) without reduced-motion handling | P2 |
| V12 | Underlined nav links and browser-default link colours (DOIs, supervisors, reading list) — no Link component | P2 |
| V13 | CSS/Tailwind conflict risk: preflight off, so Tailwind panels inherit global element styles (e.g. `button`, `h3`) differently from page CSS | P3 |

## 5. What to keep

- The petrol-teal brand (`#0f766e`) — recognisable, not a generic AI colour; refined to
  `#0E6B66` for contrast headroom.
- The postings pages' structure (title, metadata row, fit line, chips) — the best existing
  pattern, generalised into the research cards.
- `RequireAuth`'s three states and wording, the BibTeX/ICS export flows, the posting
  OpeningTermsPanel content.
- lucide-react icons.
