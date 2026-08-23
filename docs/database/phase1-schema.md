# ResearchConnect AI — Phase 1 Database Schema Design

This document specifies the **Phase 1 database schema** for ResearchConnect AI. It establishes a solid relational foundation using **PostgreSQL** and prepares the system for vector similarity search using **pgvector** with a **384-dimensional embedding** (`sentence-transformers/all-MiniLM-L6-v2`), managed via **Alembic** migrations.

---

## 1. Entity Overview

The Phase 1 schema centers around 7 core entities:

```text
┌─────────────────┐       1:1       ┌──────────────────────┐
│      users      ├─────────────────┤  research_profiles   │
└────────┬────────┘                 └──────────────────────┘
         │
         │ 1:N
         ▼
┌─────────────────┐       N:1       ┌──────────────────────┐
│saved_opps       ├─────────────────┤    opportunities     │
└─────────────────┘                 └──────────┬───────────┘
                                               │
┌─────────────────┐       1:N                  │ N:M
│     sources     ├────────────────────────────┤
└─────────────────┘                 ┌──────────┴───────────┐
                                    │  opportunity_topics  │
                                    └──────────┬───────────┘
                                               │
┌─────────────────┐       1:N                  │
│     topics      ├────────────────────────────┘
│ (Self-referent) │
└─────────────────┘
```

1. **`users`**: Platform user accounts (students, researchers, faculty, admins) for authentication and access control.
2. **`research_profiles`**: Academic profiles linked to users (institutions, research interests, domains, and preference keywords).
3. **`sources`**: Ingestion tracking for scrapers, external portals, RSS feeds, and direct faculty submissions.
4. **`topics`**: Standardized hierarchical taxonomy of research disciplines and sub-fields (e.g., Computer Science -> AI -> NLP).
5. **`opportunities`**: Unified core table representing conferences, journals, workshops, CFPs, and special issues with vector embeddings.
6. **`opportunity_topics`**: Junction table connecting opportunities to taxonomy topics with topic-extraction confidence scoring.
7. **`saved_opportunities`**: User bookmarking and tracking entity connecting users to saved opportunities with optional private notes.

---

## 2. Table Definitions

### 2.1 `users`
Manages system accounts and authentication.

| Column | Type | Nullable | Default | Constraints / Description |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `UUID` | No | `gen_random_uuid()` | **PRIMARY KEY** |
| `email` | `VARCHAR(255)` | No | — | **UNIQUE**, indexed, lowercase validated |
| `hashed_password` | `VARCHAR(255)` | No | — | Securely hashed credential |
| `full_name` | `VARCHAR(255)` | No | — | User display name |
| `role` | `VARCHAR(50)` | No | `'STUDENT'` | Check: `STUDENT`, `FACULTY`, `ADMIN` |
| `is_active` | `BOOLEAN` | No | `TRUE` | Account active state |
| `is_verified` | `BOOLEAN` | No | `FALSE` | Email / institutional verification |
| `created_at` | `TIMESTAMPTZ` | No | `NOW()` | Creation timestamp |
| `updated_at` | `TIMESTAMPTZ` | No | `NOW()` | Modification timestamp |

---

### 2.2 `research_profiles`
Captures research background, target areas, and matching preferences.

| Column | Type | Nullable | Default | Constraints / Description |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `UUID` | No | `gen_random_uuid()` | **PRIMARY KEY** |
| `user_id` | `UUID` | No | — | **FOREIGN KEY** (`users.id` ON DELETE CASCADE), **UNIQUE** (1:1) |
| `institution` | `VARCHAR(255)` | Yes | `NULL` | University or organization |
| `department` | `VARCHAR(255)` | Yes | `NULL` | Department / Faculty |
| `academic_level` | `VARCHAR(100)` | Yes | `NULL` | e.g. `UNDERGRADUATE`, `MASTERS`, `PHD`, `POSTDOC`, `FACULTY` |
| `bio` | `TEXT` | Yes | `NULL` | Short research bio or interest statement |
| `keywords` | `JSONB` | Yes | `'[]'::jsonb` | Array of extracted/user-specified keyword strings |
| `target_opportunity_types`| `JSONB` | Yes | `'[]'::jsonb` | e.g. `["CONFERENCE", "JOURNAL"]` |
| `created_at` | `TIMESTAMPTZ` | No | `NOW()` | Creation timestamp |
| `updated_at` | `TIMESTAMPTZ` | No | `NOW()` | Modification timestamp |

---

### 2.3 `sources`
Tracks opportunity ingestion pipelines and origin channels.

