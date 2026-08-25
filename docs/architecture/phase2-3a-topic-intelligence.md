# Phase 2.3A — Research Topic & Taxonomy Intelligence Architecture

## 1. Overview & System Role

Phase 2.3A introduces the **Research Topic & Taxonomy Intelligence Layer** for ResearchConnect AI. It creates a normalized canonical taxonomy shared across the **Opportunity Discovery Layer** (WikiCFP) and the **Research Knowledge Layer** (OpenAlex & Crossref), converting heterogeneous external metadata into structured, queryable academic topics.

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
             ├── taxonomy.py      (DAG hierarchy & cycle prevention)
             ├── normalization.py (Slugs, aliases & external mappings)
             ├── extraction.py    (Deterministic keyword & phrase extraction)
             ├── assignment.py    (Multi-evidence scoring & Noisy-OR confidence)
             └── process_topics.py(Batch processing CLI pipeline)
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

## 2. Canonical Taxonomy Design & Identity

### Canonical Topics Table (`topics`)
- `id` (UUID PK): Internal stable surrogate identifier.
- `name` (String(150), Unique): Display name (e.g. `Natural Language Processing`).
- `slug` (String(150), Unique, Indexed): Deterministic URL/database-safe slug (`natural-language-processing`).
- `description` (Text, Nullable): Concise definition of the field.
- `parent_id` (UUID, Self-referential FK): Parent topic pointer for DAG hierarchy.
- `created_at` (DateTime(tz=True)): Timestamp of creation.

### Canonical Seed Hierarchy
Spans 9 top-level academic domains and deep Computer Science/AI subfields:
- **Level 0 (Domains)**: `Computer Science`, `Medicine`, `Biology`, `Mathematics`, `Physics`, `Engineering`, `Social Sciences`, `Economics`, `Environmental Science`.
- **Level 1 (CS Fields)**: `Artificial Intelligence`, `Data Science`, `Software Engineering`, `Cybersecurity`, `Databases`, `Distributed Systems`, `Human-Computer Interaction`, `Computer Networks`.
- **Level 2 (AI Core)**: `Machine Learning`, `Natural Language Processing`, `Computer Vision`, `Robotics`, `Knowledge Representation`.
- **Level 3 (Specializations)**: `Deep Learning`, `Reinforcement Learning`, `Generative AI`, `Large Language Models`, `Transformers`, `Information Retrieval`, `Text Classification`, `Question Answering`, `Machine Translation`, `Object Detection`, `Image Segmentation`, `Bioinformatics`, `Medical Informatics`, `Quantum Computing`.

---

## 3. Topic Aliases (`topic_aliases`)

To bridge abbreviations, acronyms, and alternate forms to canonical topics:
- `id` (UUID PK)
- `topic_id` (UUID FK `topics.id` ondelete CASCADE)
- `alias` (String(150)): Display alias (e.g. `NLP`, `LLM`, `AI`, `CV`, `GPT`, `BERT`)
- `normalized_alias` (String(150), Indexed): Normalized lowercase form (`nlp`, `llm`, `ai`)
- `source` (String(50)): Source provenance (`MANUAL`, `OPENALEX`, `CROSSREF`, `SEED_TAXONOMY`)
- `created_at` (DateTime(tz=True))

Constraints:
- `UNIQUE (topic_id, normalized_alias)`
- Fast index on `normalized_alias`

---

## 4. Cycle-Safe DAG Hierarchy Traversal

The `TaxonomyService` implements:
- **Cycle Detection**: Validates that parent relationships contain no loops.
- **Ancestor Traversal**: Resolves paths from leaf to root (e.g. `large-language-models` → `natural-language-processing` → `artificial-intelligence` → `computer-science`).
- **Descendant Traversal**: Recursively resolves all children (e.g. `artificial-intelligence` → `machine-learning`, `deep-learning`, `transformers`, etc.).
- **Depth Calculation**: Returns node depth in the taxonomy DAG (Level 0 = Root).

---

## 5. Source Taxonomy Mapping

### OpenAlex Topics
- OpenAlex metadata (`raw_metadata.get("topics")`) includes objects with `display_name` and source `score`.
- `TopicNormalizer.resolve_openalex_topic()` maps display names to canonical topics.
- Calibrates source relevance into confidence: $C = \min(0.98, \max(0.75, 0.70 + 0.28 \times \text{score}))$.
- Assigned with `assignment_method = "SOURCE_EXPLICIT"`, `source = "OpenAlex"`.

