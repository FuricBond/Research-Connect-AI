# Phase 3.4 — Personalized Candidate Generation Architecture

## 1. Executive Summary

**Phase 3.4: Personalized Candidate Generation** introduces the foundational candidate retrieval layer of the ResearchConnect AI personalization system.

It answers the core question:
> **"Which opportunities should enter the personalized candidate pool for a researcher?"**

Crucially:
- **Phase 3.4 determines which opportunities enter the candidate pool.**
- **Phase 3.5 will determine how those personalized candidates should be ranked.**

```
Researcher Profile (Phase 3.1)
       │
       ▼
Researcher Interest / Expertise (Phase 3.2)
       │
       ▼
Personal Preferences (Phase 3.3)
       │
       ▼
Candidate Generation (Phase 3.4)
       │
       ├── Explicit preference candidates (Quota: 40%)
       ├── Inferred preference candidates (Quota: 15%, C >= 0.40)
       ├── Scholarly expertise candidates (Quota: 35%)
       ├── Profile keyword / target type candidates (Quota: 15%)
       └── Cold-start / discovery fallback candidates
       │
       ▼
Candidate Eligibility & Safety Verification
       │
       ├── Phase 2.7 Deadline Intelligence (Exclude EXPIRED)
       └── Phase 2.6 Trust & Risk Intelligence (Preserve Risk Signals)
       │
       ▼
Candidate Deduplication & Provenance Merging
       │
       ▼
Personalized Candidate Set (Unranked Pool with Traceable Provenance)
       │
       ▼
Phase 3.5 Personalization Ranking (Future Phase)
```

---

## 2. Strict Phase Boundaries & Invariants

1. **Candidate Generation $\neq$ Ranking**: Phase 3.4 generates an unranked candidate set with diagnostic provenance. No `personalization_score` is computed, and Phase 2 ranking weights (`HybridRanker`, `CrossEncoderReranker`, `MMRDiversifier`) remain 100% untouched.
2. **Expertise $\neq$ Preference**: Both can surface opportunities, but their candidate provenance explicitly separates `EXPLICIT_PREFERENCE` from `RESEARCH_EXPERTISE` and `RESEARCH_INTEREST`. A researcher may have expertise in a domain without actively preferring opportunities in it.
3. **Personalization $\neq$ Safety Override**: Phase 2.6 trust and risk intelligence remains authoritative. If an opportunity is predatory or high risk, personalization NEVER lowers, bypasses, or suppresses risk flags or reasons.
4. **Personalization $\neq$ Deadline Override**: Phase 2.7 deadline intelligence remains authoritative. Expired opportunities (`DeadlineTemporalStatus.EXPIRED`) are strictly ineligible and excluded from candidate pools. A researcher's preferred deadline notice does not override actual expiration.
5. **Relevance Floor Invariant**: Generic preference dimensions (e.g. `opportunity_type = CONFERENCE` or `delivery_mode = ONLINE`) cannot manufacture semantic relevance. If the researcher has specified or demonstrated topic scope, attribute matches must intersect with that scope to avoid generating unrelated opportunities.
6. **Reliable Cold-Start Handling**: For newly registered researchers with sparse or zero preferences and publications, the system smoothly falls back to general high-quality active discovery candidates without producing empty sets or failing.

---

## 3. Candidate Generation Sources & Provenance

Every generated candidate item in `PersonalizedCandidateSetResponse` retains complete provenance answering *"Why was this opportunity included?"*:

| Candidate Source | Taxonomy Key | Evidence Origin | Minimum Threshold |
| :--- | :--- | :--- | :--- |
| `EXPLICIT_PREFERENCE` | `CandidateSourceType.EXPLICIT_PREFERENCE` | Declared in Phase 3.3 (`ResearcherPreferenceModel`, source=`EXPLICIT`) | Active status = true |
| `INFERRED_PREFERENCE` | `CandidateSourceType.INFERRED_PREFERENCE` | Verified platform saves (`SavedOpportunityModel`) | Confidence $C \ge 0.40$ |
| `RESEARCH_EXPERTISE` | `CandidateSourceType.RESEARCH_EXPERTISE` | Phase 3.2 scholarly intelligence (`PRIMARY_EXPERTISE`, `SECONDARY_EXPERTISE`) | Confidence $C \ge 0.30$ |
| `RESEARCH_INTEREST` | `CandidateSourceType.RESEARCH_INTEREST` | Phase 3.2 emerging research interests (`EMERGING_INTEREST`) | Verified in topic taxonomy |
| `PROFILE_KEYWORD` | `CandidateSourceType.PROFILE_KEYWORD` | Declared in Phase 3.1 (`ResearchProfileModel.keywords`, target types) | Title/summary lexical match |
| `COLD_START_FALLBACK` | `CandidateSourceType.COLD_START_FALLBACK` | Phase 2.2 active opportunity discovery pool | Status = `ACTIVE`/`UNVERIFIED`, upcoming |

