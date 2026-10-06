# Route and component inventory

Audited on 2026-10-06 at commit `bd34264` (main), production build (`next build`, served by
the Compose `frontend` container on localhost:3000 against the local backend and the real
55,799-paper corpus). Screenshots: `screenshots/<role>/<state>__<width>.jpg`.

**23 routes** under `frontend/app` (20 static, 3 dynamic) plus `loading.tsx` and
`not-found.tsx`; **48 component files** under `frontend/components` (+ 2 hooks, 1 API
module of 3,364 lines with 170 exported functions, 16 type modules).

## 1. Architecture as found

| Concern | Implementation | Notes |
|---|---|---|
| Framework | Next.js 15.5 App Router, React 19, TypeScript | Every page is a Client Component; data fetched in `useEffect` |
| Shell | `app/layout.tsx`: `SessionProvider` → `AppHeader` → `DiscoveryNavbar` → `<main>` | No sidebar; one horizontal tab strip for all destinations |
| Auth | `SessionProvider` (context, verifies stored token via `/auth/me`), `RequireAuth` guard (UX only), `AuthMenu` | Token in `localStorage` (documented limitation) |
| Roles | `useSession().hasRole()`; nav hides tabs; `RequireAuth roles=[…]` shows a denial message | Only `/admin` (ADMIN) and `/supervisors` (STUDENT) are role-restricted |
| API | `services/api.ts`: `fetchJson` + 170 functions over ~130 endpoints; `ApiError`; 401 → `notifyUnauthorized` | No caching or request de-duplication |
| Styling | 11 global stylesheets (7,490 lines), Tailwind utilities (preflight **off**), inline `style={{}}` objects | Three eras, see design-language audit |
| Fonts | `--font-family: Inter, …` declared, **no font loaded** | Renders in the OS font |
| Theme | Light only, but 2 stylesheets and Tailwind `dark:` classes react to OS dark mode | Pages go half-dark |
| State hooks | `useSelectedWork` (sessionStorage), `useUnreadNotificationCount` (30 s poll) | Selected paper is not in the URL |
| Tests | 26 Vitest files (241 tests), 3 Playwright specs, 7 stack + 69 API e2e tests | Selectors listed in the redesign plan §23 |

## 2. Route matrix

Legend — Access: P public, A any signed-in account, S student, F faculty, Ad admin.
API = endpoints called on load (from the capture: count of requests at 1440px).

### Discover

**`/` — Literature search** (`components/pages/DiscoverySearch.tsx`)
- Access P. Goal: find papers on a topic. Primary CTA: Search. Secondary: suggestion chips,
  filters ("Filters & Ranking Mode"), per result: Why this rank?, Find similar research, Match
  calls & venues, Save to reading list, pagination.
- Data: rank, match %, title, year, type, citations, OA, DOI, abstract, semantic/lexical
  subscores. API: `GET /discovery/research/search`, `GET /reading-list/lookup` (saved state).
- Layout: page intro (eyebrow + **h2**, no h1), search bar, collapsed filter panel, card list,
  pagination, ExplainabilityDrawer. Components: SearchBar, SearchFilters, ResearchResultCard,
  PaginationControls, ExplainabilityDrawer, SaveToReadingListButton.
- States: prompt state before search; spinner while loading; error with Retry; empty
  message. No skeleton. Query and filters are **not in the URL** (no back button, no sharing).
- Responsive: single column; nav shows 2 of 5–13 tabs at 390px; double clear (×) icon in the
  search field. A11y: no h1; drawer unnamed; DOI links fail contrast.
- Inconsistencies: implementation jargon in the intro ("384-dimensional semantic
  embeddings", "taxonomy DAG"); green "MATCH" badge here vs pink on venue matching.

**`/similar` — Similar research** (`components/pages/SimilarResearch.tsx`)
- Access P. Goal: papers similar to a selected paper. Requires a paper selected on `/`
  (sessionStorage); direct visits show "No Research Paper Selected".
- API: `GET /discovery/research/{id}/similar`. Components: SimilarResearchCard,
  ExplainabilityDrawer. States: no-selection, loading spinner, error/retry, empty.
- Issue: listed as a top-level tab although it is a contextual action → dead end for anyone
  who clicks the tab first.

**`/opportunities` — Opportunity matcher (venue matching)** (`components/pages/OpportunityMatches.tsx`)
- Access P. Goal: calls/venues for a selected paper. Filters: category, attendance, max APC,
  location, "Require stated fee", "Upcoming only" (off by default → expired calls rank first).
- API: `GET /discovery/research/{id}/opportunities`. Components: OpportunityCard, QualityBadge,
  RiskWarning, DeadlineBadge, DeadlineTimeline, ExplainabilityDrawer.
- Issues: full abstract box (≈ 10 lines) above results; "Limited Metadata Available (Neutral
  Assessment)" panel above every title; Type Fit/Topic Overlap/Urgency Fit subscores; "OFFLINE"
  for in-person; misaligned card variant; same no-selection dead end as `/similar`.

