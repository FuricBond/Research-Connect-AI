# ResearchConnect AI — Design System

> Status: **proposal for review** (planning phase). Nothing here is implemented yet.
> Tokens: [`tokens.draft.css`](tokens.draft.css) (not imported by the app).
> Evidence: [`audit/`](audit/README.md). Rollout: [`FRONTEND_REDESIGN_PLAN.md`](FRONTEND_REDESIGN_PLAN.md).

This document is written so that another frontend engineer can build every screen without
guessing. Where it says **must**, a review should block a change that does otherwise.

---

## 1. Identity: "Scholarly Ledger"

ResearchConnect AI helps people make research decisions: what to read, where to submit, which
opening to apply for, whom to work with. The interface should read like a well-edited journal
and behave like a precise instrument.

| Attribute | How it shows up | What it rules out |
|---|---|---|
| Academic | Serif titles for research objects (papers, calls, postings) and page titles; ruled lines; citation-style evidence markers `[1]` | Marketing hero sections, illustrations, emoji |
| Intelligent | Every score comes with its reason, in words, next to the number | Unexplained percentages, "AI magic" sparkles |
| Trustworthy | One brand colour; red only for danger and high risk; unknown is shown as unknown, not as a warning | Alarm colours for missing data |
| Precise | Tabular numerals, aligned metadata rows, consistent units ("3 days left", never "2.7978d") | Raw floats, raw enum values (`IN_APP`, `INSUFFICIENT_EVIDENCE`) |
| Calm | Paper-white background, hairline borders, almost no shadows, short motion | Gradients, glass, bouncing, pulsing |
| Professional | Sentence case, one term per concept, no internal phase labels | "Phase 2.7 Intelligence Engine" in the UI |

**Why not the current look?** The audit found a teal brand used 13 times next to 121 other
hex colours, blue and violet primaries on some pages, three styling systems, and internal
roadmap labels visible to users ([audit/design-language-audit.md](audit/design-language-audit.md)).
The direction keeps the petrol-teal brand for continuity and replaces everything else with a
small, enforced system.

---

## 2. Principles (decision rules)

1. **Content first, chrome second.** Research objects get the strongest typography; UI chrome
   (nav, toolbars, labels) stays quiet.
2. **One primary action per view.** A card may have one primary action at most; a list of
   cards has *no* primary buttons on every card (use a quiet action row).
3. **Meaning never by colour alone.** Every coloured signal also has an icon or a word.
4. **Show the reason next to the score.** A number without a "because" is not shown.
5. **Unknown is neutral.** Missing data uses neutral styling and the word "Not assessed".
6. **Progressive disclosure for internals.** Raw scores, weights and signal IDs live behind
   "Technical details", never on the default surface.
7. **Same thing, same look.** One `Button`, one `Card`, one `StatusBadge`; no page-local variants.
8. **Density by default, not by force.** Lists are compact rows; detail pages are spacious.

---

## 3. Colour

### 3.1 Semantic roles (light / dark)

| Token | Light | Dark | Use |
|---|---|---|---|
| `--rc-bg` | `#F7F6F3` | `#111315` | Page background ("paper") |
| `--rc-surface` | `#FFFFFF` | `#181B1E` | Cards, panels, table body |
| `--rc-surface-sunken` | `#F0EEE9` | `#0D0F10` | Wells, code, filter rail, table header |
| `--rc-surface-raised` | `#FFFFFF` + shadow | `#1F2327` + ring | Menus, popovers, dialogs |
| `--rc-surface-selected` | `#E7F2F0` | `#14302D` | Selected row, current nav item |
| `--rc-border` | `#E2DED6` | `#2C3136` | Decorative hairlines and card edges |
| `--rc-border-control` | `#8A8478` | `#6B737B` | Input, checkbox, select boundaries (≥ 3:1) |
| `--rc-border-strong` | `#B9B3A7` | `#6B737B` | Section rules, table header rule |
| `--rc-text` | `#1B1A18` | `#ECEAE6` | Primary text |
| `--rc-text-secondary` | `#47443F` | `#C4BFB6` | Body copy in dense lists, descriptions |
| `--rc-text-muted` | `#615D56` | `#A19C93` | Metadata. **The lightest text allowed.** |
| `--rc-text-disabled` | `#B9B3A7` | `#6B737B` | Disabled controls only |
| `--rc-brand` | `#0E6B66` | `#5FBDB3` | Primary buttons, active nav marker, meters |
| `--rc-brand-hover` | `#0A5450` | `#7FCFC6` | Hover/pressed brand |
| `--rc-brand-subtle` | `#E7F2F0` | `#14302D` | Brand-tinted backgrounds |
| `--rc-brand-text` / `--rc-link` | `#0B5C57` | `#7FCFC6` | Links and brand-coloured text |
| `--rc-focus-ring` | `#0E6B66` | `#7FCFC6` | Focus indicator |
| `--rc-info` / `-subtle` | `#1D5A9E` / `#E8F0FA` | `#8AB8EC` / `#14263A` | Neutral information, "under review" |
| `--rc-success` / `-subtle` | `#1B6E3F` / `#E6F3EA` | `#7CCB98` / `#132A1C` | Completed, accepted, low risk |
| `--rc-warning` / `-subtle` | `#8A5300` / `#FBF1DC` | `#E8B65C` / `#2E2311` | Caution, risk "caution" |
| `--rc-danger` / `-subtle` | `#B42318` / `#FCEBE9` | `#F19A90` / `#341614` | Errors, destructive actions, high risk |

