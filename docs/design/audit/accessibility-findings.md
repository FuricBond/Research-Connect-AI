# Accessibility findings (baseline)

Target: WCAG 2.2 AA. Tools: axe-core 4.13 (already in `node_modules` via
`eslint-plugin-jsx-a11y`) injected into the production build with Playwright 1.63, tags
`wcag2a wcag2aa wcag21a wcag21aa wcag22aa best-practice`; a scripted keyboard pass (14 Tab
stops per page); code review of dialogs, navigation and forms; contrast computed with the
WCAG formula.

Scope: 68 page states (34 route states × 1440 and 390px, all three roles).

## 1. Automated results (axe)

| Impact | Violations (rule × page state) | Page states affected |
|---|---|---|
| Critical | 17 | 9 |
| Serious | 45 | 44 (contrast on 22 routes) |
| Moderate | 69 | 37 |
| **Page states with ≥ 1 serious/critical** | | **44 of 68** |

| Rule | Impact | WCAG | Routes | Nodes | Where |
|---|---|---|---|---|---|
| `select-name` | critical | 4.1.2 | 7 | 39 | workspace filters and per-card priority; submission; notification settings rule form; researcher profile; preferences |
| `label` | critical | 4.1.2 / 1.3.1 | 1 | 12 | notification settings: 6 alert-category switches (each viewport) |
| `button-name` | critical | 4.1.2 | 2 | 9 | researcher profile: icon-only toggle buttons (Tailwind panels) |
| `color-contrast` | serious | 1.4.3 | 22 | 988 | researcher profile (215 nodes), venue matching (75), DOI links on search (19 per page), supervisor topic labels, admin table row headers |
| `aria-dialog-name` | serious | 4.1.2 | 1 | 2 | ExplainabilityDrawer (`.drawer-overlay` has `role="dialog"`, no name) |
| `scrollable-region-focusable` | serious | 2.1.1 | 1 | 2 | researcher profile: scrollable list not reachable by keyboard |
| `heading-order` | moderate | — | 16 | 32 | skipped levels (h2 → h4 in state containers, h3 under h1) |
| `page-has-heading-one` | moderate | — | 12 | 17 | `/`, `/browse`, `/similar`, `/opportunities`, `/reading-list`, `/researcher`, `/researcher/preferences`, `/workspace/[id]`, submission, not-found, denial page |
| `landmark-no-duplicate-main` / `landmark-main-is-top-level` / `landmark-unique` | moderate | — | 4–5 | 30 | notification pages render `DiscoveryNavbar` and a `main` inside the layout's `main` |

Full per-page output: [`data/capture-results.json`](data/capture-results.json) (`axe` field).

## 2. Manual findings

| # | Finding | WCAG | Severity |
|---|---|---|---|
| A1 | **No skip link.** The first Tab stop on every page is Sign in/Sign out, followed by up to 13 nav tabs before any content. | 2.4.1 | Serious |
| A2 | **Active navigation not exposed**: no `aria-current="page"` anywhere; the "Active" pill is visual text read as part of the link name ("Opportunity Workspace Active"). | 1.3.1, 4.1.2 | Moderate |
| A3 | **Explanation drawer**: `role="dialog"`/`aria-modal` on the overlay, no accessible name, focus is not moved into it and not returned, background stays tabbable (no `inert`); Esc does close it. | 2.4.3, 4.1.2 | Serious |
| A4 | **Other modals are not dialogs**: calendar "Create planning milestone", workspace "Invite collaborator" / "Create task", submission document and version modals have no `role="dialog"`, no focus management. | 4.1.2, 2.4.3 | Serious |
| A5 | **Horizontal overflow on every signed-in page with unread notifications** (P0-1 in the visual audit) breaks reflow at 320px-equivalent widths. | 1.4.10 | Serious |
| A6 | **Colour-only meaning**: workspace priority (MEDIUM green, HIGH orange) and status chips, match colours, deadline urgency colours; meaning is partly carried by text, but the colour mapping conflicts (green = medium priority and = success). | 1.4.1 | Moderate |
| A7 | **Low-contrast text tokens**: `--text-subtle #94a3b8` = 2.56:1 on white (used for text 25×); calendar event labels ≈ 1.78:1; white on the calendar blue button 3.68:1. | 1.4.3 | Serious |
| A8 | **Focus indicators** are Chromium's default outline (visible on 13–14 of 14 stops per page), not designed; the design relies on browser defaults that differ across browsers and are thin on coloured buttons. | 2.4.7, 2.4.13 (AAA ref.) | Moderate |
| A9 | **Unlabelled form controls in settings** (switches, selects) — confirmed by axe — mean screen-reader users cannot tell which alert category a switch controls. | 1.3.1, 3.3.2 | Critical |
| A10 | **Repeated identical link names**: "View Call", "Edit Notes", "How this was scored", "Why this rank?" repeat on every card without context (no `aria-describedby` to the card title). | 2.4.4 / 2.4.9 | Moderate |
| A11 | **Live updates**: unread badge updates silently every 30s (fine), but search result counts and saved-state changes are not announced. | 4.1.3 | Minor |
| A12 | **Reduced motion** handled in one file only; `pulse` / `pulse-border` loops run regardless. | 2.3.3 (AAA), 2.2.2 | Minor |
| A13 | **Target size**: icon buttons in notification rows and reading-list checkboxes are below 24×24 CSS px in places. Not exhaustively measured — to be verified in P11. | 2.5.8 | Minor (to verify) |
| A14 | **Heading structure**: several pages have no h1, some have the page title as h2 and card titles as h3 under an h1 elsewhere; `supervisors` declares three h1 variants in different branches (only one renders, correct). | 1.3.1, 2.4.6 | Moderate |

## 3. What already works

- Auth forms have labels; errors use `role="alert"`; route guards announce state with
  `role="status"`.
- Unread count has a visually hidden "unread" suffix (its positioning is the cause of A5, not
  its intent).
- Research result cards are `<article aria-labelledby>`; tables in admin use `scope`.
- Keyboard focus is visible (browser default) on all tested pages.

## 4. Targets for the redesign

- Zero serious/critical axe violations on all main routes in both themes, enforced by an axe
  check in the e2e stack (see plan P11).
- Skip link, landmarks, one h1, `aria-current`, labelled dialogs with focus management on
  every overlay, labels on every control, 4.5:1 text contrast from tokens (all token pairs
  verified in [DESIGN_SYSTEM.md §3.4](../DESIGN_SYSTEM.md#34-verified-contrast-wcag-22)).
- Manual screen-reader pass (NVDA + Chrome, VoiceOver + Safari) on the five core workflows
  before sign-off; automated tools cover roughly a third of WCAG criteria.
