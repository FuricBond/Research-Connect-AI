# Phase 3.1 Architecture: Researcher Profile Foundation

## 1. Overview & Purpose

**Phase 3.1: Researcher Profile Foundation** establishes the authoritative, canonical researcher identity and profile data infrastructure for **ResearchConnect AI**.

Prior to Phase 3.1, ResearchConnect AI operated in an anonymous, purely query-driven paradigm:
```text
Anonymous / query-driven researcher
        ↓
Research Query / Manuscript Abstract
        ↓
Phase 2 Recommendation & Discovery Pipeline
```

Phase 3.1 transitions the platform to an identity-grounded architecture:
```text
Authenticated Platform User
        ↓
Canonical Researcher Profile (ResearchProfileModel)
        ↓
Academic Affiliation (InstitutionModel) + Scholarly Identity (ResearcherModel)
        ↓
Phase 2 Recommendation Pipeline (Relevance Dominance, Zero-LLM, Deterministic)
```

> [!IMPORTANT]
> **Strict Phase Boundary Notice**:
> Phase 3.1 establishes profile **infrastructure only**. It does **not** implement personalization algorithms, recommendation adjustments, preference filtering, behavioral tracking, user embeddings, or collaborative filtering. The recommendation pipeline behaves identically to Phase 2.7.

---

## 2. Existing Researcher-Related Entities Discovered in Repository

During the architectural audit, the following existing entities and models were identified:

1. **`UserModel` (`users` table)**:
   - Represents platform accounts.
   - Attributes: `id` (UUID), `email` (unique, indexed), `full_name`, `hashed_password`, `role` (`STUDENT`, `FACULTY`, `ADMIN`), `is_active`, `is_verified`, `created_at`, `updated_at`.
   - Has a 1:1 relationship to `ResearchProfileModel` and 1:N to `SavedOpportunityModel`.

2. **`ResearchProfileModel` (`research_profiles` table)**:
   - Initial Phase 1 profile linked 1:1 to `UserModel`.
   - Attributes: `id`, `user_id` (FK), `institution` (freeform string), `department`, `academic_level`, `bio`, `keywords` (JSONB), `target_opportunity_types` (JSONB).

3. **`ResearcherModel` (`researchers` table)**:
   - Scholarly author entity ingested from OpenAlex (Phase 2.2A) and enriched via Crossref (Phase 2.2B).
   - Attributes: `id`, `openalex_id` (unique, nullable), `display_name`, `orcid` (indexed, nullable), `works_count`, `cited_by_count`, `raw_metadata`, `last_seen_at`.
   - Connected via `ResearchWorkAuthorModel` to `ResearchWorkModel`.

4. **`InstitutionModel` (`institutions` table)**:
   - Research institutions ingested from OpenAlex / Crossref.
   - Attributes: `id`, `openalex_id`, `display_name`, `ror`, `country_code`, `institution_type`, `homepage_url`, `works_count`, `cited_by_count`.

5. **`ResearchWorkAuthorModel` (`research_work_authors` table)**:
   - Many-to-many junction connecting `ResearchWorkModel` and `ResearcherModel` with authorship positions (`first`, `middle`, `last`) and correspondence flags.

---

## 3. Canonical Researcher Identity Architecture

To prevent entity duplication, Phase 3.1 **extends and unifies** `ResearchProfileModel` rather than creating a competing researcher table.

```text
Existing Entity                Canonical Bridge                   Profile & Knowledge Data
─────────────────              ────────────────                   ────────────────────────
UserModel (users)       ──1:1─► ResearchProfileModel ──FK(nullable)──► InstitutionModel (institutions)
(id, email, full_name,          (canonical user profile)
 role, password_hash)                 │
                                      ├──FK(nullable)───────────────► ResearcherModel (researchers)
                                      │                               (openalex_id, orcid, citations)
                                      │                                      │
                                      │                                 work_authorships
                                      │                                      ▼
                                      │                               ResearchWorkModel (works)
                                      │
                                      ├── academic_status (Enum)
                                      ├── orcid / openalex_id (normalized)
                                      ├── external_identifiers (JSONB)
                                      └── completeness (computed metadata)
```

