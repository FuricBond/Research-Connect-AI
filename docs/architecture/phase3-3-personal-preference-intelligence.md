# Phase 3.3 — Personal Preference Intelligence Architecture

## 1. Executive Summary

**Phase 3.3: Personal Preference Intelligence** establishes a canonical, explainable representation of **what a researcher prefers**, answering:
> *"What kinds of research opportunities, research topics, venues, formats, locations, deadlines, and other attributes does this researcher prefer?"*

Crucially, it answers what a researcher *prefers*, **not** what to *recommend* (which belongs to Phase 3.4+).

### Core Boundaries & Safety Invariants
1. **Expertise $\neq$ Preference**: A researcher's scholarly expertise from Phase 3.2 (e.g. authored publications in Natural Language Processing) is observable evidence, **not** an explicit preference. Expertise is never silently converted into an explicit preference.
2. **No Personalized Ranking / Candidate Generation**: Preference intelligence does not alter semantic matching, hybrid search, deadline intelligence, or risk assessment. Phase 2 ranking pipelines remain 100% independent.
3. **No Fabricated Behavioral Data**: Inferred preferences are derived strictly from actual platform activity (`SavedOpportunityModel` in `saved_opportunities`). If no saved opportunities exist, inferred preferences remain empty.
4. **Explicit vs. Inferred vs. Derived Separation**: Provenance and confidence clearly distinguish researcher declarations (`EXPLICIT`, $C=0.95$), activity inferences (`INFERRED`, $C \le 0.85$), and candidate suggestions (`DERIVED_FROM_EXPERTISE`, $C=0.45$).
5. **Deterministic In-Memory Intelligence**: Zero external API or LLM dependency for scoring, confidence, conflict detection, or provenance generation.

---

## 2. Preference Taxonomy & Canonical Entity Mapping

All preference values are normalized against canonical repository entities:

| Category | Database Field / Model | Canonical Taxonomy Values | Normalization Rule |
| :--- | :--- | :--- | :--- |
| `OPPORTUNITY_TYPE` | `OpportunityModel.opportunity_type` | `CONFERENCE`, `JOURNAL`, `WORKSHOP`, `CALL_FOR_PAPERS`, `SPECIAL_ISSUE` | Uppercase normalized against canonical dictionary |
| `DELIVERY_MODE` | `OpportunityModel.delivery_mode` | `ONLINE`, `OFFLINE`, `HYBRID` | Uppercase, aliases ("remote" $\to$ `ONLINE`, "in-person" $\to$ `OFFLINE`) |
| `TOPIC` | `TopicModel` (`topics`) | Canonical topic slug + ID pointer | Slugs matched against `TopicModel.slug` and `TopicModel.name` |
| `LOCATION` | `OpportunityModel.location` | Host countries/regions (`India`, `Europe`, `United States`) | Title-cased region/country string |
| `DEADLINE_WINDOW` | Phase 2.7 Deadline Intelligence | Minimum notice days (`7`, `14`, `30`, `60`) | Digit extraction, minimum preparation day constraint |
| `OPEN_ACCESS` | `OpportunityModel.indexing` | `true`, `false` | Boolean string indicating open-access preference |
| `VENUE` | `OpportunityModel.publisher` | Publishers / societies (`IEEE`, `ACM`, `Springer`) | Trimmed publisher/organizer string |

---

## 3. Database Schema: `researcher_preferences`

Backed by `ResearcherPreferenceModel`:

```sql
CREATE TABLE researcher_preferences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id UUID NOT NULL REFERENCES research_profiles(id) ON DELETE CASCADE,
    category VARCHAR(50) NOT NULL,
    preference_key VARCHAR(100) NOT NULL,
    preference_value VARCHAR(255) NOT NULL,
    display_label VARCHAR(255) NOT NULL,
    canonical_id UUID REFERENCES topics(id) ON DELETE SET NULL,
    strength FLOAT NOT NULL DEFAULT 1.0,
    confidence FLOAT NOT NULL DEFAULT 0.95,
    source VARCHAR(50) NOT NULL DEFAULT 'EXPLICIT',
    is_active BOOLEAN NOT NULL DEFAULT true,
    recency_score FLOAT NOT NULL DEFAULT 1.0,
    provenance JSONB,
    last_observed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_researcher_preferences_profile_cat_val UNIQUE (profile_id, category, preference_value)
);

CREATE INDEX idx_researcher_preferences_profile_id ON researcher_preferences(profile_id);
CREATE INDEX idx_researcher_preferences_category ON researcher_preferences(category);
CREATE INDEX idx_researcher_preferences_source ON researcher_preferences(source);
CREATE INDEX idx_researcher_preferences_active ON researcher_preferences(is_active);
```

---

## 4. Mathematical & Scoring Formulations

