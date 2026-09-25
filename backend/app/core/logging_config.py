"""
Phase 6 — Structured logging with request correlation.

`configure_logging()` installs one root handler that emits either human-readable text or
single-line JSON records. Every record carries the current request's correlation ID
(propagated from / returned as `X-Request-ID`).
"""
from __future__ import annotations

from contextvars import ContextVar
from datetime import datetime, timezone
import json
import logging
import sys
from typing import Any

request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)

_HANDLER_NAME = "researchconnect-root"

# Attributes present on every LogRecord; anything else was passed via `extra=` and is emitted.
_RESERVED_RECORD_ATTRS = frozenset(
    vars(logging.LogRecord("", 0, "", 0, "", None, None)).keys()
    | {"message", "asctime", "request_id"}
)


class ContextFilter(logging.Filter):
    """Copies the request-scoped correlation ID onto each record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get()
        return True


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = getattr(record, "request_id", None)
        if request_id:
            entry["request_id"] = request_id
        for key, value in vars(record).items():
            if key not in _RESERVED_RECORD_ATTRS and not key.startswith("_"):
                entry[key] = value
        if record.exc_info:
            entry["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


class TextLogFormatter(logging.Formatter):
    def __init__(self) -> None:
        super().__init__("%(asctime)s %(levelname)-7s %(name)s [%(request_id)s] %(message)s")

    def format(self, record: logging.LogRecord) -> str:
        if getattr(record, "request_id", None) is None:
            record.request_id = "-"
        return super().format(record)


def configure_logging(level: str = "INFO", fmt: str = "text") -> None:
    """Idempotently installs the application's root log handler."""
    root = logging.getLogger()
    for handler in list(root.handlers):
        if handler.get_name() == _HANDLER_NAME:
            root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.set_name(_HANDLER_NAME)
    handler.addFilter(ContextFilter())
    handler.setFormatter(JsonLogFormatter() if fmt.lower() == "json" else TextLogFormatter())
    root.addHandler(handler)
    root.setLevel(level.upper())
