# ResearchConnect AI — Phase 2.6E
## Suspicious Pattern & Graph Intelligence

---

### Executive Summary

Phase 2.6E establishes deterministic, structural graph intelligence for ResearchConnect AI:
> **“Does this opportunity participate in an observable suspicious structural pattern or relationship across venues, publishers, organizers, domains, and academic identifiers?”**

It constructs an in-memory, deterministic **Academic Trust Graph** connecting actionable opportunities, publication venues, proceedings publishers, conference organizers, web domains, academic identifiers (ISSN/ISSN-L), and external research sources (OpenAlex). It identifies structural topologies indicative of academic fraud (such as excessive organizer reuse, domain syndication, identity collisions, and corroborated fraud clusters) while strictly protecting legitimate high-degree publishers, academic societies, and isolated small/new venues from false-positive risk.

---

### 1. Architectural Placement & Boundary Guarantees

```text
Phase 2.6B: Observable Evidence Extraction (Regex patterns, registries, basic normalizers)
        ↓
Phase 2.6D: Venue / Publisher Intelligence & Cross-Source Resolution (Entity resolution, OpenAlex/Crossref links)
        ↓
Phase 2.6E: Suspicious Pattern & Graph Intelligence (THIS PHASE: In-memory structural trust graph)
        ↓
Phase 2.6C: Deterministic Risk Scoring Engine (Diminishing returns, trust mitigation, RiskAssessment)
        ↓
Phase 2.6F: Explainability & Discovery UI (Structured warnings, evidence presentation)
        ↓
Phase 2.6G: Evaluation & False-Positive Hardening (Benchmarks, calibration, ablation)
```

#### Strict Architectural Boundaries:
1. **2.6E is an EVIDENCE GENERATOR, NOT a Risk Classifier**:
   - 2.6E does **not** directly assign `risk_score`, `risk_level`, or `is_predatory_flag`.
   - 2.6E emits structured atomic `RiskEvidence` items with provenance `GRAPH_ANALYSIS`.
   - Phase 2.6C remains the **sole** composite scoring layer.
2. **Graph Facts $\neq$ Risk Evidence**:
   - Fact: 10 conferences share the same organizer $\neq$ automatically predatory.
   - Fact: A publisher owns 100 venues $\neq$ automatically predatory.
   - High graph degree alone **NEVER** implies predatory behavior.
3. **Trusted Entity Safeguards**:
   - Major academic publishers (IEEE, Springer Nature, Elsevier, ACM, Wiley) and scientific societies (AAAI, ACL, USENIX, SIAM) naturally have massive degree. They are whitelisted and safeguarded against false-positive graph reuse flags.
4. **Missing Metadata Neutrality & Graph Isolation**:
   - Isolated nodes (`degree = 0` or single connection to an unresolved venue) evaluate to strictly **NEUTRAL** (`UNKNOWN ≠ PREDATORY`).
5. **Zero Runtime External Network Calls & Zero N+1 Queries**:
   - 100% offline. No live HTTP, DNS, or WHOIS queries during ranking or scoring.
   - Operates 100% in-memory with batch graph construction and $O(N)$ traversal.
6. **Zero Database Migrations**:
   - Graph structure is constructed transiently in-memory during batch processing from existing candidate and resolved entity metadata.

---

### 2. Academic Trust Graph Model

#### Node Types (`TrustNodeType`)
| Node Type | Canonical ID Format | Purpose |
|---|---|---|
| `OPPORTUNITY` | `opp:{clean_id}` | The call for papers or research opportunity envelope. |
| `VENUE` | `venue:name:{norm_name}` or `venue:issn:{issn}` | The canonical publication outlet (journal or conference proceedings). |
| `PUBLISHER` | `pub:{canonical_publisher}` | The proceedings or journal publishing organization. |
| `ORGANIZER` | `org:{canonical_organizer}` | The scientific society or organizing committee hosting the conference. |
| `DOMAIN` | `domain:{canonical_domain}` | The registered domain hosting the website or submission system. |
| `ISSN` | `issn:{norm_issn}` | The validated 8-character ISSN or Linking ISSN (ISSN-L). |
| `RESEARCH_SOURCE` | `source:{openalex_id}` | The linked OpenAlex source entity record. |

