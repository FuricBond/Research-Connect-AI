# Phase 2.3B — Semantic Embedding Generation + pgvector Integration

## Summary

Phase 2.3B adds a production-quality semantic embedding layer to ResearchConnect AI.
Every `ResearchWorkModel` and `OpportunityModel` record can be encoded into a
384-dimensional L2-normalised float vector using **`all-MiniLM-L6-v2`**, stored in
PostgreSQL via **pgvector**, and queried via approximate nearest-neighbour (HNSW) search.

This phase does **not** implement the recommendation engine. It provides the embedding
foundation that a future recommendation layer will consume.

---

## Architecture Overview

```
   ┌──────────────────────────────────────────────────┐
   │                  CLI Pipeline                     │
   │  python -m ml.embeddings.generate_embeddings      │
   └──────────┬───────────────────────────────────────┘
              │
   ┌──────────▼───────────────────────────────────────┐
   │  text_builder.py                                  │
   │  build_research_work_text() / build_opportunity_text()
   │  Deterministic, truncated (≤ 8 192 chars)         │
   └──────────┬───────────────────────────────────────┘
              │
   ┌──────────▼───────────────────────────────────────┐
   │  hash_utils.py                                    │
   │  compute_content_hash() → SHA-256 hex             │
   │  needs_reembedding()    → bool                    │
   └──────────┬───────────────────────────────────────┘
              │ (only if hash changed or model changed)
   ┌──────────▼───────────────────────────────────────┐
   │  service.py — EmbeddingService                    │
   │  encode_batch() → np.ndarray shape (N, 384)       │
   │  SentenceTransformer: all-MiniLM-L6-v2            │
   │  L2-normalised output                             │
   └──────────┬───────────────────────────────────────┘
              │
   ┌──────────▼───────────────────────────────────────┐
   │  PostgreSQL + pgvector                            │
   │  research_works.embedding   vector(384)           │
   │  opportunities.embedding    vector(384)           │
   │  HNSW index (vector_cosine_ops)                   │
   └──────────────────────────────────────────────────┘
```

---

## Files Created / Modified

### New

| File | Purpose |
|------|---------|
| `ml/embeddings/config.py` | Centralised constants (model name, dim, batch size, device) |
| `ml/embeddings/hash_utils.py` | SHA-256 content hashing + `needs_reembedding()` guard |
| `ml/embeddings/text_builder.py` | Deterministic semantic text builders per entity type |
| `ml/embeddings/service.py` | SentenceTransformer wrapper with lazy loading + batch encoding |
| `ml/embeddings/generate_embeddings.py` | CLI batch-embedding pipeline |
| `backend/alembic/versions/0006_phase2_3b_semantic_embeddings.py` | Migration |
| `scrapers/tests/test_embedding_hash_utils.py` | Hash utility tests |
| `scrapers/tests/test_embedding_text_builder.py` | Text builder tests |
| `scrapers/tests/test_embedding_service.py` | Service tests (mocked model) |
| `scrapers/tests/test_embedding_pipeline.py` | Pipeline tests (mocked DB + model) |

### Modified

| File | Change |
|------|--------|
| `backend/app/models/research_knowledge.py` | Added `embedding`, `content_hash`, `embedding_model`, `embedded_at` to `ResearchWorkModel` |
| `backend/app/models/opportunity.py` | Added `content_hash`, `embedding_model`, `embedded_at` to `OpportunityModel` (embedding already existed) |
| `backend/app/core/config.py` | Added `embedding_model`, `embedding_dim`, `embedding_batch_size`, `embedding_device` |
| `backend/requirements.txt` | Added `sentence-transformers==3.3.1` |
| `.env.example` | Added embedding config section |
| `ml/embeddings/__init__.py` | Exported public symbols |

---

## Database Schema Changes

### Migration `0006_phase2_3b_semantic_embeddings`

**`research_works` table — new columns:**

| Column | Type | Description |
|--------|------|-------------|
| `embedding` | `vector(384)` | 384-dim L2-normalised embedding |
| `content_hash` | `VARCHAR(64)` | SHA-256 of the semantic text |
| `embedding_model` | `VARCHAR(100)` | Model name used to generate embedding |
| `embedded_at` | `TIMESTAMP WITH TIME ZONE` | Last embedding timestamp |

**`opportunities` table — new columns:**

| Column | Type | Description |
|--------|------|-------------|
| `content_hash` | `VARCHAR(64)` | SHA-256 of the semantic text |
| `embedding_model` | `VARCHAR(100)` | Model name |
| `embedded_at` | `TIMESTAMP WITH TIME ZONE` | Last embedding timestamp |