| Column | Type | Nullable | Default | Constraints / Description |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `UUID` | No | `gen_random_uuid()` | **PRIMARY KEY** |
| `name` | `VARCHAR(100)` | No | — | **UNIQUE**, e.g., "WikiCFP", "IEEE Call For Papers", "Direct Faculty" |
| `source_type` | `VARCHAR(50)` | No | `'SCRAPER'` | Check: `SCRAPER`, `RSS`, `API`, `MANUAL` |
| `base_url` | `TEXT` | Yes | `NULL` | Root URL of data source |
| `is_active` | `BOOLEAN` | No | `TRUE` | Source polling enabled/disabled |
| `reliability_score` | `NUMERIC(3, 2)` | No | `1.00` | Historical accuracy / trust score (`0.00` to `1.00`) |
| `last_scraped_at` | `TIMESTAMPTZ` | Yes | `NULL` | Timestamp of last successful ingestion |
| `created_at` | `TIMESTAMPTZ` | No | `NOW()` | Ingestion record created |
| `updated_at` | `TIMESTAMPTZ` | No | `NOW()` | Record updated |

---

### 2.4 `topics`
Standardized research topics, domains, and sub-disciplines.

| Column | Type | Nullable | Default | Constraints / Description |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `UUID` | No | `gen_random_uuid()` | **PRIMARY KEY** |
| `name` | `VARCHAR(150)` | No | — | **UNIQUE**, e.g., "Natural Language Processing" |
| `slug` | `VARCHAR(150)` | No | — | **UNIQUE**, indexed (e.g., `natural-language-processing`) |
| `description` | `TEXT` | Yes | `NULL` | Brief definition of the field |
| `parent_id` | `UUID` | Yes | `NULL` | **FOREIGN KEY** (`topics.id` ON DELETE SET NULL) for taxonomy hierarchy |
| `created_at` | `TIMESTAMPTZ` | No | `NOW()` | Creation timestamp |

---

### 2.5 `opportunities` (Unified Common Model)
A unified single table accommodating all supported academic opportunity types: `CONFERENCE`, `JOURNAL`, `WORKSHOP`, `CALL_FOR_PAPERS`, and `SPECIAL_ISSUE`.

| Column | Type | Nullable | Default | Constraints / Description |
| :--- | :--- | :--- | :--- | :--- |
| **`id`** | `UUID` | No | `gen_random_uuid()` | **PRIMARY KEY** |
| **`title`** | `TEXT` | No | — | Full opportunity title / name |
| **`opportunity_type`** | `VARCHAR(50)` | No | — | Check: `CONFERENCE`, `JOURNAL`, `WORKSHOP`, `CALL_FOR_PAPERS`, `SPECIAL_ISSUE` |
| `slug` | `VARCHAR(255)` | Yes | `NULL` | URL slug |
| `publisher` | `VARCHAR(255)` | Yes | `NULL` | e.g., `IEEE`, `ACM`, `Springer`, `Elsevier`, `Nature` |
| `organizer` | `VARCHAR(255)` | Yes | `NULL` | University, research committee, or society |
| `series_name` | `VARCHAR(255)` | Yes | `NULL` | Venue series (e.g., `CVPR`, `IEEE TKDE`) |
| `edition` | `VARCHAR(50)` | Yes | `NULL` | Specific edition (e.g., `2026`, `38th Annual`) |
| `summary` | `TEXT` | Yes | `NULL` | Brief overview / abstract / TL;DR |
| `description` | `TEXT` | Yes | `NULL` | Detailed call for papers / submission guidelines |
| `website_url` | `TEXT` | Yes | `NULL` | Official event / journal homepage |
| `submission_url` | `TEXT` | Yes | `NULL` | Direct portal (e.g. OpenReview, EasyChair) |
| `delivery_mode` | `VARCHAR(50)` | No | `'OFFLINE'` | Check: `ONLINE`, `OFFLINE`, `HYBRID` |
| `location` | `VARCHAR(255)` | Yes | `NULL` | City, Country or "Virtual" |
| `submission_deadline`| `TIMESTAMPTZ`| Yes | `NULL` | Manuscript/abstract submission deadline (indexed) |
| `notification_date` | `TIMESTAMPTZ` | Yes | `NULL` | Acceptance notification deadline |
| `camera_ready_deadline`|`TIMESTAMPTZ`| Yes | `NULL` | Final manuscript due date |
| `event_start_date` | `DATE` | Yes | `NULL` | Conference/event start date |
| `event_end_date` | `DATE` | Yes | `NULL` | Conference/event end date |
| `indexing` | `JSONB` | Yes | `'[]'::jsonb` | e.g. `["Scopus", "SCIE", "IEEE Xplore", "ACM DL", "DOAJ"]` |
| `apc_or_fee` | `JSONB` | Yes | `NULL` | e.g. `{"has_fee": true, "amount": 400, "currency": "USD", "fee_type": "REGISTRATION"}` |
| `is_predatory_flag` | `BOOLEAN` | No | `FALSE` | High-risk suspicious opportunity warning flag |
| `risk_score` | `NUMERIC(3, 2)` | Yes | `0.00` | Risk rating (`0.00` = reputable, `1.00` = high risk) |
| `risk_reasons` | `JSONB` | Yes | `'[]'::jsonb` | List of flagged risk signals |
| `status` | `VARCHAR(50)` | No | `'ACTIVE'` | Check: `ACTIVE`, `EXPIRED`, `ARCHIVED`, `DRAFT`, `UNVERIFIED` |
| `source_id` | `UUID` | Yes | `NULL` | **FOREIGN KEY** (`sources.id` ON DELETE SET NULL), indexed |
| `raw_source_id` | `VARCHAR(255)` | Yes | `NULL` | External identifier from source (for deduplication) |
| `last_verified_at` | `TIMESTAMPTZ` | Yes | `NULL` | Freshness check timestamp |
| `embedding` | `vector(384)` | Yes | `NULL` | **384-dim embedding** (`all-MiniLM-L6-v2`), optional |
| `created_at` | `TIMESTAMPTZ` | No | `NOW()` | Record creation timestamp |
| `updated_at` | `TIMESTAMPTZ` | No | `NOW()` | Last record update timestamp |

