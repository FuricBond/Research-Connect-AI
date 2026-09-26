"""
Wait until the configured database accepts connections (Phase 6.1).

Entry point:
    python -m scripts.wait_for_db [--timeout SECONDS]      (run from the backend/ directory)

Container startup runs this before `alembic upgrade head`. Compose already orders the
migration after PostgreSQL reports healthy, but that ordering is not a guarantee the
database is reachable from this container at this moment (a restart, a slow first
initialisation, or a manual `docker compose run` without the healthcheck gate). Retrying
here keeps the migration step correct without relying on start order alone.

Exits 0 once `SELECT 1` succeeds, 1 if the database is still unreachable at the deadline.
The connection URL is logged with its password masked.
"""
from __future__ import annotations

import argparse
import logging
import time

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

from app.core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("wait.db")

# Short enough to notice a database that is genuinely down, long enough to ride out a
# first-time initialisation.
DEFAULT_TIMEOUT_SECONDS = 60
RETRY_INTERVAL_SECONDS = 2


def wait_for_database(url: str, timeout_seconds: float) -> bool:
    """Returns True once the database answers a trivial query within `timeout_seconds`."""
    engine = create_engine(url, pool_pre_ping=True)
    deadline = time.monotonic() + timeout_seconds
    attempt = 0
    try:
        while True:
            attempt += 1
            try:
                with engine.connect() as connection:
                    connection.execute(text("SELECT 1"))
                logger.info("database reachable after %d attempt(s)", attempt)
                return True
            except OperationalError as exc:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    # The driver's first line names the failure without echoing credentials.
                    reason = str(exc.orig).splitlines()[0] if exc.orig else type(exc).__name__
                    logger.error("database still unreachable after %d attempt(s): %s", attempt, reason)
                    return False
                logger.info("database not ready yet (attempt %d); retrying", attempt)
                time.sleep(min(RETRY_INTERVAL_SECONDS, remaining))
    finally:
        engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description="Wait for the configured database to accept connections.")
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"Seconds to keep retrying (default: {DEFAULT_TIMEOUT_SECONDS})",
    )
    args = parser.parse_args()

    target = make_url(settings.database_url).render_as_string(hide_password=True)
    logger.info("waiting up to %.0fs for %s", args.timeout, target)
    return 0 if wait_for_database(settings.database_url, args.timeout) else 1


if __name__ == "__main__":
    raise SystemExit(main())
