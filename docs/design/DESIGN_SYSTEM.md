# ResearchConnect AI — Design System

> Status: **implemented in P1** (foundations). The tokens, fonts, themes, primitives and
> enforcement below are live in `frontend/`; individual pages adopt them phase by phase
> (P2 onward). See "Implementation map" at the end of this document.
> Evidence: [`audit/`](audit/README.md), P1 results in [`audit/p1/`](audit/p1/README.md).
> Rollout: [`FRONTEND_REDESIGN_PLAN.md`](FRONTEND_REDESIGN_PLAN.md).

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
  Never wider than its container: a label that does not fit (a narrow column, 200% text) wraps
  instead of overflowing (P3).
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

## 13. Implementation map (P1)

| Part | Where | Notes |
|---|---|---|
| Tokens (§3, §5, §6) | `frontend/styles/tokens.css` | The only file with colour literals. Light and dark values; `data-theme` on `<html>` selects. Adds `--rc-brand-active`, `--rc-text-inverse`/`--rc-surface-inverse`, `--rc-surface-hover`, interaction tints (`--rc-hover`, `--rc-active`, `--rc-disabled-bg`) and `--rc-*-border` edges to the draft. |
| Element defaults, type classes, focus, layout primitives | `frontend/styles/base.css` | `.rc-display/.rc-h1…/.rc-title/.rc-reading/.rc-small/.rc-label/.rc-mono`, `.rc-container/.rc-stack/.rc-cluster/.rc-grid/.rc-switcher/.rc-ruled/.rc-scroll-x`, `.rc-skip-link`, `.rc-visually-hidden`; one `:focus-visible` ring; reduced motion. |
| Fonts (§4.1) | `frontend/app/fonts.ts`, `frontend/app/fonts/*.woff2`, `OFL.txt` | `next/font/local`; latin preloaded (sans), latin-ext only on demand (`unicode-range`). |
| Theme | `frontend/utils/theme.ts`, `components/ui/ThemeSwitcher` | Light, dark or system; stored in `localStorage` (`rc-theme`); applied before first paint by an inline script in `app/layout.tsx`. Styles never read `prefers-color-scheme`. Dark ships in P1 (the plan had P11). The control sits in the account menu from P2 (§14). |
| Primitives (§8) | `frontend/components/ui/<Name>/` | Button/ButtonLink/IconButton, Field/TextInput/PasswordInput (P3)/TextArea/Select/SearchInput/Checkbox/RadioGroup/Switch, Card, Badge/StatusBadge/PriorityLabel, Dialog/Drawer (native `<dialog>`), Skeleton/SkeletonList, EmptyState, ErrorState, Alert, PageHeader/SectionHeader, ThemeSwitcher. CSS Modules + tokens. Usage: [`components/ui/README.md`](../../frontend/components/ui/README.md). |
| Research indicators (§3.2, §8.5) | `frontend/components/research/` | DeadlineCountdown (DeadlineBadge), RiskIndicator (RiskBadge), MatchScore; `utils/date.ts`, `utils/risk.ts`. Every list that shows a call's deadline or venue risk uses them: home, workspace, recommendations, the candidate and ranking previews, submissions, the submission banner and the explanation drawer (`tests/canonical-indicators.test.tsx`). |
| Status maps (§8.4) | `frontend/utils/status.ts` | `workspaceStatusMeta`, `applicationStatusMeta`, `postingStatusMeta`, `priorityMeta`. (In `utils/`, not `lib/`: the root `.gitignore` ignores every `lib/` directory.) |
| Legacy bridge | `frontend/styles/globals.css` `:root`, `frontend/tailwind.config.ts` | Old CSS variables (including the 11 that were never defined) alias the tokens; Tailwind's palette resolves to the tokens (hue names → one brand, info, success, warning, danger; separate text/fill/edge maps), shadows flattened, radii on the scale. |
| Enforcement (§12) | `frontend/tests/design-tokens.test.ts` | No colour literals outside `tokens.css`; no `dark:` classes, text < 12px, gradients or `prefers-color-scheme` in styles; module CSS uses tokens; inline-style ratchet; token contrast computed for both themes. |

## 14. Application shell (P2)

| Width | Structure |
|---|---|
| ≥ 1024 | Header 56px (brand · global search · notification bell · account menu) + navigation sidebar 248px (`--rc-sidebar-width`) + content (max 1200) |
| 768–1023 | Header with a Menu button, the search field, bell and account; navigation in a drawer |
| < 768 | Header: Menu · brand mark · search button (opens a search sheet) · bell · account; navigation in a drawer |

- **One navigation, one place to configure it.** `frontend/utils/navigation.ts` lists every
  destination with its group and roles; the sidebar and the drawer render the same
  `PrimaryNav` (`nav aria-label="Primary"`), and only one of them is displayed at a time (the
  sidebar is not displayed below 1024px; the drawer only opens from the Menu button, which is
  not displayed from 1024px). Groups by task: Home · Discover · My research · People ·
  Administration. The current page: `aria-current="page"` on the most specific matching link,
  shown by a brand bar, weight and a tinted row (not colour alone).
- **Phones: a drawer, not a bottom tab bar.** The plan (§6) proposed a bottom bar with four
  items and More. With 12 destinations for a student, four would still hide eight behind
  "More"; a fixed bar costs 56px of a 568px screen on every page and sits over the sticky
  actions and full-screen sheets pages already use; and it would be a second navigation to keep
  in step with the drawer. The drawer (P1 `Drawer`, native `<dialog>`) lists every destination
  in its group, traps focus, closes on Escape, a click outside or following a link, and returns
  focus to the Menu button. Search, notifications and the account stay one tap away in the
  header.
- **Notifications.** `NotificationBell`: the one entry point and the one unread count, from the
  existing polling hook (one request every 30 s while visible, rendered once). Its name carries
  the count ("Notifications, 3 unread"); zero or unknown is a plain bell with no badge.
- **Account menu.** A disclosure (not an ARIA menu): name and role, Researcher profile,
  Research preferences, Settings (P3; Notification settings before it), the theme, Sign out. Escape, a click outside or
  tabbing out closes it; Escape returns focus to its button. A visitor gets Sign in, Create
  account (from 640px) and an "Appearance" button for the theme.
