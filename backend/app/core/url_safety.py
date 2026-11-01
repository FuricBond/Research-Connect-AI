"""
Audit SEC-01 — what a stored link may be.

People type these addresses and other people click them, so only plain web addresses are kept:
http or https, with a host, no credentials and no whitespace or control characters. Everything
else (javascript:, data:, vbscript:, ftp:, //host, a bare word) is refused when it is written.

Rows stored before this check keep their value: nothing is deleted behind a person's back. The
frontend never makes a link of a value that fails the same test (utils/safeUrl.ts), and
scripts/report_unsafe_urls.py lists such rows for an administrator to follow up.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit

ALLOWED_URL_SCHEMES = frozenset({"http", "https"})

_UNSAFE_CHARACTERS = re.compile(r"[\s\x00-\x1f\x7f\\]")

UNSAFE_URL_MESSAGE = "Enter a full web address starting with http:// or https://."


def is_safe_web_url(value: str | None) -> bool:
    """Whether `value` is an absolute http(s) address that is safe to offer as a link."""
    if not value or _UNSAFE_CHARACTERS.search(value):
        return False
    try:
        parts = urlsplit(value)
        hostname = parts.hostname
        username = parts.username
        password = parts.password
        # Reading .port is what rejects an impossible port such as :99999.
        _ = parts.port
    except ValueError:
        return False
    if parts.scheme.lower() not in ALLOWED_URL_SCHEMES:
        return False
    return bool(hostname) and username is None and password is None


def validate_web_url(value: str | None) -> str | None:
    """
    Schema validator for an optional link: blank means "no link", surrounding spaces are a
    typing slip, and anything else that is not a web address is refused.
    """
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if not is_safe_web_url(cleaned):
        raise ValueError(UNSAFE_URL_MESSAGE)
    return cleaned


def web_url_or_none(value: str | None) -> str | None:
    """For data arriving from outside (ingestion): keep a web address, drop anything else."""
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned if is_safe_web_url(cleaned) else None
