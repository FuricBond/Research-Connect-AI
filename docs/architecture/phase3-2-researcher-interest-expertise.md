# Phase 3.2 — Researcher Interest & Expertise Intelligence Architecture

## 1. Executive Summary

**Phase 3.2: Researcher Interest & Expertise Intelligence** transforms the canonical researcher identity and profile established in Phase 3.1 into a **structured, explainable representation of what a researcher works on and has expertise in**.

By synthesizing canonical authorship graphs (`ResearchWorkAuthorModel` $\rightarrow$ `ResearchWorkModel`), hierarchical academic taxonomies (`ResearchWorkTopicModel` $\rightarrow$ `TopicModel`), publication recency signals, citation metrics, and explicit profile keywords, Phase 3.2 establishes the foundational academic intelligence required by future Phase 3 subsystems **without implementing personalization, recommendation learning, or personalized ranking**.

---

## 2. Strict Phase Boundaries & Architectural Invariants

Phase 3.2 adheres strictly to the following system boundaries:

| Boundary Dimension | Phase 3.2 Mandate | Verification Mechanism |
| :--- | :--- | :--- |
| **Personalization** | **NOT IMPLEMENTED**. Does not personalize recommendations, candidate pools, or feeds. | Zero modifications to `HybridRanker` or recommendation endpoints. |
| **User Preferences** | **NOT IMPLEMENTED**. Academic interest $\neq$ user opportunity preference. | No preference models, weights, or user feedback loops. |
| **Phase 2 Independence** | Phase 2 ranking, risk intelligence (Phase 2.6), and deadline intelligence (Phase 2.7) operate 100% independently. | Regression test suites (`test_phase2_5g`, `test_phase2_6g`, `test_phase2_7g`) pass unmodified. |
| **LLM Dependency** | **ZERO LLM DEPENDENCY**. All scoring, confidence, classification, and provenance are deterministic and computed in-memory. | Pure mathematical formulas and rule-based provenance. |
| **Performance** | **ZERO N+1 QUERIES**. All works, authorships, and topics are batch-loaded via eager joins. | Constant query budget verified in automated test suite. |

---

## 3. Data Flow & Conceptual Architecture

```text
Canonical Researcher Profile (Phase 3.1)
          │
          ├── Profile Keywords (declared)
          ├── Department & Academic Status
          └── Canonical Researcher Link (ResearcherModel)
                    │
                    ▼
          Authored Research Works (ResearchWorkAuthorModel -> ResearchWorkModel)
                    │
                    ├── Publication Year & Dates (Recency Signal)
                    ├── Citation Metrics & Author Positions (Authority Signal)
                    └── Canonical Topics (ResearchWorkTopicModel -> TopicModel)
                              │
                              ▼ (Fallback for untagged works: KeywordExtractor & TopicNormalizer)
                    Topic Evidence Aggregation (zero N+1 batch loading)
                              │
                              ▼
                    Deterministic Intelligence Engine
                              ├── Recency Score [0.15, 1.0]
                              ├── Topic Strength [0.0, 1.0]
                              ├── Topic Confidence [0.0, 1.0]
                              ├── Expertise Classification (PRIMARY, SECONDARY, EMERGING, WEAK, INSUFFICIENT)
                              └── Deterministic Provenance & Supporting Works
                              │
                              ▼
                    Materialized Store (researcher_interests) & API / UI
```

---

## 4. Reused Canonical Entities

Phase 3.2 creates no duplicate researcher, work, topic, or embedding infrastructure:

1. **`ResearchProfileModel` (`research_profiles`)**: Platform user profile providing `canonical_researcher_id` and declared `keywords`.
2. **`ResearcherModel` (`researchers`)**: Academic author identity from OpenAlex/Crossref with citation metrics.
3. **`ResearchWorkModel` (`research_works`)**: Scholarly publications with titles, abstracts, publication years, DOIs, and citations.
4. **`ResearchWorkAuthorModel` (`research_work_authors`)**: Many-to-many junction linking authors to publications with author position and corresponding author flags.
5. **`ResearchWorkTopicModel` (`research_work_topics`)**: Junction linking works to canonical topics with assignment confidences.
6. **`TopicModel` (`topics`) & `TopicAliasModel` (`topic_aliases`)**: Canonical hierarchical taxonomy nodes.
7. **`KeywordExtractor` & `TopicNormalizer` (`ml.topic_analysis`)**: Deterministic fallbacks for works without explicit database topic associations.

