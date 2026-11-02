#!/usr/bin/env python3
"""
Runs the demonstration environment, isolated from any development stack. See demo/README.md.

    python demo/demo.py up        build from this working tree, start, migrate, seed the demo accounts
    python demo/demo.py status    containers, schema revision, and what source the running images came from
    python demo/demo.py logs      follow the logs (add a service name to narrow it)
    python demo/demo.py stop      stop the containers; the data stays

It never removes a volume. Secrets are generated once, into demo/.env.demo (git-ignored), and never printed.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import secrets
import subprocess
import sys
from datetime import datetime, timezone
import urllib.request

REPO = Path(__file__).resolve().parent.parent
ENV_FILE = REPO / "demo" / ".env.demo"
PROJECT = "rcdemo"
PORTS = {"DEMO_WEB_PORT": 3400, "DEMO_API_PORT": 8400, "DEMO_POSTGRES_PORT": 5446, "DEMO_MAIL_PORT": 8425}
BASE = [
    "docker", "compose", "-p", PROJECT, "--env-file", str(ENV_FILE),
    "-f", str(REPO / "docker-compose.yml"), "-f", str(REPO / "demo" / "compose.demo.yml"),
]


def _read_env() -> dict[str, str]:
    return dict(line.split("=", 1) for line in ENV_FILE.read_text(encoding="utf-8").splitlines() if "=" in line)


def _write_env(values: dict[str, str]) -> None:
    ENV_FILE.write_text("".join(f"{key}={value}\n" for key, value in values.items()), encoding="utf-8")


def _ensure_env() -> dict[str, str]:
    if ENV_FILE.exists():
        return _read_env()
    web, api = PORTS["DEMO_WEB_PORT"], PORTS["DEMO_API_PORT"]
    values = {
        "DEMO_PASSWORD": "Demo-" + secrets.token_urlsafe(14),
        "POSTGRES_USER": "researchconnect",
        "POSTGRES_DB": "researchconnect",
        "POSTGRES_PASSWORD": secrets.token_urlsafe(32),
        "AUTH_SECRET_KEY": secrets.token_hex(32),
        "APP_ENV": "production",
        "CORS_ORIGINS": json.dumps([f"http://localhost:{web}", f"http://127.0.0.1:{web}"]),
        "NEXT_PUBLIC_API_URL": f"http://localhost:{api}",
        "EMAIL_PROVIDER": "smtp",
        "SMTP_HOST": "mailsink",
        "SMTP_PORT": "1025",
        "SMTP_SECURITY": "none",
        "EMAIL_FROM_ADDRESS": "noreply@researchconnect.test",
        "EMAIL_RECIPIENT_ALLOWLIST": "*",
        "APP_PUBLIC_URL": f"http://localhost:{web}",
        **{key: str(value) for key, value in PORTS.items()},
    }
    _write_env(values)
    return values


def _source_identity() -> dict[str, str]:
    """HEAD, and a fingerprint of everything uncommitted, so a dirty tree is never mistaken for a commit."""

    def git(*args: str) -> str:
        return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, check=True).stdout

    head = git("rev-parse", "HEAD").strip()
    changed = git("status", "--porcelain").splitlines()
    digest = hashlib.sha256(git("diff", "HEAD").encode())
    for line in changed:
        if line.startswith("??"):
            path = REPO / line[3:].strip().strip('"')
            if path.is_file():
                digest.update(path.read_bytes())
    return {
        "DEMO_SOURCE_HEAD": head,
        "DEMO_SOURCE_DIRTY": "yes" if changed else "no",
        "DEMO_SOURCE_CHANGED_FILES": str(len(changed)),
        "DEMO_SOURCE_FINGERPRINT": digest.hexdigest()[:16],
        "DEMO_BUILT_UTC": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _compose(*args: str, capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run([*BASE, *args], cwd=REPO, check=True, text=True, capture_output=capture)


def up() -> None:
    values = _ensure_env()
    identity = _source_identity()
    _compose("up", "-d", "--build", "--wait")
    _write_env({**values, **identity})
    _compose("exec", "-T", "backend", "python", "-m", "scripts.seed_demo_data", "--password", values["DEMO_PASSWORD"])
    status()


def status() -> None:
    values = _read_env()
    _compose("ps", "--format", "table {{.Name}}\t{{.Status}}\t{{.Ports}}")
    revision = _compose(
        "exec", "-T", "postgres", "sh", "-c",
        'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -c "select version_num from alembic_version"',
        capture=True,
    ).stdout.strip()
    api, web = values["DEMO_API_PORT"], values["DEMO_WEB_PORT"]
    with urllib.request.urlopen(f"http://127.0.0.1:{api}/api/health/ready", timeout=10) as response:
        ready = json.loads(response.read())
    print(f"\nSchema revision: {revision}\nReadiness:       {ready}")
    print(
        f"Built from:      {values.get('DEMO_SOURCE_HEAD', 'unknown')}"
        f" (uncommitted changes: {values.get('DEMO_SOURCE_DIRTY', 'unknown')},"
        f" {values.get('DEMO_SOURCE_CHANGED_FILES', '?')} files,"
        f" fingerprint {values.get('DEMO_SOURCE_FINGERPRINT', 'unknown')})"
    )
    print(f"Built at:        {values.get('DEMO_BUILT_UTC', 'unknown')}")
    print(f"\nWeb:  http://localhost:{web}\nAPI:  http://localhost:{api}\nMail: http://localhost:{values['DEMO_MAIL_PORT']}/messages?to=<address>")
    print(f"Accounts: demo.student@, demo.faculty@, demo.admin@researchconnect.test. Password: DEMO_PASSWORD in {ENV_FILE.relative_to(REPO)}")


def main() -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "up":
        up()
    elif command == "status":
        status()
    elif command == "logs":
        _compose("logs", "--tail", "100", "-f", *sys.argv[2:])
    elif command == "stop":
        _compose("stop")
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
