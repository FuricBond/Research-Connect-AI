# ResearchConnect AI — Phase 2.6D
## Venue / Publisher Intelligence & Cross-Source Resolution

---

### Executive Summary

Phase 2.6D establishes deterministic academic entity resolution for ResearchConnect AI:
> **"What real academic entity does this opportunity belong to, and what trustworthy information can we establish about that entity from the data sources already available to the system?"**

It links opportunities to canonical publication venues, separates conference organizers from proceedings publishers, validates academic identifiers (ISSN, ISSN-L, DOI prefixes), normalizes web domains, enriches candidate venues using pre-ingested OpenAlex and Crossref records, and produces structured, provenance-backed evidence for the Phase 2.6C deterministic scoring engine.

---

### 1. Architectural Placement & Boundary Guarantees

```text
Phase 2.6B: Observable Evidence Extraction (Regex patterns, registries, basic normalizers)
        ↓
Phase 2.6D: Venue / Publisher Intelligence & Cross-Source Resolution (THIS PHASE)
        ↓
Phase 2.6C: Deterministic Risk Scoring Engine (Diminishing returns, trust mitigation, RiskAssessment)
        ↓
Phase 2.6E: Suspicious Pattern & Graph Signals (Network topology, community detection, co-occurrence)
        ↓
Phase 2.6F: Explainability & Discovery UI (Structured warnings, evidence presentation)
        ↓
Phase 2.6G: Evaluation & False-Positive Hardening (Benchmarks, calibration, ablation)
```

#### Strict Architectural Boundaries:
1. **2.6D is NOT a risk scoring engine**: 2.6D resolves entity identities and emits atomic `RiskEvidence` items. Phase 2.6C remains the **sole** composite scoring layer.
2. **2.6D is NOT a graph risk system**: Graph community detection, co-occurrence networks, and relationship anomaly scoring are deferred to **Phase 2.6E**.
3. **Zero runtime external network calls**: 100% offline. No live HTTP/DNS queries to OpenAlex, Crossref, DOAJ, or WHOIS during ranking or scoring.
4. **Zero N+1 database queries**: Batch resolution operates in-memory using pre-fetched source records dictionaries (`resolve_batch(opportunities, source_records)`).
5. **Entity resolution confidence ≠ Risk confidence**:
   - `resolution_confidence` measures certainty of the academic entity's identity.
   - `risk_confidence` measures the sufficiency and provenance of risk evidence.
   - High resolution confidence does NOT imply low risk (e.g. an opportunity falsely claiming a famous IEEE venue while soliciting Western Union payments).
   - Low resolution confidence does NOT imply high risk (e.g. a small regional university workshop with no ISSN).
6. **Trusted entity ≠ Guaranteed safe opportunity**: A recognized publisher or venue reduces risk via trust mitigation, but cannot completely erase affirmative fraud signals.

---

### 2. Entity Resolution Strategy & Identifier Priority

To prevent speculative string matching and dangerous entity collisions, identity resolution follows a strict deterministic hierarchy:

```text
1. Strong Identifiers: Canonical Linking ISSN (issn_l) or validated standard ISSN (issn)
        ↓
2. Secondary Identifiers: Standard DOI prefix (10.XXXX) or OpenAlex Source ID (S...)
        ↓
3. Tertiary Identifiers: Canonical Venue Key (issn:XXXX-XXXX or name:canonical_title)
        ↓
4. Quaternary: Exact normalized publisher / society registry match
        ↓
5. Contextual Alignment: Domain-to-publisher alignment (nature.com -> Springer Nature)
```

#### Identifier Normalization & Validation
- **ISSN**: Strict validation via `_ISSN_STRICT_RE` supporting formats `XXXX-XXXX`, `XXXXXXXX`, and `ISSN: XXXX-XXXX` with uppercase check digit `X`.
- **ISSN-L (Linking ISSN)**: Maintained as the primary identity anchor across print and electronic editions.
- **DOI Prefixes**: Standard `10.XXXX` prefixes mapped to recognized publishing bodies (e.g. `10.1109` $\to$ IEEE, `10.1145` $\to$ ACM, `10.1007` $\to$ Springer Nature, `10.1016` $\to$ Elsevier).
- **Invalid Identifiers**: Syntactically invalid ISSNs or DOIs produce zero positive trust evidence and do not crash the pipeline.

---

### 3. Publisher & Organizer Separation

A core failure mode in academic risk detection is conflating conference organizers with proceedings publishers.

- **Conference Organizer (Society)**: E.g., ACM, IEEE, AAAI, ACL, USENIX, SIAM, SPIE.
- **Proceedings Publisher**: E.g., Springer Nature (LNCS), IEEE Xplore, ACM Digital Library, Elsevier (Procedia).

#### Principles:
- Organizer and publisher are tracked as distinct attributes in `ResolvedAcademicEntity` (`organizer` vs `publisher`).
- An unverified organizer does not make an opportunity suspicious (`UNKNOWN ≠ PREDATORY`).
- A verified publisher does not automatically validate an unknown conference organizer.

---

### 4. Academic Domain Intelligence