Text on the brand fill is white in light mode and near-black (`#0D0F10`) in dark mode.

### 3.2 Research data colours

These encode research meaning. They are separate from feedback colours so that, for example,
a low match never looks like an error.

**Match, relevance and fit — one sequential petrol scale**

| Band | Threshold (display only) | Light (bg / fg) | Label |
|---|---|---|---|
| Strong | ≥ 70% | `#0E6B66` / `#FFFFFF` | "Strong match" / "Strong fit" |
| Good | 45–69% | `#DCEEEA` / `#0B5C57` | "Good match" |
| Partial | 25–44% | `#F0EEE9` / `#47443F` | "Partial match" |
| Weak | < 25% | outline / `#615D56` | "Weak match" |

Bands are a *presentation* of the scores the backend already returns; they do not change
ranking. The exact percentage is always available in text (badge `title` is not enough:
it is in the accessible name and in the Evidence panel).

> Open question Q3: the thresholds above are a proposal; they should be validated against the
> distribution of real scores (the audit saw search relevance between 35% and 56% for good
> results, which is why raw percentages read as "bad" today).

**Venue risk — shield icon + word + colour (filled badge)**

| Level | Icon | Light fg / bg | Label |
|---|---|---|---|
| Low | `ShieldCheck` | `#1B6E3F` / `#E6F3EA` | "Low risk" |
| Caution | `ShieldAlert` | `#8A5300` / `#FBF1DC` | "Caution" |
| High | `ShieldX` | `#B42318` / `#FCEBE9` | "High risk" |
| Not assessed | `ShieldQuestion` | `#615D56` / dashed `#B9B3A7` | "Not assessed" |

`INSUFFICIENT_EVIDENCE` maps to **Not assessed** (neutral). Today it renders as a red
"Risk: INSUFFICIENT_EVIDENCE" on every saved call ([audit P0-5](audit/visual-ux-audit.md)).

**Deadline urgency — clock icon + countdown text (no filled badge until 48 h)**

| State | Rule | Style | Text |
|---|---|---|---|
| Open | > 7 days | `--rc-data-deadline-fg`, regular | "Due 27 Oct · 21 days left" |
| Soon | ≤ 7 days | orange text `#A33F07`, semibold | "Due 9 Oct · 3 days left" |
| Urgent | ≤ 48 h | orange text on `#FCEEE3` tint | "Due tomorrow, 11:59 UTC" |
| Passed | < now | muted, struck through | "Closed 25 Aug" |

**Deadline vs risk must never be confused.** Deadline: clock icon, countdown words, orange
family, always in the metadata row, never filled except ≤ 48 h. Risk: shield icon, level
word, green/amber/red, always in the trust slot at the top right of a card, always filled.
Red is reserved for high risk, errors and destructive actions.

**Application status**

| Status | Style | Label |
|---|---|---|
| SUBMITTED | outline, `--rc-text-secondary` | "Submitted" |
| UNDER_REVIEW | `--rc-info` on `--rc-info-subtle` | "Under review" |
| SHORTLISTED | brand text on `--rc-brand-subtle` | "Shortlisted" |
| OFFERED | white on brand | "Offer made" |
| ACCEPTED | `--rc-success` on `--rc-success-subtle` | "Accepted" |
| REJECTED / DECLINED | muted outline | "Not selected" / "Declined" |
| WITHDRAWN | muted outline, icon `Undo2` | "Withdrawn" |

Rejection is **not** an error and is never red.

**Workspace status and priority**

Status (`SAVED → CONSIDERING → PLANNING → APPLIED → ACCEPTED / REJECTED / ARCHIVED`) uses the
neutral-to-brand scale: Saved and Considering neutral outline, Planning and Applied brand
subtle, Accepted success, Rejected and Archived muted. Priority is **not** colour-coded with
status colours (today MEDIUM is green): it is a 1–4 bar glyph plus the word ("High").

