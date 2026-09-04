# Phase 2.7D — Deadline Intelligence & Urgency Engine Architecture

> **Authoritative Statement**:
> Phase 2.7D provides deterministic deadline intelligence and urgency assessment. It does not introduce deadline extensions/conflict resolution or redesign recommendation ranking.

---

## 1. Executive Summary & Pipeline Architecture

Phase 2.7 establishes a principled, end-to-end deadline intelligence subsystem for ResearchConnect AI. Following Phase 2.7B (evidence extraction) and Phase 2.7C (date & timezone normalization), Phase 2.7D implements the **Deadline Intelligence & Urgency Engine**.

While Phase 2.7C answers:
> *"What temporal instant/date does this deadline evidence represent?"*

Phase 2.7D answers:
> *"Given a normalized deadline and reference time, how urgent is it?"*

### Architecture Flow

```text
Raw Source (WikiCFP, OpenAlex, Crossref, DB)
    ↓
Phase 2.7B: DeadlineEvidence & DeadlineEvidenceCollection
    ↓
Phase 2.7C: DeadlineNormalizer & NormalizedDeadline
    ↓
Phase 2.7D: DeadlineIntelligence & DeadlineAssessment
    ↓
Phase 2.7E: Extension & Conflict Intelligence (deferred)
    ↓
Phase 2.7F: API Schemas & Explainability UI (deferred)
    ↓
Phase 2.7G: Empirical Evaluation & Validation (deferred)
```

The engine is **purely in-memory, deterministic, explainable, bounded**, and **independent from trust/risk scoring**.

---

## 2. Deadline Assessment Model

The core evaluation models reside in `backend/app/ranking/deadline/models.py`.

### `DeadlineAssessment`
Represents an immutable, strongly typed assessment for a single academic milestone:

| Field | Type | Description |
| :--- | :--- | :--- |
| `deadline_type` | `DeadlineType` | Semantic milestone (`SUBMISSION`, `ABSTRACT`, `NOTIFICATION`, etc.) |
| `reference_time` | `datetime` | UTC timezone-aware anchor timestamp |
| `normalized_deadline` | `NormalizedDeadline \| None` | Input normalized deadline from Phase 2.7C |
| `status` | `DeadlineTemporalStatus` | Lifecycle-independent temporal status |
| `urgency_tier` | `UrgencyTier` | Discrete explainable categorization |
| `urgency_score` | `float` | Bounded $[0.0, 1.0]$ monotonic proximity score |
| `seconds_remaining` | `float \| None` | Exact elapsed seconds until deadline instant |
| `minutes_remaining` | `float \| None` | Exact elapsed minutes |
| `hours_remaining` | `float \| None` | Exact elapsed hours |
| `days_remaining` | `float \| None` | Exact elapsed days |
| `confidence` | `float` | Temporal confidence score $[0.0, 1.0]$ |
| `explanation` | `str` | Structured, deterministic human explanation |
| `metadata` | `dict[str, Any]` | Contextual diagnostics (precision, source) |

### `OpportunityDeadlineAssessment`
Composite model aggregating all milestone assessments for an opportunity:
- `opportunity_id: str | None`
- `reference_time: datetime`
- `primary_assessment: DeadlineAssessment | None` (the primary milestone selected for submission urgency)
- `milestone_assessments: list[DeadlineAssessment]`
- `.get_by_type(deadline_type: DeadlineType) -> list[DeadlineAssessment]`
- `.to_dict() -> dict[str, Any]`

---

## 3. Temporal Status Model

`DeadlineTemporalStatus` introduces lifecycle-independent temporal states that do not conflate with `OpportunityModel.status` (`ACTIVE`, `EXPIRED`, `UNVERIFIED`):