> The `opportunities.embedding vector(384)` column already existed from Phase 1.

**Indexes created:**

| Index | Table | Type | Operator |
|-------|-------|------|---------|
| `idx_research_works_embedding_hnsw` | `research_works` | HNSW | `vector_cosine_ops` |
| `idx_research_works_content_hash` | `research_works` | B-tree | — |
| `idx_opportunities_embedding_hnsw` | `opportunities` | HNSW | `vector_cosine_ops` |
| `idx_opportunities_content_hash` | `opportunities` | B-tree | — |

---

## Embedding Model

| Property | Value |
|----------|-------|
| Model | `all-MiniLM-L6-v2` |
| Dimensions | 384 |
| Max sequence length | 512 tokens |
| Normalisation | L2 (enables cosine similarity via dot product) |
| Source | HuggingFace / `sentence-transformers` |

The model is downloaded from HuggingFace Hub on first use and cached locally.

---

## Content Hashing

**Algorithm:** SHA-256 over the UTF-8 bytes of the normalised semantic text.

**Purpose:** An embedding is regenerated if and only if:
1. The record has never been embedded (`content_hash IS NULL`), or
2. The semantic text has changed (hash mismatch), or
3. A different model is now configured (model name mismatch).

This ensures the pipeline is **idempotent** and **fast on re-runs** — only changed
records incur model inference cost.

---

## Semantic Text Construction

### `ResearchWorkModel`

```
{title} | {abstract} | {work_type} {publication_year} [{language if non-English}]
```

- Title is required (ValueError if missing)
- Abstract included when present
- Publication year and work_type appended as metadata
- Non-English language appended (English is omitted to save tokens)
- Truncated at 8 192 characters (word boundary)

### `OpportunityModel`

```
{title} {opportunity_type} | {summary} [{description}] | {publisher}, {organizer}, {series_name}, {location}
```

- Title is required
- Summary preferred; description included only if different from summary
- Organisational context (publisher, organizer, series, location) forms the third segment

---

## CLI Usage

```bash
# Embed all research works
python -m ml.embeddings.generate_embeddings --entity research_work

# Embed all opportunities
python -m ml.embeddings.generate_embeddings --entity opportunity

# Dry-run (no DB writes)
python -m ml.embeddings.generate_embeddings --entity research_work --dry-run

# Force re-embed everything regardless of hash
python -m ml.embeddings.generate_embeddings --entity research_work --force

# Custom batch size and record limit
python -m ml.embeddings.generate_embeddings \
    --entity research_work \
    --batch-size 16 \
    --limit 500

# GPU
python -m ml.embeddings.generate_embeddings \
    --entity research_work \
    --device cuda
```

---

## Similarity Search (pgvector)

Once embeddings are generated, nearest-neighbour queries use the `<=>` cosine distance operator:

```sql
-- Top-5 research works semantically similar to a query embedding
SELECT id, title, embedding <=> '[0.1, 0.2, ...]'::vector AS distance
FROM research_works
WHERE embedding IS NOT NULL
ORDER BY distance
LIMIT 5;
```

The HNSW index (`vector_cosine_ops`) makes this fast at scale.

---

## Configuration

| Environment Variable | Default | Description |
|----------------------|---------|-------------|
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | HuggingFace model name |
| `EMBEDDING_DIM` | `384` | Embedding dimensionality |
| `EMBEDDING_BATCH_SIZE` | `32` | Records per encoding batch |
| `EMBEDDING_DEVICE` | `cpu` | PyTorch device: `cpu`, `cuda`, `mps` |

---

## What This Phase Does NOT Implement

- Recommendation engine (Phase 3+)
- Real-time embedding on ingestion (future: embed at write time)
- Multi-model support or model versioning
- Streaming / async batch processing (Celery, Kafka, Airflow)
- Approximate search API endpoint (reserved for API layer)

---

## Verification

```bash
# 1. Run all tests
cd <project root>
pytest scrapers/tests/ -v

# 2. Validate imports
python -c "from ml.embeddings.service import EmbeddingService; print('OK')"
python -c "from ml.embeddings.text_builder import build_research_work_text; print('OK')"
python -c "from ml.embeddings.hash_utils import compute_content_hash; print('OK')"

# 3. Dry-run pipeline
python -m ml.embeddings.generate_embeddings --entity research_work --dry-run

# 4. Apply migration (requires running PostgreSQL)
cd backend && alembic upgrade head && alembic current
```
