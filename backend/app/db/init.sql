-- ResearchConnect AI database initialization
-- Schema management is handled via Alembic migrations.

CREATE EXTENSION IF NOT EXISTS vector;

-- Ensure alembic_version table supports long revision IDs (> 32 characters)
CREATE TABLE IF NOT EXISTS alembic_version (
    version_num VARCHAR(255) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);