```python
class DeadlineTemporalStatus(str, Enum):
    UPCOMING = "UPCOMING"       # Future deadline (> 0 seconds remaining)
    DUE_TODAY = "DUE_TODAY"     # Falls on reference calendar day (not yet elapsed)
    EXPIRED = "EXPIRED"         # Deadline instant has elapsed (< 0 seconds remaining)
    MISSING = "MISSING"         # Unspecified date (None, TBA, TBD, N/A)
    INVALID = "INVALID"         # Malformed date components or invalid timezone
    AMBIGUOUS = "AMBIGUOUS"     # Format ambiguity (e.g. 04/05/2026)
```

**Lifecycle Decoupling Invariant**:
- `OpportunityModel.status = ACTIVE` + `DeadlineTemporalStatus = DUE_TODAY` is valid.
- `OpportunityModel.status = ACTIVE` + `DeadlineTemporalStatus = MISSING` is valid.
- `DeadlineAssessment.status` never directly mutates `OpportunityModel.status`.

---

## 4. Discrete Urgency Tiers

Tiers categorize remaining time into intuitive, actionable segments:

| Tier | Window Condition | Description |
| :--- | :--- | :--- |
| `DUE_TODAY` | Same calendar day & $> 0$ seconds | Due on current day |
| `CRITICAL` | $\le 3.0$ days remaining | Imminent deadline |
| `URGENT` | $\le 14.0$ days remaining | Short preparation window |
| `APPROACHING` | $\le 30.0$ days remaining | Approaching horizon |
| `DISTANT` | $> 30.0$ days remaining | Well beyond near-term window |
| `EXPIRED` | $< 0$ seconds remaining | Deadline elapsed; zero urgency |
| `UNKNOWN` | Missing, invalid, or ambiguous | No fabricated urgency |

All window thresholds are centralized in `backend/app/ranking/deadline/intelligence.py`:
- `DEFAULT_CRITICAL_WINDOW_DAYS = 3.0`
- `DEFAULT_URGENT_WINDOW_DAYS = 14.0`
- `DEFAULT_APPROACHING_WINDOW_DAYS = 30.0`
- `DEFAULT_MAX_URGENCY_WINDOW_DAYS = 90.0`

---

## 5. Mathematical Urgency Score Formula

The urgency score is continuous, bounded in $[0.0, 1.0]$, and strictly monotonic:

$$\text{urgency\_score} = 
\begin{cases} 
0.0 & \text{if } \text{days\_remaining} < 0.0 \text{ (expired)} \\
0.0 & \text{if } \text{days\_remaining} \ge W_{\max} \text{ (beyond horizon)} \\
0.0 & \text{if status} \in \{\text{MISSING}, \text{INVALID}, \text{AMBIGUOUS}\} \\
1.0 & \text{if } \text{days\_remaining} = 0.0 \text{ (deadline now)} \\
1.0 - \left(\frac{\text{days\_remaining}}{W_{\max}}\right) & \text{if } 0.0 \le \text{days\_remaining} < W_{\max}
\end{cases}$$

where $W_{\max} = 90.0$ days by default (configured via `settings.hybrid_ranking_urgency_window_days`).

### Monotonicity Proof
For any deadline $D$ and reference timestamps $T_1 < T_2 < D$:
$$\text{days\_remaining}(T_1) = \frac{D - T_1}{86400} > \frac{D - T_2}{86400} = \text{days\_remaining}(T_2) \ge 0$$
$$\implies 1.0 - \frac{\text{days\_remaining}(T_1)}{W_{\max}} \le 1.0 - \frac{\text{days\_remaining}(T_2)}{W_{\max}}$$
$$\implies \text{urgency}(T_1) \le \text{urgency}(T_2)$$
Monotonicity is verified under unit tests across all time offsets.

---

## 6. Reference-Time Semantics

The engine explicitly accepts an injected `reference_time: datetime | None = None`.
- If `reference_time` is `None`, it defaults to `datetime.now(timezone.utc)` at the outermost entrypoint.
- If `reference_time` is naive, it is coerced to UTC tz-aware.
- If `reference_time` is in another timezone, it is converted to UTC via `.astimezone(timezone.utc)`.
- Core calculation is a pure function: **same inputs $\to$ identical outputs across 100+ runs**.

