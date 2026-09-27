"""
Steps 3–4 — the running stack's database: one migration head, schema current, pgvector,
generated full-text columns and the indexes the workflows depend on.

`alembic current` and `alembic heads` run inside the backend container, the same image and
configuration the `migrate` service used, so this checks the deployed artefact rather than
the source tree.
"""
from __future__ import annotations

import re
import sys

from conftest import REPO, compose, request, rows, scalar

sys.path.insert(0, str(REPO / "backend"))
from alembic.script import ScriptDirectory  # noqa: E402

SCRIPT_HEAD = ScriptDirectory(str(REPO / "backend" / "alembic")).get_current_head()


def _alembic(command: str) -> str:
    result = compose("exec", "-T", "backend", "alembic", command)
    return result.stdout + result.stderr


def test_exactly_one_head_and_the_database_is_at_it(db):
    heads = re.findall(r"^(\w+) \(head\)", _alembic("heads"), re.M)
    current = re.findall(r"^(\w+) \(head\)", _alembic("current"), re.M)
    assert heads == [SCRIPT_HEAD], heads
    assert current == [SCRIPT_HEAD], current
    assert rows(db, "SELECT version_num FROM alembic_version") == [{"version_num": SCRIPT_HEAD}]


def test_readiness_reports_the_current_schema():
    response = request("GET", "/api/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok", "schema": "current"}
    assert request("GET", "/api/health").json() == {"status": "ok"}


def test_pgvector_is_installed_and_operational(db):
    assert scalar(db, "SELECT extversion FROM pg_extension WHERE extname = 'vector'")
    # The 384-dimensional columns accept and compare vectors.
    assert scalar(db, "SELECT '[1,0,0]'::vector <=> '[1,0,0]'::vector") == 0
    types = rows(db, """
        SELECT table_name, format_type(atttypid, atttypmod) AS type
        FROM information_schema.columns c
        JOIN pg_attribute a ON a.attrelid = c.table_name::regclass AND a.attname = c.column_name
        WHERE c.column_name = 'embedding' AND c.table_schema = 'public'
        ORDER BY table_name""")
    assert {r["table_name"]: r["type"] for r in types} == {
        "opportunities": "vector(384)", "research_works": "vector(384)",
    }


def test_generated_full_text_columns_are_computed_by_the_database(db):
    generated = rows(db, """
        SELECT table_name, is_generated FROM information_schema.columns
        WHERE column_name = 'fts_vector' AND table_schema = 'public' ORDER BY table_name""")
    assert generated == [
        {"table_name": "opportunities", "is_generated": "ALWAYS"},
        {"table_name": "research_works", "is_generated": "ALWAYS"},
    ]
    # Every seeded opportunity got one without the application writing it.
    assert scalar(db, "SELECT count(*) FROM opportunities WHERE fts_vector IS NULL") == 0
    assert scalar(db, "SELECT count(*) FROM opportunities WHERE fts_vector @@ plainto_tsquery('english', 'retrieval')") >= 3


def test_indexes_the_workflows_depend_on_exist(db):
    indexes = {r["indexname"]: r["indexdef"] for r in rows(db, "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = 'public'")}
    defs = list(indexes.values())

    def has(fragment: str) -> bool:
        return any(fragment in d for d in defs)

    assert has("USING hnsw (embedding vector_cosine_ops)"), "HNSW vector indexes"
    assert has("ON public.research_works USING gin (fts_vector)") and has("ON public.opportunities USING gin (fts_vector)")
    assert any("UNIQUE INDEX" in d and "ON public.users USING btree (email)" in d for d in defs), "unique account emails"
    unique_cols = {tuple(r["cols"]) for r in rows(db, """
        SELECT array_agg(a.attname ORDER BY a.attnum) AS cols
        FROM pg_index i JOIN pg_class t ON t.oid = i.indrelid
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(i.indkey)
        WHERE i.indisunique AND t.relname = 'notifications' GROUP BY i.indexrelid""")}
    assert ("deduplication_key",) in unique_cols, "notification deduplication relies on this"
