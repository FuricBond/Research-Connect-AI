# PostgreSQL and pgvector

The local database stores normalized research opportunities and vector embeddings for semantic matching.

Initial table:

```text
opportunities
  id
  title
  source
  opportunity_type
  deadline
  url
  summary
  embedding
  created_at
```

The `embedding` column uses `vector(1536)` as a practical starting point. This can be changed later if the chosen embedding model uses a different dimension.
