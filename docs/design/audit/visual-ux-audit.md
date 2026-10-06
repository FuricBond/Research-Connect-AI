# Visual and UX audit

Method: the production build was used as each role would use it (three audit accounts with
realistic data, see [README](README.md)), at 1440×900, 1280×800, 1024×768, 768×1024,
390×844 and 360×800. Findings are classified **P0** severe usability/design problem, **P1**
important, **P2** polish, **P3** minor. Every finding cites the screenshot or measurement
that shows it.

## P0 — severe

| # | Finding | Evidence | Why it matters |
|---|---|---|---|
| P0-1 | **Every signed-in page scrolls sideways when the user has unread notifications.** The visually-hidden " unread" text inside the Notifications tab is `position: absolute` with no positioned ancestor, so it escapes the nav's own scroll container and lands at x = 2,420px. Pages become 2,420px wide at every viewport (canScrollX = 400px measured at 1440 and 390). Admin pages (0 unread) are unaffected, which is how the cause was isolated. An in-browser experiment adding `position: relative` to `.discovery-nav-tab` restored a 1,440px page. Introduced with the Phase 5.16 live badge. | `screenshots/student/*__390.jpg`, measurements in `data/capture-results.json` (`horizontalOverflowPx` 746–1,920 on every student/faculty page) | Sideways panning on phones; on desktop a horizontal scrollbar on every page. Also broke automated taps at 390px (two capture steps failed). |
| P0-2 | **Most destinations are invisible.** The primary navigation is one horizontal strip of up to 13 tabs; at 1440px only 6 are visible (Literature Search → Opportunity Workspace) and Submissions, Reading List, Calendar, Peers, Supervisor, Profile and Notifications sit off-screen with no "more" affordance. At 390px only 2 tabs show. | `student/search-results__1440.jpg`, `student/workspace__1440.jpg` ("Acti…" pill cut off), `public/search-landing__390.jpg` | Users cannot discover features; the unread badge is usually off-screen. |
| P0-3 | **No home or "what needs my attention" view.** Signing in lands on literature search. Deadlines in the next 4 days, an application under review and 11 unread notifications are spread over four pages. | Audit student data: 4 calls due 8–10 Oct, 1 application under review | The product's core value (deadline and opportunity intelligence) is not surfaced. |
| P0-4 | **The researcher profile is a 25,378px stack of development phases** (49,685px on a phone, 25 API requests), including banners such as "Phase 3.1: Researcher Profile Foundation — … Recommendations remain unpersonalized until Phase 3.4+", raw enums and technical panels (calibration, governance, drift). | `student/researcher-profile__1440.jpg`, `student/researcher-profile-os-dark__1440.jpg` | Users cannot find or edit their profile; examiners see internal scaffolding. |
| P0-5 | **Deadline and risk are visually confused, and missing data looks dangerous.** Workspace cards show "Deadline … (3.7978d remaining)" next to a red "Risk: INSUFFICIENT_EVIDENCE" on every call; urgent deadlines are also red on venue matching. | `student/workspace__1440.jpg`, `student/opportunity-matcher__1440.jpg` | Unknown risk reads as high risk; urgency and trust share one colour. |
| P0-6 | **Mobile layouts break.** Calendar header actions, toolbar and month grid overflow at 390px (Fri/Sat cut off); workspace "Move to" rows are clipped; admin tables overflow; stat cards stack into five full-width blocks before any content. | `student/calendar__390.jpg`, `student/workspace__390.jpg`, `admin/admin-console__390.jpg` | Core tasks are not usable on a phone. |
| P0-7 | **Contextual tools are dead-end tabs.** "Similar Research" and "Opportunity Matcher" are top-level tabs but need a paper selected on the search page (sessionStorage); direct visits show "No Research Paper Selected". | `student/similar-no-selection__1440.jpg`, `public/similar-no-selection__1440.jpg` | Two of the first five tabs lead nowhere for new users. |

## P1 — important

