# Phase 2.4E — Hybrid Ranking Engine

## 1. Purpose

Phase 2.4E implements a dedicated, reusable **Hybrid Ranking Engine** that sits above candidate retrieval and matching services.

While upstream services (e.g. `VectorRepository`, `LexicalRepository`, `SimilarResearchService`, `ResearchOpportunityMatchingService`) retrieve candidate pools using single or dual-channel criteria, the Hybrid Ranking Engine normalizes, evaluates, and ranks these candidates against a unified, multi-signal feature vector.

> [!IMPORTANT]
> **Architectural Boundary**:
> Phase 2.4E computes **structured, explainable numerical scores** for each signal and the composite result.
> Natural-language explanation generation is explicitly deferred to **Phase 2.4F**, and HTTP API routing is deferred to **Phase 2.4G**.

---

## 2. Architecture & Pipeline

```text
       Upstream Retrieval & Matching Services
 (SimilarResearchService, ResearchOpportunityMatchingService, HybridSearchService)
                          │
                          ▼
                   Candidate Pool
                          │
                          ▼
            ┌───────────────────────────┐
            │       HybridRanker        │
            │                           │
            │ 1. Signal Extraction      │
            │    - Semantic Similarity  │
            │    - Lexical Relevance    │
            │    - Topic Compatibility  │
            │    - Type Compatibility   │
            │    - Publication Recency  │
            │    - Deadline Urgency     │
            │                           │
            │ 2. Signal Validation      │
            │    (Finite, Clamp [0, 1]) │
            │                           │
            │ 3. Weight Normalization   │
            │    (Sum of weights = 1.0) │
            │                           │
            │ 4. Composite Scoring      │
            │    final_score in [0, 1]  │
            │                           │
            │ 5. Deterministic Sort     │
            │    (7-tier tie-breaking)  │
            └─────────────┬─────────────┘
                          │
                          ▼
             list[RankedCandidate]
```

---

## 3. Signal Definitions & Normalization

All signals in the ranking layer are strictly normalized to the range $[0.0, 1.0]$:

| Signal | Symbol | Range | Description & Calculation |
|---|---|---|---|
| **Semantic Similarity** | $S_{\text{sem}}$ | $[0.0, 1.0]$ | Cosine similarity from 384-dimensional dense embeddings (`all-MiniLM-L6-v2`) via pgvector. |
| **Lexical Relevance** | $S_{\text{lex}}$ | $[0.0, 1.0)$ | Full-text relevance via PostgreSQL `ts_rank_cd`, normalized via monotonic transform: $\frac{\text{raw}}{\text{raw} + 1.0}$. |
| **Topic Compatibility** | $S_{\text{top}}$ | $[0.0, 1.0]$ | Multi-evidence canonical topic overlap, primary topic bonus ($+20\%$), and taxonomy DAG ancestor proximity. |
| **Type Compatibility** | $S_{\text{type}}$ | $[0.0, 1.0]$ | Deterministic academic matrix mapping research work classification (`article`, `preprint`, `proceedings-article`) to opportunity category (`JOURNAL`, `CONFERENCE`, `WORKSHOP`, `CALL_FOR_PAPERS`). |
| **Publication Freshness** | $S_{\text{fresh}}$ | $[0.0, 1.0]$ | Exponential recency decay based on publication age: $\exp\left(-\frac{\ln(2)}{\text{half\_life}} \cdot \max(0, Y_{\text{ref}} - Y_{\text{pub}})\right)$. Default half-life: 5.0 years. |
| **Deadline Urgency** | $S_{\text{urg}}$ | $[0.0, 1.0]$ | Proximity to opportunity submission deadline: $\max\left(0.0, 1.0 - \frac{\text{days\_remaining}}{\text{window\_days}}\right)$. Expired deadlines return $0.0$. Default window: 90.0 days. |

---

## 4. Configurable Weights & Presets

Weights are fully validated (non-negative, finite numbers) and normalized so their sum equals $1.0$:

$$\text{final\_score} = w_{\text{sem}} \cdot S_{\text{sem}} + w_{\text{lex}} \cdot S_{\text{lex}} + w_{\text{top}} \cdot S_{\text{top}} + w_{\text{type}} \cdot S_{\text{type}} + w_{\text{fresh}} \cdot S_{\text{fresh}} + w_{\text{urg}} \cdot S_{\text{urg}}$$

### Mode Defaults

| Weight Parameter | `RESEARCH_SIMILARITY` | `RESEARCH_OPPORTUNITY` | `GENERAL` |
|---|---|---|---|
| `semantic_weight` | `0.50` | `0.45` | `0.50` |
| `lexical_weight` | `0.20` | `0.15` | `0.25` |
| `topic_weight` | `0.20` | `0.20` | `0.25` |
| `type_weight` | `0.00` | `0.10` | `0.00` |
| `freshness_weight` | `0.10` | `0.00` | `0.00` |
| `urgency_weight` | `0.00` | `0.10` | `0.00` |

---

## 5. Result Model

The output `RankedCandidate` model preserves full feature attribution for subsequent explanation rendering (Phase 2.4F):

```python
@dataclass(frozen=True)
class RankedCandidate:
    entity_id: uuid.UUID
    entity_type: str
    rank: int
    final_score: float
    semantic_score: float
    lexical_score: float
    topic_score: float
    type_score: float
    freshness_score: float
    urgency_score: float
    retrieval_sources: list[str] = field(default_factory=list)
    shared_topic_ids: list[uuid.UUID] = field(default_factory=list)
    shared_topic_names: list[str] = field(default_factory=list)
    candidate: Any | None = None
```

---

## 6. Deterministic Tie-Breaking

To guarantee reproducibility across identical inputs, sorting uses a 7-tier hierarchical key:

1. `final_score` (Descending)
2. `semantic_score` (Descending)
3. `topic_score` (Descending)
4. `lexical_score` (Descending)
5. `type_score` (Descending)
6. `freshness_score` (Descending)
7. `urgency_score` (Descending)
8. `str(entity_id)` (Ascending — stable UUID tie-breaker)

---

## 7. Missing-Data Behavior

| Scenario | Handled Behavior | Result Score |
|---|---|---|
| Missing embedding | Graceful degradation | $S_{\text{sem}} = 0.0$ |
| Missing full-text score | Graceful degradation | $S_{\text{lex}} = 0.0$ |
| Missing topic assignments | Graceful degradation | $S_{\text{top}} = 0.0$ |
| Missing publication date/year | Graceful degradation | $S_{\text{fresh}} = 0.0$ |
| Missing submission deadline | Graceful degradation | $S_{\text{urg}} = 0.0$ |
| Expired submission deadline | Marked inactive/past | $S_{\text{urg}} = 0.0$ |
| `NaN` / `Inf` input value | Validation error / rejection | Raises `ValueError` |

---

## 8. Performance & Complexity

- **In-Memory Operation**: The ranker operates on pre-fetched candidate pools ($K \le 100$) in $O(K \log K)$ time, avoiding additional database round-trips.
- **Lazy Feature Computation**: Freshness and urgency calculations use fast arithmetic ($O(1)$) and avoid redundant date parsing.
- **Zero Schema Overhead**: Requires no database schema migrations.