---

## 7. Due-Today Semantics

A deadline occurring later today is **not expired**.
- Reference: `2026-08-22 10:00:00 UTC`
- Deadline: `2026-08-22 23:59:59 UTC`
- Status: `DUE_TODAY`
- Urgency Tier: `DUE_TODAY`
- Seconds Remaining: `50,399.0s` (14 hours remaining)
- Urgency Score: `0.993519`
- Is Expired: `False`

Due-today condition:
$$\text{seconds\_remaining} \ge 0 \land (\text{normalized\_utc.date}() = \text{ref.date}() \lor \text{local\_date} = \text{ref.date}())$$

---

## 8. Expiration Semantics

A deadline is expired strictly when:
$$\text{normalized\_utc} < \text{reference\_time} \quad (\text{or } \text{local\_date} < \text{ref.date}())$$

- Expired by 1 second: `seconds_remaining = -1.0`, `status = EXPIRED`, `tier = EXPIRED`, `urgency_score = 0.0`.
- Missing, invalid, or ambiguous dates **never expire**; they remain `MISSING`, `INVALID`, or `AMBIGUOUS` with `urgency_score = 0.0`.

---

## 9. Milestone Handling & Precedence

Milestones are isolated and never conflated:
1. `SUBMISSION` — Main paper submission deadline
2. `ABSTRACT` — Pre-submission abstract registration deadline
3. `NOTIFICATION` — Author acceptance/rejection notification date
4. `CAMERA_READY` — Final camera-ready manuscript deadline
5. `REGISTRATION` — Registration deadline
6. `EVENT_START` — Event convening start date
7. `EVENT_END` — Event conclusion end date

### Primary Milestone Selection
When assessing an opportunity collection, `primary_assessment` is determined by strict precedence:
$$\text{SUBMISSION} \to \text{ABSTRACT} \to \text{REGISTRATION} \to \text{CAMERA\_READY} \to \text{NOTIFICATION} \to \text{EVENT\_START} \to \text{EVENT\_END}$$

**Boundary Guard**:
If an opportunity has no submission deadline and only an `EVENT_START`, the primary assessment clearly labels the milestone as `Event start date` and explicitly states `(no submission deadline specified)`. Event dates are never misrepresented as paper submission deadlines.

---

## 10. Deadline Confidence Scoring

Confidence is computed independently from extraction, normalization, and risk confidence:

$$\text{confidence} = \text{round}\left(\text{clamp}\left(C_{\text{norm}} \times F_{\text{tz}} \times F_{\text{prec}} \times C_{\text{ext}}, 0.0, 1.0\right), 4\right)$$

- $F_{\text{tz}} = 1.0$ (explicit timezone), $0.90$ (inferred AoE), $0.75$ (unknown).
- $F_{\text{prec}} = 1.0$ (exact time), $0.95$ (date only).
- Missing/invalid/ambiguous dates: $\text{confidence} = 0.0$.

---

## 11. Structured Explanations

Explanations are deterministically generated from structured temporal attributes without LLM dependencies:
- `"Submission deadline is today (14 hours remaining). Timezone inferred from academic date convention."`
- `"Submission deadline is 18 hours away."`
- `"Submission deadline is 5 days away."`
- `"Submission deadline passed 2 days ago."`
- `"No deadline specified for submission deadline."`
- `"Deadline could not be parsed or contains invalid timezone for submission deadline."`
- `"Deadline could not be normalized because the date is ambiguous for submission deadline."`

---

## 12. `calculate_urgency()` Backward Compatibility