**`/browse` — Browse all calls** (`components/OpportunityList.tsx`)
- Access P. Goal: browse calls for papers. Heading says **"Recommended opportunities"** (not
  personalised); tab and `<title>` say "Browse All Calls".
- API: `GET /api/opportunities`. No search, filter, sort, pagination or save action in the UI,
  although the API supports search, type, mode, upcoming and sort. 63 cards in one column.
- A11y: no h1 (heading is h2).

**`/postings` — Research postings** (`app/postings/page.tsx`, 698 lines)
- Access P (browse) / A (tabs). Tabs: Discover, My postings (faculty), My applications. Faculty
  get "New posting" (inline form). Filters: search, category, work mode, accepting applications.
- Data: title, author, institution, location/mode, positions, deadline, days left, fit line
  (students), summary, skills. API: `GET /postings`, `/postings/fit-scores`,
  `/postings/mine`, `/postings/mine/summary`.
- States: loading spinner, empty variants (7), errors. Best-structured list in the app.
- Issues: "My applications" tab renders as an underlined link next to plain tabs; blue "New
  posting" button (not the brand colour); low fit shown first ("10% fit · Low").

**`/postings/[id]` — Posting detail** (dynamic)
- Access P. Student: Your fit, About, What is expected, Appointment terms, Apply form, Details.
  Faculty (author): Manage this posting (status transitions), Applications list with decisions.
- API: `GET /postings/{id}`, `/postings/{id}/fit`, `/postings/{id}/applications`, `POST …/applications`.
- Issues: deadline and work mode at the very bottom; "To strengthen your application" (h3)
  renders larger than "Your fit" (h2); raw status `UNDER_REVIEW`; decision buttons ordered
  "Offer extended" (blue primary) → "Not selected" → "Shortlisted"; status transitions "Mark
  Cancelled / Closed / Draft / Filled" all equal weight, destructive first.

### For you

**`/supervisors` — Find a supervisor** (`app/supervisors/page.tsx`)
- Access S (others see the denial message; tab hidden). Goal: faculty who fit the student.
- Filters: exclude own institution, only faculty with openings. Data: tier ("EXPLORATORY"),
  fit %, reasons (4 bullets), shared topics, open postings, "How this was scored".
- API: `GET /researchers/{id}/supervisor-matches`. Issue: the same caveat bullet repeats on
  every card; default blue underlined links.

**`/peers` — Peer & co-author discovery** (`app/peers/page.tsx`)
- Access A. Your discoverability settings form + matches. API: `GET/PATCH
  /researchers/{id}/discovery-settings`, `GET /researchers/{id}/peers`.
- Issue: says "your profile has fewer than 2 [topics]" while the same student has 3 declared
  topic interests — peers use *expertise* topics, preferences use *declared* topics, and the UI
  never explains the difference.

**`/researcher` — Researcher profile** (`app/researcher/page.tsx` + 9 large components)
- Access A. Contains: phase banner, completeness, profile header and edit, authored works,
  research intelligence, preferences summary, unified intelligence (Phase 4.7), signal
  provenance, adaptive signals, personalization settings/quality/calibration/governance,
  personalized candidates, ranking preview, recommendation history, feedback history.
