"""
Phase 6.5 — Is the database reachable, and is its schema the one this code expects?

The Alembic migration scripts shipped with the code define the schema it was written
against (their head revision). The database records the revision it was migrated to in
`alembic_version`. A backend serving a database that is behind, or that was migrated by
other code, fails on its first query against a missing table or column, which is how the
Phase 3.6/3.7 tables once shipped without a migration and returned 500 on PostgreSQL.

Two callers use this:

- `GET /api/health/ready` reports readiness (503 until the database is reachable and its
  schema is current), and the Compose healthcheck gates the frontend on it.
- The application lifespan refuses to start in production against a schema that is not
  current (`ensure_schema_current`).

Only PostgreSQL is checked. The SQLite databases in the test suite are built from the ORM
metadata, not by Alembic, so their schema is reported as `not_checked`.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
import logging
from pathlib import Path
from typing import Literal

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

ALEMBIC_DIR = Path(__file__).resolve().parents[2] / "alembic"

# Session-level advisory lock that alembic/env.py holds for a whole migration run, so
# concurrent `alembic upgrade` runs against one database are serialized. Derived like the
# scheduler's lock keys (app/scheduler/locks.py), in its own namespace.
MIGRATION_LOCK_KEY = int.from_bytes(
    hashlib.sha256(b"researchconnect-ai:alembic:migrations").digest()[:8], "big", signed=True
)

DatabaseState = Literal["ok", "unreachable"]
# current        the database is at this code's head revision
# behind         the database is at an older revision of this code; run `alembic upgrade head`
# unrecognized   the database records a revision this code does not ship (newer or foreign code)
# uninitialized  no revision recorded: migrations have never run against this database
# unknown        the database could not be asked
# not_checked    not a PostgreSQL database
SchemaState = Literal["current", "behind", "unrecognized", "uninitialized", "unknown", "not_checked"]


@dataclass(frozen=True)
class SchemaStatus:
    database: DatabaseState
    schema: SchemaState
    expected: tuple[str, ...] = ()
    found: tuple[str, ...] = ()

    @property
    def ready(self) -> bool:
        return self.database == "ok" and self.schema in ("current", "not_checked")

    def describe(self) -> str:
        """One line for logs: states plus the revisions involved (never credentials)."""
        found = ", ".join(self.found) or "none"
        expected = ", ".join(self.expected) or "none"
        return f"database={self.database} schema={self.schema} (found: {found}; expected: {expected})"


@lru_cache(maxsize=1)
def _script_revisions() -> tuple[tuple[str, ...], frozenset[str]]:
    """This code's head revision(s) and every revision it ships, read once per process."""
    from alembic.script import ScriptDirectory

    script = ScriptDirectory(str(ALEMBIC_DIR))
    heads = tuple(sorted(script.get_heads()))
    known = frozenset(rev.revision for rev in script.walk_revisions())
    return heads, known


def code_heads() -> tuple[str, ...]:
    return _script_revisions()[0]


def classify(found: tuple[str, ...]) -> SchemaState:
    """Classifies the revisions recorded in `alembic_version` against this code's scripts."""
    heads, known = _script_revisions()
    if not found:
        return "uninitialized"
    if set(found) == set(heads):
        return "current"
    if all(rev in known for rev in found):
        return "behind"
    return "unrecognized"


def check_schema(bind: Connection | Session) -> SchemaStatus:
    """Reads the database's migration state through an open connection or session."""
    expected = code_heads()
    try:
        dialect = bind.get_bind().dialect.name if isinstance(bind, Session) else bind.dialect.name
        bind.execute(text("SELECT 1"))
        if dialect != "postgresql":
            return SchemaStatus("ok", "not_checked", expected)
        # to_regclass is NULL when the table does not exist, without aborting the transaction.
        if bind.execute(text("SELECT to_regclass('alembic_version')")).scalar() is None:
            return SchemaStatus("ok", "uninitialized", expected)
        found = tuple(sorted(bind.execute(text("SELECT version_num FROM alembic_version")).scalars()))
    except DBAPIError as exc:
        # The driver's first line names the failure without echoing credentials.
        reason = str(exc.orig).splitlines()[0] if exc.orig is not None else type(exc).__name__
        logger.warning("database readiness check failed: %s", reason)
        return SchemaStatus("unreachable", "unknown", expected)
    return SchemaStatus("ok", classify(found), expected, found)


def check_engine_schema(engine: Engine) -> SchemaStatus:
    try:
        with engine.connect() as connection:
            return check_schema(connection)
    except DBAPIError as exc:  # raised by connect() itself when the server cannot be reached
        reason = str(exc.orig).splitlines()[0] if exc.orig is not None else type(exc).__name__
        logger.warning("database readiness check failed: %s", reason)
        return SchemaStatus("unreachable", "unknown", code_heads())


class SchemaNotReadyError(RuntimeError):
    """The database is unreachable or its schema does not match this code."""


def ensure_schema_current(engine: Engine) -> SchemaStatus:
    """Raises `SchemaNotReadyError` unless the database is reachable and its schema current."""
    status = check_engine_schema(engine)
    if status.ready:
        logger.info("database schema check passed: %s", status.describe())
        return status
    hint = {
        "behind": "run `alembic upgrade head` (the Compose `migrate` service does this) before starting the API",
        "uninitialized": "no migrations have run against this database; run `alembic upgrade head`",
        "unrecognized": "the database was migrated by code that is not this build; deploy the matching backend",
        "unknown": "check DATABASE_URL and that PostgreSQL is running",
    }.get(status.schema, "")
    raise SchemaNotReadyError(f"Refusing to start: {status.describe()}. {hint}".strip())