### 4.1 Preference Strength ($S \in [0.0, 1.0]$)
- **Explicit**: Default $S = 1.00$ (or user-configured weight $w \in [0.1, 1.0]$).
- **Inferred (from Saved Opportunities)**:
  Let $N_{\text{saved}}$ be total saved items and $N_{\text{match}}$ be matching attribute occurrences:
  $$S_{\text{freq}} = \frac{N_{\text{match}}}{\max(1, N_{\text{saved}})}$$
  $$S_{\text{raw}} = 0.40 \cdot \min\left(1.0, \frac{\ln(1 + N_{\text{match}})}{\ln(11)}\right) + 0.60 \cdot S_{\text{freq}}$$
  $$S = \min\left(1.0, \max\left(0.1, \text{round}(S_{\text{raw}} \cdot R, 3)\right)\right)$$
- **Derived Candidates (from Phase 3.2 Expertise)**:
  $$S = \min(1.0, \max(0.1, \text{round}(0.70 \cdot S_{\text{interest}}, 3)))$$

### 4.2 Preference Confidence ($C \in [0.0, 1.0]$)
- **Explicit**: Authoritative declaration $\to C = 0.95$.
- **Inferred**: Scales with volume and sample proportion:
  $$C = \min\left(0.85, \text{round}(0.35 + 0.10 \cdot N_{\text{match}} + 0.20 \cdot S_{\text{freq}}, 3)\right)$$
  - Halved if contradictory preferences are detected.
- **Derived from Expertise**: $C = 0.45$ (intentionally conservative).

### 4.3 Recency Modeling ($R \in [0.20, 1.0]$)
For observed interactions with timestamp $t_{\text{latest}}$ and elapsed days $\Delta d$:
$$R = \max(0.20, \text{round}(\exp(-0.005 \cdot \Delta d), 3))$$

---

## 5. Contradiction & Conflict Detection

Contradictory preference configurations are evaluated deterministically:
1. **Open Access Contradiction**: Both `prefer_open_access = true` and `prefer_open_access = false` active simultaneously.
2. **Deadline Contradiction**: Differing deadline preparation windows with $\ge 14$ days divergence.
3. **Delivery Mode Contradiction**: Both strictly `ONLINE` and strictly `OFFLINE` declared without `HYBRID`.

When conflicts are detected:
- Flagged with human-readable rationale.
- Confidence of affected inferred preferences is halved.
- Summarized under `conflicts` without discarding user declarations.

---

## 6. Preference Completeness

Measures coverage across 5 opportunity personalization dimensions:
- `opportunity_type`: 25%
- `delivery_mode`: 20%
- `topic`: 25%
- `deadline`: 15%
- `location_or_access`: 15%

$$\text{Completeness} = \sum_{\text{dim} \in \text{configured}} w_{\text{dim}} \in [0.0, 1.0]$$

Profile is considered complete when score $\ge 0.85$ (85%).

---

## 7. REST API Reference

| Method | Path | Description | Authorization |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/researchers/{id}/preference-intelligence` | Full structured preference report | Public / Authenticated |
| `GET` | `/api/v1/researchers/{id}/preferences` | List persisted preferences with filters | Public / Authenticated |
| `POST` | `/api/v1/researchers/{id}/preferences` | Declare explicit preference | `X-User-ID` Profile Owner (403 enforced) |
| `PATCH` | `/api/v1/researchers/{id}/preferences/{pref_id}` | Update preference item | `X-User-ID` Profile Owner (403 enforced) |
| `DELETE` | `/api/v1/researchers/{id}/preferences/{pref_id}` | Delete preference item | `X-User-ID` Profile Owner (403 enforced) |

---

## 8. Next.js Frontend Integration

Implemented at `/researcher` route:
- **`ResearcherPreferencesView.tsx`**:
  - Interactive multi-select toggles for Opportunity Types and Delivery Modes.
  - Topic chips with add/remove actions.
  - Regional location pills.
  - Deadline window preparation selector.
  - Open Access toggle.
  - Completeness progress bar with missing dimensions tags.
  - Separate Inferred Preferences section with `"Inferred from Activity"` badge and sample breakdown.
  - Separate Derived Candidates section with `"Derived from Expertise"` badge and one-click "+ Add" action.
  - Conflict warning banner if contradictory preferences exist.

---

## 9. Performance & Zero N+1 Queries

- All explicit preferences loaded in a single query: `O(1)`.
- All saved opportunities with `OpportunityModel` loaded via `joinedload`: `O(1)`.
- Phase 3.2 interests loaded in a single query: `O(1)`.
- Maximum queries per intelligence request: $\le 4$.
- Verified via SQLAlchemy cursor execution hook in unit tests.

---

## 10. Verification & Test Summary

- **Phase 3.3 Focused Tests**: 18 passing tests in `backend/tests/test_researcher_preferences.py`.
- **Phase 3.1 & Phase 3.2 Tests**: 48 passing tests in `test_researcher_profile.py` and `test_researcher_intelligence.py`.
- **Phase 2 Regressions**: 66 passing tests across Phase 2.5G, 2.6G, 2.7G.
- **Frontend**: TypeScript typecheck passed cleanly, Next.js production build succeeded with static prerendering.