- API: **25 requests on load**. Height: **25,378px** at 1440 (≈ 28 screens), 49,685px at 390.
- Issues: internal phase labels ("Phase 3.1: Researcher Profile Foundation … until Phase
  3.4+"); raw enums (`EXPLICIT_PREFERENCE`, `USER_DECLARED`, `UNKNOWN`); 215 contrast failures;
  unlabelled selects and buttons; one panel turns dark in OS dark mode.

**`/researcher/preferences` — Preference center** (1,380 lines)
- Access A. Structured preferences: opportunity types, delivery mode, topics, locations,
  deadline window, open access, academic level, career stage, funding, institutions,
  keywords, regions. API: `GET/POST/PATCH/DELETE /researchers/{id}/preferences…`.
- Issues: no h1; 5 unlabelled selects; heading "Researcher Preferences Foundation".

### My research

**`/workspace` — Opportunity workspace** (734 lines)
- Access A. Saved calls through a pipeline (Saved → Considering → Planning → Applied →
  Accepted/Rejected → Archived). Stat cards (5), status tabs with counts, search, priority and
  tag filters, cards with notes, tags, "Move to" transitions, priority select, Submissions,
  Collaborate, Archive, Delete.
- API: `GET /workspace`, `/workspace/summary`, `PATCH /workspace/{id}`, transitions.
- Issues: ≈ 9 actions per card, Archive offered twice, raw float countdown "3.7978d
  remaining", red `Risk: INSUFFICIENT_EVIDENCE` on every card, priority MEDIUM coloured green,
  5 unlabelled selects; at 390px the "Move to" row is cut off.

**`/workspace/[id]` — Workspace item (collaboration)** (984 lines)
- Access A (member). Tabs: Overview, Tasks, Members, Invitations, Activity & Notes; modals
  to invite and create tasks. API: 7 requests (items, members, tasks, invitations, activity).
- Issues: no h1; blue "Submission Workflow" button with underlined text; "Back to Workspace
  Opportunities" vs "Back to Opportunity Workspace" on the sibling page; undefined tokens
  (`--color-primary`, `--bg-hover`) used without fallback in `collaboration.css`.

**`/workspace/[id]/submission` — Submission workflow** (1,881 lines)
- Access A. Create draft, lifecycle transitions, documents with versions, readiness checks,
  history. API: submissions, documents, versions, readiness, history.
- Issues: no h1; unlabelled select; 26 uses of undefined tokens in `submission.css`.

**`/submissions` — Submissions** (205 lines)
- Access A. List of submissions with status filter and summary; empty state "No submissions
  yet". Uses `workspace.css`.

**`/reading-list` — Reading list** (378 lines)
- Access A. Status tabs (All/To read/Reading/Done with counts), selectable items, export
  selected/all as BibTeX, per item: status select, notes textarea (saved on blur), remove.
- Issues: no h1 in source (visual heading is not h1); centred titles; ≈ 330px per paper
  (always-open status select and notes); default blue DOI links; borrows `peers.css` and
  `postings.css`.

**`/calendar` — Research calendar & deadline planning** (887 lines)
- Access A. Month grid / agenda, category chips, add milestone modal, export .ics (Fix 1/9).
- Issues: blue primary palette unique to this page; "Upcoming deadlines 0" although four
  saved calls are due within 4 days (workspace deadlines are not projected automatically);
  event text ≈ 1.8:1 contrast; at 390px header actions and the grid overflow the viewport.

**`/postings/applications` — My applications** (173 lines)
- Access A. Status filter + summary + ApplicationCard list.

### Account

**`/notifications` — Notification center** (506 lines)
- Access A. Stat cards, All/Unread tabs, type filter, list with mark-read and open-source
  actions, Preferences link, Mark all read. Only page with a skeleton.
- Issues: **renders `DiscoveryNavbar` a second time** (two nav bars, two `main` landmarks,
  unread count polled twice); subtitle "Phase 4.5 Deadline Reminders, Scheduled Alerts &
  In-App Intelligence"; raw chips `IN_APP`, `DELIVERED`, `SUBMISSION`; message text "11:59 UTC
  (UTC)"; three reminders for the same call stack up uncollapsed.

**`/settings/notifications` — Notification & reminder preferences** (593 lines)
- Access A. Delivery channels (In-app, Email), alert categories (switches), reminder rules
  (offset + channel), Change password (Fix 5/9).
- Issues: also renders `DiscoveryNavbar` twice; 6 switches without labels; 2 unlabelled selects;
  password change lives under "notifications".

### Administration

**`/admin` — Platform administration** (215 lines + DataFreshnessCard)
- Access Ad (others see the denial message). Data freshness card (refresh on/off, last run,
  status, papers added in 24 h, next run, last 5 passes), then the user table (68 accounts,
  search, role filter, inline role select, active/verified toggles).
- Issues: the freshness card renders **above** the page h1; freshness is a key/value table,
  not a monitor (no health state, no failure emphasis); subfield shown as `1702`; the user
  table has no pagination, inline role changes apply immediately with no confirmation; at
  390px both tables overflow.

### Public and system

**`/login`**, **`/register`** — centred card forms; disabled submit until filled (pale
button reads as broken); register has role select (Student/Faculty). Fine structurally.

**`not-found.tsx`** — "Page Not Found" (h2, Title Case), button "Return to Literature Search".
**`loading.tsx`** — spinner + "Loading...". Route guard states — "Checking your session…",
"Taking you to sign in…", denial card "This page is for Student accounts."

## 3. Component inventory

Styling: **G** global CSS classes, **T** Tailwind utilities, **I** inline style objects.

| Component | Lines | Style | Used by | Notes |
|---|---|---|---|---|
| AppHeader | 31 | G | layout | Shows "Phase 2.7 Intelligence Engine" |
| DiscoveryNavbar | 189 | G | layout, notifications ×2 | 13 tabs; "Active" pill duplicates the underline; no `aria-current`; badge's hidden text overflows the page |
| AuthMenu | 69 | G | AppHeader | Name + role + sign out |
| RequireAuth | 79 | G | 14 pages | Pending, redirect, denied states |
| SessionProvider | 208 | — | 17 | Context |
| OpportunityList | 127 | G | /browse | No filters |
| DataFreshnessCard | 199 | G | /admin | Key/value table |
| DeadlineBadge | 180 | G | 2 | Urgency colours red/orange (collides with risk) |
| DeadlineTimeline | 218 | G | 1 | Stepper |
| ExplainabilityDrawer | 1,197 | G + T + I | 3 | Phase label in header, 4-decimal floats, unnamed dialog, no focus management |
| OpportunityCard | 202 | G | 1 | Risk panel above title |
| PaginationControls | 94 | G | 3 | |
| QualityBadge | 92 | G | 1 | "Verified Venue 65%" |
| ResearchResultCard | 195 | G | 1 | Three equal-weight actions |
| RiskWarning | 119 | G | 1 | Long neutral caveat on every card |
| SearchBar | 118 | G | 1 | Double clear icon |
| SearchFilters | 161 | G | 1 | Collapsed by default |
| SimilarResearchCard | 155 | G | 1 | Near-duplicate of ResearchResultCard |
| DiscoverySearch / SimilarResearch / OpportunityMatches | 270 / 227 / 337 | G | pages | Page components outside `app/` |
| PeerMatchCard | 159 | G | /peers | |
| SupervisorMatchCard | 187 | G | /supervisors | Repeated caveat |
| PostingCard / ApplicationCard / OpeningTermsPanel | 158 / 144 / 80 | G | postings | Closest to the target design |
| SaveToReadingListButton | 71 | G | 1 | |
| AdaptiveSignalsCard | 283 | T | /researcher | `dark:` classes → half-dark page |
| PersonalizationCalibration / Governance / Quality / Settings Card | 330 / 658 / 393 / 477 | T | /researcher | Technical internals on the user surface |
| PersonalizationScoreBadge / PreferenceMatchBadge | 224 / 187 | I | 1 each | 28 / 20 inline style objects |
| WhyThisRecommendationModal | 316 | T | 1 | Second, different "why" pattern |
| OpportunityInteractionBar | 223 | G | 1 | |
| FeedbackHistoryView | 383 | T | /researcher | |
| PersonalizationSummaryView | 620 | I | /researcher | 68 inline styles |
| PersonalizedCandidatePreview / RankingPreview | 539 / 652 | T | /researcher | |
| ProfileCompletenessBadge | 168 | I | /researcher | |
| RecommendationExplanationModal | 562 | I | 2 | Third "why" pattern |
| RecommendationHistoryView | 987 | I | /researcher | 125 inline styles |
| ResearcherIntelligenceView / PreferencesView / ProfileView | 677 / 1,059 / 696 | I | /researcher | 78 / 103 / 65 inline styles |
| UnifiedResearchIntelligenceView | 775 | T | /researcher | Heading "Unified Evidence-Backed Recommendations" (e2e depends on it) |

**Reuse gaps.** No shared Button, Input, Card, Badge, Tabs, Dialog, EmptyState or Skeleton
component exists: each page re-implements them (41 button classes, 49 card classes, 90
badge/pill/chip/tag classes). Three different "explain this score" patterns exist
(ExplainabilityDrawer, WhyThisRecommendationModal, RecommendationExplanationModal).