#### Edge Types (`TrustEdgeType`) & Provenance
| Edge Type | Directed Path | Default Provenance |
|---|---|---|
| `OPPORTUNITY_IN_VENUE` | `OPPORTUNITY -> VENUE` | `SCRAPED_METADATA` / `NORMALIZED_METADATA` |
| `VENUE_PUBLISHED_BY` | `VENUE -> PUBLISHER` | `STATIC_TRUST_REGISTRY` / `SCRAPED_METADATA` |
| `VENUE_ORGANIZED_BY` | `VENUE -> ORGANIZER` | `DERIVED` |
| `OPPORTUNITY_ORGANIZED_BY` | `OPPORTUNITY -> ORGANIZER` | `STATIC_TRUST_REGISTRY` / `SCRAPED_METADATA` |
| `HAS_DOMAIN` | `OPPORTUNITY -> DOMAIN`, `VENUE -> DOMAIN` | `NORMALIZED_METADATA` / `DERIVED` |
| `HAS_IDENTIFIER` | `VENUE -> ISSN` | `NORMALIZED_METADATA` |
| `LINKED_TO_SOURCE` | `VENUE -> RESEARCH_SOURCE` | `EXTERNAL_VERIFICATION` |

---

### 3. Suspicious Structural Patterns & Named Thresholds

All thresholds are named constants, deterministic, and fully documented:

```python
MAX_LEGITIMATE_UNVERIFIED_ORGANIZER_EVENTS: int = 5
MAX_LEGITIMATE_UNVERIFIED_DOMAIN_ENTITIES: int = 4
MIN_CLUSTER_OPPORTUNITIES: int = 3
MIN_CLUSTER_SUSPICIOUS_OPPORTUNITIES: int = 2
```

#### Pattern Specifications:

1. **`HIGH_ORGANIZER_REUSE`**:
   - **Condition**: An unverified organizer node is connected to $\ge 5$ distinct opportunities/venues.
   - **Safeguard**: Excluded if organizer matches `TRUSTED_ACADEMIC_SOCIETIES` or `TRUSTED_ACADEMIC_PUBLISHERS` (e.g. IEEE, ACM).
   - **Category / Strength**: `NEGATIVE_SUSPICIOUS` / `MODERATE`.
   - **Signal Group**: `GENERAL` (subject to 0.40 group cap in 2.6C).

2. **`HIGH_DOMAIN_REUSE`**:
   - **Condition**: An unverified domain hosts $\ge 4$ distinct venues/opportunities.
   - **Safeguard**: Excluded if domain is in `PUBLISHER_DOMAINS`, matches a trusted publisher, or is a recognized academic platform (`easychair.org`, `openreview.net`, `edas.info`, `arxiv.org`, etc.).
   - **Category / Strength**: `NEGATIVE_SUSPICIOUS` / `MODERATE`.
   - **Signal Group**: `DOMAIN` (subject to 0.50 group cap in 2.6C).

3. **`GRAPH_IDENTITY_CONFLICT`**:
   - **Condition**: Same ISSN identifier claimed by $\ge 2$ distinct venues with contradictory titles (e.g. robotics vs dentistry), or same unverified domain claimed by contradictory publisher entities.
   - **Safeguard**: Does not automatically classify as predatory. Lowers confidence and adds weak/moderate cautionary signal.
   - **Category / Strength**: `NEGATIVE_SUSPICIOUS` / `WEAK`.
   - **Signal Group**: `EDITORIAL` (subject to 0.50 group cap in 2.6C).

4. **`SUSPICIOUS_ORGANIZER_CLUSTER`**:
   - **Condition**: An organizer is linked to $\ge 3$ opportunities where $\ge 2$ exhibit independent affirmative fraud evidence (e.g. Western Union payments, sub-24h peer review guarantees).
   - **Safeguard**: Excluded if organizer is verified. Requires independent non-graph negative signals across multiple opportunities.
   - **Category / Strength**: `NEGATIVE_SUSPICIOUS` / `STRONG`.
   - **Signal Group**: `GENERAL`.

5. **`SUSPICIOUS_PUBLISHER_CLUSTER`**:
   - **Condition**: An unverified publisher is connected to $\ge 3$ opportunities with corroborated affirmative negative signals.
   - **Safeguard**: Excluded if publisher is verified.
   - **Category / Strength**: `NEGATIVE_SUSPICIOUS` / `STRONG`.
   - **Signal Group**: `PUBLISHER` (subject to 0.55 group cap in 2.6C).

