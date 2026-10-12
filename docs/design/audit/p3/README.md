# P3 evidence — authentication and public pages

Measured on 2026-10-12 against the isolated end-to-end stack (`python e2e/run_e2e.py --keep`:
production images of the P3 working tree on `design/frontend-redesign-p2`, seeded demo data),
then rebuilt for the two follow-up fixes below. Every number comes from `measurements.json` in
this folder. The design is in [DESIGN_SYSTEM.md §15](../../DESIGN_SYSTEM.md#15-authentication-and-public-pages-p3).
This is the phase's own implementation check, not the independent audit (which covers all
phases once they are done).

## Pages (24 loads)

Sign in, registration, the visitor's search landing, not-found (a visitor), Settings and the
permission state (`/admin` as a student) × light and dark × 1440 and 360px.

| Check | Result |
|---|---|
| Page-level horizontal overflow; fields, buttons or links off screen | **0 of 24** |
| `h1` per page | 1: "Sign in", "Create an account", "Literature search", "Page not found", "Settings", "This page is for Administrator accounts." |
| Page titles | "Sign in — ResearchConnect AI", "Create an account — …", "Literature search — …", "Page not found — …", "Settings — …" (the admin page keeps the site title: P10) |
| Theme applied | as chosen on every load |
| axe critical / serious | **0 / 0** |
| axe moderate | 4 hits, all `heading-order` on `/` (the search page's first-view `h4`, already recorded in the P2 evidence; P5) |
| 200% text at 320px (`/login`, `/register`, `/settings`, not-found) | overflow 0, nothing off screen (after the fixes below) |

## Behaviour

| Check | Result |
|---|---|
| Sign-in Tab order | Email → Password → Show password → Sign in → Create an account |
| Show-password toggle | 28 × 28px (44px on coarse pointers, from the tokens), 2px focus ring, `aria-pressed` |
| Sign in sent empty (Enter in the email field) | focus stays on Email, `aria-invalid`, "Enter your email address." under it; no request |
| Wrong password | alert "Email or password is incorrect."; focus stays in the password field |
| Registration sent empty (360px, dark) | focus on Full name; 4 fields marked invalid; no request |
| Settings: password change sent empty | focus on Current password; 3 fields marked; **0** requests |
| Settings: wrong current password | 1 request; alert "Current password is incorrect."; still signed in |
| Account menu | Researcher profile, Research preferences, Settings (`/settings`) |
| Password change, end to end | `e2e/auth.spec.ts`: changed in Settings, the browser stays signed in, signing in uses the new password and the old one is refused |

## Fixes made during this check

- **Buttons at 200% text.** The shared `Button` never wrapped its label, so on a 320px phone at
  200% text "Change password" and "Go to search" ran past their containers (by 70 and 10px), and
  full-width buttons clipped their label. `Button` is now never wider than its container and
  wraps a label that does not fit (`components/ui/Button/Button.module.css`). At the normal text
  size, every visible `Button` on 21 signed-in and 4 public pages at 1440, 768, 390 and 320px
  (145 instances) was checked: 143 keep one line; the two that wrap are "Find a paper in
  Literature Search" on `/similar` and `/opportunities` at 320px, which used to overflow their box.
- **Sign-in and registration on phones.** Below 480px the form sits on the page instead of in a
  bordered card, which gives the title and fields their width at 200% text (the title had broken
  inside a word).

## Screenshots

`light/` and `dark/`: `<state>__<width>.jpg` — sign in, registration, the visitor's search
landing, not-found, Settings and the permission state at 1440 and 360px in both themes; sign in
with field errors and after a refused password (1440, light); registration with field errors
(360, dark); Settings after a wrong current password (1440, light); and `text-200-percent-*`:
sign in, registration, Settings and not-found with 200% text at 320px. Only seeded demo data
appears.

## Known issues carried forward

- `/`: the first-view prompt's `h4` (heading order) and its legacy styling — the search page is
  rebuilt in P5. The visitor's line takes the prompt's text style until then.
- The administration page still uses `styles/auth.css` (`.auth-pending`, `.auth-error`, the
  table): P10.
- Notification and appearance settings are not yet inside `/settings` (P8); the theme stays in
  the account menu.
- Deferred, not changed here: session restore treats every `/auth/me` failure as a sign-out and
  has no timeout (P2 audit F10, needs approval); `/supervisors` is guarded without a role, so a
  faculty account can open it and the API answers 403 (authorization, pre-existing).
- Text enlargement was simulated with a 200% root font size; this is not a full WCAG 1.4.4 audit,
  and no screen-reader pass was made (P11).