- **Identity Anchor**: `ResearchProfileModel.id` represents the profile, linked 1:1 to `UserModel.id`.
- **Display Name**: Retrieved from `UserModel.full_name`.
- **Contact**: `UserModel.email`.
- **Canonical Affiliation**: `institution_id` references `institutions.id`, with `institution` string preserved as a resilient fallback.
- **Canonical Knowledge Identity**: `canonical_researcher_id` references `researchers.id`, allowing researchers to associate their OpenAlex/Crossref publications with their platform profile.

---

## 4. Profile Schema & Database Migration

### Alembic Migration
Alembic migration [`0008_phase3_1_researcher_profile_foundation.py`](file:///d:/Project/researchconnect-ai/backend/alembic/versions/0008_phase3_1_researcher_profile_foundation.py) applies the following non-destructive changes to `research_profiles`:

| Column | Type | Constraints | Description |
|---|---|---|---|
| `institution_id` | `UUID` | FK `institutions.id`, nullable, indexed | Reference to canonical institution entity |
| `canonical_researcher_id` | `UUID` | FK `researchers.id`, nullable, indexed | Reference to canonical OpenAlex/Crossref researcher |
| `orcid` | `VARCHAR(50)` | Nullable, indexed | Normalized 16-character ORCID identifier |
| `openalex_id` | `VARCHAR(50)` | Nullable, indexed | Compact OpenAlex author identifier (`A...`) |
| `academic_status` | `VARCHAR(50)` | Nullable, default `'UNKNOWN'` | Normalized academic career stage enum |
| `external_identifiers` | `JSONB` | Nullable, default `{}` | Key-value store for other IDs (Scopus, Google Scholar) |

---

## 5. External Identifier Normalization

External academic identifiers are sanitized and validated to guarantee clean indexing:

### ORCID Normalization
- Accepts: `0000-0002-1825-0097`, `https://orcid.org/0000-0002-1825-0097`, `http://orcid.org/...`, `orcid.org/...`
- Strips whitespace, protocol, and domain.
- Enforces 16-character hyphenated regex: `^\d{4}-\d{4}-\d{4}-[\dX]{4}$`.
- Uppercases trailing checksum character (`x` -> `X`).

### OpenAlex ID Normalization
- Accepts: `A5048491430`, `https://openalex.org/A5048491430`, `5048491430`.
- Strips protocol and URL prefixes.
- Prepends `A` if only digits provided.
- Validates against `^[A-Za-z]?\d+$`.

---

## 6. Academic Status Specification

Academic stage is modeled via `AcademicStatus` enum:
- `UNDERGRADUATE`: Undergraduate student
- `POSTGRADUATE`: Master's / Postgraduate student
- `PHD`: Doctoral student / candidate
- `POSTDOC`: Postdoctoral fellow / researcher
- `FACULTY`: Assistant / Associate / Full Professor
- `RESEARCHER`: Staff scientist / industry researcher
- `OTHER`: Non-standard or cross-disciplinary academic role
- `UNKNOWN`: Default fallback when unassigned

Academic status is serializable, null-safe, and validated at both model and Pydantic layers.

---

## 7. Deterministic Profile Completeness

Profile completeness is a deterministic metadata audit assessing whether sufficient profile data exists for future personalization layers.

### Completeness Weights:
| Attribute | Presence Criteria | Weight |
|---|---|---|
| **Full Name** | Non-empty string | 15% |
| **Email** | Non-empty valid email | 10% |
| **Academic Status** | Valid enum value != UNKNOWN | 15% |
| **Institution** | `institution_id` or non-empty string | 15% |
| **Department** | Non-empty string | 10% |
| **Bio** | Non-empty bio string | 10% |
| **External ID** | ORCID, OpenAlex ID, or canonical scholar ID | 15% |
| **Keywords** | At least 1 keyword | 10% |
| **Total** | | **100%** |

### Completeness Tiers:
- **`COMPLETE`**: Score >= 0.85
- **`INTERMEDIATE`**: 0.50 <= Score < 0.85
- **`BASIC`**: 0.20 <= Score < 0.50
- **`INCOMPLETE`**: Score < 0.20

> [!CAUTION]
> **Completeness Is Metadata Only**: Completeness percentage must never be used as a recommendation ranking boost, penalty, or eligibility threshold.

---

## 8. Researcher ↔ Research Work Integration

Scholarly publications are linked through the existing knowledge layer:
- When a profile has a `canonical_researcher_id`, publications are retrieved from `research_works` via `research_work_authors`.
- The service uses eager `joinedload` on `ResearchWorkAuthorModel.work`, ordered by `publication_year.desc().nulls_last()`.
- Retrieval is strictly read-only and zero-N+1.

---

## 9. API Specification

The researcher profile API is mounted under `/api/v1/researchers` and `/api/researchers`:

### `POST /api/v1/researchers`
- **Status**: `201 Created`
- **Body**: `ResearcherProfileCreate`
- **Description**: Creates a new researcher profile and user account, resolving canonical institution and researcher IDs.

### `GET /api/v1/researchers/{id}`
- **Status**: `200 OK`
- **Params**: `id` (UUID of profile or associated user)
- **Returns**: `ResearcherProfileRead`

### `PATCH /api/v1/researchers/{id}`
- **Status**: `200 OK`
- **Body**: `ResearcherProfileUpdate`
- **Description**: Partial update with re-resolution of affiliations and external IDs.

### `GET /api/v1/researchers/{id}/works`
- **Status**: `200 OK`
- **Query Params**: `limit` (default 20, max 100), `offset` (default 0)
- **Returns**: `list[ResearcherWorkSummarySchema]`

### `GET /api/v1/researchers/{id}/completeness`
- **Status**: `200 OK`
- **Returns**: `ProfileCompletenessSchema`

---

## 10. Next.js App Router UI

The frontend leverages the Next.js 15 App Router (`frontend/app/researcher/page.tsx`):
1. **Navigation**: Linked from `DiscoveryNavbar` with the `User` icon.
2. **Profile Card**: Displays researcher avatar, full name, email, academic status pill, canonical affiliation badge, ORCID link, OpenAlex link, bio, and keywords.
3. **Interactive Editor**: Allows seamless editing of identity attributes, affiliation, identifiers, and research focus.
4. **Completeness Progress Bar**: [`ProfileCompletenessBadge.tsx`](file:///d:/Project/researchconnect-ai/frontend/components/researcher/ProfileCompletenessBadge.tsx) displays visual percentage, tier, and field breakdown.
5. **Authored Works Listing**: Renders linked publications with citation counts and publication years.

---

## 11. Privacy & Security Considerations

- No passwords, auth tokens, or private secrets are exposed in profile endpoints.
- External academic identifiers (ORCID, OpenAlex) are treated as public identity metadata.
- Email is only shown to authorized profile owners.
- Unnecessary PII is strictly excluded.

---

## 12. Verification & Regression Results

| Suite | Scope | Status | Notes |
|---|---|---|---|
| `test_researcher_profile.py` | Models, Normalization, Service, API | **29 PASSED** | 100% pass |
| `test_phase2_5g_evaluation.py` | Phase 2.5 Ranking Benchmark | **13 PASSED** | Zero regression |
| `test_phase2_6g_risk_evaluation.py` | Phase 2.6 Predatory Risk Engine | **21 PASSED** | Zero regression |
| `test_phase2_7g_deadline_evaluation.py` | Phase 2.7 Deadline Intelligence | **32 PASSED** | Zero regression |
| `test_models.py` | Core Model Registration | **6 PASSED** | Zero regression |
| `npm run type-check` | Frontend TypeScript Check | **0 ERRORS** | Full type safety |
| `npm run build` | Next.js 15 App Router Build | **8/8 PAGES STATIC** | Successful compilation |

---

## 13. Future Extension Points (Phase 3.2+)

- **Phase 3.2**: Research Interest Intelligence (extracting topic vectors from profile keywords & authored works).
- **Phase 3.3**: Preference Engine (delivery modes, APC tolerances, deadline lead times).
- **Phase 3.4**: Personalized Candidate Retrieval (matching opportunities against researcher profile).
- **Phase 3.5**: Personalized Hybrid Ranking (blending Phase 2 relevance dominance with researcher-fit signals).
