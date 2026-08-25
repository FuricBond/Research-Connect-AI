# Phase 2.3A Implementation Plan: Research Topic & Taxonomy Intelligence

## 1. Overview & Architecture

Phase 2.3A introduces the **Research Intelligence Layer** by establishing a unified, canonical topic taxonomy that bridges the **Opportunity Layer** (WikiCFP) and the **Research Knowledge Layer** (OpenAlex, Crossref).

```
                 RESEARCHCONNECT AI
                         │
          ┌──────────────┴──────────────┐
          │                             │
   OPPORTUNITY LAYER              RESEARCH KNOWLEDGE
          │                             │
       WikiCFP                  ┌───────┴───────┐
          │                      │               │
          ▼                   OpenAlex       Crossref
   opportunities                  │               │
          │                       └───────┬───────┘
          │                               │
          │                         research_works
          │                               │
          └─────────────────────┬─────────┘
                                │
                                ▼
                         CANONICAL TOPICS
                       (topics & topic_aliases)
                                │
                    ┌───────────┼───────────┐
                    ▼           ▼           ▼
              opportunities research_works future profiles
                    │           │
                    └─────┬─────┘
                          ▼
                 Topic Intelligence
             (ml/topic_analysis/)
             ├── taxonomy.py
             ├── normalization.py
             ├── extraction.py
             ├── assignment.py
             └── process_topics.py
                          │
                          ▼
                    FUTURE PHASE 2.3B
                 semantic embeddings (pgvector)
                          │
                          ▼
                    FUTURE PHASE 3
                recommendation & matching
```

---

## 2. Current Topic Architecture vs Target State

### Current State
- `topics` table: `id`, `name`, `slug`, `description`, `parent_id`, `created_at`.
- `opportunity_topics` table: `opportunity_id`, `topic_id`, `confidence_score`, `is_primary`.
- `research_works`: stores OpenAlex topics and Crossref subjects in unindexed `raw_metadata` JSONB.
- No direct link between `research_works` and `topics`.
- No alias / synonym mapping table.

### Target State in Phase 2.3A
- Retain existing `topics` table as the single source of canonical taxonomy.
- Add `topic_aliases` table to map abbreviations (e.g. `NLP`, `LLM`, `AI`, `CV`) and source-specific strings to canonical topics.
- Add `research_work_topics` junction table linking `research_works ↔ topics` with confidence, primary flag, assignment method, and provenance.
- Modular service package under `ml/topic_analysis/` for deterministic keyword extraction, taxonomy traversal, alias resolution, and topic assignment.
- Shared taxonomy serving both `opportunities` and `research_works`.

---

## 3. Taxonomy Design & Hierarchy

### Extensible Hierarchical Structure
The taxonomy organizes research domains hierarchically (`parent_id` self-referential FK).
- Level 0: Broad Domains (e.g. `Computer Science`, `Medicine`, `Physics`, `Mathematics`, `Biology`, `Engineering`, `Social Sciences`).
- Level 1: Sub-fields (e.g. `Artificial Intelligence`, `Software Engineering`, `Databases`, `Cybersecurity`).
- Level 2: Core Areas (e.g. `Machine Learning`, `Natural Language Processing`, `Computer Vision`, `Robotics`).
- Level 3: Specialized Topics (e.g. `Deep Learning`, `Large Language Models`, `Reinforcement Learning`, `Information Retrieval`).

### Cycle-Safe Hierarchy Traversal
- `TaxonomyService` implements cycle detection (visited node tracking) to guarantee DAG (Directed Acyclic Graph) integrity.
- Provides ancestor resolution (e.g. `Transformers` → `Deep Learning` → `Machine Learning` → `Artificial Intelligence` → `Computer Science`).
- Provides descendant resolution for hierarchical query expansion in recommendation.

---

## 4. Topic & Keyword Normalization

### Slug & Label Normalization
- Case folding (`lower()`).
- Unicode normalization (`NFKD` strip accents).
- Punctuation stripping (retains alphanumeric and single dashes).
- Deterministic slug generation: `Natural Language Processing` → `natural-language-processing`.

