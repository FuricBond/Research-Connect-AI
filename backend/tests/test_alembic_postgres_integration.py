"""Opt-in regression coverage for a clean PostgreSQL Alembic upgrade.

Run with ``RUN_POSTGRES_MIGRATION_TESTS=1`` and a PostgreSQL ``DATABASE_URL``.
The test creates and drops an isolated database; it is deliberately opt-in so the
ordinary SQLite-oriented unit suite never touches a developer's database server.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_MIGRATION_TESTS") != "1",
    reason="set RUN_POSTGRES_MIGRATION_TESTS=1 to run destructive isolated PostgreSQL migration coverage",
)


def test_fresh_postgres_upgrade_supports_long_revision_ids() -> None:
    """A fresh upgrade must not recreate Alembic's default VARCHAR(32) table."""
    base_url = make_url(os.environ["DATABASE_URL"])
    database_name = f"researchconnect_alembic_{uuid.uuid4().hex}"
    verification_url = base_url.set(database=database_name)
    admin_engine = create_engine(base_url.set(database="postgres"), isolation_level="AUTOCOMMIT")

    try:
        with admin_engine.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{database_name}"'))

        env = os.environ.copy()
        env["DATABASE_URL"] = verification_url.render_as_string(hide_password=False)
        completed = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=Path(__file__).resolve().parents[1],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr

        verification_engine = create_engine(verification_url)
        try:
            with verification_engine.connect() as connection:
                revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                max_length = connection.execute(
                    text(
                        "SELECT character_maximum_length "
                        "FROM information_schema.columns "
                        "WHERE table_schema = 'public' "
                        "AND table_name = 'alembic_version' "
                        "AND column_name = 'version_num'"
                    )
                ).scalar_one()
        finally:
            verification_engine.dispose()

        assert revision == "0024_phase6_feedback_history"
        assert max_length >= len(revision)
    finally:
        admin_engine.dispose()
        cleanup_engine = create_engine(base_url.set(database="postgres"), isolation_level="AUTOCOMMIT")
        try:
            with cleanup_engine.connect() as connection:
                connection.execute(
                    text(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname = :database_name"
                    ),
                    {"database_name": database_name},
                )
                connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}"'))
        finally:
            cleanup_engine.dispose()
