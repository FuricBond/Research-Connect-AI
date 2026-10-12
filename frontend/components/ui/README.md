# Design-system primitives ("Scholarly Ledger")

Specification: [docs/design/DESIGN_SYSTEM.md](../../../docs/design/DESIGN_SYSTEM.md). Tokens:
[styles/tokens.css](../../styles/tokens.css). Element defaults, type and layout classes:
[styles/base.css](../../styles/base.css).

## Rules for new code

- Style with **CSS Modules** and `--rc-*` tokens only: no hex, `rgb()`, Tailwind classes or
  `dark:` in new components. The tokens follow the light/dark theme on their own.
  `tests/design-tokens.test.ts` enforces this.
- One `h1` per page: use `PageHeader`. Sections use `SectionHeader` (h2). Never skip a level.
- One primary action per section. A list of cards has no primary buttons on every card.
- Every status goes through `utils/status.ts` (`StatusBadge`), every deadline through
  `DeadlineCountdown`, every risk through `RiskIndicator`, every score through `MatchScore`:
  no enum values, no raw floats, no colour without a word.
- Research objects (papers, calls, postings) take the serif title face (`.rc-title`).

## What to use

| Need | Use |
|---|---|
| Page title + one-line purpose + actions | `PageHeader` (`components/ui/PageHeader`) |
| Section heading with a link or ghost action | `SectionHeader` |
| An action | `Button` (`primary` once per section, `secondary`, `ghost`, `danger`, `danger-ghost`, `link`); `loading` keeps the label |
| A call to action that navigates | `ButtonLink` |
| An icon-only action | `IconButton` (`label` is required) |
| Text, email, number, date input | `TextInput` (always a visible `label`; `hint`, `error`) |
| Long text / choice / search | `TextArea`, `Select` (native), `SearchInput` |
| Yes/no in a form / setting that applies at once | `Checkbox` / `Switch` |
| One of several | `RadioGroup` (fieldset + legend) |
| A grouped object | `Card` (`default`, `muted`, `interactive`; `CardHeader`, `CardFooter`) |
| Status word | `Badge`, `StatusBadge` + `utils/status.ts`, `PriorityLabel` |
| Decision or short form over the page | `Dialog` |
| Secondary detail beside a list | `Drawer` (full screen on phones) |
| Loading with known structure | `SkeletonList` / `SkeletonText` / `Skeleton` |
| Nothing to show | `EmptyState` (what is empty, why, what next) |
| Something failed / not allowed / missing | `ErrorState` (`failed`, `permission`, `not-found`, `invalid`, `unavailable`, `offline`, `unknown`) |
| Inline message in the flow | `Alert` (`announce` only for errors after an action) |
| Colour theme control | `ThemeSwitcher` (in the shell's account menu; one per page) |

Layout without new CSS: `.rc-container`, `.rc-stack`, `.rc-cluster`, `.rc-grid` (set
`--rc-grid-min`), `.rc-switcher` (set `--rc-switch-at`), `.rc-ruled` (compact ruled list),
`.rc-scroll-x` (a wide table: give it `role="region"`, an `aria-label` and `tabIndex={0}`).
Gaps: `.rc-gap-1 … .rc-gap-8`.

## The application shell

`components/shell/` (P2) frames every page from `app/layout.tsx`: the header (brand, global
search, notification bell, account menu), the primary navigation (sidebar from 1024px, drawer
below) and `<main id="main-content">`. Destinations, groups and roles live in one place,
`utils/navigation.ts`. Pages render only their own content: no page renders a navigation, a
second header or a theme control.

## Legacy code

Unmigrated pages keep their global classes and Tailwind utilities. Their old CSS variables
alias the tokens (`styles/globals.css`), and Tailwind's palette resolves to the tokens
(`tailwind.config.ts`), so they already use the Scholarly Ledger colours in both themes.
When a page is migrated, replace its classes with these primitives and delete the legacy CSS
it no longer uses; lower `INLINE_STYLE_LIMIT` in `tests/design-tokens.test.ts` as inline
styles disappear.