---

### 2.6 `opportunity_topics`
Junction table linking opportunities to standardized taxonomy topics with confidence ratings.

| Column | Type | Nullable | Default | Constraints / Description |
| :--- | :--- | :--- | :--- | :--- |
| `opportunity_id` | `UUID` | No | — | **FOREIGN KEY** (`opportunities.id` ON DELETE CASCADE) |
| `topic_id` | `UUID` | No | — | **FOREIGN KEY** (`topics.id` ON DELETE CASCADE), indexed |
| `confidence_score` | `NUMERIC(3, 2)` | No | `1.00` | Extraction confidence: `1.00` (explicit/scraped) to `<1.00` (AI-inferred) |
| `is_primary` | `BOOLEAN` | No | `FALSE` | Primary category designation |
| `created_at` | `TIMESTAMPTZ` | No | `NOW()` | Association timestamp |

- **PRIMARY KEY**: `(opportunity_id, topic_id)`

---

### 2.7 `saved_opportunities`
User bookmarking and private tracking of opportunities.

| Column | Type | Nullable | Default | Constraints / Description |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `UUID` | No | `gen_random_uuid()` | **PRIMARY KEY** |
| `user_id` | `UUID` | No | — | **FOREIGN KEY** (`users.id` ON DELETE CASCADE), indexed |
| `opportunity_id` | `UUID` | No | — | **FOREIGN KEY** (`opportunities.id` ON DELETE CASCADE), indexed |
| `notes` | `TEXT` | Yes | `NULL` | Optional private user notes |
| `created_at` | `TIMESTAMPTZ` | No | `NOW()` | Bookmark creation timestamp |

- **UNIQUE CONSTRAINT**: `uq_saved_opportunities_user_opportunity (user_id, opportunity_id)`

---

## 3. Relationships & Cardinality

| Relationship | Type | Parent | Child | Foreign Key | Cascade Action |
| :--- | :---: | :--- | :--- | :--- | :--- |
| User Profile | `1 : 1` | `users` | `research_profiles` | `research_profiles.user_id` | `ON DELETE CASCADE` |
| Saved Opportunity | `1 : N` | `users` | `saved_opportunities` | `saved_opportunities.user_id` | `ON DELETE CASCADE` |
| Opportunity Bookmark | `1 : N` | `opportunities` | `saved_opportunities` | `saved_opportunities.opportunity_id` | `ON DELETE CASCADE` |
| Source Ingestion | `1 : N` | `sources` | `opportunities` | `opportunities.source_id` | `ON DELETE SET NULL` |
| Topic Hierarchy | `1 : N` | `topics` | `topics` | `topics.parent_id` | `ON DELETE SET NULL` |
| Opportunity Topic | `N : M` | `opportunities` | `topics` | via `opportunity_topics` | `ON DELETE CASCADE` |

---

## 4. Integrity Constraints & Business Rules