### Keyword Extraction (`KeywordExtractor`)
- Extracts candidate terms from work `title`, `abstract`, and source tags.
- Removes standard English stopwords.
- Extracts unigrams, bigrams, and trigrams matching taxonomy labels and aliases.
- Computes term occurrence frequency and position weight (title terms weighted 2.0x over abstract terms).

---

## 5. Source Taxonomy Mapping

### OpenAlex Mapping
- OpenAlex metadata provides hierarchical topic objects: `display_name`, `score`, `field`, `subfield`, `domain`.
- If `display_name` matches a canonical topic or alias, it is mapped with `assignment_method = SOURCE_EXPLICIT`.
- Confidence score is derived from OpenAlex relevance (`score`), calibrated to `[0.70, 1.00]`.

### Crossref Subject Mapping
- Crossref provides `subject` string arrays (e.g. `["Artificial Intelligence", "General Computer Science"]`).
- Mapped against canonical topics and aliases with `assignment_method = SOURCE_EXPLICIT` or `ALIAS_MATCH`.
- Confidence calibrated to `[0.65, 0.85]`.

### Unresolved External Terms
- Unmapped external terms are preserved in `raw_metadata` and NOT converted into synthetic topics.

---

## 6. Topic Assignment Methodology & Confidence Scoring

### Assignment Methods
1. `SOURCE_EXPLICIT`: Directly provided by OpenAlex/Crossref with matching taxonomy entry.
2. `ALIAS_MATCH`: Exact match against registered `topic_aliases`.
3. `RULE_INFERRED`: Inferred from title and abstract keyword evidence.
4. `MANUAL`: Verified or manually added by administrator/researcher.

### Confidence Scoring Model
- Single Evidence Confidence:
  - Source Explicit: `0.75 - 0.95`
  - Exact Alias Match: `0.70 - 0.90`
  - Title Keyword Rule: `0.60 - 0.80`
  - Abstract Keyword Rule: `0.45 - 0.65`
- Multi-Source Confidence Aggregation (Noisy-OR model):
  $$C_{\text{combined}} = 1 - \prod_{i} (1 - C_i)$$
  Bounded strictly within $[0.00, 1.00]$.
- Minimum threshold: topics below $0.40$ confidence are filtered out.

### Primary Topic Selection (`is_primary`)
- Ranked by: (1) composite confidence score, (2) title presence, (3) taxonomy specificity (depth).
- Top-ranked topic is flagged `is_primary = True`.

---

## 7. Database Migration (`0005_phase2_3a_topic_intelligence.py`)

1. Create `topic_aliases`:
   - `id`: UUID (PK)
   - `topic_id`: UUID (FK `topics.id` ondelete CASCADE)
   - `alias`: String(150)
   - `normalized_alias`: String(150), indexed
   - `source`: String(50), default 'MANUAL'
   - `created_at`: DateTime(tz=True)
   - Unique constraint: `(topic_id, normalized_alias)`
2. Create `research_work_topics`:
   - `id`: UUID (PK)
   - `work_id`: UUID (FK `research_works.id` ondelete CASCADE)
   - `topic_id`: UUID (FK `topics.id` ondelete CASCADE)
   - `confidence_score`: Numeric(3, 2), default 1.00
   - `is_primary`: Boolean, default False
   - `assignment_method`: String(50)
   - `source`: String(50)
   - `created_at`: DateTime(tz=True)
   - Unique constraint: `(work_id, topic_id)`
   - Check constraints: `confidence_score >= 0.0 AND confidence_score <= 1.0`
3. Seed canonical taxonomy topics and aliases.

---

## 8. Batch Processing CLI & Reprocessing

- Script: `ml/topic_analysis/process_topics.py`
- Supports `--dry-run`, `--limit`, `--reprocess`, `--work-id`.
- Idempotent: re-running updates existing assignments or refreshes scores without duplicate entries.

---

## 9. Future AI Compatibility (Phase 2.3B & Phase 3)

The structured output of Phase 2.3A (canonical topics, hierarchy paths, normalized keywords) will feed directly into Phase 2.3B's semantic text representation builder:
$$\text{Document Representation} = \text{Title} + \text{Abstract} + \text{Canonical Topics} + \text{Keywords}$$
which is then embedded into `pgvector` for similarity matching.
