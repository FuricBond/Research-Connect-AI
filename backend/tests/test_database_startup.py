"""
Phase 6.5 — Database and migration startup.

A fresh environment must go: PostgreSQL ready -> `alembic upgrade head` -> backend starts ->
application works. These tests need no database server:

  A  the migration chain itself: one head, linear, every revision reversible and recordable
  B  classifying a database's recorded revisions against this code's head
  C  GET /api/health/ready: 200 only when the database answers and the schema is current
  D  the production startup gate: refuses a schema that is not current, skipped elsewhere
  E  the Compose file gates the frontend on readiness, and migrations are serialized

The same guarantees against a real PostgreSQL server (fresh upgrade, round trip, concurrent
runs, model parity) are in test_alembic_postgres_integration.py, opt-in.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import re
from unittest.mock import MagicMock

from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db import schema_status
from app.db.schema_status import (
    ALEMBIC_DIR,
    SchemaNotReadyError,
    SchemaStatus,
    check_schema,
    classify,
    code_heads,
    ensure_schema_current,
)
from app.db.session import get_db
from app.main import app
from app.scheduler import lifecycle

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent


@pytest.fixture(scope="module")
def script() -> ScriptDirectory:
    return ScriptDirectory(str(ALEMBIC_DIR))


# ── A. The migration chain ────────────────────────────────────────────────────


def test_a_the_chain_has_exactly_one_head(script):
    """Two migrations branching from the same parent would leave `upgrade head` ambiguous."""
    assert len(script.get_heads()) == 1, script.get_heads()
    assert code_heads() == tuple(script.get_heads())


def test_a_the_chain_is_linear_from_base_to_head(script):
    revisions = list(script.walk_revisions())  # head first
    assert revisions[-1].down_revision is None, "the oldest revision must start from an empty database"
    for newer, older in zip(revisions, revisions[1:]):
        assert newer.down_revision == older.revision, f"{newer.revision} does not follow {older.revision}"
    assert len({r.revision for r in revisions}) == len(revisions)
    assert len(revisions) == len(list(ALEMBIC_DIR.joinpath("versions").glob("*.py")))


def test_a_every_revision_id_fits_the_widened_version_column(script):
    """env.py and init.sql widen alembic_version.version_num to 255; Alembic's default is 32."""
    lengths = {r.revision: len(r.revision) for r in script.walk_revisions()}
    assert max(lengths.values()) <= 255
    assert any(n > 32 for n in lengths.values()), "the widening exists for these long IDs"