### Merged Provenance on Deduplication
When the same opportunity is surfaced by multiple sources (e.g., matching both an explicit topic preference and primary scholarly expertise):
- The opportunity appears **once** in the candidate set.
- Its `sources` array combines all discovering sources: `[EXPLICIT_PREFERENCE, RESEARCH_EXPERTISE]`.
- Its `matched_topics`, `matched_preferences`, `matched_expertise`, and `reasons` are unioned deterministically.

---

## 4. Source Allocation & Balancing Quotas

To prevent any single source (e.g. 1,000 expertise matches) from starving explicit preferences or profile constraints, deterministic allocation quotas are applied:

$$\text{Quota}_{\text{explicit}} = \max(1, \lfloor L \times 0.40 \rfloor)$$
$$\text{Quota}_{\text{expertise}} = \max(1, \lfloor L \times 0.35 \rfloor)$$
$$\text{Quota}_{\text{inferred}} = \max(1, \lfloor L \times 0.15 \rfloor)$$
$$\text{Quota}_{\text{profile}} = \max(1, \lfloor L \times 0.15 \rfloor)$$
$$\text{Quota}_{\text{fallback}} = \max(0, L - N_{\text{personalized}})$$

Where $L$ is the target candidate limit ($1 \le L \le 200$, default $50$). Unused quotas from sparse sources adaptively roll over to subsequent sources and discovery fallback.

---

## 5. Candidate Eligibility & Safety Engine

Before an opportunity enters the candidate set, it undergoes dual eligibility and safety verification:

```python
# 1. Status Filter
if opp.status not in ("ACTIVE", "UNVERIFIED"):
    continue

# 2. Phase 2.7 Deadline Intelligence Assessment
deadline_assessment = DeadlineIntelligence.assess_opportunity_model(opp, reference_time=ref_time)
if deadline_assessment.primary_assessment.status == DeadlineTemporalStatus.EXPIRED:
    continue  # Excluded: expired deadline

# 3. Phase 2.6 Trust & Risk Intelligence Assessment
risk_assessment = assess_opportunity_risk(opp)
# Risk metadata preserved and attached to candidate:
# opp_schema.risk_level = risk_assessment.risk_level.value
# opp_schema.risk_score = risk_assessment.risk_score
# opp_schema.risk_reasons = risk_assessment.risk_reasons
```

---

## 6. Service Architecture: `PersonalizedCandidateGenerationService`

Located in `backend/app/services/personalized_candidate_generation_service.py`:
- Pure $O(1)$ query count ($\le 6$ SQL statements executed in batch).
- Eager relationship pre-fetching with `selectinload(OpportunityModel.topic_associations).joinedload(OpportunityTopicModel.topic)`.
- Zero per-candidate database queries.
- Zero network calls or external LLM dependencies.
- Deterministic presentation sorting:
  1. Multi-source count descending (items satisfying both preferences and expertise appear first in exploration).
  2. Deadline days remaining ascending (upcoming deadlines prioritized; null deadlines last).
  3. Opportunity title and canonical ID alphabetical tie-breakers.

---

## 7. REST API & Authorization

### Endpoint
`GET /api/v1/researchers/{researcher_id}/personalized-candidates`

#### Query Parameters
- `limit` (int, 1-200, default 50): Desired candidate set size.
- `include_inferred` (bool, default true): Include inferred preference candidates.
- `include_expertise` (bool, default true): Include Phase 3.2 expertise candidates.
- `include_fallback` (bool, default true): Include cold-start discovery fallback candidates.

#### Authorization Header
- `X-User-ID` (UUID, optional in open mode, strictly enforced when provided):
  A researcher can only retrieve their own personalized candidate set. Cross-user access returns `403 Forbidden`.