| # | Finding | Evidence |
|---|---|---|
| P1-1 | Internal labels visible to users: header pill "Phase 2.7 Intelligence Engine" on every page; "(PHASE 2.5F)" in the explanation drawer; "Phase 4.5 …" subtitle on notifications; "PHASE 4.7 UNIFIED INTELLIGENCE"; "Phase 3.3 — Canonical preference intelligence". | all screenshots; `search-why-this-drawer__1440.jpg`; `notifications__1440.jpg` |
| P1-2 | Raw system values shown as text: `UNDER_REVIEW`, `INSUFFICIENT_EVIDENCE`, `IN_APP`, `DELIVERED`, `EXPLICIT_PREFERENCE`, `USER_DECLARED`, `UNKNOWN`, `OFFLINE`, `CONFERENCE`, "Data-Paper", "Conference-Paper", "4 exp / 0 inf". | workspace, notifications, posting detail, researcher profile |
| P1-3 | Unformatted numbers: "3.7978d remaining", "+0.5630", "56.3%", "Score: 76% \| W: 50% \| C: +0.3792 (Raw:" (text overlaps in the drawer), "11:59 UTC (UTC)". | `workspace__1440.jpg`, `search-why-this-drawer__1440.jpg`, `notifications__1440.jpg` |
| P1-4 | Notification pages render a second navigation bar (two nav strips, two `main` landmarks, unread count polled twice per 30s). | `student/notifications__1440.jpg`; duplicate `GET /notifications/unread-count` in `data/capture-results.json` |
| P1-5 | Three primary colours: brand teal (search, workspace), bright blue `#3B82F6` (calendar "Add Milestone", notifications "Mark All Read", faculty "New posting", "Offer extended", "Submission Workflow"), pink/magenta match % on venue matching. | `calendar__1440.jpg`, `postings-mine__1440.jpg`, `opportunity-matcher__1440.jpg` |
| P1-6 | Pages go half-dark with the OS in dark mode: Tailwind `dark:` panels and two `prefers-color-scheme: dark` blocks (peers, postings) switch while the rest stays light. | `student/researcher-profile-os-dark__1440.jpg` |
| P1-7 | Workspace cards carry about nine actions (four "Move to" buttons, priority select, Submissions, Collaborate, Archive, Delete); Archive appears twice; notes box shows "No notes added yet." on every card. | `workspace__1440.jpg` |
| P1-8 | Venue matching: a long "Limited Metadata Available (Neutral Assessment)" panel sits above the title of almost every result; expired calls rank first because "Upcoming only" defaults to off; the selected paper's full abstract (~10 lines) pushes results below the fold. | `opportunity-matcher__1440.jpg` |
| P1-9 | Faculty applicant review: the most prominent action is "Offer extended" (blue primary), followed by "Not selected" and "Shortlisted" in no pipeline order; posting status actions "Mark Cancelled / Closed / Draft / Filled" have equal weight with the destructive one first. | `faculty/posting-manage__1440.jpg` |
| P1-10 | Faculty experience is the student UI plus a button: postings opens on "Discover", there is no applicant inbox across postings and no faculty home. | `faculty/postings-mine__1440.jpg` |
| P1-11 | Admin: data-freshness card renders above the page title; it is a key/value table without a health state; subfield shown as `1702`; 68 users in one unpaginated table with role changes applied from an inline select without confirmation. | `admin/admin-console__1440.jpg` |
| P1-12 | Browse page heading "Recommended opportunities" for anonymous visitors (nothing is personalised); no search, filters, sort or save although the API supports them. | `public/browse-calls__1440.jpg` |
| P1-13 | Calendar "Upcoming deadlines: 0" while four saved calls are due within 4 days (workspace deadlines are not projected unless done manually). | `calendar__1440.jpg` vs `workspace__1440.jpg` |
| P1-14 | Two meanings of "topics" collide: peers says the profile has "fewer than 2" topics while the student declared 3 topic interests; profile shows "Research Topics 0" next to "Preferred Topics: 3". | `peers__1440.jpg`, `researcher-profile-os-dark__1440.jpg` |
| P1-15 | Three different "explain this score" patterns (ExplainabilityDrawer, WhyThisRecommendationModal, RecommendationExplanationModal) with different layouts and vocabularies. | component inventory |
| P1-16 | Relevance shown as low raw percentages (35–56% for clearly relevant papers; "10% fit · Low" on postings) — reads as failure. | `search-results__1440.jpg`, `postings__1440.jpg` |

## P2 — polish