**Notifications**

Unread: 8px petrol dot + semibold title. Read: regular weight, no dot. Count badge in the
header: white on `#B42318` (the one non-risk use of red, because counts must stand out on the
bell; it carries a number, never an icon alone). Delivery states (`DELIVERED`, `FAILED`,
`SKIPPED`) appear only in Settings and Admin, never on the user's notification list.

### 3.3 Colour rules

- Components use **semantic** tokens (`--rc-*`), never primitives (`--rc-p-*`) or literals.
- At most **one** filled brand element per viewport section (the primary action).
- Chart colours: petrol for "you/this", ink-300 for "others/baseline"; a second series uses
  `--rc-info`. Never more than three hues in one chart.
- No gradients, except none. No translucent "glass" surfaces.

### 3.4 Verified contrast (WCAG 2.2)

Measured with `audit/tools/contrast.py` (same formula as WCAG 2.x). Minimum 4.5:1 for text,
3:1 for control boundaries and focus indicators.

| Pair | Light | Dark |
|---|---|---|
| Text on page / on card | 16.09 / 17.39 | 15.50 / 14.39 |
| Secondary text on page / card | 8.97 / 9.69 | 10.17 / 9.45 |
| Muted text on page / card / sunken | 6.06 / 6.55 / 5.65 | 6.82 / 6.33 / 7.04 |
| Link on card / on page | 7.83 / 7.24 | 9.59 / 10.32 |
| Brand text on brand-subtle (selected nav) | 6.84 | 7.81 |
| Info / success / warning / danger badges | 6.07 / 5.49 / 5.64 / 5.70 | 7.42 / 7.89 / 8.26 / 7.68 |
| Urgent deadline chip / text on card | 5.65 / 6.42 | 7.50 / 8.36 |
| Good-match badge | 6.51 | 7.14 |
| Primary button text | 6.34 (white on brand) | 8.62 (near-black on brand) |
| Danger button text | 6.57 | — |
| Input boundary on card (1.4.11) | 3.72 | 3.59 |
| Focus ring on card / page | 6.34 / 5.86 | 9.59 / 10.32 |

For comparison, today: `--text-subtle #94a3b8` on white is **2.56:1** (used 25 times as
text), calendar event text ≈ **1.78:1**, white on the calendar's blue button **3.68:1**.

---

## 4. Typography

### 4.1 Families

| Role | Family | Why | Loading |
|---|---|---|---|
| UI and body | **Source Sans 3** (variable, 400–700) | Humanist, highly legible at 13–15px, true tabular figures, excellent Latin Extended coverage for author names | `next/font/local`, preloaded |
| Research titles, page titles | **Source Serif 4** (600, 600 italic) | Designed as a companion to Source Sans; reads as "journal" without being decorative; distinguishes content from chrome | `next/font/local`, not preloaded |
| Identifiers | system `ui-monospace` stack | DOIs, ORCID, IDs need character clarity; no extra download | none |

Both families are SIL Open Font License. **Self-hosted with `next/font/local`** from WOFF2
files committed under `frontend/app/fonts/` (latin + latin-ext subsets): no request to any
font CDN at build *or* run time, so the existing CSP (`font-src 'self' data:`) is unchanged
and offline/CI builds stay deterministic. `display: "swap"` and `adjustFontFallback` keep
layout shift minimal. Budget: **≤ 100 KB WOFF2 in total**, measured in P1.

Today the app names `Inter` but never loads it, so every visitor sees their OS font
(Segoe UI on Windows, SF on macOS): the product looks different on every machine.

### 4.2 Scale

| Token | Size / line height | Family, weight | Tracking | Use |
|---|---|---|---|---|
| display | 32 / 38 | serif 600 | -0.01em | Dashboard greeting only |
| h1 | 28 / 35 | serif 600 | -0.01em | One per page: the page title |
| h2 | 20 / 27 | sans 600 | 0 | Section titles |
| h3 | 17 / 24 | sans 600 | 0 | Card and panel titles |
| title | 18 / 24 | serif 600 | 0 | Paper, call, posting titles in lists |
| reading | 16 / 26 | sans 400 | 0 | Abstracts, descriptions, cover notes (max 72ch) |
| body | 15 / 23 | sans 400 | 0 | Default UI copy |
| small | 13 / 19 | sans 400 | 0 | Metadata rows, helper text |
| label | 12 / 16 | sans 600 | +0.02em | Field labels, column headers, eyebrows (sentence case, **not** all caps) |
| mono | 13 / 19 | mono 400 | 0 | DOI, ORCID, IDs |

