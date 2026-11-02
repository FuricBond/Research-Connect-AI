"""
The models know about every index the database relies on.

The HNSW and GIN search indexes used to exist only in migrations, so `alembic revision --autogenerate`
would have proposed dropping them, and search with them. These run without a database; the real
comparison against a migrated database is in test_alembic_postgres_integration.py.
"""
from __future__ import annotations

import app.models  # noqa: F401
from app.models.base import Base


def _index(table: str, name: str):
    return next(index for index in Base.metadata.tables[table].indexes if index.name == name)


def test_the_search_indexes_are_declared_with_their_real_methods() -> None:
    for table in ("research_works", "opportunities"):
        gin = _index(table, f"idx_{table}_fts_gin")
        assert gin.dialect_options["postgresql"]["using"] == "gin"
        assert [column.name for column in gin.columns] == ["fts_vector"]

        hnsw = _index(table, f"idx_{table}_embedding_hnsw")
        assert hnsw.dialect_options["postgresql"]["using"] == "hnsw"
        assert hnsw.dialect_options["postgresql"]["ops"] == {"embedding": "vector_cosine_ops"}


def test_openalex_identifiers_stay_unique_in_the_models_as_in_the_database() -> None:
    for table, name in (
        ("institutions", "idx_institutions_openalex_id"),
        ("research_sources", "idx_research_sources_openalex_id"),
        ("research_works", "idx_research_works_openalex_id"),
        ("researchers", "idx_researchers_openalex_id"),
    ):
        assert _index(table, name).unique is True, table


def test_every_single_column_foreign_key_is_indexed_in_the_models() -> None:
    missing = []
    for table in Base.metadata.tables.values():
        leading = {next(iter(index.columns)).name for index in table.indexes}
        leading |= {next(iter(constraint.columns)).name for constraint in table.constraints if hasattr(constraint, "columns") and len(list(constraint.columns)) and constraint.__class__.__name__ in ("UniqueConstraint", "PrimaryKeyConstraint")}
        for key in table.foreign_key_constraints:
            if len(key.columns) == 1 and next(iter(key.columns)).name not in leading:
                missing.append(f"{table.name}.{next(iter(key.columns)).name}")
    assert missing == []
