"""
Phase 6.4 — Production configuration.

The Phase 6 specification for 6.4: audit secrets, environment variables, CORS, JWT
configuration, database credentials, debug mode, logging, the frontend API URL, scheduler
settings and seed-data settings; keep secrets out of source, Dockerfiles, committed .env
files and frontend bundles; and make sure development defaults can never silently become
production authentication bypasses.

  A  settings validation that applies in every environment (ranges, closed sets, formats)
  B  production startup validation (validate_security_settings)
  C  the real application refusing insecure production configuration at import
  D  API docs are not served in production unless explicitly enabled
  E  the demo seeder in production (no public password, never logged)
  F  committed configuration: templates, Compose, Dockerfiles carry no secrets or bypasses
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile

from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core import security
from app.core.config import DEVELOPMENT_DATABASE_URL, Settings, settings
from app.core.security import verify_password
from app.db.types import TSVector, Vector
from app.main import app
from app.models.base import Base
from app.models.user import UserModel
from scripts import seed_demo_data

# The same SQLite stand-ins every other suite registers (these registrations are global).
compiles(JSONB, "sqlite")(lambda type_, compiler, **kw: "JSON")
compiles(Vector, "sqlite")(lambda type_, compiler, **kw: "TEXT")
compiles(TSVector, "sqlite")(lambda type_, compiler, **kw: "TEXT")

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
# Generated per run, like a real deployment secret; never a literal in the suite.
GOOD_SECRET = secrets.token_urlsafe(48)
PRODUCTION_DATABASE_URL = f"postgresql+psycopg://rc_app:{secrets.token_urlsafe(16)}@db.internal:5432/researchconnect"


def make_settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


def production(**overrides) -> Settings:
    values = dict(
        app_env="production",
        auth_secret_key=GOOD_SECRET,
        database_url=PRODUCTION_DATABASE_URL,
    )
    values.update(overrides)
    return make_settings(**values)


def validate(monkeypatch, cfg: Settings) -> None:
    monkeypatch.setattr(security, "settings", cfg)
    security.validate_security_settings()


# ── A. Settings validation in every environment ───────────────────────────────


@pytest.mark.parametrize("raw", ["production", "Production", "PRODUCTION", "  production  "])
def test_a_app_env_is_normalized_so_a_capitalized_value_is_still_production(raw):
    assert make_settings(app_env=raw).app_env == "production"


@pytest.mark.parametrize("raw", ["prod", "staging", "live", "production-eu", ""])
def test_a_an_unknown_app_env_is_refused_instead_of_running_as_development(raw):
    with pytest.raises(ValidationError, match="app_env"):
        make_settings(app_env=raw)


def test_a_app_env_accepts_exactly_three_environments():
    assert {make_settings(app_env=v).app_env for v in ("development", "test", "production")} == {
        "development",
        "test",
        "production",
    }
    assert make_settings().app_env == "development"


@pytest.mark.parametrize("algorithm", ["HS256", "HS384", "HS512"])
def test_a_symmetric_jwt_algorithms_are_accepted(algorithm):
    assert make_settings(auth_algorithm=algorithm).auth_algorithm == algorithm


@pytest.mark.parametrize("algorithm", ["none", "None", "RS256", "ES256", "hs256", ""])
def test_a_other_jwt_algorithms_are_refused(algorithm):
    with pytest.raises(ValidationError, match="auth_algorithm"):
        make_settings(auth_algorithm=algorithm)


@pytest.mark.parametrize(
    ("field", "accepted", "refused"),
    [
        ("auth_access_token_expire_minutes", [1, 480, 10_080], [0, -5, 10_081]),
        ("auth_bcrypt_rounds", [4, 12, 31], [3, 32]),
        ("auth_login_rate_limit_per_minute", [1, 10], [0, -1]),
        ("discovery_rate_limit_per_minute", [1, 60], [0]),
    ],
)
def test_a_numeric_auth_settings_are_bounded(field, accepted, refused):
    for value in accepted:
        assert getattr(make_settings(**{field: value}), field) == value
    for value in refused:
        with pytest.raises(ValidationError, match=field):
            make_settings(**{field: value})


def test_a_log_settings_are_normalized_and_validated():
    assert make_settings(log_level=" info ").log_level == "INFO"
    assert make_settings(log_level="debug").log_level == "DEBUG"
    assert make_settings(log_format="JSON").log_format == "json"
    for bad in ("verbose", "TRACE", ""):
        with pytest.raises(ValidationError, match="log_level"):
            make_settings(log_level=bad)
    for bad in ("jsn", "xml"):
        with pytest.raises(ValidationError, match="log_format"):
            make_settings(log_format=bad)


def test_a_exact_cors_origins_are_accepted():
    origins = ["http://localhost:3000", "http://127.0.0.1:3000", "https://researchconnect.example.org"]
    assert make_settings(cors_origins=origins).cors_origins == origins
    assert make_settings(cors_origins=[]).cors_origins == []


@pytest.mark.parametrize(
    "origin",
    [
        "*",
        "https://*.example.org",
        "http://localhost:3000/",
        "http://localhost:3000/app",
        "localhost:3000",
        "ftp://example.org",
        "https://user:pw@example.org",
        "HTTP://LOCALHOST:3000",
        "http://localhost:3000?x=1",
        "http://localhost:99999",
        "https://",
    ],
)
def test_a_wildcard_and_malformed_cors_origins_are_refused(origin):
    with pytest.raises(ValidationError, match="cors_origins"):
        make_settings(cors_origins=["http://localhost:3000", origin])


def test_a_cors_wildcard_from_the_environment_is_refused(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", '["*"]')
    with pytest.raises(ValidationError, match="'\\*' is not allowed"):
        Settings(_env_file=None)


# ── B. Production startup validation ──────────────────────────────────────────


def test_b_a_complete_production_configuration_is_accepted(monkeypatch):
    validate(monkeypatch, production())


def test_b_development_enforces_nothing_at_startup(monkeypatch):
    validate(
        monkeypatch,
        make_settings(app_env="development", auth_secret_key="", auth_dev_identity_enabled=True, auth_bcrypt_rounds=4),
    )


def test_b_a_capitalized_production_env_can_no_longer_enable_developer_identity(monkeypatch):
    """The bypass this phase closes: APP_ENV=Production used to skip every production check."""
    with pytest.raises(RuntimeError, match="AUTH_DEV_IDENTITY_ENABLED must be false"):
        validate(monkeypatch, production(app_env="Production", auth_dev_identity_enabled=True))


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"auth_secret_key": ""}, "AUTH_SECRET_KEY must be at least 32 characters"),
        ({"auth_secret_key": "x" * 31}, "AUTH_SECRET_KEY must be at least 32 characters"),
        ({"auth_secret_key": "a" * 64}, "too repetitive"),
        ({"auth_secret_key": "changeme" * 8}, "too repetitive"),
        ({"auth_dev_identity_enabled": True}, "AUTH_DEV_IDENTITY_ENABLED must be false"),
        ({"auth_bcrypt_rounds": 4}, "AUTH_BCRYPT_ROUNDS must be at least 10"),
        ({"database_url": DEVELOPMENT_DATABASE_URL}, "DATABASE_URL must be set explicitly"),
        (
            {"database_url": "postgresql+psycopg://researchconnect:researchconnect@postgres:5432/researchconnect"},
            "DATABASE_URL must be set explicitly",
        ),
    ],
)
def test_b_insecure_production_configuration_is_refused(monkeypatch, overrides, message):
    with pytest.raises(RuntimeError, match=re.escape(message)):
        validate(monkeypatch, production(**overrides))


def test_b_production_accepts_generated_secrets_and_other_database_credentials(monkeypatch):
    validate(monkeypatch, production(auth_secret_key=secrets.token_hex(32)))  # 16-character alphabet
    validate(monkeypatch, production(auth_bcrypt_rounds=10))
    validate(monkeypatch, production(database_url="postgresql+psycopg://rc@/researchconnect?host=/run/postgresql"))


def test_b_every_production_problem_is_reported_at_once(monkeypatch):
    cfg = production(
        auth_secret_key="short",
        auth_dev_identity_enabled=True,
        auth_bcrypt_rounds=4,
        database_url=DEVELOPMENT_DATABASE_URL,
    )
    with pytest.raises(RuntimeError) as refused:
        validate(monkeypatch, cfg)
    text = str(refused.value)
    assert text.startswith("Refusing to start with APP_ENV=production")
    for fragment in ("AUTH_SECRET_KEY", "AUTH_DEV_IDENTITY_ENABLED", "AUTH_BCRYPT_ROUNDS", "DATABASE_URL"):
        assert fragment in text
    assert GOOD_SECRET not in text and "short" not in text, "the secret itself is never echoed"


def test_b_debug_logging_in_production_is_flagged(monkeypatch, caplog):
    caplog.set_level(logging.WARNING, logger="app.core.security")
    validate(monkeypatch, production(log_level="DEBUG"))
    assert "LOG_LEVEL=DEBUG with APP_ENV=production" in caplog.text
    caplog.clear()
    validate(monkeypatch, production(log_level="INFO"))
    assert "LOG_LEVEL=DEBUG" not in caplog.text


def test_b_production_never_falls_back_to_an_ephemeral_signing_key(monkeypatch):
    monkeypatch.setattr(security, "settings", production(auth_secret_key=""))
    with pytest.raises(RuntimeError, match="AUTH_SECRET_KEY must be set"):
        security.get_signing_key()


# ── C. The real application at import ────────────────────────────────────────

_SAFE_ENV_PREFIXES = ("APP_ENV", "AUTH_", "DATABASE_URL", "CORS_", "LOG_", "API_DOCS", "SCHEDULER_", "TRUST_PROXY")

_PROBE = r"""
import json, logging, sys
sys.path.insert(0, sys.argv[1])
from fastapi.testclient import TestClient
from app.main import app
logging.disable(logging.CRITICAL)
client = TestClient(app)
print("RESULT" + json.dumps({p: client.get(p).status_code for p in ("/docs", "/redoc", "/openapi.json", "/api/health")}))
"""


def run_app_import(**env: str) -> subprocess.CompletedProcess:
    clean = {k: v for k, v in os.environ.items() if not k.startswith(_SAFE_ENV_PREFIXES)}
    clean.update({"LOG_LEVEL": "WARNING", **env})
    # Run outside backend/: the settings loader reads .env from the working directory, so
    # a developer's backend/.env would otherwise supply the very settings a test leaves unset.
    with tempfile.TemporaryDirectory() as workdir:
        return subprocess.run(
            [sys.executable, "-c", _PROBE, str(BACKEND)],
            cwd=workdir,
            env=clean,
            capture_output=True,
            text=True,
            timeout=300,
        )


def result_of(proc: subprocess.CompletedProcess) -> dict:
    line = next((l for l in proc.stdout.splitlines() if l.startswith("RESULT")), None)
    assert line, proc.stderr[-2000:]
    return json.loads(line[len("RESULT"):])


def test_c_the_application_refuses_a_capitalized_production_env_with_developer_identity():
    proc = run_app_import(
        APP_ENV="Production",
        AUTH_DEV_IDENTITY_ENABLED="true",
        AUTH_SECRET_KEY=GOOD_SECRET,
        DATABASE_URL=PRODUCTION_DATABASE_URL,
    )
    assert proc.returncode != 0
    assert "AUTH_DEV_IDENTITY_ENABLED must be false" in proc.stderr
    assert GOOD_SECRET not in proc.stderr and GOOD_SECRET not in proc.stdout


def test_c_the_application_refuses_an_unknown_environment_name():
    proc = run_app_import(APP_ENV="prod", AUTH_DEV_IDENTITY_ENABLED="true")
    assert proc.returncode != 0
    assert "app_env" in proc.stderr and "prod" in proc.stderr


def test_c_the_application_refuses_production_without_database_url():
    proc = run_app_import(APP_ENV="production", AUTH_SECRET_KEY=GOOD_SECRET)
    assert proc.returncode != 0
    assert "DATABASE_URL must be set explicitly" in proc.stderr


# ── D. API docs ───────────────────────────────────────────────────────────────


def test_d_production_does_not_serve_api_docs_by_default():
    proc = run_app_import(APP_ENV="production", AUTH_SECRET_KEY=GOOD_SECRET, DATABASE_URL=PRODUCTION_DATABASE_URL)
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert result_of(proc) == {"/docs": 404, "/redoc": 404, "/openapi.json": 404, "/api/health": 200}


def test_d_production_serves_api_docs_only_when_explicitly_enabled():
    proc = run_app_import(
        APP_ENV="production",
        AUTH_SECRET_KEY=GOOD_SECRET,
        DATABASE_URL=PRODUCTION_DATABASE_URL,
        API_DOCS_ENABLED="true",
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert result_of(proc) == {"/docs": 200, "/redoc": 200, "/openapi.json": 200, "/api/health": 200}


def test_d_development_keeps_api_docs_and_the_switch_resolves_as_documented():
    assert TestClient(app).get("/openapi.json").status_code == 200  # this suite runs as development
    assert make_settings(app_env="development").serve_api_docs is True
    assert make_settings(app_env="production").serve_api_docs is False
    assert make_settings(app_env="production", api_docs_enabled=True).serve_api_docs is True
    assert make_settings(app_env="development", api_docs_enabled=False).serve_api_docs is False


# ── E. Demo seeder in production ──────────────────────────────────────────────


@pytest.mark.parametrize("requested", [None, seed_demo_data.DEFAULT_PASSWORD])
def test_e_production_refuses_the_public_demo_password(requested):
    with pytest.raises(ValueError, match="APP_ENV=production: pass --password"):
        seed_demo_data.resolve_demo_password(requested, "production")


@pytest.mark.parametrize("requested", ["short", " padded-password ", "x" * 80])
def test_e_a_supplied_password_must_meet_the_registration_policy(requested):
    for env in ("production", "development"):
        with pytest.raises(ValueError, match="--password"):
            seed_demo_data.resolve_demo_password(requested, env)


def test_e_development_keeps_the_public_demo_password_and_accepts_a_chosen_one():
    chosen = secrets.token_urlsafe(16)
    assert seed_demo_data.resolve_demo_password(None, "development") == seed_demo_data.DEFAULT_PASSWORD
    assert seed_demo_data.resolve_demo_password(chosen, "production") == chosen


def test_e_production_seeding_without_a_password_stops_before_touching_the_database(monkeypatch, caplog):
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(seed_demo_data, "SessionLocal", lambda: pytest.fail("the database was opened"))
    monkeypatch.setattr(sys, "argv", ["seed_demo_data"])
    caplog.set_level(logging.ERROR, logger="seed.demo")
    assert seed_demo_data.main() == 2
    assert "public demo password is not accepted" in caplog.text


def _sqlite_session_factory():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def test_e_a_chosen_password_is_used_but_never_logged(monkeypatch, caplog):
    factory = _sqlite_session_factory()
    chosen = secrets.token_urlsafe(16)
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(seed_demo_data, "SessionLocal", factory)
    monkeypatch.setattr(sys, "argv", ["seed_demo_data", "--password", chosen])
    caplog.set_level(logging.DEBUG)

    assert seed_demo_data.main() == 0

    assert chosen not in caplog.text
    assert "with the password given by --password" in caplog.text
    with factory() as db:
        admin = db.execute(select(UserModel).where(UserModel.role == "ADMIN")).scalar_one()
        assert verify_password(chosen, admin.hashed_password)
        assert not verify_password(seed_demo_data.DEFAULT_PASSWORD, admin.hashed_password)


def test_e_development_still_prints_only_the_public_demo_password(monkeypatch, caplog):
    monkeypatch.setattr(seed_demo_data, "SessionLocal", _sqlite_session_factory())
    monkeypatch.setattr(sys, "argv", ["seed_demo_data"])
    caplog.set_level(logging.INFO, logger="seed.demo")
    assert seed_demo_data.main() == 0
    assert f"/ {seed_demo_data.DEFAULT_PASSWORD}" in caplog.text


# ── F. Committed configuration ────────────────────────────────────────────────


def _read(relative: str) -> str:
    return (REPO / relative).read_text(encoding="utf-8")


def _env_file_values(relative: str) -> dict[str, str]:
    values = {}
    for line in _read(relative).splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def test_f_no_real_env_file_is_tracked():
    try:
        tracked = subprocess.run(["git", "ls-files"], cwd=str(REPO), capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git is not available")
    env_files = [p for p in tracked.splitlines() if re.search(r"(^|/)\.env(\.|$)", p) and not p.endswith(".env.example")]
    assert env_files == []


def test_f_templates_ship_empty_secrets():
    root, backend = _env_file_values(".env.example"), _env_file_values("backend/.env.example")
    assert root["POSTGRES_PASSWORD"] == "" and root["AUTH_SECRET_KEY"] == ""
    assert backend["AUTH_SECRET_KEY"] == ""
    assert "CHANGE_ME" in backend["DATABASE_URL"]
    assert Settings.model_fields["auth_secret_key"].default == ""


def test_f_the_backend_template_is_a_valid_development_configuration(tmp_path):
    """Every key must be a real setting, and developer identity is off by default (D3)."""
    env_file = tmp_path / ".env"
    env_file.write_text(_read("backend/.env.example"), encoding="utf-8")
    cfg = Settings(_env_file=env_file)
    assert cfg.app_env == "development"
    assert cfg.auth_dev_identity_enabled is False
    assert cfg.api_docs_enabled is None


def test_f_the_compose_template_values_are_valid_production_settings(tmp_path, monkeypatch):
    template = _env_file_values(".env.example")
    backend_keys = {name.upper() for name in Settings.model_fields}
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(f"{k}={v}" for k, v in template.items() if k in backend_keys and v != ""),
        encoding="utf-8",
    )
    cfg = Settings(_env_file=env_file, auth_secret_key=GOOD_SECRET, database_url=PRODUCTION_DATABASE_URL)
    assert cfg.app_env == "production" and cfg.serve_api_docs is False
    validate(monkeypatch, cfg)


def _backend_service_block(compose: str) -> str:
    match = re.search(r"\n  backend:\n(.*?)(?=\n  [a-z][\w-]*:\n)", compose, re.S)
    assert match, "backend service not found in docker-compose.yml"
    return match.group(1)


def test_f_compose_requires_secrets_and_pins_production_behaviour():
    compose = _read("docker-compose.yml")
    backend = _backend_service_block(compose)
    assert "${POSTGRES_PASSWORD:?" in compose
    assert "AUTH_SECRET_KEY: ${AUTH_SECRET_KEY:?" in backend
    assert 'AUTH_DEV_IDENTITY_ENABLED: "false"' in backend
    assert "APP_ENV: ${APP_ENV:-production}" in backend
    assert "API_DOCS_ENABLED: ${API_DOCS_ENABLED:-false}" in backend
    assert "SCHEDULER_ENABLED: ${SCHEDULER_ENABLED:-false}" in backend
    assert "SCHEDULER_OPPORTUNITY_REFRESH_ENABLED: ${SCHEDULER_OPPORTUNITY_REFRESH_ENABLED:-false}" in backend
    for port in re.findall(r'-\s*"([^"]+:\d+:\d+)"', compose):
        assert port.startswith("127.0.0.1:"), port


def test_f_backend_stop_grace_outlasts_the_scheduler_shutdown_wait():
    from app.scheduler.scheduler import Scheduler
    import inspect

    grace = re.search(r"stop_grace_period:\s*(\d+)s", _backend_service_block(_read("docker-compose.yml")))
    assert grace, "the backend needs an explicit stop_grace_period"
    shutdown_wait = inspect.signature(Scheduler).parameters["shutdown_timeout_seconds"].default
    assert int(grace.group(1)) > shutdown_wait


@pytest.mark.parametrize("dockerfile", ["backend/Dockerfile", "frontend/Dockerfile"])
def test_f_dockerfiles_bake_in_no_secrets(dockerfile):
    for line in _read(dockerfile).splitlines():
        if re.match(r"\s*(ENV|ARG)\s", line):
            assert not re.search(r"SECRET|PASSWORD|TOKEN|API_KEY|DATABASE_URL|PRIVATE", line, re.I), line


def test_f_the_backend_image_does_not_advertise_its_server():
    assert '"--no-server-header"' in _read("backend/Dockerfile")


def _runtime_stage(dockerfile: str) -> str:
    match = re.search(r"^FROM \S+ AS runtime$(.*)", dockerfile, re.S | re.M)
    assert match, "runtime stage not found in backend/Dockerfile"
    return match.group(1)


def test_f_the_backend_image_bakes_in_the_embedding_model_and_runs_offline():
    """F-3: the model is fetched at build time, as the runtime user, and never at runtime."""
    from ml.embeddings.config import DEFAULT_MODEL_NAME

    runtime = _runtime_stage(_read("backend/Dockerfile"))
    user_at = re.search(r"^USER app$", runtime, re.M)
    download = re.search(
        r"""^RUN python -c "from sentence_transformers import SentenceTransformer; """
        r"""SentenceTransformer\('\$\{EMBEDDING_MODEL\}'\)"$""",
        runtime,
        re.M,
    )
    assert user_at, "the runtime stage must drop to the unprivileged user"
    assert download, "the backend image must download the embedding model at build time"
    assert download.start() > user_at.start(), "the model must be cached as the unprivileged user"
    assert re.search(rf"^ARG EMBEDDING_MODEL={re.escape(DEFAULT_MODEL_NAME)}$", runtime, re.M)
    offline = re.search(r"^ENV HF_HUB_OFFLINE=1 \\\n\s+TRANSFORMERS_OFFLINE=1$", runtime, re.M)
    assert offline and offline.start() > download.start(), "go offline only after the download"
    assert 'HF_HOME="/home/app/.cache/huggingface"' in runtime
    # Still a single worker: the rate limiter and discovery cache live in process memory.
    assert "--workers" not in runtime


def test_f_compose_warms_the_embedding_model_by_default():
    backend = _backend_service_block(_read("docker-compose.yml"))
    assert "EMBEDDING_WARMUP_ON_STARTUP: ${EMBEDDING_WARMUP_ON_STARTUP:-true}" in backend
    assert Settings.model_fields["embedding_warmup_on_startup"].default is False
