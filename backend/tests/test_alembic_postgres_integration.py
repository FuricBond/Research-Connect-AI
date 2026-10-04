"""Opt-in Phase 6.5 coverage: the migration chain against a real, empty PostgreSQL database.

Run with ``RUN_POSTGRES_MIGRATION_TESTS=1`` and a PostgreSQL ``DATABASE_URL`` whose role may
create databases. Each test creates and drops its own isolated database; the suite is opt-in
so the ordinary SQLite-oriented run never touches a developer's database server.

Covered: a fresh `alembic upgrade head` reaches this code's head (derived from the scripts,
never pinned; a pinned literal went stale for four revisions), installs pgvector without
`init.sql`, and leaves the backend ready; a second run is a no-op; the migrated schema has
every table, column, type, nullability and uniqueness the ORM models declare; every
downgrade works back to an empty database and up again; and concurrent runs are serialized.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
import pytest
from sqlalchemy import UniqueConstraint, create_engine, inspect, text
from sqlalchemy.engine import URL, make_url

from app.db.schema_status import ALEMBIC_DIR, MIGRATION_LOCK_KEY, check_engine_schema
from app.models import Base

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_MIGRATION_TESTS") != "1",
    reason="set RUN_POSTGRES_MIGRATION_TESTS=1 to run destructive isolated PostgreSQL migration coverage",
)

BACKEND = Path(__file__).resolve().parents[1]
SCRIPT = ScriptDirectory(str(ALEMBIC_DIR))
HEAD = SCRIPT.get_current_head()


@contextmanager
def isolated_database() -> Iterator[URL]:
    base_url = make_url(os.environ["DATABASE_URL"])
    name = f"researchconnect_alembic_{uuid.uuid4().hex}"
    admin = create_engine(base_url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{name}"'))
        yield base_url.set(database=name)
    finally:
        with admin.connect() as connection:
            connection.execute(
                text("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = :name"),
                {"name": name},
            )
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
        admin.dispose()


def _alembic_env(url: URL) -> dict[str, str]:
    return {**os.environ, "DATABASE_URL": url.render_as_string(hide_password=False)}


def alembic(url: URL, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND,
        env=_alembic_env(url),
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )


def recorded_revisions(url: URL) -> list[str]:
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            return list(connection.execute(text("SELECT version_num FROM alembic_version")).scalars())
    finally:
        engine.dispose()


def test_fresh_upgrade_reaches_head_and_leaves_the_backend_ready() -> None:
    with isolated_database() as url:
        engine = create_engine(url)
        try:
            # Before any migration the backend must not report ready.
            assert check_engine_schema(engine).schema == "uninitialized"

            completed = alembic(url, "upgrade", "head")
            assert completed.returncode == 0, completed.stderr

            with engine.connect() as connection:
                max_length = connection.execute(
                    text(
                        "SELECT character_maximum_length FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = 'alembic_version' "
                        "AND column_name = 'version_num'"
                    )
                ).scalar_one()
                vector = connection.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")).scalar()
            assert recorded_revisions(url) == [HEAD]
            assert max_length >= max(len(r.revision) for r in SCRIPT.walk_revisions())
            assert vector == 1, "migration 0001 installs pgvector itself; init.sql is not required"

            status = check_engine_schema(engine)
            assert status.ready and status.schema == "current" and status.found == (HEAD,)
        finally:
            engine.dispose()


def test_upgrade_head_is_idempotent() -> None:
    with isolated_database() as url:
        assert alembic(url, "upgrade", "head").returncode == 0
        second = alembic(url, "upgrade", "head")
        assert second.returncode == 0, second.stderr
        assert "Running upgrade" not in second.stderr
        assert recorded_revisions(url) == [HEAD]


def test_readiness_follows_the_recorded_revision() -> None:
    with isolated_database() as url:
        assert alembic(url, "upgrade", "head").returncode == 0
        engine = create_engine(url)
        try:
            assert alembic(url, "downgrade", "-1").returncode == 0
            assert check_engine_schema(engine).schema == "behind"
            assert alembic(url, "upgrade", "head").returncode == 0
            assert check_engine_schema(engine).schema == "current"
            with engine.begin() as connection:
                connection.execute(text("UPDATE alembic_version SET version_num = '9999_written_by_newer_code'"))
            assert check_engine_schema(engine).schema == "unrecognized"
        finally:
            engine.dispose()


# Differences that are not structural. Column comments exist only on the models, and the
# models declare 37 plain single-column indexes that no migration creates (documented in
# docs/architecture/phase6-5-database-startup.md for the performance audit). Both leave
# every query correct. Anything else fails.
_NON_STRUCTURAL = {"modify_comment", "add_index", "remove_index"}


@pytest.mark.filterwarnings("ignore:Computed default on .*fts_vector cannot be modified:UserWarning")
def test_the_migrated_schema_has_everything_the_models_declare() -> None:
    with isolated_database() as url:
        assert alembic(url, "upgrade", "head").returncode == 0
        engine = create_engine(url)
        try:
            with engine.connect() as connection:
                diffs = compare_metadata(MigrationContext.configure(connection), Base.metadata)
            flat = [d for diff in diffs for d in (diff if isinstance(diff, list) else [diff])]
            structural = [d for d in flat if d[0] not in _NON_STRUCTURAL | {"add_constraint", "remove_constraint"}]
            assert not structural, "\n".join(repr(d)[:300] for d in structural)

            # Uniqueness may be implemented under a different name (index vs constraint), but
            # every unique rule the models declare must exist on the same columns.
            inspector = inspect(engine)
            missing = []
            for table in Base.metadata.sorted_tables:
                unique_sets = {tuple(inspector.get_pk_constraint(table.name)["constrained_columns"])}
                unique_sets |= {tuple(u["column_names"]) for u in inspector.get_unique_constraints(table.name)}
                unique_sets |= {tuple(i["column_names"]) for i in inspector.get_indexes(table.name) if i["unique"]}
                declared = [tuple(c.name for c in con.columns) for con in table.constraints if isinstance(con, UniqueConstraint)]
                declared += [tuple(c.name for c in ix.columns) for ix in table.indexes if ix.unique]
                declared += [(c.name,) for c in table.columns if c.unique]
                missing += [f"{table.name}{cols}" for cols in declared if cols not in unique_sets]
            assert not missing, missing
        finally:
            engine.dispose()


def test_every_downgrade_works_back_to_an_empty_database_and_up_again() -> None:
    with isolated_database() as url:
        assert alembic(url, "upgrade", "head").returncode == 0
        down = alembic(url, "downgrade", "base")
        assert down.returncode == 0, down.stderr
        engine = create_engine(url)
        try:
            with engine.connect() as connection:
                tables = set(connection.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")).scalars())
            assert tables == {"alembic_version"}, tables
            assert recorded_revisions(url) == []
        finally:
            engine.dispose()
        up = alembic(url, "upgrade", "head")
        assert up.returncode == 0, up.stderr
        assert recorded_revisions(url) == [HEAD]


def test_concurrent_upgrades_are_serialized_and_both_succeed(tmp_path) -> None:
    """Both runs must wait on the migration lock; released, one migrates and one no-ops."""
    key = MIGRATION_LOCK_KEY
    # Output goes to files, not pipes: a run blocked writing to a full pipe would stall while
    # holding the lock, and the test would deadlock instead of measuring the lock.
    logs = [tmp_path / f"run{i}.log" for i in range(2)]
    with isolated_database() as url:
        holder = create_engine(url)
        runs: list[subprocess.Popen] = []
        try:
            with holder.connect() as connection:
                connection.execute(text("SELECT pg_advisory_lock(:key)"), {"key": key})
                connection.commit()
                for log in logs:
                    with log.open("w", encoding="utf-8") as sink:
                        runs.append(
                            subprocess.Popen(
                                [sys.executable, "-m", "alembic", "upgrade", "head"],
                                cwd=BACKEND,
                                env=_alembic_env(url),
                                stdout=sink,
                                stderr=subprocess.STDOUT,
                            )
                        )
                deadline = time.monotonic() + 120
                waiting = 0
                while time.monotonic() < deadline:
                    waiting = connection.execute(
                        text(
                            "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND NOT granted "
                            "AND database = (SELECT oid FROM pg_database WHERE datname = current_database())"
                        )
                    ).scalar_one()
                    connection.commit()
                    if waiting == 2 or any(run.poll() is not None for run in runs):
                        break
                    time.sleep(0.2)
                assert waiting == 2, "both migration runs should block on the migration lock"
                connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
                connection.commit()
            for run in runs:
                run.wait(timeout=600)
        finally:
            for run in runs:
                if run.poll() is None:
                    run.kill()
            holder.dispose()
        output = [log.read_text(encoding="utf-8", errors="replace") for log in logs]
        assert [run.returncode for run in runs] == [0, 0], [out[-1500:] for out in output]
        assert sum("Running upgrade" in out for out in output) == 1, "exactly one run migrates"
        assert recorded_revisions(url) == [HEAD]


def test_token_version_migration_starts_existing_accounts_at_version_0() -> None:
    """0032 (Phase 6.7): accounts that exist before it keep their sessions (version 0)."""
    with isolated_database() as url:
        assert alembic(url, "upgrade", "0031_phase5_16_email_delivery").returncode == 0
        engine = create_engine(url)
        try:
            user_id = uuid.uuid4()
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO users (id, email, hashed_password, full_name) "
                        "VALUES (:id, 'existing@example.test', 'x', 'Existing Account')"
                    ),
                    {"id": user_id},
                )

            up = alembic(url, "upgrade", "0032_phase6_7_token_revocation")
            assert up.returncode == 0, up.stderr
            with engine.connect() as connection:
                version = connection.execute(
                    text("SELECT token_version FROM users WHERE id = :id"), {"id": user_id}
                ).scalar_one()
            assert version == 0

            down = alembic(url, "downgrade", "0031_phase5_16_email_delivery")
            assert down.returncode == 0, down.stderr
            columns = {c["name"] for c in inspect(engine).get_columns("users")}
            assert "token_version" not in columns
            with engine.connect() as connection:
                assert connection.execute(text("SELECT count(*) FROM users")).scalar_one() == 1
        finally:
            engine.dispose()