Deterministic mapping from web hostnames and registered domains to canonical academic publishers:
- `ieee.org`, `computer.org` $\to$ **IEEE**
- `acm.org`, `dl.acm.org` $\to$ **ACM**
- `springer.com`, `link.springer.com`, `nature.com` $\to$ **Springer Nature**
- `elsevier.com`, `sciencedirect.com`, `cell.com` $\to$ **Elsevier**
- `wiley.com`, `onlinelibrary.wiley.com` $\to$ **John Wiley & Sons**
- `oup.com`, `academic.oup.com` $\to$ **Oxford University Press**
- `cambridge.org` $\to$ **Cambridge University Press**
- `tandfonline.com` $\to$ **Taylor & Francis**
- `plos.org` $\to$ **PLOS**
- `frontiersin.org` $\to$ **Frontiers Media**
- `mdpi.com` $\to$ **MDPI**

Zero live DNS/WHOIS queries are made; domain parsing operates strictly in-memory via `normalize_url`.

---

### 5. Cross-Source Integration (OpenAlex, Crossref, DOAJ)

#### OpenAlex / ResearchSource Integration
Links opportunities to existing local `ResearchSourceModel` database records via ISSN/ISSN-L or canonical key:
- Enriches venue with `openalex_id`, `works_count`, and `cited_by_count`.
- Inherits `host_organization` and `is_in_doaj`.
- Emits `OPENALEX_METADATA_MATCH` signal with provenance `EXTERNAL_VERIFICATION`.

#### Crossref Integration
Identifies verified Crossref container titles or bibliographic registration from ingestion metadata, emitting `CROSSREF_METADATA_MATCH`.

#### Mandatory DOAJ Evidence Invariant
- **`is_in_doaj == True`**: Emits `DOAJ_INDEXED` positive trust evidence (`strength = STRONG`, `confidence = HIGH`).
- **`is_in_doaj == False`**: Evaluates to strictly **NEUTRAL** (Zero negative evidence, zero risk penalty).
- **`is_in_doaj is None`**: Evaluates to strictly **NEUTRAL**.

*Rationale*: Thousands of legitimate, prestigious subscription journals, conference proceedings, and non-OA venues are not in DOAJ. Absence from DOAJ is never evidence of predatory behavior.

---

### 6. Conflict Handling & Discrepancy Detection

When independent sources disagree:
1. **Opportunity Publisher vs External Host Organization**: E.g., opportunity claims "Elsevier", but OpenAlex source records "Springer Nature".
2. **Domain Publisher Mismatch**: E.g., opportunity claims "IEEE", but website is on "sciencedirect.com" (Elsevier).
3. **ISSN Mismatch**: Opportunity ISSN does not match Linking ISSN or alternative ISSNs in the linked source record.

#### Safeguards:
- Conflicts are appended to `ResolvedAcademicEntity.conflicts`.
- `resolution_confidence` is penalized ($-0.25$ per conflict).
- Emits cautionary `CONFLICTING_METADATA` signal (`category = NEGATIVE_SUSPICIOUS`, `strength = WEAK`, `confidence = MEDIUM`).
- **Never triggers an automatic predatory classification**: Discrepancies reduce resolution confidence and warrant manual scrutiny, avoiding catastrophic false positives.

---

### 7. Resolution Status & Confidence Formula

Resolution confidence is bounded in $[0.00, 1.00]$:

$$\text{Confidence} = \min\left(1.0, \max\left(0.0, \sum w_{\text{observed}} - \sum w_{\text{conflicts}}\right)\right)$$

| Factor | Weight |
|---|---|
| Valid ISSN-L or ISSN | $+0.45$ |
| Verified Trusted Publisher | $+0.20$ |
| Domain-to-Publisher Confirmation | $+0.10$ |
| DOI Prefix Confirmation | $+0.10$ |
| Verified Scientific Society / Organizer | $+0.15$ |
| External Source Record Linked (OpenAlex / Crossref) | $+0.20$ |
| Canonical Key Match (`issn:...`) | $+0.10$ |
| Canonical Key Match (`name:...`) | $+0.05$ |
| Each Discrepancy / Conflict | $-0.25$ |

#### Resolution Categories:
- **`RESOLVED`**: $\text{Confidence} \ge 0.75$ (Strong identifier, verified publisher, corroborated sources).
- **`PARTIALLY_RESOLVED`**: $0.35 \le \text{Confidence} < 0.75$ (Recognized name or domain, but missing verified ISSN).
- **`UNRESOLVED`**: $\text{Confidence} < 0.35$ (Insufficient metadata to establish identity).

---

### 8. Evidence Deduplication

When multiple extractors or cross-source links establish the same fact:
- Canonical singular signals (e.g. `DOAJ_INDEXED`) are strictly deduplicated so that only one occurrence exists in `RiskEvidenceCollection`.
- Publisher trust evidence preserves provenance indicating external verification and static registry matching.

---

### 9. Known Limitations & Transition to Phase 2.6E

- **Static Domain & Prefix Registries**: New academic domains or recent publisher acquisitions require updates to static lookup dictionaries.
- **Pre-Ingestion Dependency**: Resolution against OpenAlex relies on `ResearchSourceModel` records already loaded in the database; uningested venues rely on opportunity-level metadata.
- **Next Phase (2.6E)**: Phase 2.6E will construct suspicious graph signals (co-occurrence of dubious organizers, shared payment addresses, network topology) building on top of the entity boundaries established in 2.6D.