def test_a_every_revision_can_be_applied_and_reversed(script):
    for rev in script.walk_revisions():
        spec = importlib.util.spec_from_file_location(f"_migration_{rev.revision}", rev.path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert callable(getattr(module, "upgrade", None)), f"{rev.revision} has no upgrade()"
        assert callable(getattr(module, "downgrade", None)), f"{rev.revision} has no downgrade()"


# ── B. Classifying the recorded revision ──────────────────────────────────────


def test_b_the_database_state_is_classified_against_this_codes_head(script):
    head = script.get_current_head()
    older = script.get_revision(head).down_revision
    assert classify((head,)) == "current"
    assert classify((older,)) == "behind"
    assert classify(("9999_written_by_newer_code",)) == "unrecognized"
    assert classify(()) == "uninitialized"


def test_b_only_a_reachable_database_at_head_is_ready():
    head = code_heads()
    assert SchemaStatus("ok", "current", head, head).ready
    assert SchemaStatus("ok", "not_checked", head).ready  # SQLite, built from the models
    for state in ("behind", "unrecognized", "uninitialized", "unknown"):
        assert not SchemaStatus("ok", state, head).ready
    assert not SchemaStatus("unreachable", "unknown", head).ready


# ── C. Readiness endpoint ─────────────────────────────────────────────────────


def _serve(session) -> TestClient:
    app.dependency_overrides[get_db] = lambda: session
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _postgres_session(recorded: list[str] | None) -> MagicMock:
    """A PostgreSQL session whose alembic_version holds `recorded` (None: no such table)."""
    session = MagicMock(spec=Session)
    session.get_bind.return_value.dialect.name = "postgresql"

    def execute(statement, *args, **kwargs):
        sql = str(statement)
        result = MagicMock()
        if "to_regclass" in sql:
            result.scalar.return_value = None if recorded is None else "alembic_version"
        elif "FROM alembic_version" in sql:
            result.scalars.return_value = iter(recorded or [])
        return result

    session.execute.side_effect = execute
    return session


def test_c_liveness_is_unchanged_and_never_touches_the_database():
    unreachable = MagicMock(spec=Session)
    unreachable.execute.side_effect = AssertionError("liveness must not query the database")
    response = _serve(unreachable).get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_c_ready_when_the_database_answers_and_its_schema_is_current():
    response = _serve(_postgres_session(list(code_heads()))).get("/api/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok", "schema": "current"}


def test_c_a_sqlite_database_built_from_the_models_is_ready():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    session = sessionmaker(bind=engine)()
    try:
        response = _serve(session).get("/api/health/ready")
    finally:
        session.close()
        engine.dispose()
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok", "schema": "not_checked"}


@pytest.mark.parametrize(
    "recorded, state",
    [
        (None, "uninitialized"),  # migrations never ran
        ([], "uninitialized"),  # version table created by init.sql, no revision yet
        ("older", "behind"),
        (["9999_written_by_newer_code"], "unrecognized"),
    ],
)
def test_c_not_ready_until_the_schema_is_this_codes_head(script, recorded, state, caplog):
    if recorded == "older":
        recorded = [script.get_revision(script.get_current_head()).down_revision]
    response = _serve(_postgres_session(recorded)).get("/api/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "database": "ok", "schema": state}
    # Revisions go to the server log, never into the public response.
    assert code_heads()[0] in caplog.text
    assert code_heads()[0] not in response.text


def test_c_not_ready_when_the_database_does_not_answer():
    session = MagicMock(spec=Session)
    session.get_bind.return_value.dialect.name = "postgresql"
    session.execute.side_effect = OperationalError("SELECT 1", {}, Exception("connection refused"))
    response = _serve(session).get("/api/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "database": "unreachable", "schema": "unknown"}


def test_c_check_schema_reads_through_a_plain_connection_too():
    engine = create_engine("sqlite:///:memory:")
    with engine.connect() as connection:
        assert check_schema(connection) == SchemaStatus("ok", "not_checked", code_heads())
    engine.dispose()


# ── D. Production startup gate ────────────────────────────────────────────────


def test_d_production_refuses_to_start_on_a_schema_that_is_not_current(monkeypatch):
    def not_current(engine):
        raise SchemaNotReadyError("Refusing to start: database=ok schema=behind")

    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(schema_status, "ensure_schema_current", not_current)
    monkeypatch.setattr(lifecycle, "build_scheduler", lambda cfg: pytest.fail("scheduler built before the gate"))
    monkeypatch.setattr(settings, "scheduler_enabled", True)
    with pytest.raises(SchemaNotReadyError, match="schema=behind"):
        with TestClient(app):
            pass


def test_d_production_starts_once_the_schema_is_current(monkeypatch):
    checked = []
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(schema_status, "ensure_schema_current", lambda engine: checked.append(engine))
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
    assert len(checked) == 1


@pytest.mark.parametrize("env", ["development", "test"])
def test_d_outside_production_startup_opens_no_connection(monkeypatch, env):
    monkeypatch.setattr(settings, "app_env", env)
    monkeypatch.setattr(schema_status, "ensure_schema_current", lambda engine: pytest.fail("checked outside production"))
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200


def test_d_the_refusal_names_the_state_and_the_fix_without_credentials():
    engine = MagicMock()
    connection = engine.connect.return_value.__enter__.return_value
    connection.dialect.name = "postgresql"
    older = "0027_phase5_11_openings_and_applications"

    def execute(statement, *args, **kwargs):
        result = MagicMock()
        if "to_regclass" in str(statement):
            result.scalar.return_value = "alembic_version"
        else:
            result.scalars.return_value = iter([older])
        return result

    connection.execute.side_effect = execute
    with pytest.raises(SchemaNotReadyError) as raised:
        ensure_schema_current(engine)
    message = str(raised.value)
    assert "schema=behind" in message and older in message and code_heads()[0] in message
    assert "alembic upgrade head" in message


def test_d_an_unreachable_database_is_refused_in_production():
    engine = MagicMock()
    engine.connect.side_effect = OperationalError("connect", {}, Exception("connection refused"))
    with pytest.raises(SchemaNotReadyError, match="database=unreachable"):
        ensure_schema_current(engine)


# ── E. Deployment wiring ──────────────────────────────────────────────────────


def _service_block(compose: str, name: str) -> str:
    match = re.search(rf"\n  {name}:\n(.*?)(?=\n  [a-z][\w-]*:\n|\nvolumes:)", compose, re.S)
    assert match, f"{name} service not found in docker-compose.yml"
    return match.group(1)


def test_e_compose_runs_migrations_before_the_api_and_gates_the_frontend_on_readiness():
    compose = (REPO / "docker-compose.yml").read_text(encoding="utf-8")
    migrate, backend, frontend = (_service_block(compose, n) for n in ("migrate", "backend", "frontend"))
    assert "wait_for_db && alembic upgrade head" in migrate
    assert re.search(r"migrate:\s*\n\s*condition: service_completed_successfully", backend)
    assert "/api/health/ready" in backend
    assert re.search(r"backend:\s*\n\s*condition: service_healthy", frontend)


def test_e_migration_runs_are_serialized_by_an_advisory_lock():
    env = (BACKEND / "alembic" / "env.py").read_text(encoding="utf-8")
    assert "pg_advisory_lock" in env and "pg_advisory_unlock" in env
    # The lock is taken before the version-table pre-flight and the migration transaction.
    assert env.index("_acquire_migration_lock(connection)") < env.index("_ensure_wide_version_table(connection)\n            context")