1. **Email Lowercase & Format**: Users must have valid, unique emails.
2. **Opportunity Types**: Enforced via `CHECK (opportunity_type IN ('CONFERENCE', 'JOURNAL', 'WORKSHOP', 'CALL_FOR_PAPERS', 'SPECIAL_ISSUE'))`.
3. **Delivery Modes**: Enforced via `CHECK (delivery_mode IN ('ONLINE', 'OFFLINE', 'HYBRID'))`.
4. **Lifecycle Status**: Enforced via `CHECK (status IN ('ACTIVE', 'EXPIRED', 'ARCHIVED', 'DRAFT', 'UNVERIFIED'))`.
5. **User Roles**: Enforced via `CHECK (role IN ('STUDENT', 'FACULTY', 'ADMIN'))`.
6. **Source Types**: Enforced via `CHECK (source_type IN ('SCRAPER', 'RSS', 'API', 'MANUAL'))`.
7. **Deduplication Rule**: Unique composite constraint on `(source_id, raw_source_id)` where `raw_source_id IS NOT NULL` prevents re-ingestion of the same external item from a single source.
8. **Bookmark Uniqueness**: Composite unique constraint on `(user_id, opportunity_id)` ensures a user bookmarks an opportunity at most once.

---

## 5. Indexing Strategy

### 5.1 B-Tree Indexes (Relational & Filtering)
- `ix_users_email` ON `users(email)`
- `ix_research_profiles_user_id` ON `research_profiles(user_id)`
- `ix_opportunities_opportunity_type` ON `opportunities(opportunity_type)`
- `ix_opportunities_status` ON `opportunities(status)`
- `ix_opportunities_source_id` ON `opportunities(source_id)`
- `ix_opportunities_submission_deadline` ON `opportunities(submission_deadline)`
- `idx_opportunities_type_status` ON `opportunities(opportunity_type, status)`
- `idx_opportunities_deadline` ON `opportunities(submission_deadline)`
- `ix_opportunity_topics_topic_id` ON `opportunity_topics(topic_id)`
- `ix_topics_slug` ON `topics(slug)`
- `ix_topics_parent_id` ON `topics(parent_id)`
- `ix_saved_opportunities_user_id` ON `saved_opportunities(user_id)`
- `ix_saved_opportunities_opportunity_id` ON `saved_opportunities(opportunity_id)`

### 5.2 Vector Search Index (pgvector)
- An **HNSW** (Hierarchical Navigable Small World) index will be added for the 384-dim vector embeddings:
  ```sql
  CREATE INDEX idx_opportunities_embedding ON opportunities 
  USING hnsw (embedding vector_cosine_ops) 
  WITH (m = 16, ef_construction = 64);
  ```

---

## 6. Field Categorization (Data Provenance)

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. SCRAPED DATA (Originates from raw feeds, external sites, and CFPs)       │
│    • title, description, summary (raw), publisher, organizer, series_name,  │
│      edition, website_url, submission_url, delivery_mode, location,         │
│      submission_deadline, notification_date, camera_ready_deadline,         │
│      event_start_date, event_end_date, raw_source_id, source_id             │
├─────────────────────────────────────────────────────────────────────────────┤
│ 2. AI-GENERATED DATA (Produced by NLP pipelines and ML models)              │
│    • embedding (384-dimensional vector from all-MiniLM-L6-v2)               │
│    • opportunity_topics.confidence_score (inferred topic tags)              │
│    • risk_score & risk_reasons (predatory / quality scoring model)          │
│    • is_predatory_flag (threshold heuristic)                                │
│    • research_profiles.keywords (auto-extracted keywords)                   │
├─────────────────────────────────────────────────────────────────────────────┤
│ 3. USER-GENERATED DATA (Provided explicitly by platform users)              │
│    • users.email, users.hashed_password, users.full_name, users.role        │
│    • research_profiles.institution, department, academic_level, bio         │
│    • research_profiles.target_opportunity_types                             │
│    • saved_opportunities.notes                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│ 4. SYSTEM-GENERATED DATA (Maintained by application state & audit log)      │
│    • id (UUIDs), created_at, updated_at                                     │
│    • status (ACTIVE -> EXPIRED -> ARCHIVED lifecycle)                       │
│    • last_verified_at (data freshness timestamp)                            │
│    • sources.reliability_score & sources.last_scraped_at                    │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 7. Deferred Extensions (Phase 2 & Phase 3)

The following modules remain cleanly deferred:
- **`submissions`**: Formal manuscript submission lifecycle tracking.
- **`risk_assessments`**: Deep multi-criteria risk audit logs.
- **`research_papers`**: User uploaded drafts/manuscripts for automated parsing.
- **`notifications`**: Scheduled alert queues and read state.
- **`faculty_opportunities`**: Direct departmental student-recruitment postings.
