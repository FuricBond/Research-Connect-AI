# Phase 2.7E — Conflict, Extension & Multi-Deadline Intelligence Architecture

> **Authoritative Statement**:
> Phase 2.7E implements deterministic multi-source conflict resolution, temporal equivalence matching, revision tracking, and canonical deadline view synthesis. It does not alter Phase 2.5 recommendation ranking weights, Phase 2.6 risk scoring, or introduce speculative database migrations.

---

## 1. Executive Summary & Problem Statement

Academic deadline management presents complex real-world challenges across multiple dimensions:
1. **Representational Diversity**: Different sources express the exact same temporal deadline in differing syntactic forms (e.g. `Aug 22, 2026 AoE`, `2026-08-23 11:59:59 UTC`, `2026-08-22 23:59:59 -12:00`). A naive string comparison treats these as conflicting.
2. **Deadline Postponements & Revisions**: Conferences frequently extend submission deadlines (e.g. `Aug 20 AoE` $\to$ `Aug 27 AoE`). Ingestion systems that overwrite database columns discard historical evidence and prevent users from knowing that a deadline was extended.
3. **Multi-Source Disagreements**: Multiple scrapers and aggregators (WikiCFP list pages, WikiCFP detail pages, OpenAlex, Crossref, official websites) may report conflicting dates. Naive systems either silently pick one or crash.
4. **Multi-Milestone Isolation**: Academic opportunities involve distinct milestones (`SUBMISSION`, `ABSTRACT`, `NOTIFICATION`, `CAMERA_READY`, `REGISTRATION`, `EVENT_START`, `EVENT_END`). Conflating notification dates or event dates with submission deadlines leads to catastrophic false positives and incorrect urgency evaluations.
5. **Retractions vs Missing Metadata**: When a scraped page temporarily omits a date field due to parsing glitches or layout changes, naive systems may flag the deadline as "cancelled" or "retracted".

Phase 2.7E solves these challenges by establishing an in-memory, deterministic **Conflict, Extension & Multi-Deadline Intelligence** subsystem that sits downstream of Phase 2.7B (evidence extraction), Phase 2.7C (normalization), and Phase 2.7D (urgency intelligence).

### Architectural Data Flow

```text
Evidence Collection (2.7B)
          ↓
Date & Timezone Normalization (2.7C)
          ↓
Temporal Assessment (2.7D)
          ↓
Observation & Revision Modeling (2.7E)
          ↓
Temporal Equivalence & Cluster Analysis (2.7E)
          ↓
Source Authority Resolution & Supersession (2.7E)
          ↓
Canonical Deadline View (2.7E)
```

---

## 2. Observation & Revision Domain Models

