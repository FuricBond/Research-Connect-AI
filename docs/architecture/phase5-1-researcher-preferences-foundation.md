# Phase 5.1 — Researcher Preferences Foundation

## 1. Executive Summary

Phase 5.1 establishes the **explicit researcher preference foundation** for Research Connect AI. This layer provides a strongly typed, deterministic, and auditable domain representation of what a researcher prefers, remains neutral about, or explicitly excludes across opportunities, research topics, delivery formats, geographic regions, institutions, funding requirements, and academic career stages.

In accordance with strict phase boundaries:
- **No recommendation or ranking modifications** were introduced in Phase 5.1.
- **No behavioral learning, implicit inference, collaborative filtering, or ML personalization** was implemented.
- **No duplicate identities or parallel profile models** were created; all preferences are anchored directly to the canonical `ResearchProfileModel` established in Phase 3.1.

---

## 2. 3-State Preference Hierarchy

A critical design requirement of Phase 5.1 is the formal distinction between three preference states:

$$\text{Preferred} \neq \text{Neutral / Unspecified} \neq \text{Excluded}$$

1. **Preferred (`PREFERRED`)**: The researcher explicitly seeks opportunities matching this attribute (e.g. `CONFERENCE`, `machine-learning`, `North America`).
2. **Neutral / Unspecified (`NEUTRAL`)**: The researcher has not declared a preference. **Absence of a preference is never treated as a negative preference.** Unspecified attributes remain open for general discovery. In the database, neutral state is represented by the absence of a preference row.
3. **Excluded (`EXCLUDED`)**: The researcher explicitly rejects opportunities matching this dimension (e.g., excluding `SPECIAL_ISSUE` or specific regions/topics).

---

## 3. Data Model & Alembic Migration

### Model: `ResearcherPreferenceModel` (`researcher_preferences`)

The canonical `ResearcherPreferenceModel` in `backend/app/models/researcher_preference.py` was enhanced with:
- `preference_type`: `VARCHAR(50)`, default `"PREFERRED"`, server_default `"PREFERRED"`, non-nullable.
- Index: `idx_researcher_preferences_type` on `("preference_type")`.
- Check constraint: `chk_researcher_preferences_type` enforcing `preference_type IN ('PREFERRED', 'EXCLUDED')`.
- Unique constraint: `uq_researcher_preferences_profile_cat_val` on `("profile_id", "category", "preference_value")`.

### Migration: `0017_phase5_1_researcher_preferences_foundation.py`
- Non-destructive and fully reversible (`downgrade` drops constraint, index, and column).
- Backwards compatible: existing rows in `researcher_preferences` have server default `'PREFERRED'`.

---

## 4. Normalization & Validation

The `ResearcherPreferenceService.normalize_preference` method deterministically normalizes inputs across all canonical taxonomy dimensions:
- `OPPORTUNITY_TYPE`: Normalizes to canonical enum values (`CONFERENCE`, `WORKSHOP`, `JOURNAL`, `CALL_FOR_PAPERS`, `SPECIAL_ISSUE`, `FELLOWSHIP`, `GRANT`, `INTERNSHIP`).
- `DELIVERY_MODE`: Normalizes to `ONLINE`, `OFFLINE`, `HYBRID`.
- `TOPIC`: Resolves against `TopicModel` taxonomy where matches exist, falls back to slugified representation.
- `KEYWORD`: Trims whitespace and lowercases.
- `RESEARCH_DOMAIN`: Normalizes to Title Case.
- `COUNTRY`: Normalizes 2/3-letter ISO codes to uppercase (e.g. `USA`, `GBR`, `DE`), country names to Title Case.
- `REGION` & `INSTITUTION`: Trims and standardizes case.
- `FUNDING`: Normalizes boolean requirement, minimum amount, and uppercase currency code.
- `ACADEMIC_LEVEL` & `CAREER_STAGE`: Normalizes to standardized uppercase snake_case tokens.

---

## 5. API Design

### Endpoints
- `GET /api/v1/researchers/{id}/preferences`: Lists persisted preferences with optional filters (`category`, `source`, `is_active`, `preference_type`).
- `GET /api/v1/researchers/{id}/preferences/structured`: Retrieves structured hierarchical preferences partitioned into research interests, opportunities, geography, funding, academic, and exclusions.
- `POST /api/v1/researchers/{id}/preferences`: Creates or updates an explicit preference item.
- `PUT /api/v1/researchers/{id}/preferences`: Atomically synchronizes multiple preferences with optional `replace_existing`.
- `PATCH /api/v1/researchers/{id}/preferences/{pref_id}`: Partially updates a preference item.
- `DELETE /api/v1/researchers/{id}/preferences/{pref_id}`: Removes a preference item (resets to neutral).

---

## 6. Frontend Architecture (Next.js App Router)

- **Dedicated Page**: `/researcher/preferences` (`frontend/app/researcher/preferences/page.tsx`)
  - Full-featured preference control center with 3-state cycling controls.
  - Dedicated modules for Opportunity Formats, Delivery Modes, Topics & Keywords, Geographic/Institutional Targeting, Funding & Career Stage, and Explicit Exclusions.
- **Embedded Component**: `ResearcherPreferencesView` (`frontend/components/researcher/ResearcherPreferencesView.tsx`)
  - Enhanced with expanded canonical opportunity types and direct navigation to the Preference Center.
- **Strict Type Parity**: `frontend/types/researcher.ts` exactly mirrors backend Pydantic schemas without using `any`.

---

## 7. Safety Invariants Verification

All 20 safety invariants defined for Phase 5.1 passed automated verification:
1. Missing preference ≠ negative preference.
2. Unspecified ≠ excluded.
3. Preferred ≠ automatically required.
4. Explicit exclusion is preserved.
5. Duplicate preferences do not create duplicate semantic entries.
6. Invalid identifiers are never silently fabricated.
7. Researcher identity remains anchored to `ResearchProfileModel`.
8. Preferences cannot create a duplicate researcher identity.
9. Preferences do not alter existing ranking by themselves.
10. Preferences do not alter deadline intelligence.
11. Preferences do not alter risk/trust scores.
12. Preferences do not alter academic-quality scores.
13. Existing researchers without preferences remain valid (cold start).
14. Existing Phase 2 APIs remain backward compatible.
15. Existing Phase 3 APIs remain backward compatible.
16. Existing Phase 4 recommendation behavior remains unchanged.
17. API serialization is lossless.
18. Repeated identical updates are deterministic.
19. Concurrent/duplicate preference updates do not create duplicate records.
20. No N+1 queries are introduced (measured $\le 6$ queries for aggregate retrieval).
