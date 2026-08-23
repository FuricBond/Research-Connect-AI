CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS opportunities (
    id UUID PRIMARY KEY,
    title TEXT NOT NULL,
    source TEXT NOT NULL,
    opportunity_type TEXT NOT NULL,
    deadline DATE,
    url TEXT,
    summary TEXT,
    embedding vector(1536),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