`backend/app/ranking/signals.py::calculate_urgency()` implements an adapter pattern:
- Accepts `DeadlineAssessment` instance: returns `assessment.urgency_score`.
- Accepts `NormalizedDeadline` instance: delegates to `DeadlineIntelligence.assess_deadline()`.
- Accepts `datetime`, ISO string, or `None`: maintains 100% byte-for-byte and floating-point backward compatibility with existing Phase 2.5 callers.

---

## 13. Ranking & Expiration Compatibility

- **Ranking Compatibility**: Phase 2.5 ranking weights, relevance dominance ($\ge 85\%$), academic quality, diversity, and cross-encoder re-ranking remain completely untouched.
- **Risk Compatibility**: Phase 2.6 risk scoring, thresholds, graph intelligence, and evidence remain completely orthogonal. Imminent deadlines do not affect venue risk.
- **Expiration Compatibility**: `scrapers/expiration/manager.py` continues to evaluate opportunity lifecycle status independently. `DeadlineAssessment.is_expired()` duck-types safely with expiration checkers.

---

## 14. Performance & In-Memory Invariants

The engine operates entirely in memory:
- **0 Database Queries**
- **0 Network Calls**
- **0 N+1 Queries**
- **0 LLM Calls**

### Benchmark Results
Measured on Python 3.13.5:
| Candidate Count | Total Time | Time / Candidate | Target |
| :--- | :--- | :--- | :--- |
| **10 candidates** | $0.051\text{ ms}$ | $0.0051\text{ ms}$ | $< 0.1\text{ ms}$ |
| **50 candidates** | $0.229\text{ ms}$ | $0.0046\text{ ms}$ | $< 0.1\text{ ms}$ |
| **100 candidates** | $0.448\text{ ms}$ | $0.0045\text{ ms}$ | $< 0.1\text{ ms}$ |
| **200 candidates** | $0.887\text{ ms}$ | $0.0044\text{ ms}$ | $< 0.1\text{ ms}$ |
| **1,000 candidates** | $4.410\text{ ms}$ | $0.0044\text{ ms}$ | $< 0.1\text{ ms}$ |

The engine processes over **225,000 candidates per second**, beating the $< 0.1\text{ ms/candidate}$ requirement by a factor of 22x.

---

## 15. Test Coverage & Verification

### Test Suite Summary
1. **`backend/tests/test_deadline_intelligence.py`**: 37 tests (100% passing in 0.45s)
   - Lifecycle-independent temporal status (6 tests)
   - Urgency tiers and boundary conditions (5 tests)
   - Mathematical properties & monotonicity (3 tests)
   - Due-today and expired semantics (3 tests)
   - AoE and day/month/year rollover (3 tests)
   - DST and IANA timezones (2 tests)
   - Milestone independence & precedence (3 tests)
   - Confidence scoring (3 tests)
   - 100-run determinism & batch benchmarks (6 tests)
   - `calculate_urgency()` compatibility (3 tests)
2. **`backend/tests/test_date_timezone_normalization.py`**: 28 tests (100% passing)
3. **`backend/tests/test_deadline_evidence_extraction.py`**: 16 tests (100% passing)
4. **`backend/tests/test_ranking_signals.py`**: 21 tests (100% passing)
5. **Full Backend Suite**: 628 passed, 8 skipped (100% green)
6. **Full Scrapers Suite**: 389 passed (100% green)
7. **Frontend Build**: `tsc -b && vite build` built in 1.27s (0 errors)

---

## 16. Scope Boundaries & Deferred Functionality

Strict phase boundaries were preserved throughout Phase 2.7D:
- **Deferred to Phase 2.7E**: Deadline extension detection, multi-source conflict resolution, and historical deadline tracking.
- **Deferred to Phase 2.7F**: API schemas exposure (`OpportunityDeadlineSchema`), frontend badges (`DeadlineBadge`), timeline component, and Explainability Drawer deadline tab.
- **Deferred to Phase 2.7G**: Empirical evaluation, precision/recall analysis, and historical CFP validation.

---

## 17. Verdict

**READY FOR PHASE 2.7E**
