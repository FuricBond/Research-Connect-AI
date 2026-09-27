"""
Phase 6.6 — end-to-end verification runner.

Builds and starts the production Compose stack as an isolated project (own name, ports,
image tags, volume and freshly generated secrets), then verifies it across service
boundaries:

  1. clean startup: PostgreSQL -> migrate -> backend (ready) -> frontend, with timings,
     restart counts and a log scan
  2. the API workflow suite (e2e/api, pytest): real HTTP, bearer tokens, database checks
  3. the browser suite (frontend/e2e, Playwright)
  4. the stack suite: scheduler jobs against the running application, restarts and
     persistence
  5. log collection and a scan for leaked secrets

and removes the project again (`down -v` and its images) unless --keep is given.

Usage (from the repository root, with the backend virtualenv's Python):
    python e2e/run_e2e.py                 # everything
    python e2e/run_e2e.py --skip-build    # reuse the :e2e images from a previous run
    python e2e/run_e2e.py --keep          # leave the stack running afterwards
    python e2e/run_e2e.py --skip-browser  # API and stack suites only
    python e2e/run_e2e.py --reuse e2e/results/<run>   # rerun the suites on a --keep stack

Evidence goes to e2e/results/<UTC timestamp>/ (git-ignored): summary.json, the pytest and
Playwright reports, and every container's log. The generated env file holding the run's
secrets is deleted at teardown.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import re
import secrets
import shutil
import subprocess
import sys
import time
import urllib.request

REPO = Path(__file__).resolve().parents[1]
E2E = REPO / "e2e"
PROJECT = "rce2e"
PORTS = {"E2E_WEB_PORT": 3300, "E2E_API_PORT": 8300, "E2E_POSTGRES_PORT": 5436}
SERVICES = ("postgres", "migrate", "backend", "frontend")
IMAGES = ("researchconnect-backend:e2e", "researchconnect-frontend:e2e")


def log(message: str) -> None:
    print(f"[e2e {datetime.now().strftime('%H:%M:%S')}] {message}", flush=True)


def run(cmd: list[str], *, check: bool = True, capture: bool = True, timeout: float = 3600, env=None, cwd=REPO):
    completed = subprocess.run(
        cmd, cwd=cwd, env=env, text=True, encoding="utf-8", errors="replace",
        capture_output=capture, timeout=timeout,
    )
    if check and completed.returncode != 0:
        tail = (completed.stderr or completed.stdout or "")[-3000:] if capture else ""
        raise SystemExit(f"command failed ({completed.returncode}): {' '.join(cmd[:6])} ...\n{tail}")
    return completed


def version(cmd: list[str]) -> str:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return (out.stdout or out.stderr).strip().splitlines()[0]
    except (OSError, IndexError, subprocess.TimeoutExpired):
        return "unavailable"


class Stack:
    def __init__(self, results: Path) -> None:
        self.results = results
        self.env_file = results / "stack.env"
        self.secrets: dict[str, str] = {}

    @property
    def base(self) -> list[str]:
        return ["docker", "compose", "-p", PROJECT, "--env-file", str(self.env_file),
                "-f", str(REPO / "docker-compose.yml"), "-f", str(E2E / "compose.e2e.yml")]

    def compose(self, *args: str, **kw):
        return run([*self.base, *args], **kw)

    def write_env(self) -> None:
        self.secrets = {
            "POSTGRES_PASSWORD": secrets.token_urlsafe(32),
            "AUTH_SECRET_KEY": secrets.token_hex(32),
            # Meets the registration policy; never the public demo password.
            "E2E_DEMO_PASSWORD": "E2e-" + secrets.token_urlsafe(18),
        }
        web, api = PORTS["E2E_WEB_PORT"], PORTS["E2E_API_PORT"]
        lines = {
            # Read by the suites, not by Compose (an unused variable is ignored there).
            "E2E_DEMO_PASSWORD": self.secrets["E2E_DEMO_PASSWORD"],
            "POSTGRES_USER": "researchconnect",
            "POSTGRES_DB": "researchconnect",
            "POSTGRES_PASSWORD": self.secrets["POSTGRES_PASSWORD"],
            "AUTH_SECRET_KEY": self.secrets["AUTH_SECRET_KEY"],
            "APP_ENV": "production",
            "CORS_ORIGINS": json.dumps([f"http://localhost:{web}", f"http://127.0.0.1:{web}"]),
            "NEXT_PUBLIC_API_URL": f"http://localhost:{api}",
            **{k: str(v) for k, v in PORTS.items()},
        }
        self.env_file.write_text("".join(f"{k}={v}\n" for k, v in lines.items()), encoding="utf-8")

    def load_env(self) -> None:
        values = dict(
            line.split("=", 1) for line in self.env_file.read_text(encoding="utf-8").splitlines() if "=" in line
        )
        self.secrets = {k: values[k] for k in ("POSTGRES_PASSWORD", "AUTH_SECRET_KEY", "E2E_DEMO_PASSWORD")}

    def suite_env(self) -> dict[str, str]:
        web, api, pg = PORTS["E2E_WEB_PORT"], PORTS["E2E_API_PORT"], PORTS["E2E_POSTGRES_PORT"]
        return {
            **os.environ,
            "E2E_API_URL": f"http://127.0.0.1:{api}",
            "E2E_BROWSER_API_URL": f"http://localhost:{api}",
            "E2E_WEB_URL": f"http://localhost:{web}",
            "E2E_DATABASE_URL": (
                f"postgresql+psycopg://researchconnect:{self.secrets['POSTGRES_PASSWORD']}@127.0.0.1:{pg}/researchconnect"
            ),
            "E2E_DEMO_PASSWORD": self.secrets["E2E_DEMO_PASSWORD"],
            "E2E_COMPOSE": json.dumps(self.base),
            "E2E_COMPOSE_SCHEDULER_FILE": str(E2E / "compose.e2e-scheduler.yml"),
            "E2E_RESULTS_DIR": str(self.results),
        }

    def inspect(self) -> dict[str, dict]:
        states = {}
        ids = self.compose("ps", "-a", "-q").stdout.split()
        for cid in ids:
            data = json.loads(run(["docker", "inspect", cid]).stdout)[0]
            service = data["Config"]["Labels"].get("com.docker.compose.service", data["Name"])
            health = (data["State"].get("Health") or {}).get("Status")
            states[service] = {
                "container": data["Name"].lstrip("/"),
                "status": data["State"]["Status"],
                "exit_code": data["State"]["ExitCode"],
                "restart_count": data["RestartCount"],
                "health": health,
                "started_at": data["State"]["StartedAt"],
                "finished_at": data["State"]["FinishedAt"],
            }
        return states

    def logs(self, service: str) -> str:
        return self.compose("logs", "--no-color", "--no-log-prefix", service, check=False).stdout or ""


def _ts(value: str) -> float:
    # Docker reports nanoseconds; datetime accepts microseconds.
    trimmed = re.sub(r"(\.\d{6})\d*", r"\1", value).replace("Z", "+00:00")
    return datetime.fromisoformat(trimmed).timestamp()


def verify_startup(stack: Stack, up_seconds: float) -> dict:
    states = stack.inspect()
    pg0 = _ts(states["postgres"]["started_at"])
    order = {
        "postgres_started": 0.0,
        "migrate_started": round(_ts(states["migrate"]["started_at"]) - pg0, 1),
        "migrate_finished": round(_ts(states["migrate"]["finished_at"]) - pg0, 1),
        "backend_started": round(_ts(states["backend"]["started_at"]) - pg0, 1),
        "frontend_started": round(_ts(states["frontend"]["started_at"]) - pg0, 1),
    }
    migrate_log, backend_log = stack.logs("migrate"), stack.logs("backend")
    checks = {
        "postgres_healthy": states["postgres"]["health"] == "healthy",
        "migrate_exit_0": states["migrate"]["status"] == "exited" and states["migrate"]["exit_code"] == 0,
        "backend_healthy": states["backend"]["health"] == "healthy",
        "frontend_healthy": states["frontend"]["health"] == "healthy",
        "no_restarts": all(s["restart_count"] == 0 for s in states.values()),
        "order_migrate_after_postgres": order["migrate_started"] > 0,
        "order_backend_after_migrate": order["backend_started"] >= order["migrate_finished"],
        "order_frontend_after_backend": order["frontend_started"] > order["backend_started"],
        "backend_schema_check_passed": "database schema check passed" in backend_log and "schema=current" in backend_log,
    }
    with urllib.request.urlopen(f"http://127.0.0.1:{PORTS['E2E_API_PORT']}/api/health/ready", timeout=10) as r:
        ready = json.loads(r.read())
    checks["readiness_current"] = ready == {"status": "ready", "database": "ok", "schema": "current"}
    return {
        "up_seconds": round(up_seconds, 1),
        "timeline_seconds_from_postgres_start": order,
        "migrations_applied": migrate_log.count("Running upgrade"),
        "states": states,
        "readiness": ready,
        "checks": checks,
        "passed": all(checks.values()),
    }


def run_pytest(stack: Stack, name: str, marker: str, extra: list[str]) -> dict:
    junit = stack.results / f"{name}.xml"
    started = time.monotonic()
    completed = run(
        [sys.executable, "-m", "pytest", str(E2E / "api"), "-m", marker, "-p", "no:cacheprovider",
         "-rfEs", f"--junitxml={junit}", *extra],
        check=False, capture=False, env=stack.suite_env(), timeout=7200,
    )
    return {"exit_code": completed.returncode, "seconds": round(time.monotonic() - started, 1), **junit_counts(junit)}


def junit_counts(path: Path) -> dict:
    if not path.exists():
        return {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    text = path.read_text(encoding="utf-8", errors="replace")
    totals = dict.fromkeys(("tests", "failures", "errors", "skipped"), 0)
    for suite in re.findall(r"<testsuite [^>]*>", text):  # Playwright writes one per spec file
        attrs = dict(re.findall(r'(\w+)="([^"]*)"', suite))
        for key in totals:
            totals[key] += int(attrs.get(key, 0))
    return totals


def run_browser(stack: Stack) -> dict:
    frontend = REPO / "frontend"
    npx = shutil.which("npx") or shutil.which("npx.cmd")
    if not npx:
        return {"exit_code": None, "skipped_reason": "npx not found"}
    env = {**stack.suite_env(), "PLAYWRIGHT_JUNIT_OUTPUT_NAME": str(stack.results / "browser.xml")}
    started = time.monotonic()
    completed = run([npx, "playwright", "test", "--reporter=list,junit"], check=False, capture=False,
                    env=env, cwd=frontend, timeout=3600)
    return {"exit_code": completed.returncode, "seconds": round(time.monotonic() - started, 1),
            **junit_counts(stack.results / "browser.xml")}


def snapshot_logs(stack: Stack, label: str) -> None:
    """Saves every container's log. Taken at several points because the stack suite
    recreates containers, which discards the logs written before."""
    target = stack.results / "logs" / label
    target.mkdir(parents=True, exist_ok=True)
    for service in SERVICES:
        (target / f"{service}.log").write_text(stack.logs(service), encoding="utf-8")


ACCESS_5XX = re.compile(r"app\.access \[[^\]]*\] \w+ \S+ 5\d\d\s*$", re.M)


def scan_logs(stack: Stack, tokens_file: Path) -> dict:
    needles = dict(stack.secrets)
    if tokens_file.exists():  # bearer tokens and passwords the suites used
        for i, value in enumerate(tokens_file.read_text(encoding="utf-8").split()):
            needles[f"suite-secret-{i}"] = value
    leaks: dict[str, list[str]] = {}
    tracebacks: dict[str, int] = {}
    server_errors: dict[str, list[str]] = {}
    for log in sorted((stack.results / "logs").glob("*/*.log")):
        name = f"{log.parent.name}/{log.stem}"
        text = log.read_text(encoding="utf-8")
        found = [key for key, value in needles.items() if value and value in text]
        # A JWT-shaped string in a log line is a leak even if the suites did not issue it.
        if re.search(r"eyJ[\w-]{10,}\.eyJ[\w-]{10,}\.[\w-]{10,}", text):
            found.append("jwt-shaped-string")
        if found:
            leaks[name] = found
        tracebacks[name] = text.count("Traceback")
        errors = ACCESS_5XX.findall(text)
        if errors:
            server_errors[name] = errors[:20]
    return {
        "secret_leaks": leaks,
        "tracebacks": {k: v for k, v in tracebacks.items() if v},
        "server_errors_5xx": server_errors,
        "log_files_scanned": len(tracebacks),
        "passed": not leaks and not server_errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 6.6 end-to-end verification")
    parser.add_argument("--keep", action="store_true", help="leave the stack running afterwards")
    parser.add_argument("--skip-build", action="store_true", help="reuse existing :e2e images")
    parser.add_argument("--skip-browser", action="store_true", help="skip the Playwright suite")
    parser.add_argument("--reuse", type=Path, help="results dir of a --keep run: rerun the suites on that stack")
    parser.add_argument("--suites", default="api,browser,stack", help="comma-separated subset to run")
    parser.add_argument("pytest_args", nargs="*", help="extra arguments passed to pytest")
    args = parser.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    suites = set(args.suites.split(","))
    if args.skip_browser:
        suites.discard("browser")
    if args.reuse:
        results = args.reuse.resolve()
        stack = Stack(results)
        stack.load_env()
    else:
        results = E2E / "results" / stamp
        results.mkdir(parents=True)
        stack = Stack(results)
        stack.write_env()
    summary: dict = {
        "started_utc": stamp,
        "environment": {
            "os": f"{platform.system()} {platform.release()} ({platform.version()})",
            "python": platform.python_version(),
            "docker": version(["docker", "version", "--format", "{{.Server.Version}}"]),
            "docker_compose": version(["docker", "compose", "version", "--short"]),
            "node": version([shutil.which("node") or "node", "--version"]),
        },
    }
    try:
        if args.reuse:
            log(f"reusing the running '{PROJECT}' stack from {results}")
        else:
            start_clean(stack, summary, args)

        snapshot_logs(stack, "1-startup")
        if "api" in suites:
            log("API workflow suite")
            summary["api_suite"] = run_pytest(stack, "api", "not stack", args.pytest_args)
        auth_window_end = time.monotonic() + 61  # the login limiter's one-minute window

        if "browser" in suites:
            time.sleep(max(0.0, auth_window_end - time.monotonic()))
            log("browser suite (Playwright)")
            summary["browser_suite"] = run_browser(stack)

        snapshot_logs(stack, "2-workflows")
        if "stack" in suites:
            log("stack suite: scheduler, restarts, persistence")
            summary["stack_suite"] = run_pytest(stack, "stack", "stack", args.pytest_args)
        summary["states_after_suites"] = stack.inspect()
    finally:
        log("collecting logs and scanning for secrets")
        try:
            snapshot_logs(stack, "3-final")
            summary["observability"] = scan_logs(stack, results / "suite_secrets.txt")
        except Exception as exc:  # never let evidence collection hide the real failure
            summary["observability"] = {"error": repr(exc)}
        (results / "suite_secrets.txt").unlink(missing_ok=True)
        if args.keep or args.reuse:
            log(f"stack kept; env file: {stack.env_file}")
        else:
            log("tearing down: down -v, removing :e2e images")
            stack.compose("down", "-v", "--remove-orphans", check=False)
            run(["docker", "image", "rm", *IMAGES], check=False)
            stack.env_file.unlink(missing_ok=True)
        name = "summary.json" if not args.reuse else f"summary-reuse-{stamp}.json"
        (results / name).write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        log(f"evidence: {results / name}")

    suite_results = [summary.get(k, {}) for k in ("api_suite", "browser_suite", "stack_suite")]
    ok = (args.reuse or summary.get("startup", {}).get("passed")) and all(
        s.get("exit_code") in (0, None) for s in suite_results
    ) and summary.get("observability", {}).get("passed")
    for key in ("startup", "api_suite", "browser_suite", "stack_suite"):
        if key in summary:
            shown = {k: v for k, v in summary[key].items() if k != "states"}
            log(f"{key}: {shown}")
    log("RESULT: " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def start_clean(stack: Stack, summary: dict, args) -> None:
    log(f"removing any previous '{PROJECT}' project")
    stack.compose("down", "-v", "--remove-orphans", check=False)
    if not args.skip_build:
        log("building images (backend, frontend)")
        t = time.monotonic()
        stack.compose("build", capture=True, timeout=5400)
        summary["build_seconds"] = round(time.monotonic() - t, 1)
    log("starting a clean stack: docker compose up -d --wait")
    t = time.monotonic()
    up = stack.compose("up", "-d", "--wait", check=False, timeout=900)
    up_seconds = time.monotonic() - t
    if up.returncode != 0:
        summary["startup"] = {"passed": False, "error": (up.stderr or up.stdout)[-3000:], "states": stack.inspect()}
        raise SystemExit("stack did not start; see summary.json and logs/")
    summary["startup"] = verify_startup(stack, up_seconds)
    log(f"startup {'OK' if summary['startup']['passed'] else 'FAILED'} in {up_seconds:.1f}s")


if __name__ == "__main__":
    raise SystemExit(main())