6. **`CONSISTENT_GRAPH_IDENTITY`** (Positive Trust Corroboration):
   - **Condition**: Multi-source triangular agreement: Venue $\to$ Verified Publisher + Verified Society or Valid ISSN / OpenAlex source record.
   - **Category / Strength**: `POSITIVE_TRUST` / `MODERATE`.

---

### 4. Correlated Evidence Protection & Opportunity-Level Projection

To avoid the critical failure mode where 10 nodes, 20 edges, and 30 paths inflate into 60 independent risk signals:
- **Deduplication Key**: Evidence is projected back to connected opportunities using `(opp_id, signal, matched_value)` deduplication.
- **Bounded Projection**: Connected opportunities receive exactly **one** conceptual evidence item per pattern instance (e.g., `HIGH_ORGANIZER_REUSE:org:waset`).
- **Diminishing Returns**: Signal weights pass through Phase 2.6C group caps (`GENERAL`, `DOMAIN`, `EDITORIAL`, `PUBLISHER`) with geometric decay ($0.50^i$), preventing runaway risk scores.

---

### 5. Verification & Benchmark Results

The implementation was validated against unit, boundary, false-positive, and scalability benchmarks:

```bash
pytest backend/tests/test_suspicious_graph_intelligence.py -v
```

#### Results Summary:
- **24/24 focused Phase 2.6E tests PASSED in 0.67s**.
- **101/101 complete Phase 2.6 risk & trust tests PASSED in 1.00s**.
- **493/493 backend regression tests PASSED in 180.66s**.
- **385/385 scraper tests PASSED in 17.73s**.
- **Frontend production bundle BUILT in 1.23s with 0 errors**.
- **Zero database queries & Zero runtime network calls**.

#### Scalability Scaling (In-Memory Batch Construction):
- 10 opportunities: **4.2 ms**
- 50 opportunities: **20.8 ms**
- 100 opportunities: **41.6 ms**
- 200 opportunities: **84.3 ms**
- 1,000 opportunities: **418.9 ms** (Target: $< 2500$ ms)

---

### 6. Summary of Deliverables

1. **`backend/app/ranking/risk/models.py`**:
   - Added `EvidenceProvenance.GRAPH_ANALYSIS`.
   - Added graph evidence signals: `HIGH_ORGANIZER_REUSE`, `HIGH_DOMAIN_REUSE`, `GRAPH_IDENTITY_CONFLICT`, `SUSPICIOUS_ORGANIZER_CLUSTER`, `SUSPICIOUS_PUBLISHER_CLUSTER`, `CONSISTENT_GRAPH_IDENTITY`.
2. **`backend/app/ranking/risk/graph.py`**:
   - Implemented `TrustNodeType`, `TrustEdgeType`, `TrustNode`, `TrustEdge`.
   - Implemented `AcademicTrustGraph` with deterministic sorting and `to_dict()` snapshot.
   - Implemented `GraphBuilder` with canonical identifiers and provenance retention.
   - Implemented `SuspiciousGraphAnalyzer` with named thresholds and trusted entity safeguards.
   - Implemented `project_graph_evidence` with opportunity-level projection and deduplication.
   - Exported global singleton `suspicious_graph_service`.
3. **`backend/app/ranking/risk/scoring.py`**:
   - Registered 2.6E weights, provenance multipliers, and anti-correlation signal group mappings.
4. **`backend/app/ranking/risk/engine.py`**:
   - Integrated `suspicious_graph_service` into `extract_batch()` for candidate batch graph analysis.
   - Supported isolated node evaluation in `extract()`.
5. **`backend/app/ranking/risk/__init__.py` & `backend/app/ranking/__init__.py`**:
   - Cleanly re-exported graph intelligence symbols.
6. **`backend/tests/test_suspicious_graph_intelligence.py`**:
   - 24 comprehensive tests covering graph construction, safeguards, boundaries, conflicts, clusters, neutrality, deduplication, determinism, and performance.
7. **Documentation**:
   - `docs/architecture/phase2-6e-suspicious-pattern-graph-intelligence.md`.