All models reside in [`backend/app/ranking/deadline/models.py`](file:///d:/Project/researchconnect-ai/backend/app/ranking/deadline/models.py).

### 2.1 `DeadlineObservation`
An atomic, provenance-tracked observation of an academic milestone from a specific source at a specific time:

| Field | Type | Description |
| :--- | :--- | :--- |
| `opportunity_id` | `str \| None` | Associated opportunity identifier |
| `deadline_type` | `DeadlineType` | Milestone (`SUBMISSION`, `ABSTRACT`, `NOTIFICATION`, etc.) |
| `raw_value` | `str \| None` | Verbatim date string from source |
| `normalized_deadline` | `NormalizedDeadline \| None` | Phase 2.7C normalized model |
| `source` | `str` | Name of source (e.g. `"wikicfp"`, `"official_site"`) |
| `source_url` | `str \| None` | URL of the scraped page |
| `observation_time` | `datetime \| None` | Timestamp when the observation was extracted/scraped |
| `provenance` | `DeadlineProvenance` | Provenance category |
| `extraction_method` | `ExtractionMethod` | Extraction method |
| `authority_tier` | `SourceAuthorityTier` | Evidentiary reliability tier |
| `normalization_confidence` | `float` | Confidence from Phase 2.7C |
| `source_confidence` | `float` | Extraction confidence from Phase 2.7B |
| `is_current` | `bool` | True if this is an active observation |
| `is_retracted` | `bool` | True if explicitly retracted by source |
| `retraction_evidence` | `str \| None` | Textual quote or notice confirming retraction |
| `metadata` | `dict[str, Any]` | Extensible metadata |

### 2.2 `DeadlineRevision`
Models the temporal delta and transition classification between two successive observations:

| Field | Type | Description |
| :--- | :--- | :--- |
| `deadline_type` | `DeadlineType` | Milestone evaluated |
| `previous_observation` | `DeadlineObservation \| None` | Prior baseline observation |
| `current_observation` | `DeadlineObservation` | Latest incoming observation |
| `classification` | `RevisionClassification` | Transition type (`INITIAL`, `EXTENDED`, etc.) |
| `days_diff` | `float \| None` | Signed day delta ($> 0$ postponed, $< 0$ earlier) |
| `hours_diff` | `float \| None` | Signed hour delta |
| `explanation` | `str` | Deterministic structured explanation |

### 2.3 `CanonicalDeadlineView`
The synthesized authoritative output for a specific milestone:
- `canonical_deadline`: Normalized deadline (or `None` if unresolved conflict).
- `canonical_assessment`: Phase 2.7D assessment (urgency, status, tier).
- `selected_source`: Source whose observation was selected.
- `conflict_state`: `NO_CONFLICT`, `EQUIVALENT_SOURCES`, `SOURCE_CONFLICT`, `SUPERSEDED`, `INSUFFICIENT_EVIDENCE`.
- `all_observations`: Full list of preserved observations (zero evidence loss).
- `revision_history`: Chronological sequence of revisions.
- `latest_revision`: Most recent transition.
- `unresolved_alternatives`: Conflicting observations when in conflict or superseded.
- `explanation`: Deterministic human explanation.

### 2.4 `OpportunityCanonicalView`
Aggregates canonical views across all milestones for an entire opportunity:
- `primary_milestone`: Precedence-selected primary milestone (default `SUBMISSION`).
- `primary_view`: Canonical view for the primary milestone.
- `milestone_views`: Dictionary mapping each `DeadlineType` to its `CanonicalDeadlineView`.

---

## 3. Temporal Equivalence Engine

The function `are_deadlines_equivalent(d1, d2)` in [`backend/app/ranking/deadline/resolvers.py`](file:///d:/Project/researchconnect-ai/backend/app/ranking/deadline/resolvers.py) evaluates semantic equivalence:

1. **UTC Instant Comparison**:
   If both deadlines possess a `normalized_utc` instant, the absolute difference in seconds is calculated:
   $$\Delta t = |\text{utc}_1 - \text{utc}_2|$$
   $$\Delta t < 1.0\text{ s} \implies \text{Equivalent}$$
   - `Aug 22, 2026 AoE` ($\equiv 2026\text{-}08\text{-}23\text{ 11:59:59 UTC}$) and `2026-08-23 11:59:59 UTC` are **EQUIVALENT**.
   - `2026-08-22 23:59:59 -12:00` and `2026-08-23 11:59:59 UTC` are **EQUIVALENT**.
   - `July 15, 2026 17:00 America/New_York` (EDT, UTC-4) and `2026-07-15 21:00 UTC` are **EQUIVALENT**.
2. **Calendar Date Comparison**:
   If both deadlines are date-only without synthesized UTC instants, calendar dates are compared:
   $$\text{local\_date}_1 == \text{local\_date}_2 \implies \text{Equivalent}$$
3. **Missing Equivalence**:
   Two `MISSING` deadlines are equivalent. A `MISSING` deadline and a populated deadline are **not equivalent**.

Raw strings are **never** compared directly.

---

## 4. Revision & Extension Classification

The `classify_revision(previous_obs, current_obs)` engine determines the exact lifecycle change:

```python
class RevisionClassification(str, Enum):
    INITIAL = "INITIAL"              # First observed deadline for this milestone
    UNCHANGED = "UNCHANGED"          # Identical deadline instant reported
    EXTENDED = "EXTENDED"            # Deadline postponed to a later date/time
    MOVED_EARLIER = "MOVED_EARLIER"  # Deadline moved earlier
    REPLACED = "REPLACED"            # Format change / unresolvable transition
    RETRACTED = "RETRACTED"          # Explicitly withdrawn or cancelled
    CONFLICTING = "CONFLICTING"      # Concurrent incompatible source observation
    EQUIVALENT = "EQUIVALENT"        # Different syntax expressing the same instant
```

### Transition Logic
- If `current_obs.is_retracted`: `RETRACTED`.
- If `previous_obs is None`: `INITIAL`.
- If `previous_obs.is_retracted` and not `current_obs.is_retracted`: `INITIAL` (reinstated).
- If `current_obs` dropped the date without retraction evidence: `REPLACED` (missing $\ne$ retracted).
- If `are_deadlines_equivalent(prev, curr)`: `UNCHANGED`.
- If $\Delta t > 0$: `EXTENDED` (with positive `days_diff`).
- If $\Delta t < 0$: `MOVED_EARLIER` (with negative `days_diff`).

---

## 5. Multi-Source Conflict Detection & Source Authority

When multiple independent observations exist for the same `(opportunity_id, deadline_type)`, `DeadlineConflictResolver.resolve_milestone()` groups them into equivalence clusters:

### Source Authority Hierarchy (`SourceAuthorityTier`)
Evidentiary reliability is determined strictly by source transparency:
1. `OFFICIAL_CFP` (Tier 4): Official conference portal or organizer domain.
2. `DETAIL_PAGE` (Tier 3): Comprehensive aggregator detail page (e.g. WikiCFP `event.showcfp`).
3. `LIST_PAGE` (Tier 2): Aggregator list/table row (e.g. WikiCFP `/cfp/call`).
4. `GENERAL_AGGREGATOR` (Tier 1): General citation indexers (OpenAlex, Crossref).
5. `UNKNOWN` (Tier 0): Unspecified origin.

### Conflict States
- `EQUIVALENT_SOURCES`: All sources report deadlines belonging to a single equivalence cluster. Disagreement is syntactic only.
- `SUPERSEDED`: Multiple clusters exist, but one cluster has a strictly higher authority tier (e.g. Official CFP vs aggregator list page). The higher tier supersedes the lower tier.
- `SOURCE_CONFLICT`: Multiple clusters exist with **equal top authority** (e.g. two aggregators disagreeing, or two official conflicting announcements without timestamp clarity).
- `NO_CONFLICT`: Single active observation.
- `INSUFFICIENT_EVIDENCE`: Zero active observations.

### Invariant on Equal-Authority Conflicts
When `SOURCE_CONFLICT` occurs:
$$\text{canonical\_deadline} = \text{None}$$
$$\text{canonical\_assessment} = \text{None}$$
$$\text{selected\_source} = \text{None}$$
$$\text{unresolved\_alternatives} = \text{active\_observations}$$

The system **never fabricates a winner**. Disagreement is preserved and made visible to downstream explainability services.

---

## 6. Retraction vs Missing Semantics

A critical boundary enforced in Phase 2.7E:
$$\text{Missing Field} \neq \text{Retracted Deadline}$$

- If a parser fails or an aggregator temporarily drops a field: `REPLACED` (or `MISSING`), preserving previous evidence.
- If explicit affirmative evidence exists (e.g. `"Submissions cancelled by organizers"`, `"CFP withdrawn"`): `RETRACTED`.

---

## 7. Multi-Milestone Independence & Precedence

All milestones operate independently:
- `SUBMISSION`
- `ABSTRACT`
- `NOTIFICATION`
- `CAMERA_READY`
- `REGISTRATION`
- `EVENT_START`
- `EVENT_END`

Different milestones never conflict with each other. For example:
- Submission deadline: August 20
- Notification date: September 10
- Event start: October 15

These are 3 harmonious milestones, not a 3-way conflict.

### Primary Milestone Precedence
When determining the primary deadline for submission urgency:
$$\text{SUBMISSION} \to \text{ABSTRACT} \to \text{REGISTRATION} \to \text{CAMERA\_READY} \to \text{NOTIFICATION} \to \text{EVENT\_START} \to \text{EVENT\_END}$$

If an opportunity only has an `EVENT_START`, the primary view designates `deadline_type = EVENT_START` and labels it as `Event start date`. Event dates are **never** disguised as paper submission deadlines.

---

## 8. Safety Invariants Compliance

Phase 2.7E enforces all 15 required safety invariants under automated test:

| # | Invariant | Enforcement Mechanism |
| :---: | :--- | :--- |
| **1** | Missing $\neq$ Expired | Missing deadlines have `status=MISSING`, `urgency_score=0.0`, `is_expired=False`. |
| **2** | Missing $\neq$ Retracted | Dropped fields classify as `REPLACED`, not `RETRACTED` without explicit proof. |
| **3** | Unknown TZ $\neq$ Known TZ | `STRICT_UNKNOWN` policy preserves `DATE_ONLY` without synthesized UTC. |
| **4** | Ambiguous $\neq$ Fabricated | Slash dates (e.g. `04/05/2026`) yield `AMBIGUOUS` with $0.0$ urgency score. |
| **5** | Equivalent Dates $\neq$ Conflict | AoE and UTC representations yield `ConflictState.EQUIVALENT_SOURCES`. |
| **6** | Different Milestones $\neq$ Conflict | Milestone views are partitioned by `DeadlineType`. |
| **7** | Observation Time $\neq$ Deadline Time | Scrape timestamp is decoupled from event calendar deadline. |
| **8** | Newer Ingestion $\neq$ Higher Authority | Official CFP beats newer aggregator scrape. |
| **9** | Source Conflict $\neq$ Automatic Risk | Predatory risk scores and flags are completely untouched. |
| **10** | Extension $\neq$ Relevance Boost | Phase 2.5 ranking signals and weights remain unchanged. |
| **11** | Extension $\neq$ Predatory Risk | Deadline extensions do not increase venue risk penalties. |
| **12** | Deadline Intelligence $\neq$ Academic Quality | Indexing tiers, citations, and prestige remain orthogonal. |
| **13** | Deadline Intelligence $\neq$ Personalization | Recommendation candidate scoring remains unmodified. |
| **14** | Strict Determinism | 100 consecutive runs with fixed reference time produce identical output. |
| **15** | No Silent Evidence Loss | All raw observations preserved in `all_observations`. |

---

## 9. Performance & In-Memory Efficiency

The resolver operates entirely in memory:
- **0 Database Queries**
- **0 Network Calls**
- **0 N+1 Queries**
- **0 LLM Dependencies**

### Benchmark Results (Python 3.13.5)
| Candidate / Observation Count | Total Duration | Time per Candidate | Target | Status |
| :--- | :--- | :--- | :--- | :--- |
| **10 candidates** | $0.076\text{ ms}$ | $0.0076\text{ ms}$ | $< 0.1\text{ ms}$ | **PASSED** |
| **50 candidates** | $0.354\text{ ms}$ | $0.0071\text{ ms}$ | $< 0.1\text{ ms}$ | **PASSED** |
| **100 candidates** | $0.702\text{ ms}$ | $0.0070\text{ ms}$ | $< 0.1\text{ ms}$ | **PASSED** |
| **200 candidates** | $1.411\text{ ms}$ | $0.0071\text{ ms}$ | $< 0.1\text{ ms}$ | **PASSED** |
| **1,000 candidates** | $7.025\text{ ms}$ | $0.0070\text{ ms}$ | $< 0.1\text{ ms}$ | **PASSED** |

Throughput exceeds **140,000 candidate evaluations per second**, outperforming the $< 0.1\text{ ms/candidate}$ ceiling by over 14x.

---

## 10. Test Coverage Summary

- **`backend/tests/test_deadline_conflict_resolution.py`**: 38 tests (100% passing)
  - Temporal equivalence (8 tests)
  - Revision & extension classification (7 tests)
  - Multi-source conflict & supersession (4 tests)
  - Multi-milestone isolation & precedence (3 tests)
  - Safety invariants (11 tests)
  - Batch performance benchmarks (5 tests)
- **Combined Deadline Suite**: 140 tests passing in 0.57s
- **Full Backend Suite**: 666 passed, 8 skipped
- **Scrapers Suite**: 389 passed
- **Frontend Build**: `npm run build` succeeds cleanly in 1.23s

---

## 11. Limitations & Deferred Functionality

Strict phase boundaries were preserved:
- **Deferred to Phase 2.7F**: Public REST API response serialization (`CanonicalDeadlineViewSchema`), UI extension badges (`"Extended!"`), timeline visualizer, and Explainability Drawer deadline conflict tab.
- **Deferred to Phase 2.7G**: Empirical evaluation against historical multi-year CFP repositories.

---

## 12. Verdict

**READY FOR PHASE 2.7F**