#### Response Schema: `PersonalizedCandidateSetResponse`
```json
{
  "researcher_id": "7b79a834-8b63-4b68-bf06-538741364b66",
  "candidate_count": 28,
  "is_cold_start": false,
  "coverage": {
    "explicit_preference_count": 14,
    "inferred_preference_count": 6,
    "expertise_count": 18,
    "profile_count": 4,
    "fallback_count": 0,
    "unique_candidate_count": 28,
    "deduplication_ratio": 0.3333
  },
  "candidates": [
    {
      "candidate_id": "c1f7b762-b91c-4b69-ba79-ec0a1c6a2318",
      "opportunity": {
        "id": "2d8f99e3-e1d0-4d52-87cb-aa410c5982e0",
        "title": "International Conference on Machine Learning (ICML 2026)",
        "opportunity_type": "CONFERENCE",
        "delivery_mode": "HYBRID",
        "location": "Vienna, Austria",
        "organizer": "IMLS",
        "submission_deadline": "2026-02-01T23:59:59Z",
        "topics": ["Machine Learning", "Deep Learning"],
        "status": "ACTIVE",
        "is_predatory_flag": false,
        "risk_level": "LOW_RISK",
        "risk_score": 0.0,
        "risk_reasons": ["Standard academic characteristics with zero suspicious indicators."],
        "deadline_status": "UPCOMING",
        "days_remaining": 45.2,
        "urgency_tier": "APPROACHING",
        "deadline_explanation": "Submission deadline is 45 days away."
      },
      "provenance": {
        "candidate_id": "c1f7b762-b91c-4b69-ba79-ec0a1c6a2318",
        "opportunity_id": "2d8f99e3-e1d0-4d52-87cb-aa410c5982e0",
        "sources": ["EXPLICIT_PREFERENCE", "RESEARCH_EXPERTISE"],
        "matched_topics": ["Machine Learning"],
        "matched_preferences": ["Topic: Machine Learning", "Type: CONFERENCE"],
        "matched_expertise": ["Machine Learning (PRIMARY_EXPERTISE)"],
        "reasons": [
          "Matches explicit topic preference 'Machine Learning'",
          "Aligns with scholarly expertise in 'Machine Learning' (PRIMARY_EXPERTISE)"
        ],
        "retrieval_channels": ["explicit_topic_association", "expertise_topic_association"]
      },
      "eligibility_passed": true,
      "eligibility_reasons": [
        "Status 'ACTIVE' valid",
        "Deadline temporal status: 'UPCOMING'",
        "Risk assessed: LOW_RISK"
      ]
    }
  ],
  "metadata": {
    "requested_limit": 50,
    "safe_limit": 50,
    "phase_boundary": "Phase 3.4 Candidate Generation (Unranked Candidate Pool)"
  }
}
```

---

## 8. Next.js Frontend Integration

Implemented in `frontend/components/researcher/PersonalizedCandidatePreview.tsx` and embedded in `frontend/app/researcher/page.tsx`:
- Clearly labeled **Personalized Candidate Preview (Phase 3.4)** with strict architectural disclaimer stating results represent an unranked candidate set.
- Diagnostic source coverage indicators (total candidates, explicit, inferred, expertise, profile, fallback).
- Interactive filter controls (toggle inferred preferences, expertise, fallback, candidate limit selector).
- Full opportunity card with Phase 2.7 deadline urgency badges, Phase 2.6 risk badges, and expandable **"Why Included?"** provenance inspect panels.

---

## 9. Performance & Verification Metrics

- **Total DB Queries**: Constant $O(1) \le 6$ queries per candidate set generation.
- **N+1 Prevention**: Verified via SQLAlchemy execution hooks.
- **Regression Passes**:
  - Phase 3.1: 100% passing
  - Phase 3.2: 100% passing
  - Phase 3.3: 100% passing
  - Phase 3.4: 15/15 passing
  - Phase 2.5G: 100% passing
  - Phase 2.6G: 100% passing
  - Phase 2.7G: 100% passing
- **Frontend Build**: Zero TypeScript errors (`npm run type-check`), all 8 routes prerendered cleanly (`npm run build`).

---

## 10. Phase 3.5 Boundary & Next Steps

Phase 3.4 is strictly confined to generating the **personalized candidate set**.
The subsequent phase will introduce:
- **Phase 3.5: Personalized Ranking & Recommendation Scoring**:
  Blending Phase 2 match scores, Phase 3.2 expertise relevance, and Phase 3.3 preference alignments into a multi-objective ranking architecture.