---

## 5. Mathematical & Scoring Models

### 5.1 Recency Modeling ($R \in [0.15, 1.0]$)

Research activity shifts over time, but older foundational expertise must never be completely erased:

$$\Delta = \max(0, Y_{\text{ref}} - Y_{\max})$$

Where $Y_{\text{ref}} = 2026$ and $Y_{\max}$ is the most recent publication year for topic $T$:

$$R = \begin{cases}
1.00 & \text{if } \Delta \le 1 \\
1.00 - 0.10 \cdot (\Delta - 1) & \text{if } 2 \le \Delta \le 5 \\
\max(0.15, 0.60 \cdot 0.92^{\Delta - 5}) & \text{if } \Delta > 5 \\
0.50 & \text{if publication year is missing}
\end{cases}$$

- **Recent Work**: 2025/2026 publications achieve peak recency $1.00$.
- **Older Sustained Work**: Work from 2000 decays toward the strict floor of $0.15$, preserving long-term scholarly authority.

### 5.2 Topic Strength ($S \in [0.0, 1.0]$)

Topic strength measures the volume, corpus coverage, leadership, and declared relevance of a topic:

$$S = 0.40 \cdot S_{\text{vol}} + 0.25 \cdot S_{\text{cov}} + 0.15 \cdot S_{\text{auth}} + 0.10 \cdot R + 0.10 \cdot S_{\text{prof}}$$

Where:
- **Volume & Depth**: $S_{\text{vol}} = \min\left(1.0, \frac{\ln(1 + \text{work\_count})}{\ln(1 + 15)}\right)$ (diminishing returns, saturated at 15 works).
- **Corpus Coverage**: $S_{\text{cov}} = \frac{\text{work\_count}}{\max(1, \text{total\_works})}$.
- **Scholarly Authority**: $S_{\text{auth}} = 0.6 \cdot S_{\text{lead}} + 0.4 \cdot \min\left(1.0, \frac{\ln(1 + \text{citations})}{\ln(1 + 100)}\right)$.
  - $S_{\text{lead}} = 0.5 \cdot \frac{\text{lead\_works}}{\text{work\_count}} + 0.5 \cdot \frac{\text{primary\_works}}{\text{work\_count}}$.
- **Profile Declaration**: $S_{\text{prof}} = 1.0$ if present in profile `keywords`, else $0.0$.
- **Zero-Work Profiles**: For new researchers with profile keywords only, $S = 0.50$.

### 5.3 Topic Confidence ($C \in [0.0, 1.0]$)

Confidence reflects certainty based on extraction reliability, evidence volume, metadata completeness, and multi-source diversity:

$$C = 0.40 \cdot C_{\text{extract}} + 0.30 \cdot C_{\text{qty}} + 0.20 \cdot C_{\text{meta}} + 0.10 \cdot C_{\text{div}}$$

Where:
- $C_{\text{extract}}$ = Mean taxonomy assignment confidence score across supporting works.
- $C_{\text{qty}} = \min(1.0, \text{work\_count} / 5.0)$.
- $C_{\text{meta}} = \frac{\text{abstracts} + \text{dois} + \text{years}}{3 \cdot \text{work\_count}}$ (metadata richness).
- $C_{\text{div}} = 0.15$ if verified across publications AND declared profile keywords.

### 5.4 Expertise Classification Tiers

Deterministic tiering partitions topics into distinct scholarly tiers:

1. **`PRIMARY_EXPERTISE`**:
   - $\text{work\_count} \ge 3$, $S \ge 0.65$, $C \ge 0.60$.
   - Sustained track record: $\text{span\_years} \ge 2$, or $\text{work\_count} \ge 5$, or $S_{\text{cov}} \ge 0.35$.
2. **`SECONDARY_EXPERTISE`**:
   - $\text{work\_count} \ge 2$, $S \ge 0.40$, $C \ge 0.45$ (and not primary).
3. **`EMERGING_INTEREST`**:
   - $R \ge 0.75$ (work within last 2–3 years), $\text{work\_count} \ge 1$ (and not primary).
4. **`WEAK_INTEREST`**:
   - $S \ge 0.20$ (incidental publication or profile declared interest).
