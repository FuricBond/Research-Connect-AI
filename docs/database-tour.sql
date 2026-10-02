-- ResearchConnect AI: a short guided tour of the database, for demonstrations.
-- Open this file in pgAdmin's Query Tool (or any PostgreSQL client), select ONE query,
-- and run it with F5 (pgAdmin runs only the selected text). Every query is read-only.


-- 1. What is stored: the main tables and how many rows each holds.
SELECT 'research_works (papers)'        AS table_name, count(*) AS row_count FROM research_works
UNION ALL SELECT 'opportunities (calls for papers)', count(*) FROM opportunities
UNION ALL SELECT 'topics (taxonomy)',               count(*) FROM topics
UNION ALL SELECT 'users',                           count(*) FROM users
UNION ALL SELECT 'research_postings',               count(*) FROM research_postings
UNION ALL SELECT 'research_posting_applications',   count(*) FROM research_posting_applications
UNION ALL SELECT 'notifications',                   count(*) FROM notifications;


-- 2. Platform users by role (the password column holds bcrypt hashes, so it is left out).
SELECT role, count(*) AS accounts
FROM users
GROUP BY role
ORDER BY accounts DESC;


-- 3. How the paper corpus (collected from OpenAlex) spreads across publication years.
SELECT publication_year, count(*) AS papers, sum(cited_by_count) AS total_citations
FROM research_works
WHERE publication_year IS NOT NULL
GROUP BY publication_year
ORDER BY publication_year DESC;


-- 4. Open calls for papers, with their real conference links (from WikiCFP).
SELECT title, opportunity_type, location,
       submission_deadline::date AS deadline, website_url
FROM opportunities
WHERE status = 'ACTIVE' AND submission_deadline > now()
ORDER BY submission_deadline
LIMIT 15;


-- 5. The two venues flagged as predatory, and the warning signs in their own text that the
--    risk engine detects (its risk score is computed live by the app, not stored here).
SELECT title, publisher, description
FROM opportunities
WHERE is_predatory_flag;


-- 6. Every paper carries a 384-dimensional semantic embedding (pgvector).
SELECT title, vector_dims(embedding) AS dimensions, embedding_model
FROM research_works
WHERE embedding IS NOT NULL
LIMIT 5;


-- 7. Semantic search inside the database: the papers closest in meaning to one paper,
--    ranked by cosine similarity through the HNSW vector index.
SELECT other.title,
       round((1 - (other.embedding <=> source.embedding))::numeric, 3) AS similarity
FROM research_works AS source
JOIN research_works AS other ON other.id <> source.id
WHERE source.title = 'Information Retrieval: Recent Advances and Beyond'
  AND other.embedding IS NOT NULL
ORDER BY other.embedding <=> source.embedding
LIMIT 10;


-- 8. Keyword (full-text) search, the lexical channel of hybrid search.
SELECT title, publication_year,
       round(ts_rank_cd(fts_vector, query)::numeric, 3) AS rank
FROM research_works, websearch_to_tsquery('english', 'graph neural networks') AS query
WHERE fts_vector @@ query
ORDER BY rank DESC
LIMIT 10;


-- 9. Faculty postings and how many students applied to each.
SELECT p.title, p.posting_type, p.status, u.full_name AS author,
       count(a.id) AS applications
FROM research_postings AS p
JOIN users AS u ON u.id = p.author_user_id
LEFT JOIN research_posting_applications AS a ON a.posting_id = p.id
GROUP BY p.id, u.full_name
ORDER BY applications DESC
LIMIT 10;


-- 10. Schema version: the Alembic migration the database is on.
SELECT version_num FROM alembic_version;