### Crossref Subjects
- Crossref metadata (`raw_metadata.get("crossref", {}).get("subject")`) includes subject strings.
- `TopicNormalizer.resolve_crossref_subject()` maps standard subjects (e.g. `"Computer Vision and Pattern Recognition"` → `computer-vision`).
- Assigned with `assignment_method = "SOURCE_EXPLICIT"`, `confidence_score = 0.80`, `source = "Crossref"`.

---

## 6. Keyword & Keyphrase Extraction (`KeywordExtractor`)

Lightweight, deterministic extractor without heavy external dependencies:
1. **Tokenization & Stopword Filtering**: Strips standard English stopwords and academic noise words (`paper`, `proposed`, `study`, `framework`, `approach`).
2. **N-gram Generation**: Generates unigrams, bigrams, and trigrams.
3. **Weighting**:
   - Title matches: $2.0\times$ multiplier
   - Abstract matches: $1.0\times$ multiplier
   - Source keywords: $2.5\times$ multiplier
   - Taxonomy match bonus: $1.5\times$ boost
4. **Ranking**: Sorts by taxonomy relevance, weight, and occurrence count.

---

## 7. Multi-Evidence Topic Assignment & Confidence Model

### Evidence Signals
- **`SOURCE_EXPLICIT`**: Direct taxonomy match from OpenAlex or Crossref ($0.75 - 0.98$).
- **`ALIAS_MATCH`**: Exact match against registered aliases ($0.70 - 0.90$).
- **`RULE_INFERRED`**:
  - Title keyword match: $0.75$ (`TitleRule`)
  - Abstract keyword match: $0.55$ (`AbstractRule`)
  - Source keyword tag match: $0.65$ (`KeywordRule`)

### Multi-Source Confidence Aggregation (Noisy-OR)
When multiple independent sources identify the same topic:
$$C_{\text{combined}} = 1 - \prod_{i} (1 - C_i)$$
- Bounded strictly within $[0.00, 1.00]$ and rounded to 2 decimal places.
- Filter: Topics with $C_{\text{combined}} < 0.40$ are excluded.

### Primary Topic Selection (`is_primary`)
Candidates are ranked deterministically by:
1. Title presence (anchoring in paper title)
2. Combined confidence score
3. Taxonomy depth (prefers specific leaf topics over broad root categories)
Top-ranked candidate is flagged `is_primary = True`.

---

## 8. Database Junction Tables

### Research Work Topics (`research_work_topics`)
- `id` (UUID PK)
- `work_id` (UUID FK `research_works.id` ondelete CASCADE)
- `topic_id` (UUID FK `topics.id` ondelete CASCADE)
- `confidence_score` (Numeric(3, 2), check $\in [0.0, 1.0]$)
- `is_primary` (Boolean, default False)
- `assignment_method` (String(50), check $\in \{\text{SOURCE\_EXPLICIT}, \text{ALIAS\_MATCH}, \text{RULE\_INFERRED}, \text{MANUAL}\}$)
- `source` (String(50))
- `created_at` (DateTime(tz=True))
- `UNIQUE (work_id, topic_id)`

### Opportunity Topics (`opportunity_topics`)
Reuses the same canonical `topics` table with `confidence_score` and `is_primary`.

---

## 9. Batch Processing CLI (`process_topics.py`)

### Usage
```bash
# Dry run on research works
python -m ml.topic_analysis.process_topics --dry-run --limit 20

# Live processing on research works
python -m ml.topic_analysis.process_topics --limit 100

# Single work by ID
python -m ml.topic_analysis.process_topics --work-id "<UUID>" --dry-run

# Process opportunities
python -m ml.topic_analysis.process_topics --opportunities --dry-run --limit 20

# Reprocess existing records
python -m ml.topic_analysis.process_topics --reprocess --limit 100
```

### Idempotency & Reprocessing
- Running `--reprocess` cleanly deletes existing junction rows and re-inserts fresh assignments.
- Re-running without `--reprocess` only processes unassigned records, avoiding redundant computation.

---

## 10. Future AI Compatibility (Phase 2.3B)

Phase 2.3A creates the structured inputs required for embedding generation in Phase 2.3B:
$$\text{Document Representation} = \text{Clean Title} + \text{Abstract} + \text{Canonical Topics} + \text{Ancestor Hierarchy} + \text{Keywords}$$
which will be encoded by the embedding model into `pgvector` for similarity matching.