- **Global search.** "Search papers" opens `/?q=…`; the literature search page runs the URL's
  query once. `/` focuses the field from 768px; on phones a search sheet. Not shown on `/`,
  which has its own search box.
- **Session restore.** Until `/auth/me` answers, the navigation shows placeholder rows, the
  header reserves the account controls' room, and guarded pages show a page-shaped skeleton
  with the status "Checking your session…" — never the visitor's navigation or Sign in. A check
  the browser cancels because the page is being left (a reload, a typed address) is not a
  failure and signs nobody out (P4); every answered failure still does (audit F10, deferred).

| Part | Where |
|---|---|
| Frame | `frontend/components/shell/AppShell.tsx` (in `app/layout.tsx`, inside `SessionProvider`) |
| Header | `ShellHeader.tsx`, `GlobalSearch.tsx`, `NotificationBell.tsx`, `AccountMenu.tsx` |
| Navigation | `PrimaryNav.tsx` (sidebar and drawer), `NavDrawer.tsx`; config `frontend/utils/navigation.ts` |
| Guard waiting state | `frontend/components/auth/RequireAuth.tsx` (Skeleton + SkeletonList) |
| Tests | `tests/navigation.test.tsx`, `shell-account-menu.test.tsx`, `global-search.test.tsx`, `session-restore.test.tsx`, `notification-live-updates.test.tsx`; e2e `layout.spec.ts`, `shell.spec.ts` |

## 15. Authentication and public pages (P3)

| Page | What it is |
|---|---|
| `/login`, `/register` | One flat `Card` (no shadow) holding the page's `PageHeader` (its one h1), the form and a ruled line linking to the other form, which keeps `?next=`. Below 480px the form sits on the page without the card's border and padding (full-width fields, §16); registration puts two fields side by side when the card is wide enough. |
| `/settings` | Settings → **Account**: who is signed in (name, email, account type) and **Change password**, moved here from the notification settings; **Notifications** leads to `/settings/notifications`. Notification and appearance settings join this page in P8; the theme stays in the account menu until then. The account menu's "Settings" replaces its direct "Notification settings" link (plan §6). |
| `/` for a visitor | The search, and under its first-view prompt one line: searching is open to everyone; sign in or create an account to save papers, track calls and get recommendations. It sits below the search box so it never moves it. |
| Not found | `ErrorState` `not-found` as the page's h1: "Page not found", "Go to search". |
| Loading (`app/loading.tsx`) | The "structure unknown" state (§10): a small spinner and "Loading…", shown after 300ms. |
| Guard | Unchanged waiting skeleton (P2); the permission state keeps its words and now leads home ("Go to home" → `/dashboard`). |

**Forms** (sign in, registration, password change):

- Labels always visible; required fields carry `aria-required`, optional ones say "(optional)".
- The submit button is never greyed out. Sending the form checks each field (the backend's rules,
  `components/auth/formRules.ts`), shows the problem under the field (`aria-invalid`, linked by
  `aria-describedby`) and moves focus to the first one. What only the server knows (wrong
  password, email in use, too many attempts) is an `Alert` with `role="alert"` above the form,
  in words from `authMessages.ts` (never a 5xx body).
- While the request runs the button is busy (spinner, same label, `aria-busy`) and the fields are
  read-only, not disabled, so keyboard focus is never lost.
- `PasswordInput`: a show/hide toggle inside the field, `aria-pressed`, named by its own
  visually hidden text ("Show password", "Show new password"…) rather than `aria-label`, so it
  is never a second label for the field. Autocomplete attributes stay as password managers
  expect (`email`, `current-password`, `new-password`), and so do the ids the e2e suite uses
  (`#login-*`, `#register-*`).
- Each page has its own title ("Sign in — ResearchConnect AI", …).

