# PostgreSQL and pgvector Foundation

ResearchConnect AI uses PostgreSQL 16 with the `pgvector` extension for storing core research metadata and 384-dimensional vector embeddings (`sentence-transformers/all-MiniLM-L6-v2`).

## Database Configuration

- **Database Engine:** PostgreSQL 16 (`pgvector/pgvector:pg16`)
- **Vector Dimension:** `384` (embedding model: `all-MiniLM-L6-v2`)
- **Connection URL:** `postgresql+psycopg://researchconnect:researchconnect@localhost:5432/researchconnect`
- **Migration Framework:** Alembic (migration: `0001_initial_phase1_schema.py`)

## Phase 1 Schema

The Phase 1 database contains 7 relational tables:

1. **`users`**: Platform users (Students, Faculty, Admins).
2. **`research_profiles`**: Academic domain metadata, keywords, and publication level.
3. **`sources`**: Ingestion sources/feeds (`WikiCFP`, etc.) with health and reliability scores.
4. **`opportunities`**: Core unified opportunities (Conferences, Journals, Workshops, CFPs, Special Issues) with 384-dim embedding vector column and composite unique constraint on `(source_id, raw_source_id)`.
5. **`topics`**: Hierarchical academic domain taxonomy.
6. **`opportunity_topics`**: Many-to-many junction mapping opportunities to topics with extraction confidence scores.
7. **`saved_opportunities`**: User bookmarks and target deadlines.

## Extension Initialization

The extension is enabled automatically via `init.sql` upon container startup:

```sql
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";
```
