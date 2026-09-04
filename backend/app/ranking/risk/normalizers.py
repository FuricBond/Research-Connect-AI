"""
Deterministic URL, Domain, and Identifier Normalization for Phase 2.6B.

Operates purely in-memory with zero network calls.
"""
from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlparse

from app.ranking.venue_intelligence import normalize_issn

# Standard DOI pattern: 10.XXXX/...
_DOI_RE = re.compile(r"\b(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)\b")
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


def normalize_url(raw_url: str | None) -> dict[str, str | None]:
    """
    Parse and normalize a website or submission URL.

    Parameters
    ----------
    raw_url:
        Raw input URL string.

    Returns
    -------
    dict[str, str | None]
        Dictionary with keys:
          - 'raw': original string or None
          - 'scheme': 'http', 'https', or None
          - 'hostname': lowercase hostname or None
          - 'domain': registered domain or hostname
          - 'path': URL path
          - 'is_ip': 'true' or 'false'
    """
    if not raw_url or not isinstance(raw_url, str):
        return {
            "raw": None,
            "scheme": None,
            "hostname": None,
            "domain": None,
            "path": None,
            "is_ip": "false",
        }

    clean = raw_url.strip()
    if not clean:
        return {
            "raw": None,
            "scheme": None,
            "hostname": None,
            "domain": None,
            "path": None,
            "is_ip": "false",
        }

    # Prepend scheme if missing for uniform parsing
    parse_target = clean
    if not (clean.startswith("http://") or clean.startswith("https://") or clean.startswith("ftp://")):
        parse_target = f"https://{clean}"

    try:
        parsed = urlparse(parse_target)
        hostname = parsed.hostname.lower() if parsed.hostname else None
        scheme = parsed.scheme.lower() if parsed.scheme else None
        path = parsed.path if parsed.path else None

        is_ip = "false"
        if hostname:
            try:
                ipaddress.ip_address(hostname)
                is_ip = "true"
            except ValueError:
                is_ip = "false"

        # Simple registered domain extraction: take last 2 parts if not IP
        domain = hostname
        if hostname and is_ip == "false":
            parts = hostname.split(".")
            if len(parts) >= 2:
                # Handle second-level domains like .co.uk, .ac.uk, .edu.cn
                if len(parts) >= 3 and parts[-2] in ("co", "ac", "edu", "org", "gov", "net", "com"):
                    domain = ".".join(parts[-3:])
                else:
                    domain = ".".join(parts[-2:])

        return {
            "raw": clean,
            "scheme": scheme,
            "hostname": hostname,
            "domain": domain,
            "path": path,
            "is_ip": is_ip,
        }
    except Exception:
        return {
            "raw": clean,
            "scheme": None,
            "hostname": None,
            "domain": None,
            "path": None,
            "is_ip": "false",
        }


def is_ip_address_host(hostname: str | None) -> bool:
    """Check if a hostname is an IPv4 or IPv6 address string."""
    if not hostname or not isinstance(hostname, str):
        return False
    try:
        ipaddress.ip_address(hostname.strip())
        return True
    except ValueError:
        return False


def extract_emails(text: str | None) -> list[str]:
    """Extract all email addresses from a text string."""
    if not text or not isinstance(text, str):
        return []
    return [e.lower() for e in _EMAIL_RE.findall(text)]


def validate_issn(raw_issn: str | None) -> str | None:
    """Validate and normalize ISSN format via venue intelligence."""
    return normalize_issn(raw_issn)


def validate_doi(raw_doi: str | None) -> str | None:
    """
    Validate and return canonical DOI string.

    Strips leading https://doi.org/ or dx.doi.org/ if present.
    """
    if not raw_doi or not isinstance(raw_doi, str):
        return None

    clean = raw_doi.strip()
    # Strip common URL prefixes
    clean = re.sub(r"^https?://(dx\.)?doi\.org/", "", clean, flags=re.IGNORECASE)

    match = _DOI_RE.search(clean)
    if match:
        return match.group(1)

    return None