5. **`INSUFFICIENT_EVIDENCE`**:
   - $C < 0.35$ or $S < 0.20$ (sparse, unverified noise).

### 5.5 Deterministic Tie-Breaking

All interests are ordered strictly by:
$$\text{strength DESC} \rightarrow \text{confidence DESC} \rightarrow \text{evidence\_count DESC} \rightarrow \text{topic\_name ASC}$$

---

## 6. Database Schema & Migration

### 6.1 `researcher_interests` Table

```sql
CREATE TABLE researcher_interests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id UUID REFERENCES research_profiles(id) ON DELETE CASCADE,
    canonical_researcher_id UUID REFERENCES researchers(id) ON DELETE SET NULL,
    topic_id UUID REFERENCES topics(id) ON DELETE SET NULL,
    topic_name VARCHAR(150) NOT NULL,
    topic_slug VARCHAR(150) NOT NULL,
    topic_category VARCHAR(50),
    strength FLOAT NOT NULL DEFAULT 0.0,
    confidence FLOAT NOT NULL DEFAULT 0.0,
    evidence_count INTEGER NOT NULL DEFAULT 1,
    recency_score FLOAT NOT NULL DEFAULT 0.0,
    classification VARCHAR(50) NOT NULL DEFAULT 'WEAK_INTEREST',
    is_primary_expertise BOOLEAN NOT NULL DEFAULT FALSE,
    first_observed_year INTEGER,
    last_observed_year INTEGER,
    source VARCHAR(100) NOT NULL DEFAULT 'SCHOLARLY_WORKS',
    provenance JSONB,
    supporting_work_ids JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_researcher_interests_profile_topic_name UNIQUE (profile_id, topic_name)
);
```

Migration: `backend/alembic/versions/0009_phase3_2_researcher_interest_expertise.py`.

---

## 7. REST API Endpoints

Mounted under `/api/v1/researchers` (and `/api/researchers`):

| Method | Endpoint | Response Schema | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/{researcher_id}/research-intelligence` | `ResearcherIntelligenceResponse` | Complete intelligence report with interests, expertise, emerging topics, summary metrics, and provenance. Supports `?refresh=true`. |
| `GET` | `/{researcher_id}/interests` | `list[ResearcherInterestItemSchema]` | All inferred interests ordered by strength. |
| `GET` | `/{researcher_id}/expertise` | `list[ResearcherInterestItemSchema]` | Confirmed primary and secondary expertise areas. |

---

## 8. Frontend Next.js App Router Integration

Implemented in `frontend/app/researcher/page.tsx` using `ResearcherIntelligenceView`:

- **Strict Boundary Banner**: Explicitly communicates that intelligence is inferred from scholarly activity and is completely separate from profile declarations.
- **Summary Metrics Strip**: Total topics analyzed, primary expertise count, emerging interests count, analyzed publications count, active scholarly years span.
- **Interactive Tabs**: Filter between "All Topics", "Primary Expertise", "Emerging Interests", and "Secondary".
- **Structured Cards**:
  - Color-coded classification pills.
  - Visual strength progress bar (0–100%).
  - Confidence meter badge.
  - Recency pill with year range.
  - Collapsible "Why this area?" provenance drawer detailing evidence reasons and supporting publications with DOI links.
- **One-Click Refresh**: Recomputes intelligence with instant UI feedback.

---

## 9. Performance & Complexity Verification

- **Batch Loading**: Eager joins on `ResearchWorkAuthorModel` $\rightarrow$ `ResearchWorkModel` $\rightarrow$ `topic_associations` $\rightarrow$ `TopicModel`.
- **Query Complexity**: Constant $O(1)$ queries regardless of publication volume (verified in test suite comparing 15 works vs 30 works).
- **Execution Budget**: Deterministic in-memory aggregation executes in $< 5\text{ms}$ for 100+ works.

---

## 10. Future Phase 3 Dependencies

Phase 3.2 provides the canonical intelligence required by downstream phases:
- **Phase 3.3 (Preference Intelligence)**: Compares inferred scholarly interests against explicit researcher preferences (e.g. "I have expertise in Machine Learning, but prefer CFPs in Computational Biology").
- **Phase 3.4 (Candidate Generation)**: Uses high-strength interest topics for semantic candidate expansion.
- **Phase 3.5 (Personalized Ranking)**: Incorporates expertise alignment features into the ranking pipeline.