| # | Finding | Evidence |
|---|---|---|
| P2-1 | Navigation tabs are underlined like body links, and each active tab also shows an "Active" pill. | all signed-in screenshots |
| P2-2 | Stat cards that repeat counts already visible in tabs (workspace 5, calendar 4, notifications 4, workspace item 3). | workspace, calendar, notifications |
| P2-3 | Mixed heading case: "Notification Center", "Opportunity Workspace", "Page Not Found" vs "Platform administration", "Create an account". | route inventory |
| P2-4 | Reading list: centred titles over left-aligned metadata; each paper ≈ 330px tall because status select and notes are always open; browser-default blue DOI links. | `reading-list__1440.jpg` |
| P2-5 | Search field shows two clear (×) icons (native + custom). | `search-results__1440.jpg` |
| P2-6 | Every result card has a filled primary "Match Calls & Venues" button: 20 primary buttons per page. | `search-results__1440.jpg` |
| P2-7 | Supervisor cards repeat the same system caveat bullet in every card; default blue underlined posting links. | `supervisors__1440.jpg` |
| P2-8 | Posting detail: key facts (deadline, work mode, positions) at the bottom; single 900px column leaves the right third empty at 1440. | `posting-detail__1440.jpg` |
| P2-9 | Disabled submit buttons (search, sign in) look like a broken pale teal. | `public/login__1440.jpg`, `public/search-landing__1440.jpg` |
| P2-10 | Notifications stack three reminders for the same call (3, 7, 14 days) without grouping. | `notifications__1440.jpg` |
| P2-11 | Inconsistent back links: "Back to Workspace Opportunities" vs "Back to Opportunity Workspace". | workspace item / submission |
| P2-12 | The header block is a floating white box with margins rather than a full-width bar; content width (1120) does not match the nav width at some pages. | all |

## P3 — minor

| # | Finding |
|---|---|
| P3-1 | "Loading..." with three dots vs "…" elsewhere. |
| P3-2 | Junk test data visible in the dev database ("hmkjyifwefwe" posting) — data, not design, but it appears in screenshots. |
| P3-3 | Icons mix 14/15/16px sizes in the same row. |
| P3-4 | Notification timestamps "6 Oct, 22:16" have no year or relative time. |
| P3-5 | "No account yet? Create one" vs "Create account" vs "Create an account". |

## UX audit

**Information architecture.** The app is organised by *build phase*, not by user job: 13
peer-level tabs in one row, personal tools mixed with discovery, account pages reachable only
through the strip, and a profile page that is really six products (identity, expertise,
preferences, personalization diagnostics, recommendation history, feedback). Proposed
structure: Home · Discover · For you · My research · Account, filtered per role
(plan §7).

**Navigation.** No `aria-current`; active state shown twice; off-screen tabs; duplicated nav on
two pages; no breadcrumbs on detail pages; contextual tools exposed as tabs.

**Hierarchy.** Several pages lead with decoration (stat cards, phase banners, caveat panels)
and push the actual list below the fold. The admin page shows a card before its own title.

**Discoverability.** Recommendations (the personalization engine) live 2,000+ px down the
profile page; there is no "Recommended for you" entry point. Venue matching and similar
research are reachable only from a search result card.

**Cognitive load.** Scores without reasons (match %), reasons without plain language
(signal names, weights), and repeated caveats. The explanation drawer opens on raw score
decomposition.

**Consistency.** 41 button classes, three primary colours, three explanation patterns, two
"back" phrasings, mixed case, mixed date formats ("10/10/2026", "6 Oct", "2026-10-09 11:59
UTC (UTC)").

**Action placement and competing CTAs.** 20 primary buttons on a search results page; nine
actions per workspace card; offer-before-shortlist ordering for faculty decisions.

**Forms.** Labels are mostly present on auth forms; settings and preferences have unlabelled
selects and switches (axe: 39 select-name nodes on 7 routes, 12 unlabelled inputs). Reading
list notes save on blur (good) but give no saved confirmation.

**Search.** Strong engine, weak surface: query and filters are not in the URL, filters are
collapsed behind "Filters & Ranking Mode", ranking mode jargon, no sort control, reasons
hidden in a drawer.

**Filtering and pagination.** Postings and workspace have usable filters; browse has none;
venue matching filters are a cramped inline row; pagination exists only on search.

**Feedback.** Spinners on 20 pages, a skeleton on one; no toasts; inline success messages in
settings only.

**Error recovery.** Retry exists on search and discovery pages; most other pages show an error
string without a retry action.

**Empty states.** Present but inconsistent (centered icon blocks with different copy styles);
good examples: postings ("22 postings"), submissions ("No submissions yet").

**Loading states.** No skeletons except notifications; layout shift up to 0.067 (workspace)
as content arrives.

**Mobile.** Navigation unusable (2 visible tabs), sideways scrolling everywhere (P0-1),
broken calendar and workspace rows, tables overflowing, five stacked stat cards before
content.

**Unnecessary clicks.** Similar/venue tools require search → result → button; changing a
workspace status takes the right one of four "Move to" buttons; reading-list status change
needs the select on each item (fine) but notes are always expanded.

**Confusing terminology.** "Opportunity" means calls for papers (workspace, matcher) *and* is
used inside postings ("About this opportunity", "Apply for this opening"); "Calls & Venues",
"Browse All Calls", "Recommended opportunities" refer to the same list; "Match", "Fit",
"Composite score", "Relevance" are used interchangeably.
