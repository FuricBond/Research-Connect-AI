# P0 evidence — before and after

Captured on the local production build (Compose `frontend`, localhost:3000) with the
design-audit student account. `before/` is the build at `bd34264` (main); `after/` is the
working tree with the seven P0 fixes. Each folder has the same screenshots and a
`measurements.json` (landing page after sign-in, horizontal overflow of 15 pages at seven
widths, and axe results on 12 affected page states at 1440 and 390px).

| Measure | Before | After |
|---|---|---|
| Landing page after sign-in | `/researcher` (25,378px tall) | `/dashboard` (home) |
| Page/width states that scroll sideways (15 pages × 1440–320px) | 105 of 105 | 0 of 105 |
| axe on affected pages: critical / serious / moderate | 26 / 28 / 32 | 0 / 18 / 8 |
| Researcher profile requests on load | 25 | 3 (default section) |
| Duplicate unread-count requests on notification pages | 2 per load | 1 |

The remaining serious findings are colour contrast in the existing palette (`--text-subtle`,
the calendar's blue, the dark personalization panels) and the remaining moderate ones are
heading order inside existing panels; none comes from an element P0 added. Both are P1
(design tokens and component restyling).

| Screenshot | Shows |
|---|---|
| `nav-workspace__1440`, `nav-workspace__390` | Primary navigation (P0.1, P0.2) |
| `nav-workspace-menu-open__1440`, `__390` | The "More" / "Menu" list of every other destination |
| `home__1440`, `home__390` | Signed-in home (before: 404) (P0.3) |
| `profile__1440`, `profile-recommendations__1440` | Profile sections (P0.4) |
| `venue-matching__1440`, `nav-workspace__1440` | Deadline vs risk on venue matching and workspace cards (P0.5) |
| `workspace__360`, `calendar__390`, `calendar__320`, `notifications__390` | Mobile layouts (P0.6) |
| `similar-direct__1440`, `similar-direct__390`, `opportunities-direct__1440` | The paper-based tools opened directly (P0.7) |

The navigation model lives in `frontend/utils/navigation.ts` (the plan named `lib/`, but the
repository's root `.gitignore` ignores every `lib/` directory).