Rules: no text below 12px; numbers in tables, scores and counts use
`font-variant-numeric: tabular-nums`; long titles clamp to 3 lines in lists (full title on
hover via the link's accessible name and on the detail view); all-caps only for 2–3 letter
abbreviations (`DOI`, `ACM`), never for labels or statuses.

---

## 5. Spacing, layout and shape

**4px rhythm**: 4, 8, 12, 16, 20, 24, 32, 40, 48, 64 (`--rc-space-1 … -16`).

| Context | Desktop (≥ 1280) | Tablet (768–1279) | Mobile (< 768) |
|---|---|---|---|
| Page padding | 32 | 24 | 16 |
| Section gap | 32 | 32 | 24 |
| Card padding | 20 | 20 | 16 |
| Compact list row | 12 × 16 | 12 × 16 | 12 × 16 |
| Form: label → field | 6 | 6 | 6 |
| Form: field → field | 16 | 16 | 16 |
| Table cell | 8 × 12 (compact), 12 × 16 (comfortable) | same | tables become DataLists |
| Sidebar item | 36 high, 8 × 12 padding | — | — |
| Touch target | ≥ 24 (WCAG 2.5.8) | ≥ 44 on coarse pointers | ≥ 44 |

**Grid.** Content max width 1200px; reading column 72ch. Desktop page = sidebar (248, or 64
rail) + content. Search and lists: 12-column grid; filter rail 3 columns at ≥ 1280.

**Breakpoints.** 480 / 768 / 1024 / 1280 / 1440 (see tokens). Layout changes only at 768
(drawer navigation, 2-column grids), 1024 (sidebar rail) and 1280 (expanded sidebar, filter
rail). 1440 only widens margins.

**Radius.** Chips/badges 4, buttons/inputs 6, cards 8, dialogs/sheets 12, full only for
avatars, switches and count badges. Today: 21 distinct radius values, including token
fallbacks that disagree with their own tokens.

**Elevation.** Cards are flat (1px border). Shadows exist only for things that float:
popovers/menus (`--rc-shadow-popover`), dialogs and sheets (`--rc-shadow-dialog`), and a
1px rule under the sticky header. Z-index scale: sticky 100, header 200, dropdown 300,
drawer 400, dialog 500, toast 600, tooltip 700.

**Icons.** `lucide-react` only (already a dependency). 16px in text and buttons, 20px in
navigation, 1.75 stroke. Decorative icons get `aria-hidden="true"`; an icon-only control
always has an accessible name.

---

## 6. Motion

| Interaction | Duration | Easing | Notes |
|---|---|---|---|
| Hover / press colour | 80ms | standard | Colour and background only |
| Tooltip, menu, popover enter | 140ms | enter | Fade + 4px translate |
| Same, exit | 100ms | exit | Fade only |
| Dialog / drawer enter | 200ms | enter | Drawer slides 24px + fade, not full width |
| Dialog / drawer exit | 150ms | exit | |
| Accordion / disclosure | 200ms | standard | Height via `grid-template-rows` |
| Skeleton shimmer | none | — | Static tint; shimmer is decorative |
| Toast | 200ms in, 150ms out | enter/exit | |

Never: page transitions, bouncing, pulsing badges, parallax, animated gradients, motion longer
than 300ms. `prefers-reduced-motion: reduce` sets all durations to 0 (tokens do this); the
only remaining feedback is instant state change.

---

## 7. Voice and copy (summary)

Full glossary and rewrite list: [FRONTEND_REDESIGN_PLAN.md §21](FRONTEND_REDESIGN_PLAN.md#21-copy-and-terminology).

- Sentence case everywhere (titles, buttons, tabs, badges).
- Plain words over system words: "Why this result?" not "Composite signal decomposition".
- Numbers in human units: "3 days left", "Due 9 Oct, 11:59 UTC".
- Never show enum values (`IN_APP`, `UNDER_REVIEW`, `OFFLINE`) or phase labels.
- One term per concept: **Paper**, **Call** (call for papers), **Venue**, **Posting**,
  **Application**, **Workspace**, **Reading list**, **Match** (personal), **Relevance**
  (search), **Fit** (posting/supervisor), **Risk**, **Deadline**.

---

## 8. Component system

Conventions for every component below:

- Lives in `frontend/components/ui/<Name>/` with `<Name>.tsx` + `<Name>.module.css`
  (academic components in `frontend/components/research/`).
- Styled **only** with `--rc-*` tokens; no hex, no inline colour styles, no Tailwind
  arbitrary values.
- Size scale where relevant: `sm` (32 high), `md` (36, default), `lg` (44, default on coarse
  pointers).
- States listed are required; "focus" always means a 2px `--rc-focus-ring` outline with 2px
  offset, visible only for keyboard focus (`:focus-visible`).

### 8.1 Actions

**Button**
- Purpose: trigger an action in place.
- Anatomy: [leading icon] label [trailing icon | spinner].
- Variants: `primary` (brand fill, one per section), `secondary` (surface + control border),
  `ghost` (text-only, for toolbars), `danger` (danger fill, only inside confirmations),
  `danger-ghost` (red text, for the "Remove" entry point).
- Sizes: sm, md, lg. Full-width only in mobile forms and dialogs.
- States: default, hover, active, focus-visible, disabled (no pointer events, `aria-disabled`
  when it must stay focusable to explain why), loading (spinner replaces leading icon, label
  stays, `aria-busy`, width does not change).
- Accessibility: native `<button type="button">`; loading keeps the accessible name.
- Responsive: label never hides below 768 unless the button becomes an IconButton with a name.
- Usage: verb-first labels ("Save paper", "Apply"); one primary per section.
- Anti-patterns: a primary button on every card in a list; links styled as buttons for
  navigation inside text; disabled buttons with no explanation.

**IconButton**
- Purpose: compact action with a universally understood icon (close, more, refresh).
- Anatomy: icon inside a 32/36/44 square; tooltip shows the name.
- Variants: ghost (default), secondary. Sizes: sm, md, lg.
- States: as Button; `aria-pressed` for toggles.
- Accessibility: required `aria-label`; tooltip mirrors it but is not the only name.
- Anti-patterns: icon-only buttons for domain actions ("Find venues"); ambiguous icons.

**Link**
- Purpose: navigation. Variants: `inline` (underlined, `--rc-link`), `standalone`
  (no underline until hover, with arrow), `external` (adds `ExternalLink` icon and
  "(opens in new tab)" visually hidden).
- States: default, hover (underline), visited (same colour: research links are revisited
  constantly), focus-visible.
- Anti-patterns: browser-default blue links (today on DOIs, reading list, supervisors);
  underlined navigation tabs (today).

### 8.2 Inputs

**Input** — Anatomy: label (always visible), optional hint, field, error text. Variants:
text, email, password (with show/hide IconButton), number, date. States: default, hover,
focus, filled, invalid (`aria-invalid`, danger border + message linked by
`aria-describedby`), disabled, read-only. Sizes md/lg. Responsive: full width below 768.
Anti-patterns: placeholder as label; validation only on submit with no message near the field.

**SearchInput** — Purpose: query entry. Anatomy: search icon, field, clear IconButton (one —
today the native and custom clear buttons both show), submit button (search page) or Enter
(header). Keyboard: `/` focuses the global search; `Esc` clears then blurs. Accessible name
"Search papers". States as Input plus `loading`. Anti-patterns: disabling the submit button
while empty (looks broken; show a hint instead).

**Textarea** — As Input; auto-grows to 8 lines, then scrolls; optional character count
("120 / 1,000") announced politely. Used for notes and cover letters.

**Select** — Native `<select>` styled with tokens (best accessibility and mobile pickers).
Must have a visible label (axe found 39 unlabelled selects on 7 routes). For multi-select
use Checkbox groups or Chips, not custom listboxes.

**Checkbox** / **Radio** — Native inputs, 16px box, 24px hit area, label to the right,
group with `<fieldset><legend>`. Indeterminate state for "select all".

**Switch** — For settings that apply immediately (notifications on/off). `role="switch"`,
`aria-checked`, label on the left, state word on the right ("On"). Anti-pattern: a switch
inside a form that needs "Save" (use Checkbox).

### 8.3 Navigation and structure

**Tabs** — Purpose: switch between views of the same object. Anatomy: tablist with
underline indicator, optional count. ARIA tabs pattern (arrow keys move, Enter/Space
activate when manual). Sizes md. Responsive: scrolls horizontally with edge fade and
visible scroll buttons below 768. Anti-patterns: tabs as page navigation (use Link + `aria-current`).

**Breadcrumb** — `nav aria-label="Breadcrumb"`, ordered list, current item `aria-current="page"`.
Used on detail pages (Workspace › Call title › Submission). On mobile shows only the parent
("‹ Workspace").

**Pagination** — Anatomy: "Showing 21–40 of 312", previous/next, page numbers on desktop,
page size select. Mobile: previous/next + "Page 2 of 16". Buttons named "Previous page",
"Page 3". Infinite scroll is not used (results need stable positions to compare).

**PageHeader** — One per page. Anatomy: breadcrumb (optional), h1 (serif), one-sentence
description (optional, max 2 lines), actions (max one primary + overflow menu), optional
tabs underneath. Responsive: actions move under the title below 768 (never squeezed beside it
— see the calendar today). Anti-patterns: eyebrow + h2 instead of h1; implementation details in
the description.

**SectionHeader** — h2 + optional description + right-aligned link or ghost action.

**Card** — Purpose: group content about one object. Anatomy: optional header (title, meta,
trust slot), body, optional footer actions. Variants: `default` (border, radius 8),
`interactive` (whole card is a link: hover border `--rc-border-strong`, focus ring on the
card, inner actions still separate), `muted` (sunken background for secondary info).
Anti-patterns: cards inside cards inside cards (the workspace today nests three levels);
shadows on cards; stat cards that only repeat counts already visible in tabs.

**Table** — For dense, comparable data (admin, ingestion runs, applicants on desktop).
`<table>` with `<caption>` (visually hidden if a heading exists), `scope` headers, sticky
header, numeric columns right-aligned with tabular figures, row hover, optional row selection
with checkboxes. Below 768 a Table becomes a **DataList**.

**DataList** — Stacked key/value rows (`<dl>`) or a list of compact items; the mobile form
of tables and the detail "facts" block (e.g. posting terms).

**Drawer** — Side sheet for secondary detail without leaving the list (Evidence panel, paper
panel, filters on mobile). Built on native `<dialog>` + `showModal()` (inert background, Esc
closes). Anatomy: header with title (`aria-labelledby`) and close IconButton, scrollable body,
optional footer. Width 480 (md) / 640 (lg); full-screen sheet below 768. Focus moves to the
title on open and returns to the trigger on close. Anti-pattern: today's drawer has
`role="dialog"` on the overlay with no name and no focus management.

**Modal** — Native `<dialog>` for decisions and short forms (confirm delete, invite member).
Max width 480; title + body + footer (primary right). Destructive confirmations name the
object ("Remove 'GraphLIME' from your reading list?").

**Popover / Dropdown** — Menus for overflow actions ("More actions"), account menu,
notification preview. Use the native Popover API (`popover` attribute) with a button trigger,
`aria-expanded`, arrow-key navigation for menus (`role="menu"` only for action menus; plain
lists of links stay links).

**Tooltip** — Short supplementary label on hover *and* focus, 140ms delay, never contains
essential information or interactive content, dismissible with Esc (WCAG 1.4.13). Use for
icon names and abbreviations only.

### 8.4 Feedback and status

**Alert** — Inline, persistent message in the flow. Variants: info, success, warning, danger.
Anatomy: icon, title (optional), text, action (optional). `role="alert"` only for errors that
appear after an action; static notices use no live role.

**Toast** — Transient confirmation of a completed action ("Paper saved", with Undo when
possible). Bottom-right on desktop, bottom above the tab bar on mobile, 5s, pauses on hover
and focus, `aria-live="polite"`. Errors are not toasts (they need to persist).

**Badge** — Short status word (+ optional icon). Variants map to semantic tokens: neutral,
info, success, warning, danger, brand. Radius 4, 12px label text, sentence case.

**Chip** — Interactive or removable token (filters, topics in an editor). Selected state
uses brand-subtle background + check icon. Removable chip has a remove IconButton named
"Remove machine learning".

**StatusBadge** — Badge pre-mapped from a domain status (application, workspace, posting,
submission) using the tables in §3.2. One mapping function per domain lives next to the type
(e.g. `applicationStatusMeta(status) → { label, tone, icon }`). Never render the raw enum.

**Progress** — Linear bar (`role="progressbar"` with `aria-valuenow`/`aria-valuetext`) for
profile completeness, reading progress. Indeterminate only for operations > 1s.

**Skeleton** — Placeholder blocks shaped like the final content (title line, two meta lines,
two text lines). Static tint (`--rc-surface-sunken`), no shimmer. Shown after 150ms to avoid
flashes; container gets `aria-busy="true"` and one visually hidden "Loading results" status.

**EmptyState** — Anatomy: optional icon (24px, muted), title, one sentence explaining *why*
it is empty, one primary next action. Variants: `first-use` (nothing yet: teach), `no-results`
(filters: offer "Clear filters"), `done` (all caught up).

**ErrorState** — Title in plain words, what happened, what to do, Retry button, technical
detail behind a disclosure. Variants: `failed` (retry), `offline` (retry when back online),
`permission` (who can access, how to get access), `not-found`.

**StatCard** — Number + label + optional delta or link. Allowed only when the number is
actionable (e.g. "3 applications need a decision →"). Not allowed as decoration (today the
workspace, calendar and notifications pages open with 4–5 stat cards repeating tab counts).

**Avatar** — Initials on a neutral background (no generated colours), 24/32/40. Image only if
the profile provides one. `alt` = person's name when standalone; empty when next to the name.

### 8.5 Data display

**ScoreMeter** — Horizontal bar 0–100 with band label; used in the Evidence panel to show
signal contributions. Track `--rc-data-meter-track`, fill `--rc-data-meter-fill`.
Accessible as text ("Semantic similarity: 76 out of 100").

**MatchScore** — Band badge ("Good match") + optional exact value ("62%") + reason link
("Why?"). Sizes sm (list), md (detail). The band is the visual, the number is secondary.

**RiskBadge** — Shield icon + level word, colours from §3.2. Clicking opens the risk
explanation (existing `/api/opportunities/{id}/risk-explanation`). "Not assessed" is neutral.

**DeadlineBadge** — Clock icon + date + countdown, styles from §3.2. Accepts timezone and
always shows the deadline's own timezone ("11:59 UTC"), never "UTC (UTC)".

---

## 9. Academic components

These make the product read as a research platform. All compose the primitives above.

**PaperCard** (search results, similar research, reading list)
- Anatomy, top to bottom: (1) serif title link (3-line clamp); (2) AuthorList · venue · year;
  (3) CitationMetadata row: type, citations, open-access, DOI; (4) abstract excerpt, 2 lines,
  "Show abstract" disclosure; (5) evidence line: MatchScore/relevance band + top two reasons in
  words ("Similar meaning · title terms"); (6) action row: **Save** (secondary), Find similar
  (ghost), Find venues (ghost), "Why this result?" (link). Rank number as a muted prefix.
- Variants: `result` (default), `compact` (dashboard, 1-line meta, no abstract), `saved`
  (reading list: status select and notes behind "Notes" disclosure).
- Anti-patterns: centred titles (reading list today), three full buttons with equal weight,
  subscores labelled "Lexical: 9%".

**ResearcherCard** (supervisors, peers)
- Anatomy: Avatar, name (h3), role · institution · department, availability badge
  ("Taking students", "Open to collaboration"), FitScore, up to 3 shared ResearchTopicTags,
  top 2 reasons, open postings (links), "How this was scored" disclosure.
- Rule: caveats that apply to *all* results ("No publication embeddings yet, scored on topics
  only") appear once above the list, not in every card (today they repeat in every card).

**OpportunityCard** (calls for papers / venues)
- Anatomy: type badge (Conference, Journal, Workshop, Special issue) and RiskBadge in the
  header row; serif title; organiser/venue · location · mode (In person / Online / Hybrid);
  DeadlineIndicator; relevant topics; MatchScore when personalised; actions: Save to
  workspace (secondary), Source (external link).
- Expired calls are hidden by default in lists (filter "Include closed calls").
- Anti-pattern: the neutral "Limited metadata available" panel above the title on every card
  (move to the RiskBadge "Not assessed" + explanation on demand).

**PostingCard** (faculty research postings)
- Anatomy: type badge + status ("Open", "Closed") + DeadlineIndicator in the header row;
  serif title; author · institution · location · mode · positions; FitScore line with one
  reason (students only); summary (2 lines); skill chips.

**RecommendationCard** (dashboard, recommendations page)
- PaperCard or OpportunityCard in `compact` variant + a **reason strip**: "Because you follow
  *Graph neural networks*" + MatchScore + feedback (Helpful / Not relevant, existing feedback
  endpoints) + "Why this?".

**ApplicationCard** (student "My applications", faculty applicant review)
- Student: posting title, author, StatusBadge, submitted date, next step text ("The author is
  reviewing applications"), withdraw (danger-ghost, confirm).
- Faculty: applicant name, level · institution, FitScore + reasons, cover note (reading
  style, 4-line clamp), decision actions in pipeline order — **Shortlist** (primary when
  submitted/under review), **Make offer** (primary when shortlisted), **Not selected**
  (danger-ghost with confirmation) — and History disclosure.

**DeadlineIndicator** — DeadlineBadge + optional mini timeline (abstract → paper →
notification → camera-ready) on detail pages, using `/api/opportunities/{id}/deadlines`.

**RiskIndicator** — RiskBadge + one-line reason + "How we assess venues" link; on detail pages
expands to the risk explanation evidence list.

**FitScore** — MatchScore specialised for postings/supervisors: band ("Good fit") + exact value
+ the strongest reason; low fit reads "Partial fit — add your skills to improve it" with a link
to preferences (actionable, not judgemental).

**ResearchTopicTag** — Non-interactive chip for topics; `shared` variant (petrol outline +
check) when the topic is also in the viewer's interests.

**CitationMetadata** — Inline row: work type ("Journal article"), year, "217 citations",
open-access badge, DOI in mono as a link "doi:10.1109/…". Tabular figures.

**AuthorList** — "Schnake, Lederer, Müller et al." (first three, family names first); full
list on the paper panel; ORCID icon link when known. Never truncates inside a name.

**VenueBadge** — Venue name + verification ("Verified venue", "DBLP-indexed") with info
tooltip; replaces today's "Verified Venue 65%" percentage.

**"Why this?" explanation** — An inline link on every scored item that opens the Evidence
panel. Label depends on context: "Why this result?" (search), "Why this match?"
(recommendations), "How this fit was scored" (postings/supervisors). Because the visible label
repeats on every card, its accessible name includes the item (`aria-describedby` pointing at
the card title), so a screen-reader list of links reads "Why this result? Parameterized
Explainer for Graph Neural Network", not twenty identical links.

**Evidence panel** (Drawer)
- (1) Summary sentence in plain words ("Ranked #1 mainly because its meaning is close to your
  query and it uses your search terms in the title."); (2) contribution chart: ScoreMeters for
  each signal with human names (Meaning, Search terms, Topics, Academic quality), each with one
  sentence; (3) evidence list with citation markers `[1] Your query mentions "explainability";
  the abstract discusses explanation methods.`; (4) quality facts (citations, open access,
  venue risk); (5) "Technical details" disclosure: raw scores, weights, ranking mode — the
  content of today's "Exact score decomposition", unchanged, for examiners.
- No phase labels, no 4-decimal floats on the default view.

**Research profile summary** — Profile header for /researcher and the dashboard sidebar:
name (serif), role, institution, ORCID/OpenAlex links, ResearchTopicTags (declared vs
inferred, labelled), Progress for profile completeness with the next missing item as a
link ("Add your ORCID to import publications").

---

## 10. State patterns (every page)

| State | Pattern | Required behaviour |
|---|---|---|
| Initial load (structure known) | Skeleton of the real layout | No spinner-only pages |
| Initial load (structure unknown) | Small inline spinner + text, after 300ms | |
| Background refresh | Keep content; subtle "Updating…" text in the header | No layout jump |
| Empty, first use | EmptyState `first-use` with one next action | |
| Empty, filtered | EmptyState `no-results` + "Clear filters" | |
| Error | ErrorState with Retry; keep any data already shown | |
| Partial failure | Inline Alert in the failing section; other sections render | Dashboard modules fail independently |
| Offline | Top Alert "You're offline. Changes will fail until you reconnect." + Retry | Listen to `online`/`offline` |
| Permission denied | ErrorState `permission`: who can see it, how to get access, link home | Today's RequireAuth message, restyled |
| Success | Toast for completed actions; inline confirmation for forms | |
| Disabled | Explain why (hint text or tooltip on an `aria-disabled` control) | |
| Unauthenticated | Redirect to sign in with `next` (exists) | |

---

## 11. Accessibility contract (WCAG 2.2 AA)

- Exactly one `h1` per page (the PageHeader); headings never skip levels.
- Landmarks: one `header` (banner), one `nav` per navigation with a unique label ("Primary",
  "Breadcrumb"), one `main`, `footer` optional. A "Skip to main content" link is the first
  focusable element.
- Every form control has a visible label; groups use `fieldset`/`legend`.
- Focus: visible 2px ring, 2px offset, ≥ 3:1 against adjacent colours; never removed.
- Dialogs/drawers: labelled, focus moves in, Esc closes, focus returns to the trigger.
- Targets ≥ 24×24 CSS px everywhere, 44×44 on coarse pointers.
- Live regions: one polite region for toasts and search result counts; errors after submit use
  `role="alert"`.
- Colour is never the only carrier of meaning (§3).
- Reduced motion respected (§6). Text zoom to 200% and 320px reflow without loss.

## 12. Enforcement

Design-system rules are checked by tests, not memory (no new dependencies; Vitest scans
files):

1. No colour literals (`#…`, `rgb(`, `hsl(`) in `components/ui`, `components/research` or any
   `*.module.css`; only `styles/tokens.css` may contain them.
2. Legacy ratchet: the count of colour literals and `style={{` in legacy files may only go down.
3. No Tailwind arbitrary values (`-[`) in new code; Tailwind's palette is mapped to tokens.
4. Every `*.module.css` declaration of `font-size`, `border-radius`, `z-index` or
   `transition-duration` uses a token.
5. An axe check (axe-core, already present) runs against the main routes in the e2e stack
   and fails on any serious or critical violation.
