# Phase 2.4F — Explainable Results

## 1. Purpose

Phase 2.4F implements a deterministic, structured **Explainability Layer** for the ResearchConnect AI discovery engine.

It bridges the gap between raw statistical matching scores and transparent academic decision-making by answering:

> *"Why did this research work or opportunity receive this ranking, what signals drove the match, and what limitations exist?"*

The system provides:
1. **Machine-Readable Structured Evidence**: Normalized signal attributions, weighted contribution values ($w_i \cdot S_i$), primary factor tags, topic overlap descriptors, and retrieval channel provenance.
2. **Human-Readable Natural Language Explanations**: Concise summaries, positive reasons (strengths), and limiting factors (weaknesses) generated deterministically without an LLM.

---

## 2. Architecture & Pipeline

```text
       Ranked Candidate (RankedCandidate, SimilarResearchResult, ResearchOpportunityMatch)
                                       │
                                       ▼
                       ┌───────────────────────────────┐
                       │        ResultExplainer        │
                       │                               │
                       │ 1. Signal Extraction          │
                       │    (Extract & validate        │
                       │     raw scores & metadata)    │
                       │                               │
                       │ 2. Active Weight Resolution   │
                       │    (Mode-aware weights)       │
                       │                               │
                       │ 3. Score Contribution         │
                       │    (contrib = score * weight) │
                       │                               │
                       │ 4. Threshold & Tier Mapping   │
                       │    (Very Strong / Moderate /  │
                       │     Weak / Not Available)     │
                       │                               │
                       │ 5. Strengths & Limitations    │
                       │    (Deterministic narratives) │
                       │                               │
                       │ 6. Topic & Provenance Evidence│
                       │                               │
                       │ 7. Summary Synthesis          │
                       └───────────────┬───────────────┘
                                       │
                                       ▼
                              ResultExplanation
                                       │
                                       ▼
                                ExplainedResult
```

---

## 3. Supported Explanation Signals

| Signal Name | Mathematical Basis | Human-Readable Assessment |
|---|---|---|
| `semantic_similarity` | 384-dimensional dense cosine similarity | Conceptual alignment in latent representation space. |
| `lexical_relevance` | PostgreSQL full-text search score (`ts_rank_cd`) | Direct keyword overlap in titles, abstracts, and descriptions. |
| `topic_compatibility` | Canonical taxonomy DAG overlap & ancestor proximity | Domain topical alignment across shared research fields. |
| `type_compatibility` | Academic publication category compatibility matrix | Compatibility between research type (e.g. `article`) and venue category (`JOURNAL`). |
| `publication_freshness` | Half-life exponential recency decay ($t_{1/2} = 5.0$y) | Contemporary vs historical publication age. |
| `deadline_urgency` | Linear proximity within active window (90 days) | Immediacy of approaching opportunity submission deadlines. |
| `retrieval_sources` | Channel provenance (`semantic`, `lexical`, `topic`) | Verification of independent multi-channel surfacing. |

---

## 4. Threshold Strategy & Verbal Tiers

Qualitative labels and natural-language triggers are governed by configurable thresholds in [`backend/app/core/config.py`](file:///d:/Project/researchconnect-ai/backend/app/core/config.py):

| Threshold Setting | Default | Verbal Tier | Behavior |
|---|---|---|---|
| `explainability_high_threshold` | `0.75` | **"Very Strong"** | Triggers primary strength claims (e.g. *"Strong semantic similarity reflecting deep conceptual alignment"*). |
| `explainability_positive_threshold` | `0.50` | **"Moderate"** | Triggers moderate positive evidence (e.g. *"Moderate topical overlap in shared fields"*). |
| `explainability_weak_threshold` | `0.25` | **"Low"** / **"Minimal"** | Triggers limitation statements if signal was available and weighted. |
| `is_available = False` | N/A | **"Not Available"** | Suppresses false negative claims (e.g., does not claim "old publication" if publication date was unavailable). |

---

## 5. Result Model

```python
@dataclass(frozen=True)
class SignalContribution:
    signal_name: str
    score: float
    weight: float
    contribution: float
    qualitative_assessment: str
    is_available: bool = True
    is_primary_driver: bool = False

@dataclass(frozen=True)
class ResultExplanation:
    summary: str
    strengths: list[str]
    limitations: list[str]
    signal_contributions: dict[str, SignalContribution]
    topic_evidence: TopicEvidence
    provenance_evidence: ProvenanceEvidence
    primary_factors: list[str]
    final_score: float
    rank: int
```

---

## 6. Example Explanations

### A. Academic Opportunity Match
```json
{
  "summary": "Ranked as a relevant academic opportunity driven primarily by semantic similarity and type compatibility.",
  "strengths": [
    "Strong semantic similarity reflecting deep conceptual and contextual alignment.",
    "Strong topical alignment in shared fields (Information Systems, Artificial Intelligence).",
    "Publication type is highly compatible with this opportunity category.",
    "Upcoming submission deadline due in the immediate term.",
    "Independently surfaced by both semantic vector search and full-text keyword matching."
  ],
  "limitations": [],
  "primary_factors": ["semantic_similarity", "type_compatibility"],
  "final_score": 0.842,
  "rank": 1
}
```

### B. Similar Research Work with Limiting Factors
```json
{
  "summary": "Ranked as a relevant similar research work driven primarily by semantic similarity and lexical relevance.",
  "strengths": [
    "Strong semantic similarity reflecting deep conceptual and contextual alignment.",
    "Substantial keyword and terminology overlap in title and textual metadata."
  ],
  "limitations": [
    "Minimal canonical topic overlap.",
    "Older publication with lower recency weight."
  ],
  "primary_factors": ["semantic_similarity", "lexical_relevance"],
  "final_score": 0.625,
  "rank": 4
}
```

---

## 7. Deterministic Guarantees & Zero-LLM Architecture

- **100% Deterministic**: Identical candidate inputs always produce identical summaries, reasons, and contributions.
- **Zero Latency / Offline**: Operates in sub-millisecond CPU time without external API calls or LLM prompts.
- **Zero Hallucination**: All reasons and evidence are strictly bound to computed numbers and verified database metadata.

---

## 8. Limitations & Roadmap

- Does not incorporate personalized researcher preferences or past submission histories (reserved for Phase 3).
- Does not expose HTTP endpoints (reserved for **Phase 2.4G — FastAPI Discovery Layer**).
