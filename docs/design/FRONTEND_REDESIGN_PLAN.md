# ResearchConnect AI — Frontend redesign plan

> Status: **audit and specification for review. No application code has been changed.**
> Branch: `design/frontend-redesign-plan`. Companion documents:
> [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md) · [tokens.draft.css](tokens.draft.css) (not imported) ·
> [audit/](audit/README.md) (106 screenshots, axe, performance, inventories).

Implementation starts only after this plan is approved. Every decision below cites the audit
finding it answers (`P0-n`, `P1-n`, `A-n`, `V-n`).

---

## 1. Current frontend architecture

- **Next.js 15.5 App Router, React 19, TypeScript.** 23 routes; every page is a Client
  Component that fetches after mount through `services/api.ts` (170 functions over ~130
  endpoints, no cache, no request de-duplication).
- **Shell**: `layout.tsx` → `SessionProvider` → `AppHeader` (brand, "Phase 2.7 Intelligence
  Engine" pill, `AuthMenu`) → `DiscoveryNavbar` (one horizontal strip of up to 13 tabs) →
  `<main>`. No sidebar, no home page; `/` is literature search.
- **Auth/roles**: session context verified against `/auth/me`; `RequireAuth` guards 14 pages;
  only `/admin` (ADMIN) and `/supervisors` (STUDENT) are role-restricted; nav hides tabs per
  role. Backend remains the authority.
- **Styling**: three eras coexist — 11 global stylesheets (7,490 lines), Tailwind utilities
  with preflight off (13 personalization components), and 910 inline style objects (9
  researcher-profile components with no classes at all). 33 tokens defined, 11 more used but
  undefined. Fonts declared, never loaded. No responsive system (two media queries).
- **Tests**: 26 Vitest files (241 tests, mostly role/text queries), 3 Playwright specs plus
  69 API and 7 stack e2e tests run by `e2e/run_e2e.py`; CI runs Vitest, type-check, lint and
  build (not e2e).

Full detail: [audit/route-inventory.md](audit/route-inventory.md).

## 2. Audit summary

**23 routes** and **48 component files** audited, by role, at six viewports.

### Top 10 UX problems

1. No home: deadlines, application updates and notifications are scattered over four pages
   (P0-3).
2. Navigation hides most destinations: 6 of 13 tabs visible at 1440px, 2 at 390px (P0-2).
3. Similar research and venue matching are top-level tabs that dead-end without a selected
   paper (P0-7).
4. The profile page is six products stacked into 25,378px, 25 requests (P0-4).
5. Recommendations — the personalization engine — are buried 2,000px down the profile;
   no "For you" entry point.
6. Workspace cards carry ~9 actions; status changes need the right one of four "Move to"
   buttons (P1-7).
7. Faculty have no home, no applicant inbox, and decision buttons in the wrong order (P1-9,
   P1-10).
8. Search state is not in the URL; filters hidden behind "Filters & Ranking Mode";
   reasons only in a drawer (P1-16).
9. Browse calls has no search, filters, sort, pagination or save (P1-12); venue matching
   ranks expired calls first (P1-8).
10. Terminology: "opportunity", "call", "venue", "posting", "opening" overlap; "match",
    "fit", "composite score", "relevance" are interchangeable.

### Top 10 visual/design problems

1. Whole-page horizontal scrolling on signed-in pages with unread notifications (P0-1).
2. Deadline and risk share red; unknown risk shown as a red warning on every saved call (P0-5).
3. Broken mobile layouts: calendar, workspace rows, admin tables, stacked stat cards (P0-6).
4. Internal phase labels in the header and on five pages (P1-1).
5. Raw enums and floats: `UNDER_REVIEW`, `IN_APP`, "3.7978d remaining", "+0.5630" (P1-2, P1-3).
6. Three primary colours (teal, blue, indigo/purple) (P1-5, V5).
7. Half-dark pages under OS dark mode (P1-6, V4).
8. 121 colours, 41 font sizes, 50 spacing values, 21 radii, 41 button classes (V7).
9. No loaded font: the product looks different on every OS (V3).
10. Decorative stat cards and caveat panels push the real content below the fold (P2-2, P1-8).

### Top accessibility problems

No skip link (A1); unnamed dialogs without focus management (A3, A4); 39 unlabelled selects
and 12 unlabelled switches (A9); 988 contrast failures (A7); reflow broken by overflow (A5);
active nav not exposed (A2); several pages without an h1. **44 of 68 page states** have a
serious or critical axe violation. [audit/accessibility-findings.md](audit/accessibility-findings.md)

### Performance baseline

103 kB shared first-load JS; routes 112–129 kB except `/researcher` 167 kB; CSS 24.4 kB gzip;
no fonts; local LCP 36–536 ms; CLS ≤ 0.067; `/researcher` 25 requests; unread count polled
twice on notification pages. [audit/performance-baseline.md](audit/performance-baseline.md)

---

## 3. Design directions

### Direction A — "Scholarly Ledger" (recommended)

- **Philosophy**: the interface is an annotated research record. Research objects are set like
  a bibliography; evidence is presented like footnotes; chrome recedes.
- **Colour**: paper `#F7F6F3`, white surfaces, warm ink neutrals, one petrol-teal brand
  `#0E6B66`; status hues only for meaning; red reserved for danger/high risk.
- **Typography**: Source Serif 4 for page and object titles, Source Sans 3 for UI and reading,
  system mono for identifiers; tabular figures.
- **Density**: compact lists (12×16 rows), spacious detail pages; 4px rhythm.
- **Components**: flat cards with hairline borders, radius 6–8, no shadows except floating
  layers; badges with icons and words.
- **Navigation**: left sidebar grouped by user job (Discover · For you · My research),
  collapsible rail; header with global search, notifications, account.
- **Cards**: title (serif) → metadata row → evidence line ("Good match · similar meaning,
  title terms") → quiet action row.
- **Data visualisation**: thin horizontal meters, dot timelines for deadlines, small
  multiples; petrol for "this", ink for baseline; never more than three hues.
- **Mobile**: header + bottom tab bar (4 role-specific items + More), full-screen sheets for
  filters and evidence, tables become lists.
- **Sample dashboard (student, 1440)**

```
┌ sidebar ┬────────────────────────────────────────────────────────────────────────┐
│ Home    │ Good morning, Priya                         [ Search papers…      / ]  │
│ Discover│────────────────────────────────────────────────────────────────────────│
│  Search │ NEEDS ATTENTION                          │ RECOMMENDED FOR YOU         │
│  Calls  │ ◷ BTSD 2026 workshop · due in 2 days     │ Explainability in GNNs: a   │
│  Postings│   Planning · next: draft related work →  │ taxonomic survey            │
│ For you │ ◷ IEEE MLCA 2026 · due in 4 days         │ Good match · follows "Graph │
│  Recomm.│   Applied                                │ neural networks"   Why? →   │
│  Superv.│ ● Application under review               │ …2 more                     │
│  Peers  │   RA: explainable GNNs · Dr Okafor       │─────────────────────────────│
│ My resea│──────────────────────────────────────────│ POSTINGS THAT FIT YOU       │
│  Worksp.│ UPCOMING · next 30 days                  │ RA: GNN traffic forecasting │
│  Reading│ 8 ●──9 ●──10 ●●────────────24 ○──27 ○    │ Good fit · 2 shared topics  │
│  Calend.│                                          │─────────────────────────────│
│  Applic.│ READING   To read 2 · Reading 2 · Done 1 │ PROFILE 50% · add ORCID →   │
└─────────┴──────────────────────────────────────────┴─────────────────────────────┘
```

- **Sample search page (1440)**

```
 Search papers  [ graph neural networks explainability          ×][Search]
 20 results · sorted by relevance ▾                     Ranking: Hybrid ▾
┌ Filters ────────┐ ┌──────────────────────────────────────────────────────────────┐
│ Year  2019–2026 │ │ 1  Parameterized Explainer for Graph Neural Network            │
│ Type  ☑ Article │ │    Luo, Zong, Xu et al. · NeurIPS · 2020 · 217 citations · OA  │
│       ☑ Preprint│ │    Despite recent progress in GNNs, explaining predictions…    │
│ Open access ☐   │ │    ▮▮▮▮▯ Good match · similar meaning · terms in title  Why? → │
│ Min. citations  │ │    [Save]  Find similar  Find venues                           │
│ Topic …         │ ├──────────────────────────────────────────────────────────────┤
│ [Clear filters] │ │ 2  Explainability in Graph Neural Networks: A Taxonomic Survey │
└─────────────────┘ └──────────────────────────────────────────────────────────────┘
```

- **Advantages**: distinctive and appropriate for academia; readable long titles and
  abstracts; calm enough for dense data; maps cleanly onto the existing brand; works for all
  three roles; low bundle cost.
- **Disadvantages**: serif titles cost ~30 kB of font; warm neutrals need care in dark mode;
  restraint can look plain if spacing and type are executed poorly (mitigated by the
  enforced scale).

### Direction B — "Research Console"

- **Philosophy**: an instrument panel for power users: maximum density, keyboard-first,
  everything visible at once.
- **Colour**: cool slate neutrals, dark-first theme, electric cyan accent, signal colours for
  states.
- **Typography**: IBM Plex Sans + IBM Plex Mono for all numbers and IDs.
- **Density**: very high; 28px rows; split panes everywhere.
- **Components**: square corners, outline buttons, inline editing, command palette (Ctrl/⌘K).
- **Navigation**: icon-only rail + command palette; tabs in panes.
- **Cards**: none — tables and split panes (list left, detail right).
- **Data visualisation**: sparklines, heat strips, monospaced score columns.
- **Mobile**: list ↔ detail stack; command palette as search.
- **Sample dashboard**: a three-pane grid — tasks table, deadline heat strip, live activity log.
- **Sample search page**: a results table (rank, title, year, cites, match, risk) with a
  detail pane on the right showing the abstract and evidence.
- **Advantages**: excellent for admins and faculty triaging many items; fast keyboard flows.
- **Disadvantages**: intimidating for students and first-time users; tables truncate long
  paper titles; dark-first harms long reading; reads as a developer tool, not an academic
  product; more custom interaction code (split panes, palette) and higher accessibility risk.

### Decision

**Direction A.** The product's primary users are students and researchers reading,
comparing and deciding; its examiners judge credibility. Direction A serves reading and
trust; Direction B serves operators. From B we keep three ideas that strengthen A without
changing its character: **tabular figures everywhere**, **`/` to focus search** (no command
palette), and a **compact table mode** for the admin console and faculty applicant inbox.

---

## 4. Visual identity

Defined in [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md): colour roles and research data colours
(§3, all pairs measured, 0 failures), typography (§4), spacing/shape/elevation (§5), motion
(§6), components (§8–9), states (§10), accessibility contract (§11), enforcement (§12).

## 5. Information architecture and entities

| Entity (one term) | What it is | Replaces |
|---|---|---|
| **Paper** | A research work in the corpus | "research work", "literature", "manuscript" |
| **Call** (call for papers) | An ingested conference/journal/workshop/special-issue call | "opportunity", "call", "venue & call" |
| **Venue** | The conference or journal behind a call | (unchanged) |
| **Posting** | A faculty-authored opening (project, thesis topic, RA, internship, …) | "opening", "position", "research opportunity" |
| **Application** | A student's application to a posting | (unchanged) |
| **Workspace** | The user's tracked calls and their submissions/collaboration | "Opportunity Workspace", "workspace opportunities" |
| **Reading list** | Saved papers | (unchanged) |
| **Relevance** | How well a paper matches a *search* | "match %" on search |
| **Match** | How well an item matches *you* (personalised) | "composite score" |
| **Fit** | How well a posting or supervisor suits a student | (unchanged) |

Route URLs stay as they are (bookmarks, tests, e2e); only labels change. New routes are
additive: `/dashboard`, `/recommendations`, `/calls/[id]`, `/postings/applicants`,
`/admin/users`, `/admin/research-data`, `/settings`.

## 6. Application shell

| Width | Structure |
|---|---|
| ≥ 1280 | Sidebar 248px (collapsible to a 64px rail, remembered per browser) + header 56px (global search, notification bell with count and popover, account menu) + content (max 1200px) |
| 1024–1279 | Same, sidebar starts collapsed as a rail with tooltips |
| 768–1023 | Header with a menu button; navigation in a modal drawer |
| < 768 | Compact header (logo mark, search icon → full-screen search sheet, bell, avatar) + bottom tab bar (4 role items + More → drawer) |

- **Global search**: header field "Search papers" (`/` focuses it) → `/?q=…`.
- **Notification centre**: bell with unread count (one poll for the whole app, shared through
  context — fixes the duplicate polling), popover with the latest 5 grouped items and
  "View all".
- **Account menu**: name, role, Profile, Research preferences, Settings, Sign out.
- **Skip link** first; one `nav aria-label="Primary"`; `aria-current="page"` on the active item;
  no "Active" pill.
- Removes: "Phase 2.7 Intelligence Engine" pill, the duplicated `DiscoveryNavbar` on the two
  notification pages.

## 7. Navigation by role

Grouped by job; groups have visible labels; items in a group are ordered by frequency.

**Student**
- Home (`/dashboard`)
- Discover: Search papers (`/`), Calls for papers (`/browse`), Research postings (`/postings`)
- For you: Recommendations (`/recommendations`), Find a supervisor (`/supervisors`), Peers (`/peers`)
- My research: Workspace (`/workspace`, with a Submissions tab → `/submissions`), Reading list
  (`/reading-list`), Calendar (`/calendar`), Applications (`/postings/applications`)
- Account menu: Profile (`/researcher`), Research preferences (`/researcher/preferences`),
  Settings (`/settings`), Sign out. Notifications via the bell (`/notifications`).
- Mobile bar: Home · Search · Workspace · Reading list · More

**Faculty**
- Home (`/dashboard`, recruiting view)
- Discover: Search papers, Calls for papers, Research postings
- Recruiting: My postings (`/postings?view=mine`), Applicants (`/postings/applicants`)
- For you: Recommendations, Peers
- My research: Workspace (+ Submissions), Reading list, Calendar
- Account menu as student. Mobile bar: Home · Search · My postings · Applicants · More

**Admin**
- Overview (`/admin`)
- Administration: Users (`/admin/users`), Research data (`/admin/research-data`)
- Discover: Search papers, Calls for papers, Research postings
- Account menu: Settings, Sign out. Mobile bar: Overview · Users · Research data · Search · More

Hidden per role (navigation only; authorisation unchanged): supervisors for faculty/admin;
recruiting for students/admin; personal research tools for admin (Q5). Similar research and
venue matching leave the navigation and become actions on a paper (P0-7).

## 8. Dashboard (`/dashboard`)

Answers, in order: *what needs my attention, what is new for me, what is coming up.*

**Student modules** (each loads and fails independently, skeleton per module):

| Module | Content | Source (existing API) |
|---|---|---|
| Needs attention | Workspace calls due ≤ 14 days with status and next step; application status changes; "profile incomplete" nudge | `GET /workspace`, `GET /postings/applications/mine/summary` |
| Upcoming (30 days) | Dot timeline of call deadlines + calendar milestones | `GET /workspace` (deadlines), `GET /calendar/{id}/events` |
| Recommended for you | Top 3 with match band, one reason, Why? | `GET /researchers/{id}/recommendations/unified?limit=3` |
| Postings that fit you | Top 3 open postings accepting applications, by fit | `GET /postings?…`, `POST /postings/fit-scores` |
| Reading progress | To read / reading / done counts | `GET /reading-list?limit=1` (counts) |
| Notifications | Unread count + latest 3 (shared with the bell) | shell context |

Request budget: **≤ 7 parallel requests**, nothing sequential. Empty account: a three-step
"Get started" checklist (add interests, save a call, save a paper).

**Faculty**: Needs your decision (applications submitted/under review across your postings),
Your open postings (applicants, deadline, status), Upcoming deadlines, Recommended papers.
**Admin**: the admin overview (§15) is the home.

Rule: no module that only repeats a count available one click away (P2-2).

## 9. Search experience

- **URL state**: `/?q=…&type=…&year=…&oa=1&page=2` (back button, sharing, reload).
- **Layout**: query bar; result count + sort (Relevance, Newest, Most cited — client-side
  sort of the returned page where the API has no sort, labelled accordingly); filter rail at
  ≥ 1280, filter sheet below; ranking mode kept as an advanced control.
- **Result (PaperCard)**: rank · serif title · authors · venue · year · citations · OA ·
  DOI; 2-line abstract with "Show abstract"; **evidence line** — relevance band + the two
  strongest reasons in words, + "Why this result?"; quiet actions: Save, Find similar, Find
  venues. No primary button per card (P2-6).
- **Why this result? → Evidence panel** (Drawer): plain-language summary, contribution meters
  with human names, evidence list, quality facts, "Technical details" with today's exact
  decomposition (kept for examiners). Proper dialog semantics (A3).
- **States**: skeleton results, "no results" with suggestions and "Clear filters", error with
  Retry, slow-query notice after 3 s.
- One clear (×) control; `aria-live` announces "20 results".

## 10. Paper experience

There is no paper page today and the backend has no "get paper by id" endpoint (Q4).
Plan: a **Paper panel** (Drawer, 640px; full-screen sheet on mobile) opened from any paper
title, built from data already in hand:

title (serif, full) → AuthorList (all authors, ORCID links) → venue · year · type → topics
(ResearchTopicTags, shared ones marked) → abstract (reading style, 72ch) → relevance/match
with reasons → CitationMetadata (citations, OA, DOI) → actions: **Save to reading list**
(primary), Export citation (BibTeX of this paper via the reading list export when saved, Q4),
Find similar, Find venues, Open publisher page → Similar papers (first 5 inline).

`/similar` and `/opportunities` remain as full pages reached from the panel, with a
breadcrumb "Search › <paper> › Similar papers" and the selected paper summarised at the top
(collapsed abstract). If Q4 adds `GET /discovery/research/{id}`, the panel gains a shareable
`/papers/[id]` URL with no other change.

## 11. Opportunity experience (calls and postings)

**OpportunityCard (call)** — header row: type badge, RiskBadge (shield); title; venue ·
location · mode (In person / Online / Hybrid); DeadlineBadge (clock + countdown); topics; match
when personalised; actions: Save to workspace, Source. Expired calls hidden by default ("Include
closed calls" filter) on Browse and venue matching (Q10). The "Limited metadata" caveat becomes
"Not assessed" on the badge, explained on demand (P1-8).

**Call detail `/calls/[id]`** (new, existing APIs `GET /api/opportunities/{id}`,
`/deadlines`, `/risk-explanation`): summary, deadline timeline (abstract → paper →
notification → camera-ready), risk explanation with evidence, workspace status if saved,
actions Save / Add deadlines to calendar (existing projection endpoint) / Source.

**Browse calls** (`/browse`): title "Calls for papers"; search, type, mode, upcoming, sort
(the API already supports them), pagination (20 per page), Save action.

**Postings**: keep the current structure (the best in the app); move facts (deadline, mode,
positions, terms) into a right-hand summary column on detail at ≥ 1024; FitScore phrased as
an action ("Partial fit — add your skills to improve it").

Deadline and risk are never confused: different icons, colours, positions and words
(DESIGN_SYSTEM §3.2).

## 12. Personalization

- **`/recommendations`** (new): sections "Because you follow *Graph neural networks*", each item
  a RecommendationCard with match band, reason, feedback (Helpful / Not relevant — existing
  feedback endpoints) and Why this match?
- **Transparency ("What shapes your recommendations")**: one panel listing declared
  interests, inferred interests (labelled "from your saved calls", with strength in words),
  and controls: edit, remove, pause personalization, reset (existing settings/reset
  endpoints). Not creepy: only what the user did on this platform, stated plainly.
- **One explanation UI**: the Evidence panel replaces ExplainabilityDrawer,
  WhyThisRecommendationModal and RecommendationExplanationModal (P1-15).
- **Profile** (`/researcher`) becomes: profile summary, publications, research topics
  (declared vs from publications — resolves P1-14 by naming both), preferences link. The
  diagnostics (calibration, governance, quality, drift, history, feedback log) move to
  `/recommendations` under "Technical details" — nothing is removed (P0-4).

## 13. Workspace

**Decision: list-first hybrid.** A Kanban board looks good in demos but needs drag-and-drop
(new code, accessibility cost) and wastes space for 4–30 items; the real questions are
"what is due next" and "what's my next step".

- `/workspace`: tabs Calls | Submissions; status filter chips with counts (replace the five stat
  cards); sort by deadline (default), priority, updated. Each row: title, venue type,
  DeadlineBadge, RiskBadge, status (StatusBadge **as a menu**: one control replaces four "Move
  to" buttons, offering only valid transitions), priority (glyph + word), next action ("Draft
  submission →"), overflow menu (Collaborate, Notes, Archive, Delete with confirmation).
- Notes collapse into an "Add note" disclosure; tags as chips.
- `/workspace/[id]`: PageHeader with breadcrumb, deadline timeline, status; tabs Overview,
  Tasks, Submission, Members, Activity (the submission workflow becomes a tab instead of a
  blue external-style button).
- Mobile: rows stack (title, then deadline/risk line, then status menu + overflow) with no
  horizontal overflow (P0-6).

## 14. Faculty experience

- Home = recruiting dashboard (§8).
- **My postings**: table at ≥ 1024 (title, status, applicants, new, deadline, actions), cards on
  mobile; "New posting" opens a full-page editor with sections (basics, description, skills,
  terms, contact) and a live preview of the PostingCard.
- **Applicants** (`/postings/applicants`, new): one inbox across postings, grouped by posting,
  filter by status; built from `GET /postings/mine` + `GET /postings/{id}/applications` per
  posting (capped at the 10 most recent open postings; Q4 offers an aggregate endpoint later).
- **Applicant review**: ApplicationCard (faculty variant) with fit and reasons, cover note,
  decisions in pipeline order — Shortlist → Make offer — and "Not selected" as a confirmed
  secondary action (P1-9). Posting status actions: Close, Mark filled (primary actions) and
  Cancel posting (danger, confirmed).

## 15. Admin experience

- **Overview** (`/admin`): system health (`GET /api/health/ready`: database, schema), research
  data monitor, latest failed runs, account counts by role, inactive accounts.
- **Research data monitor** (replaces DataFreshnessCard): status line with health dot and
  word ("Healthy · refreshed 2 hours ago · next in 6 hours"), papers added in 24 h, run
  history strip (last 20 runs as coloured squares with tooltips; failures red with a link),
  lane table with human names ("Newest papers", "Rising papers") and subfield names (Q7);
  stale (> 2 intervals without success) and failing states are prominent.
- **Users** (`/admin/users`): table with pagination (25), search, role/active filters; role
  change through a menu with a confirmation dialog naming the person and the consequence;
  active/verified toggles with undo toast. Mobile: DataList.
- The page title comes first; the monitor is a section, not a card above the title (P1-11).

## 16. Mobile strategy

Defined layouts at 360, 390 and 768 — not desktop squeezed:

| Area | < 768 | 768–1023 |
|---|---|---|
| Navigation | Bottom bar (4 + More) + drawer | Header + drawer |
| Search | Full-screen search sheet from the header icon; filters as a bottom sheet | Inline field; filter sheet |
| Cards | Single column; action row wraps to icons + overflow menu | Single column, wider |
| Tables | DataList (label: value stacks) | Table with horizontal scroll only for admin runs |
| Drawers | Full-screen sheets with a close button and back gesture | 480px drawer |
| Forms | Full-width fields, 44px targets, sticky submit bar | Two columns where natural |
| Workspace | Stacked rows, status menu | List |
| Calendar | **Agenda view by default**, month grid optional (7 columns of 44px fit 360) | Month grid |
| Notifications | Grouped list, swipe-free (buttons), timestamp under the title | List |

Rule: no horizontal page scroll at 320px CSS width (WCAG 1.4.10); verified by the overflow
check from the audit tool in CI-able e2e.

## 17. Accessibility plan

Contract in DESIGN_SYSTEM §11. Concretely: skip link, landmarks and one h1 per page (P2);
labelled controls everywhere (fix the 39 selects/12 switches in the phases that touch them);
native `<dialog>` for every overlay with focus in/return (P1 primitives); `aria-current`; contrast
via tokens only; reduced motion via tokens; target size checks; axe in the e2e stack failing
on serious/critical (P11); manual NVDA/VoiceOver pass on five workflows (search → save,
apply to posting, track a call, faculty decision, admin role change).

## 18. Performance plan

Budgets in [audit/performance-baseline.md §5](audit/performance-baseline.md#5-budgets-for-the-redesign-p12-acceptance).
Means: next/font/local with one preloaded file; primitives without dependencies; a small
`useApiResource` hook (abort on unmount, in-memory de-duplication per URL for the session,
stale-while-revalidate on focus) to remove duplicate requests; split `/researcher` panels so
diagnostics load only when opened (dynamic import); skeletons sized to content (CLS ≤ 0.02);
delete legacy CSS as pages migrate.

## 19. States

Every page implements the state table in DESIGN_SYSTEM §10. Page-specific notes: search shows
skeleton results; dashboard modules fail independently; workspace/reading list keep
optimistic updates with rollback + toast on error; offline banner app-wide; permission-denied
uses ErrorState `permission` (today's RequireAuth message, restyled, same text so tests stay
valid).

## 20. Motion

DESIGN_SYSTEM §6: 80/140/200ms, three easings, no page transitions, no infinite animations
(remove `pulse`, `pulse-border`), reduced motion = no motion.

## 21. Copy and terminology

Rules: sentence case; plain words; human units; no enums or phase labels; one term per
concept (§5). Rewrites (current → proposed):

| Current | Proposed |
|---|---|
| Phase 2.7 Intelligence Engine | *(removed)* |
| Discover peer-reviewed papers with multi-channel hybrid intelligence. Combines dense 384-dimensional semantic embeddings with PostgreSQL full-text cover density… | Search papers — Find papers by topic, method or author. Results combine meaning and keyword matching. |
| Literature Search / Similar Research / Opportunity Matcher / Browse All Calls / Research Postings / Opportunity Workspace | Search papers / Similar papers / Find venues / Calls for papers / Research postings / Workspace |
| Recommended opportunities (on /browse) | Calls for papers |
| Why this rank? / Why similar? / Why matched? | Why this result? / Why similar? / Why this venue? |
| MATCH 56% | Good match · 56% |
| Deadline: 10/10/2026 (3.7978d remaining) | Due 10 Oct · 3 days left |
| Risk: INSUFFICIENT_EVIDENCE | Not assessed |
| Limited Metadata Available (Neutral Assessment) — Insufficient evidence to establish… | *(badge "Not assessed"; explanation on demand)* |
| OFFLINE / ONLINE | In person / Online |
| UNDER_REVIEW | Under review |
| Offer extended / Not selected / Shortlisted | Shortlist → Make offer; Not selected (confirmed) |
| Notification Center · Phase 4.5 Deadline Reminders… | Notifications |
| The canonical Submission for '…' is scheduled for 2026-10-09 11:59 UTC (UTC). This is your 3 days reminder. | "…" is due in 3 days (9 Oct, 11:59 UTC). |
| IN_APP · DELIVERED · SUBMISSION | *(removed from the user list; delivery state in Settings)* |
| Research Calendar & Deadline Planning | Calendar |
| Researcher Interest & Expertise Intelligence | Profile |
| Researcher Preferences Foundation | Research preferences |
| Unified Evidence-Backed Recommendations | Recommendations |
| Notification & Reminder Preferences | Notification settings |
| Page Not Found / Return to Literature Search | Page not found / Go to search |
| Back to Workspace Opportunities / Back to Opportunity Workspace | Back to workspace |

Notification text changes that live in backend templates are **not** changed in this
redesign (no backend changes); the frontend formats what it can (dates, enum labels) and the
template wording is listed as a follow-up (Q4).

---

## 22. Implementation roadmap

Each phase is independently mergeable and revertable (one branch, small commits, all tests
green at the end of each phase). Order matters: P0 → P1 → P2 unlock everything else; P3–P10
can be reordered by priority; P11–P12 close out.

### P0 — Stabilise (optional, before the redesign; ~1 day)

- **Objective**: fix the four audit bugs that hurt users today, independent of the redesign.
- **Files**: `styles/globals.css` (`.discovery-nav-tab { position: relative; }` — P0-1),
  `app/notifications/page.tsx` and `app/settings/notifications/page.tsx` (remove the second
  `DiscoveryNavbar` — P1-4), `tailwind.config.ts` (`darkMode: "selector"` so `dark:` classes
  stop following the OS) and the two `prefers-color-scheme: dark` blocks in `peers.css` /
  `postings.css` (P1-6), `components/AppHeader.tsx` (remove the phase pill — P1-1).
- **Dependencies**: none. **Risk**: low.
- **Tests**: a Vitest test that the unread badge's hidden text sits inside a positioned
  ancestor (render + class check) and an e2e assertion `scrollWidth === clientWidth` on a
  signed-in page; navbar rendered once on notification pages; next-config test unchanged.
- **Visual QA**: re-run `audit/tools/capture.mjs` — overflow column must be 0 everywhere.
- **A11y QA**: axe `landmark-no-duplicate-main` disappears.
- **Rollback**: revert the commit.

### P1 — Design foundations

- **Objective**: tokens, fonts, base styles, primitives, and the guards that keep them honest.
- **Files**: `styles/tokens.css` (from `tokens.draft.css`), `styles/base.css` (box-sizing,
  body type, links, `:focus-visible`, reduced motion, `color-scheme`), `app/fonts/*.woff2`
  + `OFL.txt`, `app/layout.tsx` (next/font/local variables, `data-theme="light"`),
  `tailwind.config.ts` (theme colours/spacing/radii mapped to `--rc-*`; legacy palette kept
  until migrated), `components/ui/*` (Button, IconButton, Link, Input, SearchInput, Textarea,
  Select, Checkbox, Radio, Switch, Tabs, Badge, Chip, StatusBadge, Tooltip, Popover/Menu,
  Dialog, Drawer, Toast, Alert, Card, Table, DataList, Skeleton, EmptyState, ErrorState,
  PageHeader, SectionHeader, Breadcrumb, StatCard, Avatar, Progress, ScoreMeter, Pagination,
  VisuallyHidden, SkipLink), `lib/status.ts` (enum → label/tone/icon maps), `lib/format.ts`
  (dates, countdowns, numbers), optional dev-only `app/(dev)/ui-kit/page.tsx` that returns
  404 in production (visual QA without Storybook).
- **Dependencies**: Q2 (font sourcing). **Risks**: base styles altering legacy pages (mitigate:
  base.css only sets inherited defaults and is loaded *before* legacy CSS; capture diff on all
  routes); font payload.
- **Tests**: Vitest per primitive (roles, names, keyboard for Tabs/Menu/Dialog/Drawer, focus
  return, disabled/loading semantics); `tests/design-tokens.test.ts` (no colour literals in
  `ui/`, ratchet counts for legacy files, no arbitrary Tailwind values in new code);
  `lib/format` and `lib/status` unit tests (e.g. 3.7978 days → "3 days left").
- **Visual QA**: ui-kit page at 1440/390, light and dark tokens; all existing routes captured
  and compared (must be visually unchanged except fonts).
- **A11y QA**: axe on the ui-kit page = 0 violations; contrast script = 0 failures.
- **Rollback**: additive; revert removes new files and the font variables.

### P2 — Application shell

- **Objective**: sidebar/header/mobile navigation per role; skip link; notification bell;
  account menu; global search.
- **Files**: `components/shell/{AppShell,Sidebar,Header,MobileNav,NavDrawer,NotificationBell,AccountMenu,GlobalSearch}.tsx`,
  `lib/navigation.ts` (single nav config with roles), `app/layout.tsx`,
  `hooks/useUnreadNotificationCount.ts` → context provider (one poll), delete
  `AppHeader`/`DiscoveryNavbar` after migration.
- **Dependencies**: P1. **Risks**: e2e link names change (`/^Opportunity Workspace/`, …);
  layout shift of every page.
- **Tests**: nav config per role (student/faculty/admin items, hidden items); `aria-current`;
  skip link focus; bell count + popover; existing `notification-live-updates` adapted to the
  provider; e2e `auth.spec`, `pages.spec`, `workflow.spec` link names updated in the same
  commit (§23).
- **Visual QA**: all routes at six widths; overflow = 0.
- **A11y QA**: landmarks unique, one nav per mode, keyboard through drawer and popover.
- **Rollback**: revert; old shell components stay in git history.

### P3 — Authentication and public experience

- **Objective**: sign in, register, change password, signed-out landing, not-found,
  loading and guard states.
- **Files**: `app/login`, `app/register`, `app/settings/page.tsx` (new, Account section with
  the existing change-password form moved from notification settings), `app/not-found.tsx`,
  `app/loading.tsx`, `components/auth/RequireAuth.tsx` (ErrorState), `app/page.tsx` signed-out
  intro (one line + search).
- **Dependencies**: P1, P2. **Risks**: e2e selectors `#register-*`, `.auth-error` — keep ids,
  keep `.auth-error` class or update spec deliberately.
- **Tests**: existing auth tests unchanged in intent; change-password test follows the form.
- **QA**: forms at 360; error and loading states; password manager autofill attributes kept.
- **Rollback**: revert.

### P4 — Dashboard

- **Objective**: `/dashboard` for student and faculty; post-sign-in default destination.
- **Files**: `app/dashboard/page.tsx`, `components/dashboard/*` (modules), `hooks/useApiResource.ts`,
  `components/auth/authMessages.ts` (`DEFAULT_REDIRECT` → `/dashboard`, Q9).
- **Dependencies**: P1, P2. **Risks**: request fan-out (budget ≤ 7), empty accounts.
- **Tests**: each module's loading/empty/error; budget test (mocked fetch counts requests);
  `auth-messages` test updated for the new default.
- **QA**: demo and audit accounts; empty new account; 360–1440.
- **Rollback**: revert; `/` remains reachable.

### P5 — Search and discovery

- **Objective**: search, Evidence panel, Paper panel, similar papers, venue matching, calls
  browse, call detail.
- **Files**: `components/pages/DiscoverySearch.tsx`, `components/research/{PaperCard,EvidencePanel,PaperPanel,OpportunityCard,RiskBadge,DeadlineBadge,MatchScore,CitationMetadata,AuthorList,VenueBadge}.tsx`,
  `components/discovery/*` (replaced), `app/browse/page.tsx`, `components/OpportunityList.tsx`,
  `app/calls/[id]/page.tsx` (new), `components/pages/{SimilarResearch,OpportunityMatches}.tsx`.
- **Dependencies**: P1, P2. **Risks**: e2e names "Why this rank?", "Why similar?", "Why
  matched?", "Find Similar Research", "Match Calls for This Paper", `.opportunity-card`;
  URL state regressions.
- **Tests**: URL ↔ state round trip; Evidence panel semantics (dialog name, focus); risk
  mapping (`INSUFFICIENT_EVIDENCE` → "Not assessed"); deadline formatting; browse filters
  call the API with the right params; e2e names updated in the same commit.
- **QA**: long titles, missing abstracts, no DOI, expired calls, zero results.
- **Rollback**: revert per sub-feature commit.

### P6 — Personalization and profile

- **Objective**: `/recommendations`, transparency panel, one explanation UI, restructured
  `/researcher`, supervisors, peers, postings (student side).
- **Files**: `app/recommendations/page.tsx`, `app/researcher/page.tsx`,
  `components/researcher/*` and `components/personalization/*` (restyled from inline/Tailwind
  to primitives; diagnostics behind dynamic imports), `app/supervisors`, `app/peers`,
  `components/{supervisors,peers}/*`, `app/postings/page.tsx` (student view).
- **Dependencies**: P1, P2, P5 (Evidence panel). **Risks**: largest code surface (≈ 12,000
  lines across the profile, preferences, personalization and researcher components); heading
  names asserted by e2e ("Unified Evidence-Backed Recommendations",
  "Researcher Interest & Expertise Intelligence").
- **Tests**: existing unified-intelligence adapter tests unchanged; new tests for
  transparency controls and feedback; e2e headings updated deliberately.
- **QA**: profile height ≤ 3 screens at 1440; requests ≤ 6 on `/researcher`.
- **Rollback**: revert; diagnostics components unchanged in behaviour.

### P7 — Research workflow

- **Objective**: workspace (list + status menu), workspace item tabs, submission, submissions,
  reading list, calendar.
- **Files**: `app/workspace/**`, `app/submissions`, `app/reading-list`, `app/calendar`,
  `styles/{workspace,collaboration,submission,calendar}.css` (deleted as pages move to modules).
- **Dependencies**: P1, P2, P5 (cards). **Risks**: e2e `.workspace-card`, "Save opportunity",
  "Create Task", "Submission Workflow", "New Submission Attempt|Create New Research
  Submission Draft"; unit tests `calendar-events`, `calendar-export`, `reading-list-page`,
  `submissions-page`, `workspace-collaborate-link`, `.calendar-stat-value`.
- **Tests**: status menu offers only valid transitions; optimistic update + rollback; mobile
  agenda default; export flows unchanged (Fix 1/9 test stays).
- **QA**: 360px workspace and calendar without overflow.
- **Rollback**: revert per page.

### P8 — Notifications and settings

- **Objective**: grouped notification list, bell popover, `/settings` (Account, Notifications,
  Appearance).
- **Files**: `app/notifications`, `app/settings/**`, `styles/notifications.css` (deleted).
- **Dependencies**: P2. **Risks**: e2e heading "Notification Center"; tests
  `notification-types`, `notification-settings-push`, `notification-settings-posting-match`,
  `notification-live-updates`.
- **Tests**: grouping by source; enum labels; switches labelled; push option still absent.
- **Rollback**: revert.

### P9 — Faculty

- **Objective**: recruiting dashboard, My postings table, posting editor, applicant inbox,
  applicant review.
- **Files**: `app/postings/**`, `app/postings/applicants/page.tsx` (new),
  `components/postings/*`.
- **Dependencies**: P1, P2, P4. **Risks**: e2e "Apply now", "Submit application", `#cover-note`,
  posting link names; `posting-fit` test.
- **Tests**: decision order; confirmation on "Not selected" and "Cancel posting"; inbox
  aggregation and its request cap.
- **Rollback**: revert.

### P10 — Admin

- **Objective**: overview, research data monitor, users page.
- **Files**: `app/admin/**`, `components/admin/*` (DataFreshnessCard → ResearchDataMonitor).
- **Dependencies**: P1, P2. **Risks**: `data-freshness-card` tests (keep `formatRelative`,
  pass/lane parsing).
- **Tests**: health states (healthy/stale/failing), role change confirmation, pagination.
- **Rollback**: revert.

### P11 — Accessibility, responsive refinement, dark theme

- **Objective**: zero serious/critical axe violations; 320px reflow; dark theme (Q6).
- **Files**: `e2e/` axe suite (axe-core injected like the audit tool), theme switch in
  Settings → Appearance (System/Light/Dark, `data-theme` on `<html>`, stored per browser).
- **Tests**: axe on all main routes × light/dark × 1440/390; overflow check; reduced motion.
- **QA**: manual NVDA/VoiceOver workflows.
- **Rollback**: theme switch can be hidden (light only) without reverting components.

### P12 — Performance and visual regression

- **Objective**: meet budgets; lock the new look with screenshot tests; remove legacy CSS.
- **Files**: `frontend/e2e/visual.spec.ts`, snapshot directory, deletion of unused
  stylesheets and Tailwind legacy palette, `audit/` re-run for an after report.
- **Tests**: `toHaveScreenshot` on 15 routes × 3 widths (§24); bundle budget check script on
  `next build` output.
- **Rollback**: snapshots can be re-baselined; budget failures block merge.

## 23. Test preservation

**Semantic selectors the tests depend on** (from `frontend/e2e/*.ts` and `frontend/tests`):

| Selector | Used in | Plan |
|---|---|---|
| `getByRole("button", { name: /sign out/i })`, `/sign in/i`, links `/sign in/i`, `/create account/i` | e2e auth, pages | Keep names |
| `getByLabel(/email/i)`, `/password/i`; `#register-name/-email/-password/-confirm/-role` | e2e auth | Keep labels and ids |
| `getByRole("searchbox", { name: "Search research literature" })` | e2e workflow/pages | Keep accessible name in P5 (visible label may read "Search papers"; `aria-label` stays) or update spec deliberately |
| Links `/^Opportunity Workspace/`, `/^Researcher Profile/`, `/^Research Postings/`, `/^Notifications/`, `/^Browse All Calls/`, `/Submission Workflow/`, `/Collaborate/` | e2e | **Updated in P2/P7** with the new labels (one commit per rename) |
| Headings "Opportunity Workspace", "Notification Center", "Recommended opportunities", "Unified Evidence-Backed Recommendations", page list in `pages.spec.ts` | e2e | **Updated in the phase that renames them**; the assertion (heading visible) is kept, only the text changes |
| Buttons "Why this rank?", "Why similar?", "Why matched?", "Find Similar Research", "Match Calls for This Paper", "Save opportunity", "Create Task", "Apply now", "Submit application", "How this was scored", `/^Tasks/` | e2e | Keep or update deliberately in P5/P7/P9 |
| `.opportunity-card`, `.workspace-card`, `.auth-error`, `#cover-note`, `.calendar-stat-value` | e2e / unit | Keep these class names on the new components as stable hooks, or replace with role queries in the same commit |
| `ByTestId(...)` (6 ids) | unit (session probes only) | Unaffected |
| `DEFAULT_REDIRECT` | `auth-messages.test.ts` | Updated in P4 if Q9 approved |

Rules: never delete an assertion to make a phase pass; a renamed string is updated in the
test in the same commit, and the commit message lists every changed test; new code uses role
and label queries (data-testid only where no semantic query works).

## 24. Visual regression

- **Baseline now**: the 106 audit screenshots are the "before" record for review (not an
  automated baseline — data and dates change).
- **Automated (P12)**: `frontend/e2e/visual.spec.ts` in the e2e stack (deterministic demo seed),
  Playwright `toHaveScreenshot` with `page.clock.setFixedTime(...)` so countdowns are stable,
  masks for relative timestamps and counts, `maxDiffPixelRatio: 0.01`, Chromium only, 15 routes
  × 1440/768/390, light (and dark after P11). Run by `python e2e/run_e2e.py --suites visual`
  (new suite option), not in GitHub CI (needs the stack).
- **Process**: each phase PR attaches before/after captures from `audit/tools/capture.mjs`;
  a visual change is accepted only with a reason; "tests pass" is not sufficient.

## 25. Engineering decisions

| Topic | Decision | Reason |
|---|---|---|
| Styling for new code | CSS Modules + `--rc-*` tokens | Native to Next.js, no dependency, scoped (fixes V9), works with legacy global CSS during migration |
| Tailwind | Kept for legacy panels during migration, theme mapped to tokens, `darkMode: "selector"`; removed from a component when it is migrated | Avoids a big-bang rewrite of 13 components |
| Overlays | Native `<dialog>` (`showModal`) and the Popover API | Focus containment, Esc, top layer, inert background for free; supported in all current browsers |
| Data fetching | `useApiResource` hook (abort, dedupe, revalidate on focus) | Removes duplicate requests without adding SWR/React Query |
| Formatting | `lib/format.ts` (Intl.DateTimeFormat, Intl.RelativeTimeFormat, Intl.NumberFormat) | Kills raw floats and mixed date formats |
| Enum labels | `lib/status.ts` maps | No raw enums in UI |
| Token enforcement | Vitest scans (no stylelint) | Zero new dependencies; fails CI |
| Icons | lucide-react (existing) | Tree-shaken; one icon family |
| Fonts | next/font/local, WOFF2 committed | No CDN, no build-time network, CSP unchanged |

## 26. Dependencies

**No new runtime dependencies are proposed.**

| Candidate | Decision | Reason |
|---|---|---|
| Radix UI / Headless UI | Rejected | Native `<dialog>`, Popover API and small hooks cover dialogs, menus, tabs and tooltips; +20–40 kB |
| React Query / SWR | Rejected | A 60-line hook covers the needs (abort, dedupe, revalidate) |
| Chart library | Rejected | Meters, dot timelines and run strips are simple SVG/CSS |
| `@fontsource/*` packages | Rejected | Font files committed with `next/font/local` give the same result without a dependency |
| `axe-core` (dev only) | **Optional**: pin it explicitly as a devDependency | Already installed transitively (eslint-plugin-jsx-a11y → axe-core 4.13); pinning protects the P11 axe suite from transitive version changes. No runtime or bundle impact, CSP irrelevant (test-only), improves accessibility testing. |

## 27. Adversarial reviews

### Review 1 — Product designer

| Question | Finding | Resolution in this plan |
|---|---|---|
| Does every page have a clear purpose? | `/similar` and `/opportunities` have none without context | Removed from nav; reached from the paper panel with breadcrumb (§10) |
| Is hierarchy obvious? | First drafts kept stat cards on workspace and calendar | Replaced by filter chips with counts; StatCard allowed only when actionable (§8, DS §8.4) |
| Is the UI useful? | Dashboard draft mirrored the notification list | Changed to "Needs attention" synthesised from deadlines and applications (§8) |
| Anything decorative? | Serif everywhere was considered | Serif limited to page and object titles; everything else sans (DS §4) |
| Cohesive? | Three explanation UIs would survive a restyle | Merged into one Evidence panel (§12) |
| Low scores read as failure? | Raw percentages kept prominent | Bands first, number second, thresholds an open question (Q3) |

### Review 2 — Accessibility specialist

| Question | Finding | Resolution |
|---|---|---|
| Keyboard completion? | Kanban drag-and-drop was an option | Rejected; status menu instead (§13) |
| Contrast? | First palette failed input borders (2.09:1) and dark brand fill (3.91:1) | Tuned to 3.72 / 3.59 and 5.14; all pairs pass (DS §3.4) |
| Dialogs/drawers? | Custom overlays repeat today's bugs | Native `<dialog>` primitives with focus tests (P1) |
| Meaningful names? | Repeated "Why this rank?" links | Accessible names include the item ("Why this result? Parameterized Explainer…") via `aria-describedby` (DS §9) |
| Colour only? | Deadline vs risk distinguished by colour in early sketches | Icon + word + position + colour (DS §3.2) |
| Mobile nav landmarks? | Bottom bar + drawer could create two navs | Only one navigation is rendered per breakpoint; drawer is a dialog containing the same nav |
| Tooltips? | Subscore explanations in tooltips | Moved to disclosures; tooltips only name icons (DS §8.3) |

### Review 3 — Senior frontend engineer

| Question | Finding | Resolution |
|---|---|---|
| Maintainable? | Two styling systems in new code would recreate the problem | New code: CSS Modules only; Tailwind only in unmigrated components (§25) |
| Tokens enforceable? | Docs alone will not stop hex literals | Vitest guards + ratchet (DS §12) |
| Duplication? | PaperCard vs SimilarResearchCard vs reading-list item | One PaperCard with variants (DS §9) |
| Scales? | Dashboard request fan-out | Budget ≤ 7, parallel, module isolation, shared hook (§8, §18) |
| Bundle? | Fonts and primitives | Fonts ≤ 100 kB with one preload; primitives ≤ 7 kB; `/researcher` diagnostics lazy (§18) |
| Tests resilient? | Renames break e2e | Explicit selector inventory and same-commit updates (§23) |
| Build determinism? | `next/font/google` downloads at build time | `next/font/local` (§25, Q2) |
| Dark mode cost? | Doubling QA from P1 | Tokens now; dark ships in P11; until then light is forced and stray dark rules removed (P0) |

Contradictions found and fixed while writing: (1) "no new dependencies" vs a chart library — removed; (2) "deadline never red" vs the old urgency palette — orange family only; (3) "one primary per section" vs a primary Save on every PaperCard — Save is secondary in lists, primary only in the paper panel; (4) "no route changes" vs a paper page — paper panel now, `/papers/[id]` only if Q4 is approved.

## 28. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Scope: ≈ 34,000 lines touched (10,699 route TSX, 15,604 component TSX, 7,490 CSS) | High | High | Phases P0–P12, each shippable; P6 split per panel |
| e2e churn from renamed strings | High | Medium | §23 inventory; same-commit updates; no deleted assertions |
| Legacy CSS interacting with base styles | Medium | Medium | base.css minimal; capture diff of every route after P1 |
| Backend gaps (paper by id, applicant aggregate, deadline projection, notification template wording) | Certain | Medium | Designed around them; listed as optional follow-ups (Q4) |
| Font licensing/size | Low | Low | OFL fonts, subset, budget |
| Dark theme quality | Medium | Medium | Deferred to P11 behind a switch |
| Score bands misrepresent scores | Medium | Medium | Validate thresholds on real distributions (Q3); exact value always available |
| Terminology change confuses existing users/examiners | Low | Low | Glossary in README; consistent labels |

## 29. Open questions

1. **Q1** Approve Direction A ("Scholarly Ledger")?
2. **Q2** Fonts: commit WOFF2 files and use `next/font/local` (recommended), or use
   `next/font/google` (self-hosted at runtime, downloads at build time)?
3. **Q3** Show match/fit as bands with the number secondary? Approve thresholds 70/45/25
   after checking real score distributions?
4. **Q4** Are small, read-only backend additions acceptable later (each separately approved):
   `GET /discovery/research/{id}` (shareable paper page, single-paper BibTeX), an applicant
   aggregate for faculty, automatic calendar projection of workspace deadlines, plainer
   notification templates?
5. **Q5** Should admins see personal research tools (workspace, reading list, calendar)?
6. **Q6** Ship the dark theme in P11, or stay light-only?
7. **Q7** Confirm terminology: "Call" for ingested calls for papers, "Posting" for faculty
   openings; show subfield names instead of ids (needs a name lookup).
8. **Q8** Ship P0 (four bug fixes) now as a separate small change?
9. **Q9** Send people to `/dashboard` after sign-in (instead of search)?
10. **Q10** Hide expired calls by default on Browse and venue matching (a UI default;
    ranking unchanged)?
11. **Q11** Keep the 10.8 MB of audit screenshots in git, move them to Git LFS, or keep them
    out of the repository?
12. **Q12** Can faculty apply to postings (e.g. collaborations)? This decides whether faculty
    see "Applications".

## 30. Final recommendation

Approve **Direction A** and start with **P0** (four contained bug fixes, about a day, high
user value) followed by **P1 → P2** (foundations and shell), which remove the largest
problems — sideways scrolling, hidden navigation, inconsistent primitives, no font — and make
every later phase cheaper. Then **P4 (dashboard) and P5 (search)**, which carry the product's
value. P6–P10 can follow in the order the examiners' demo needs; P11–P12 close with
accessibility, dark theme, budgets and visual regression.

The test for each phase is the one in the brief: *could a professional product team ship
this?* Each phase has measurable gates (axe 0 serious/critical, overflow 0, budgets, visual
diff reviewed) so the answer is checked, not assumed.