| Part | Where |
|---|---|
| Frame and form layout | `frontend/components/auth/AuthPage.tsx` |
| Field rules, messages | `components/auth/formRules.ts`, `components/auth/authMessages.ts` |
| Password change | `components/auth/ChangePasswordForm.tsx`, `components/settings/SettingsPage.tsx` (`app/settings/page.tsx`) |
| Visitor line | `components/auth/VisitorIntro.tsx` (in the search page's first view) |
| Tests | `tests/auth-pages.test.tsx`, `auth-revocation.test.tsx`, `auth-messages.test.ts`; e2e `auth.spec.ts` (the password is changed in Settings, then the old one is refused), `layout.spec.ts` (the public pages at 320–1440px for a visitor, both themes), `pages.spec.ts` |

## 16. Dashboard (P4)

`/dashboard` is the signed-in home and the default destination after sign-in (`?next=` still
wins). It answers, in order, what needs attention, what is new, and what is coming up (plan §8).
Modules sit in two columns from 1280px (3 : 2) and one below; each is a section with an h2 and
one flat card that reserves the height of a typical answer from its first paint (titles and
reasons clamp to two lines), so answers arriving, an empty state or a failure do not move the
modules below; a narrow timeline (small phone, enlarged text) puts each date above its title.
Each module loads and fails on its own: a failed module says so in plain words with Try again,
and the others carry on.

| Role | Modules |
|---|---|
| Student | **Needs attention**: tracked calls due within 14 days (status and next step), offers and applications in progress, a nudge while the profile is incomplete, and the three-step **Get started** checklist (add interests, save a call, save a paper) until it is done · **Upcoming (next 30 days)**: a dot timeline of call deadlines (filled) and calendar milestones (hollow) · **Recommended for you**: three calls with match band, one reason and "Why?" (the explanation loads when asked) · **Postings that fit you**: the three open postings that fit best, with the main reason · **Reading progress**: to read, reading, done |
| Faculty | **Needs your decision**: new and under-review applications of the three busiest open postings (no aggregate endpoint; more are named and linked) · **Your open postings**: applicants, deadline, status · **Upcoming deadlines**: tracked calls and postings closing within 30 days · **Recommended papers**: papers similar to the newest paper of the researcher's (no endpoint recommends papers) |
| Admin | Platform administration (the admin overview is P10) |

Notifications stay in the bell until P8 gives it a shared list (the plan's latest-three module
would otherwise only repeat the bell's count).

**Requests.** At most seven of the dashboard's own per page load, all started together; the only
ones that wait are inside their module (fit scores after the open postings; a faculty member's
application lists after their postings; related papers after the newest paper). Student: tracked
calls, application summary, calendar (`/researchers/{id}/calendar`, one request instead of
calendar id + events), recommendations, open postings, fit scores, reading list = 7. Faculty:
tracked calls, own postings, up to three application lists, newest paper, related papers ≤ 7.
The shell's session check and unread count are not counted (every signed-in page makes them).

**Data.** `hooks/useApiResource.ts`: `useApiResource(key, load, { isEmpty })` →
`{ status: "idle" | "loading" | "success" | "empty" | "error", data, error, retries, retry }`.
Components using the same key share one request; answers belong to the current key and the
signed-in account only; nothing is kept once the last component using it unmounts (no cache
across pages or accounts); a request nobody needs is aborted and a late answer ignored; errors
are a classification, never the server's text; `retry()` is the only retry. Module loading
placeholders are busy but not live regions, so the page is not read out once per module.

| Part | Where |
|---|---|
| Page | `frontend/app/dashboard/page.tsx` (title in `layout.tsx`), `components/dashboard/Dashboard.tsx` |
| Requests | `components/dashboard/resources.ts` |
| Modules | `components/dashboard/{NeedsAttention,Upcoming,RecommendedForYou,PostingsThatFit,ReadingProgress,NeedsDecision,OpenPostings,RecommendedPapers}.tsx`, frame `Module.tsx`, styles `Dashboard.module.css` |
| Tests | `tests/use-api-resource.test.tsx`, `tests/home-page.test.tsx` (every module's states, request counts per role); e2e `dashboard.spec.ts` (live API: requests per load, reload, phones) |

## 17. Search and discovery (P5)

The literature search, the Evidence and paper panels, similar papers, venue matching, the calls
for papers and a call's own page (plan §9–11). Everything shown comes from the API's answers;
where the API has no data (authors, a paper by id, a sort for search) the page says less rather
than inventing it.

**The search lives in the address** (`utils/searchState.ts`). Defaults are left out, so the plainest
search is still `/?q=…`, as the header search and older links make it.

| Parameter | Meaning | Values (anything else is ignored, never sent) |
|---|---|---|
| `q` | the query | any text, trimmed; none or blank is the start page |
| `type` | publication type | `article`, `preprint`, `book-chapter`, `dataset` |
| `year` | publication years | `2020`, `2018-2024`, `2018-` (from), `-2024` (until) |
| `oa` | open access only | `1` |
| `cites` | at least this many citations | a whole number above 0 |
| `mode` | ranking mode (advanced) | `research_similarity`, `research_opportunity` (`general` is the default) |
| `sort` | order of the page | `newest`, `cited` (relevance is the default) |
| `page`, `per` | page from 1, papers per page | above 1; `10` or `50` (20 is the default) |

- A change made on the page (a query, a filter, a page, the sort) is recorded at once with the
  browser's own history (`pushState`) and searched at once; the URL starts a search only when it
  changes from outside the page (a link, back/forward, the header search) and only for the address
  the bar shows (the P2 race rules, unchanged). A newer search aborts the older one; an older
  answer is never shown. A new query keeps the filters, sort and page size, from page 1; a filter
  change goes back to page 1.
- The search API has no sort: **Newest** and **Most cited** reorder the page in hand, ask nothing,
  and say so ("Reorders the papers on this page; pages follow relevance").
- Year and citation filters apply on Enter or on leaving the field, so typing "2018" is one search.
- States: the start page (with the visitor line, P3); a skeleton while loading, with one status
  ("Searching papers…", "Still searching…" after 3 s, then "45 results"); "No papers matched your
  search" with Clear filters when filters are set; a failure in plain words with Try again
  (`role="alert"`, never the server's text); a page past the last one offers the first.

**Layout.** Query bar; from 1280px a filter rail beside the results, below it a Filters button that
opens the same filters in a sheet. The results header is an h2 with the count (focus moves there
on a new page) and the sort. **PaperCard** (`components/research/PaperCard.tsx`): rank and serif
title — the title opens the paper panel — venue · year (the venue only when the explanation names
it), CitationMetadata (type, citations, open access, `doi:` link), a two-line abstract with "Show
full abstract", the evidence line (band, the backend's two primary factors as words, "Why this
result?" named with its paper) and quiet actions: Save, Find similar, Find venues. No primary
button on a card.

**Evidence panel** (`EvidencePanel.tsx`, a Drawer named by its question with the paper or call as
its description): a sentence from the backend's primary factors ("Ranked #1 mainly for similar
meaning and shared topics"), a ScoreMeter for every signal that counted (human names and the
backend's own word: "Meaning — 76 out of 100, very strong"), shared topics, the backend's evidence
and limits, the paper facts, and "Technical details" with the exact decomposition (subtotals,
adjustments, reconciliation, the signal table, the ranking mode), unchanged, for examiners. For a
call it adds **Venue risk** (RiskDetails: level, summary, reasons, signs of trust, warning signs,
missing information — never a warning — and limits; scores behind Technical details) and
**Deadlines**. The risk badge and "All dates" open it at that heading. One panel serves search,
similar papers and venue matching; these pages no longer use the old explainability drawer.

**Paper panel** (`PaperPanel.tsx`, Drawer 640px, full screen below 768): the full title as its
name, venue · year · type, shared topics, the abstract in reading type, why it is here, the
citation facts, the actions — **Save to reading list** (the panel's primary action), Export
citation (BibTeX of the saved item, through the reading list's export; until saved it says so),
Find similar, Find venues, Open publisher page — and the first five similar papers, asked for
only when the panel opens. There are no authors: the search response does not include them.
Both panels load with their first opening (`lazyPanels.ts`) and unmount when closed, which hands
focus back to the title or button that opened them.

**Similar papers and Find venues** (`/similar?paper=<id>`, `/opportunities?paper=<id>`) are actions
on a paper and left the navigation (plan §7); the navigation marks "Literature search" while on
them, and "Calls for papers" on a call's page. The paper's id is in the address, so reload, back
and forward keep their own paper; its details come from this tab's memory of chosen papers
(`hooks/useSelectedWork.ts`), because the API cannot look a paper up (plan Q4). A shared link this
tab never saw still lists results from the id and says what it cannot show; an id that is not a
UUID is not sent. A breadcrumb leads back to the search the paper came from ("Search › paper ›
Similar papers"; "‹ Search" on phones). Venue matching keeps its API filters (type, attendance,
highest fee, location, stated fee, upcoming). **"Upcoming deadlines only" starts off on both
calls pages** (the P5 decision on plan Q10): nothing is hidden unasked, a past deadline reads
"Closed 25 Aug 2026", and the hint says the filter also leaves out calls with no listed deadline.

**Calls for papers** (`/browse`, `components/OpportunityList.tsx`, `utils/callsState.ts`):
`/browse?q=…&type=CONFERENCE&mode=ONLINE&upcoming=1&sort=deadline&page=2` — the API's own filters,
20 a page, all in the address. Each **OpportunityCard** has the type and the venue risk in its
header row (risk in the trust slot), the serif title linking to the call's page, organiser ·
location · attendance, the deadline in words, its indexes and a two-line summary, and quiet
actions (Save to workspace, signed in; Source). The API already leaves out calls marked expired,
archived or draft.

**A call's page** (`/calls/[id]`, `components/calls/CallDetail.tsx`): the type, the title (also the
document title) and organiser · location · attendance; the deadline and the risk, apart; the
workspace status when tracked, with a link to it; About; **Dates** in academic order (abstract →
paper → notification → camera-ready → registration → event), each in its own time zone ("20 Oct
2026, 23:59 AoE"), the main deadline marked, an extension or a disagreement between sources said
in words, the source named; **Venue risk** with its evidence; and a Facts column from 1024px.
Actions: Save to workspace (primary), Add dates to calendar (the existing projection), Source,
Submission site; a visitor gets "Sign in to save" with `?next=` back here. An id that is not a
UUID, or one the API does not know, is "Call for papers not found" (h1); any other failure can be
retried; a risk explanation that fails leaves the rest of the page with its own Try again.

**Requests.** `useApiResource` gained `scope: "public"` for data that is the same for everyone
(calls, papers): it loads for visitors too and from the first render; account data still waits for
the session. Per page load, without the shell's session check and unread count:

| Page | Requests |
|---|---|
| Search | 1 per search (+ signed in, 1 reading-list lookup); sorting 0; the paper panel +1 (5 similar papers) |
| Similar papers, Find venues | 1 per paper, filter set and page (+ signed in: the reading-list lookup, or the tracked calls) |
| Calls for papers | 1 per state of the list (+ signed in, 1 tracked-calls lookup, shared with the cards) |
| A call | 2, together: the call (with its deadline intelligence) and its risk explanation (+ signed in, the tracked-calls lookup) |

The tracked-calls lookup reads the 100 most recently updated workspace items (the API's page
limit); saving is idempotent, so a call beyond them that reads "Save" is saved without harm.

| Part | Where |
|---|---|
| Search page | `components/pages/DiscoverySearch.tsx`, `components/discovery/{SearchBar,SearchFilters}.tsx`, `Search.module.css`, `utils/searchState.ts` |
| Research objects | `components/research/{PaperCard,OpportunityCard,CitationMetadata,ScoreMeter,TopicTags,RiskDetails,DeadlineMilestones,EvidencePanel,PaperPanel,SaveCallButton}.tsx`, `paper.ts`, `trackedCalls.ts`, `lazyPanels.ts`; words in `utils/research.ts` |
| Paper tools | `components/pages/{SimilarResearch,OpportunityMatches}.tsx`, `components/discovery/{paperContext.ts,SourcePaper.tsx,PaperContextRequired.tsx}` |
| Calls | `components/OpportunityList.tsx`, `utils/callsState.ts`, `app/calls/[id]/`, `components/calls/CallDetail.tsx` |
| Primitives | `components/ui/Breadcrumb`, `components/ui/Pagination`; `hooks/useAddressSearch.ts` (state in the query string, the address bar as the truth) |
| Tests | `tests/search-state.test.ts`, `search-page.test.tsx`, `paper-tools.test.tsx`, `calls-pages.test.tsx`, `research-components.test.tsx`, `use-api-resource.test.tsx` (public scope); P2's `global-search.test.tsx` and P0's `paper-context.test.tsx` kept; e2e `discovery.spec.ts` (visitor) and the renamed steps in `pages`, `shell`, `layout`, `workflow` |

## 18. Personalization and profile (P6)

The recommendations page, what shapes it, one explanation for every recommendation, the profile,
and the people pages (plan §12). Everything shown is the API's: its ranking, its reasons, its
scores and its words for a band or tier. Where it has nothing to say the page says so; a score the
API could not compute is "Not available" or "Fit not scored", never zero.

**Navigation.** The "People" group is now **For you**: Recommendations, Find a supervisor
(students), Find peers. Hiding a link is a convenience; the backend authorises every request
(supervisor matching answers any other role 403, and the page explains itself to them without
asking).

**Recommendations** (`/recommendations`, `components/recommendations/`): the Phase 3.5 ranking (the
one the dashboard's three come from; viewing it keeps a snapshot for the history, as before), 25
calls, grouped by the interest each matched — "Because you follow *Graph neural networks*" (a topic
preference), "Because of your work on *…*" (expertise in the publications), "Because your profile
mentions *…*" (a keyword), and "More calls for you" last. An item joins the group of its matched
topic that most items share; groups keep the ranking and every card its overall rank. Each
**RecommendationCard** is the shared OpportunityCard with a reason strip: the match band, the
API's main reason and "Why this match?" (named with its call), then Save and **Helpful / Not
relevant** — recommendation feedback (Phase 3.6) with the item's rank, pressed state, a polite
confirmation and Undo (the feedback is deleted). Save from this page is also a "saved"
interaction, so learned signals see it, and adds the call to the workspace.

**What shapes your recommendations** (beside the list from 1024px, sticky): what you stated (each
removable, "Edit your research preferences" for the rest), what was inferred **from your saved
calls** with its strength in words (Strong, Moderate, Light) and the API's reason ("3 of 5 saved
opportunities were conferences (60%)"); three switches that apply at once — Personalize my
recommendations, Use what I have done here, Keep learning from new activity — and **Reset what was
learned**, behind a dialog that lists what is cleared and what is kept (stated preferences, the
profile and publications, the account, the workspace and the record of past activity), with an
optional reason kept in the control history. A change re-ranks the list; while the preferences
reload, the last list stays so the panel does not jump.

**One explanation UI.** "Why this match?" opens the P5 Evidence panel (`RecommendationEvidence.tsx`
inside `EvidencePanel.tsx`): how well it matches (band, rank, how far preferences moved it, the
main reason, the relevance and preference meters — the latter "Not available" while
personalization is paused — matched topics and preferences, reasons by origin: publications,
preferences, feedback, counted against), how your preferences and activity shaped it (Phase 5.9,
asked for when the panel opens), and Technical details (scores, confidence, ranking version, the
score breakdown; evidence tiers and the preference assessment asked for when opened). A
recommendation from the history opens the same panel with the explanation kept then, in the past
tense, and asks nothing live. The dashboard's "Why?" uses it too. WhyThisRecommendationModal and
RecommendationExplanationModal are no longer used.

**Technical details** (below the list; nothing removed, plan P0-4): thirteen parts, each closed
until opened and loaded — code and data — only then, each behind its own error boundary: the
ranking with and without personalization (this page's comparison needs no request; a ranking with
parts switched off is made on request and kept in the history, as before), your research context
and its signals, the personalization summary, your preferences in detail (from the page's own
copy), the calls considered before ranking, signals learned from your activity, calibration,
quality of personalization, health and drift with the audit trail, your feedback (each
removable), the recommendation history (offline quality, by ranking version, every list kept with
"Why?"), changes to your settings, and how the order is protected. Recalculate and Evaluate again
are kept.

**Profile** (`/researcher`, `components/profile/`): the name as h1 with career stage · institution
· department and Edit profile; **Profile** (completeness with what is still missing in words, the
ORCID and OpenAlex links, the research summary, keywords; the same fields to edit); **Research
topics** — *You stated* (topic preferences and profile keywords) beside *From your publications*
(Phase 3.2: classification, works, years, strength, confidence and recency, "Why this topic?" with
the supporting works), "Work out again", and the topics suggested from the publications to follow
in one step (nothing is added unasked); **Publications** (five, then Show all; title, year,
position, citations, DOI), asked for only once the profile is linked to a scholarly record; and
**Research preferences** (stated, from saved calls, complete; what is not stated yet; any
contradictions; links to the editor and to what shapes your recommendations). An edit works the
topics out again at once, as before. Creating a profile sends only what was entered. The P0.4
section links still work: `?section=recommendations`, `personalization` and `history` open
`/recommendations`; `interests` opens `/researcher#topics`.

**Find a supervisor, Find peers** (`components/people/`): filters above, then the results under an
h2; the caveat that applies to every result (how scores are made, "ranked on research topics
only") is said **once above the list**, not in every card. The **ResearcherCard**: initials, name
(h3), career stage · institution · department, availability, **FitScore** in the API's tier words
with its value ("Strong match · 62%") and the strongest reason, the second reason, up to three
shared topics, the supervisor's two papers closest to your interests and open postings, the
person's note, what they will collaborate on, their email if they chose to share it, and "How this
was scored" (confidence, the signal table, the other reasons, topics, papers). Anything a person
chose not to share is left out, never "unknown". Find peers starts with **Your discoverability**:
the opt-in switch with the date of the last change, availability, what others may see,
collaboration types and an optional note (saved with its own button).

**Research postings, student side** (`/postings` Discover; authoring and "My postings" are P9):
search (applied when submitted), category, work mode and "Accepting applications"; the results
under an h2 with one polite count. **PostingCard**: category, status and deadline in the header
row; the serif title; author · institution · place · mode · positions; for a student a FitScore
with the API's band first ("Strong fit · 82%") and its strongest reason, a partial or low fit
saying what would raise it with a link to the preferences; a two-line summary and skill tags. The
author's lifecycle buttons follow the server's allowed transitions; failures are in plain words.

**FitScore** (`components/research/FitScore.tsx`): the band (postings) or tier (supervisors,
peers) word first, the exact value second, the strongest reason; Partial, Low and Exploratory read
as an action; no score is "Fit not scored".

**Requests.** Per page load, without the shell's session check and unread count:

| Page | Requests |
|---|---|
| Recommendations | 4, together: the ranking, the preference record, the personalization settings, the tracked calls; "Why this match?" +1 (+2 for its technical details); each technical part its own, when opened |
| Profile | 4: the profile, then its publications (once linked), the topics in them and the preference record (3 when not linked) |
| Find a supervisor | 1 per filter set (none for other roles) |
| Find peers | 2: your discoverability and the matches (+1 per filter set) |
| Research postings | 1 per search or filter (+ for a student, 1 batch of fits) |

| Part | Where |
|---|---|
| Recommendations | `app/recommendations/`, `components/recommendations/{RecommendationsPage,RecommendationCard,TransparencyPanel,PreferenceSummary,PersonalizationSwitches,ResetPersonalization,TechnicalDetails}.tsx`, `grouping.ts`, `resources.ts`, `technical/*` |
| Explanation | `components/research/{RecommendationEvidence,EvidencePanel}.tsx`; words in `utils/personalization.ts` |
| Profile | `app/researcher/`, `components/profile/*` |
| People | `app/supervisors/`, `app/peers/`, `components/people/*`, `components/research/FitScore.tsx` |
| Postings | `components/postings/{PostingCard.tsx,PostingCard.module.css,PostingsPage.module.css}`, `app/postings/page.tsx` (Discover) |
| Tests | `tests/recommendations-page.test.tsx`, `researcher-profile.test.tsx`, `researcher-sections.test.tsx` (the old sections' addresses), `people-cards.test.tsx`, `fit-score.test.tsx`, `canonical-indicators.test.tsx` (on the new components), `supervisors-page.test.tsx`, `posting-fit.test.tsx`, `navigation.test.tsx`; e2e `pages`, `workflow`, `layout`, `design-system` updated |

## 19. Research workflow (P7)

The workspace, a tracked call's page with its tabs, the submission workflow, the submissions list,
the reading list and the calendar (plan §13, §16, §19). Pages are named as the navigation names
them: **Workspace**, **Submissions**, **Reading list**, **Calendar**. Everything moved from page
CSS (`styles/{workspace,collaboration,submission,calendar,peers}.css`, deleted) to CSS Modules on
the tokens; no page here has an inline style left.

**Workspace** (`/workspace`, `components/workspace/`): list first, no stat cards. Status filter
chips carry their counts as text ("Planning (3)", read as part of the name); while unknown there
is no number, never 0, but a hidden, unannounced placeholder keeps each chip's width so nothing
rewraps when the counts come (`ChipCount`; same on Submissions and the reading list). Then search (titles and
notes) and sort (deadline first, priority, recently updated) — all in the address
(`?status=PLANNING&sort=priority&q=retrieval`). **Calls | Submissions** above are links with
`aria-current` (two pages), not tabs. Each row: the serif title (it opens the item), type ·
publisher · place · mode, the deadline in words and the venue risk, then the **status menu**,
priority as a word with its glyph, the next step ("Draft submission →", "Open submission →",
which open the Submission tab) and **More actions** (Open, Collaborate, Archive or Restore,
Remove from workspace). Notes, tags and priority sit behind one disclosure. Rows stack on phones.

**Status menu** (`StatusMenu.tsx`, the `Menu` primitive): one button ("Status: Planning. Change
status") offering only the moves the server lists for that item (`allowed_transitions`, from the
backend's state machine), in workflow order, as "Move to applied". No moves: a plain badge. The
change shows at once ("Saving…", nothing else to choose), is replaced by the server's answer (with
its new allowed moves) and the counts reload; a refusal restores the last confirmed status, says
so in an alert with **Try again**, and is announced. Each item numbers its requests: an answer to
an older one never overwrites a newer state (`useWorkspaceList`, `useWorkspaceItem`). Removal is a
danger dialog naming the call and what goes with it (notes, tags, tasks, submissions and their
documents; collaborators lose access) and suggests archiving.

**Workspace item** (`/workspace/[id]`, `components/workspace/item/`): Breadcrumb (Workspace ›
title), the call's title as h1 with its facts, the status menu and priority; the deadline and risk
under it; "Shared with you · Editor" for a collaborator. Tabs **Overview, Tasks, Submission,
Members, Activity** (`Tabs`, ARIA tabs; they wrap onto a second line on narrow screens or with
large text rather than scroll, so none is out of view) with the tab in the address (`?tab=tasks`; Overview is
left out; the old `?tab=invitations` opens Members), so links, back and forward open a tab. A tab
asks for its data the first time it opens and stays mounted (hidden), so returning to it asks
nothing; its code loads then too (`lazyTabs.tsx`). The item is read by id (`GET
/workspace/{id}`), so a shared item opens for its members. What can be changed follows the role
(`workflow.ts`, mirroring WorkspaceAuthorizationService): viewers read; contributors add tasks,
documents and notes; editors also change the status, the item's notes and the submission; the
owner manages members and invitations. The server still decides; its refusals are said in words.

- **Overview**: the call's dates (`DeadlineMilestones`, with time zones and extensions), a link to
  the call's page, notes, tags and priority (read-only below editor), and the next step.
- **Tasks**: status and priority filters (one request each), a checkbox per task named "Mark *task*
  done" / "Reopen *task*", status as a word, priority, assignee, due date; **New task** in a
  dialog (title checked first, sent once, kept on failure); delete after a dialog naming the task.
- **Members**: members (role change and removal for the owner, each removal confirmed naming the
  person and what they lose) and invitations (status in words, expiry, Withdraw confirmed);
  **Invite someone** in a dialog (address checked first; roles described).
- **Activity**: the latest 50 events with actor and time, and **Post a note** (contributors).
  Changes made in the other tabs make an opened Activity tab read again.
- **Submission** (replaces `/workspace/[id]/submission`, which now redirects to `?tab=submission`;
  `components/workspace/submission/`): with none yet, **Draft a submission** (title required,
  format), sent once however often pressed, kept when refused. Then the submission's title and
  status, the lifecycle as steps (Draft, Ready, Submitted, Under review, Decision; the current one
  `aria-current="step"`, states in words), the **readiness** check (the server's, in words:
  required documents ready, how much of the details is filled in, what blocks it and what is worth
  checking; its summary sentence repeats these with enum values and is not shown), and **Change status**:
  one button per allowed move ("Mark ready to submit", "Mark as submitted", "Withdraw"…), the
  forward move primary; "ready" is disabled with its reason while the check has blockers. A note
  for the change is optional and says that it replaces the submission's notes (as the API does).
  **Details** (title, format, venue or track, submission ID, portal address checked as a web
  address, abstract, notes) save together and keep the draft on failure; Discard changes.
  **Documents** (status, required or optional, kind, version, format, where stored, checksum):
  Mark ready, and More actions — Record a new version (dialog), Version history (dialog, asked for
  when opened), Archive, Delete (confirmed). **History** is a disclosure asked for when opened.
  Delete submission (owner; draft or withdrawn only) is confirmed. Several submissions for one call
  are listed to choose from; Start another submission.

**Submissions** (`/submissions`): chips with counts per status in the address (`?status=`), then
each submission: title (opens its item's Submission tab), format · venue, status, deadline in
words, last update.

**Reading list** (`/reading-list`, `components/reading-list/`): Export selected (.bib) and Export
all (.bib) in the header (unchanged: the selected ids, or the whole list or the current status;
at most 200 selected), chips "To read (4)" in the address with the page (`?status=READING&page=2`,
`Pagination`). Each paper: a checkbox "Select *title*", the serif title linking to its DOI or page
(described as opening a new tab), authors · venue · year, "DOI: …", **Status** (shown at once,
rolled back with the reason if refused), **Notes** behind a disclosure ("Add notes", open from the
start when the paper has notes; private, saved when the box is left, never exported) and Remove —
a dialog naming the paper, since its notes go with it. The papers are under an h2 ("All papers" or
the status). Empty and filtered
states differ; a failed list offers Try again.

**Calendar** (`/calendar`, `components/calendar/`): Export calendar (.ics) (unchanged: fetched with
the session, "Exporting…" while in flight, the server's reason on failure) and Add milestone, both
there from the first paint (disabled until the calendar is known, so the page does not move).
A line of facts instead of stat cards (upcoming dates, disputed dates, extended deadlines), filter
chips with counts, Previous month / Today / Next month and the month as h2 (announced), and the
view: **Agenda** (default below 768px) or **Month** (default from 768px); view, month and filter
are in the address (`?view=month&month=2026-11&type=SUBMISSIONS`). The agenda lists the month's
days with their events; an empty month says when the next date is and offers to go there. The
month grid is a table, Sunday first, seven equal columns that fit 320px: a day with events is a
button ("Tuesday 18 November 2026, today: 2 events") that lists them below; titles show in the
cells from 768px, a count below. Your milestones are marked with a dashed rule, call dates with a
solid one (and in words: "Your milestone" / the venue). An event opens a dialog: kind, date, time
with its zone, source, the call, an extension's reason, a dispute between sources, links to the
call and the workspace; your milestones can be deleted after a confirmation. Add milestone checks
the title and date first, is sent once and kept on failure. No emoji, no `alert()` or
`confirm()`.

**Requests.** Per page load, without the shell's session check and unread count:

| Page | Requests |
|---|---|
| Workspace | 2: the list and the counts (+1 list per filter, search or sort; +1 counts after a change) |
| Workspace item | 1: the item (+1 the members for a collaborator); each tab's own on first opening — Tasks 2 (tasks, members), Submission 3 (submissions, then the readiness check and documents of the one shown; history when opened), Members 2, Activity 1 |
| Submissions | 2: the list and the counts |
| Reading list | 1 per status and page |
| Calendar | 2: the default calendar, then its events (the month, view and filter need none) |

| Part | Where |
|---|---|
| Primitives | `components/ui/{Tabs,Menu}/` |
| Workspace | `app/workspace/{page,layout}.tsx`, `components/workspace/{WorkspacePage,WorkspaceRow,WorkspaceNav,StatusMenu,ItemNotesForm,ChipCount,useWorkspaceList,workflow}.ts(x)`, `Workspace.module.css` |
| Item | `app/workspace/[id]/page.tsx`, `app/workspace/[id]/submission/page.tsx` (redirect), `components/workspace/item/*`, `components/workspace/submission/*` |
| Submissions | `app/submissions/{page,layout}.tsx`, `components/workspace/SubmissionsPage.tsx` |
| Reading list | `app/reading-list/{page,layout}.tsx`, `components/reading-list/{ReadingListPage.tsx,ReadingList.module.css}` |
| Calendar | `app/calendar/{page,layout}.tsx`, `components/calendar/{CalendarPage.tsx,calendarModel.ts,Calendar.module.css}` |
| Words | `utils/status.ts` (submission, document, task, invitation, readiness, role), `components/workspace/submission/words.ts`, `components/calendar/calendarModel.ts` |
| Tests | `tests/workspace-status.test.tsx`, `workspace-item.test.tsx`, `workspace-submission.test.tsx`, `calendar-view.test.tsx`, `reading-list-page.test.tsx` (P7 states), `ui-primitives.test.tsx` (Menu, Tabs); updated: `deadline-risk`, `workspace-collaborate-link`, `submissions-page`, `session-restore`, `calendar-events`, `calendar-export`, `design-tokens` (ratchet 120); e2e `auth`, `shell`, `pages`, `layout`, `workflow` |

## 20. Notifications and settings (P8)

**Notifications** (`/notifications`, `components/notifications/`): titled "Notifications". The list
is grouped by where a notification comes from — the API's `source_type`: Calls for papers
(`OPPORTUNITY`), Calendar, Workspace, Research postings, System; an unknown source goes under
"Other updates". Groups come in the order of their newest notification, newest first inside each.
Each notification: its kind in words (`utils/notifications.ts`; an unknown kind is humanised,
never shown raw), the title as the link to where it leads (a call's page, the calendar, the
workspace item — which opens for its members, P7 — or the posting; none when there is nowhere
valid), the time under the title, "Unread" as a word with a dot and a leading rule, "Also emailed"
when it was, and "Mark as read". Filters "All" / "Unread" with counts from the API and the kind,
in the address (`?show=unread&type=…`); "Mark all as read"; administrators get "Check reminders
now". The list refreshes quietly every 30 seconds while the tab is visible. Delivery internals
(channel, delivery status) are no longer shown per notification; how notifications reach the
person is in Settings.

**Bell** (`components/shell/NotificationBell.tsx`): a button named with the unread count
("Notifications, 3 unread"; the badge is hidden from assistive technology) from the one polling
hook. It opens a disclosure (`components/shell/Disclosure.tsx`, shared with the account menu)
hanging from the sticky header, so it fits any width and text size: the latest five, grouped,
"View all notifications" and "Notification settings". It asks for the latest each time it opens.
Escape, a click outside or tabbing away close it; Escape returns focus to the bell.

**Settings** (`/settings`): Account (P3, unchanged), **Notifications** and **Appearance**, with
"On this page" links (`#account`, `#notifications`, `#appearance`); `/settings/notifications`
redirects to `#notifications`. Notifications: how notifications reach you and the reminder
schedule (the server's delivery status), the switches the API stores (`Switch`: named, described,
state in words; each saved on its own, held while saving, rolled back with the reason when
refused), the posting-match alert and its minimum fit for students, and the reminder schedule
(add with a checked amount, delete). There is no push option. Appearance: Match the system, Light,
Dark (`RadioGroup`), applied at once and kept per browser; the account menu's theme switch follows
through `THEME_CHANGED_EVENT` (`utils/theme.ts`). `styles/notifications.css` is deleted.

| Part | Where |
|---|---|
| Notifications | `app/notifications/{page,layout}.tsx`, `components/notifications/*`, `utils/notifications.ts` |
| Bell | `components/shell/{NotificationBell.tsx,NotificationBell.module.css,Disclosure.tsx}` |
| Settings | `app/settings/page.tsx`, `app/settings/notifications/page.tsx` (redirect), `components/settings/{SettingsPage,NotificationSettings,AppearanceSettings}.tsx` |
| Tests | `tests/notifications-p8.test.tsx`, `settings-p8.test.tsx`; updated `notification-types`, `notification-settings-push`, `notification-settings-posting-match`, `notification-live-updates`, `auth-pages`, `auth-revocation`, `design-tokens` (ratchet 105); e2e `pages`, `workflow`, `layout` |

## 21. Faculty (P9)

The faculty side of research postings (plan §14). Faculty get a **Recruiting** group in the
navigation — My postings (`/postings?view=mine`) and Applicants (`/postings/applicants`); students
and administrators do not see it (navigation only: the pages check the role and the API scopes
every answer to the signed-in author). A link may carry a query: `currentHref(path, hrefs, search)`
marks My postings on its view only, and writing or editing a posting belongs to it. The postings'
own pages are links with `aria-current` under the header: Discover · My postings · Applicants
(FACULTY and ADMIN, the accounts the server lets author) · My applications.

**Home** (`/dashboard`): the P4 recruiting modules, now leading to the faculty pages — each row of
"Needs your decision" opens the inbox filtered to that posting, "Manage postings" opens My
postings — and "New posting" as the page's one primary action.

**My postings**: every posting of the author's, drafts included, 25 a page, status chips with the
server's counts (`/postings/mine/summary`), all in the address (`?view=mine&status=&page=`). From
1024px a table — Posting (title and category), Status, Applicants, New, Deadline, actions — and
below, each row stacks as a card with its labels (the table keeps explicit `role`s, so it is still
a table to assistive technology). "New" counts applications not reviewed yet (`SUBMITTED`) for up
to ten open postings with applications; any other posting shows a dash read as "Not counted",
never a zero. A row's actions: Edit (not for archived postings — the backend refuses them) and an
"Actions for …" menu of the moves the server lists, in the order Publish/Reopen, Close, Mark
filled, Return to draft, Archive, **Cancel posting** (last, confirmed), plus **Delete draft**
(confirmed) for drafts.

**Editor** (`/postings/new`, `/postings/[id]/edit`): a full page with sections Basics,
Description, Skills, Dates and terms, Contact, and a live preview of the PostingCard (sticky beside
the form from 1280px, under it below). The backend's rules (title 5–300, description ≥ 20, 25
skills, 1–100 positions, two-letter country, email, a web address, a future deadline on create,
end after start, the appointment terms' ranges) are checked before anything is sent; a summary
lists what to fix and the first field takes focus. Saving sends one request; a refusal or a network
failure keeps everything entered, with the reason above the form. A new posting is a draft; an edit
sends only the fields that changed (the backend's PATCH applies only what it gets), and nothing
when nothing did. Appointment terms are offered only for internships, assistantships and
post-docs. The posting's own page opens afterwards.

**Applicants** (`/postings/applicants`): one inbox, grouped by posting (h2 per posting with its
status, deadline and count), filtered by status (chips with counts from the answers) and by
posting, in the address (`?status=&posting=`). There is no aggregate endpoint (plan Q4): the inbox
reads the author's postings, then — all at once — the applications of the ten most recently
published open postings that have applications (at most 11 requests; a posting without
applications costs none). Older open postings and postings that are no longer open are listed
under "Applications not shown here", each linked to its page, where its applications are. Each
application appears once, under the posting it was made to (the API's `posting_id`).

**Applicant review** (`ApplicantCard`, the faculty ApplicationCard; in the inbox and on the
posting's page): the applicant, level · institution, the status in words, when they applied, email
and CV link (a link only when it is a web address), the statement of interest (serif, four lines,
then "Show the whole statement"), the message shared with them and the private note, what happens
next once nothing is left to decide, and the history. Decisions follow the review pipeline —
**Mark under review → Shortlist → Make offer** — with one primary (Shortlist while submitted or
under review, Make offer once shortlisted) and **Not selected** last as a danger-ghost action that
asks first, with an optional message to the applicant; only the moves the server lists are
offered (it sends them sorted by name, which is never used). Nothing is shown before the server
agrees; one request per application at a time; a refusal leaves the server's state and says so in
plain words (the server's enum words are not shown); an older answer never replaces a newer one.
The API gives the author no fit for an applicant, so none is shown.

**Confirmations** (`ConfirmDialogs.tsx`, on `Dialog`): the title names the change and its object
("Mark Ada Lovelace as not selected for “RA: benchmark curation”?", "Cancel “…”?", "Delete the draft
“…”?"), the body its consequences as the backend applies them. Cancel, Close, Escape and the
backdrop send nothing; the danger button sends once and the dialog stays open with the reason if
the server refuses. Focus returns to the button that opened it, or to the applicant's name (the
list's heading after a deleted draft) when that button is gone.

**A posting's page** (`/postings/[id]`): on the design system (styles/postings.css now serves only
`/postings/applications`). The author gets "Manage this posting" (where it stands, Edit, the
lifecycle actions as above) and its applications; a student keeps their fit and the apply flow
("Apply now", `#cover-note`, "Submit application"); the reader's own application status is in
words. The applicant review, the confirmations and the application form load when needed
(`components/postings/lazy.tsx`); the author's controls come with the page, since arriving late
above the posting they would push it down.

**Links into a page's query** (`hooks/useAddressSearch.ts`, P5): a link renders the new page
before the router updates the address bar, so arriving from another page the router's query is
used until the bar shows this page, and the page renders once more after every router change. A
late router report for an address the bar has left is still ignored. Without this, a link to
`/postings?view=mine` or `/postings/applicants?posting=…` from another page opened the page's
default view.

**Requests and size.** My postings: the page and the counts, then up to ten application lists.
Applicants: at most 11. A posting's page: the posting (after the session check), plus its
applications for the author or the fit for a student. First-load JS: `/postings` 138 kB,
`/postings/[id]` 138, `/postings/new` 135, `/postings/[id]/edit` 136, `/postings/applicants` 141
(1 kB over the 140 kB budget; P12), `/dashboard` 138.

| Part | Where |
|---|---|
| Routes | `app/postings/page.tsx` (Discover, `?view=mine`), `app/postings/new/`, `app/postings/[id]/{page,edit/}`, `app/postings/applicants/` |
| Pages | `components/postings/{PostingsPage,MyPostings,ApplicantsInbox,PostingEditor,EditPosting,PostingDetail,PostingManage,PostingAuthor,ApplyForm,PostingsNav}.tsx`, `Faculty.module.css`, `lazy.tsx` |
| Review | `components/postings/{ApplicantCard,ConfirmDialogs}.tsx`, `useApplicationDecisions.ts`, `usePostingChanges.ts`, `errors.ts` |
| Rules and words | `utils/postings.ts` (decision order, lifecycle actions, addresses, the inbox's choice), `components/postings/postingForm.ts` (the editor's rules and payloads), `resources.ts` |
| Tests | `tests/postings-p9.test.tsx`, `address-search.test.tsx`; updated `navigation`, `home-page`, `design-tokens` (ratchet 102); e2e `faculty.spec.ts` (new), `shell` |
