"""
Static Trust & Risk Registries for Phase 2.6B.

Provides deterministic, offline, in-memory reference sets for recognized academic
publishers, scientific societies, recognized indexing bodies, and suspicious domain patterns.

Zero external network calls; fully reproducible and versionable.
"""
from __future__ import annotations

import re

# ── Verified Academic Publishers ──────────────────────────────────────────────

# Normalized lowercase lookup set of verified global academic publishers
TRUSTED_ACADEMIC_PUBLISHERS: dict[str, str] = {
    "ieee": "IEEE",
    "institute of electrical and electronics engineers": "IEEE",
    "acm": "ACM",
    "association for computing machinery": "ACM",
    "springer": "Springer Nature",
    "springer nature": "Springer Nature",
    "springer verlag": "Springer Nature",
    "nature portfolio": "Nature Portfolio",
    "nature publishing group": "Nature Portfolio",
    "elsevier": "Elsevier",
    "cell press": "Cell Press",
    "wiley": "John Wiley & Sons",
    "john wiley & sons": "John Wiley & Sons",
    "wiley-blackwell": "John Wiley & Sons",
    "oxford university press": "Oxford University Press",
    "oup": "Oxford University Press",
    "cambridge university press": "Cambridge University Press",
    "cup": "Cambridge University Press",
    "mit press": "MIT Press",
    "taylor & francis": "Taylor & Francis",
    "taylor and francis": "Taylor & Francis",
    "routledge": "Taylor & Francis (Routledge)",
    "crc press": "Taylor & Francis (CRC Press)",
    "sage": "SAGE Publishing",
    "sage publications": "SAGE Publishing",
    "plos": "PLOS",
    "public library of science": "PLOS",
    "frontiers": "Frontiers Media",
    "frontiers media": "Frontiers Media",
    "mdpi": "MDPI",
    "de gruyter": "De Gruyter",
    "iop publishing": "IOP Publishing",
    "institute of physics": "IOP Publishing",
    "aip publishing": "AIP Publishing",
    "american institute of physics": "AIP Publishing",
    "american physical society": "APS",
    "aps": "APS",
    "american chemical society": "ACS",
    "acs": "ACS",
    "american mathematical society": "AMS",
    "ams": "AMS",
    "aaas": "AAAS",
    "science / aaas": "AAAS",
    "american association for the advancement of science": "AAAS",
    "bmj": "BMJ Publishing",
    "british medical journal": "BMJ Publishing",
    "emerald": "Emerald Publishing",
    "emerald publishing": "Emerald Publishing",
    "karger": "Karger Publishers",
    "wolters kluwer": "Wolters Kluwer",
    "lippincott williams & wilkins": "Wolters Kluwer (LWW)",
}

# ── Verified Academic & Scientific Societies ──────────────────────────────────

TRUSTED_ACADEMIC_SOCIETIES: dict[str, str] = {
    "ieee": "IEEE",
    "acm": "ACM",
    "aaai": "AAAI",
    "association for the advancement of artificial intelligence": "AAAI",
    "acl": "ACL",
    "association for computational linguistics": "ACL",
    "usenix": "USENIX Association",
    "siam": "SIAM",
    "society for industrial and applied mathematics": "SIAM",
    "aps": "American Physical Society",
    "acs": "American Chemical Society",
    "ams": "American Mathematical Society",
    "asme": "ASME",
    "american society of mechanical engineers": "ASME",
    "asce": "ASCE",
    "american society of civil engineers": "ASCE",
    "aiche": "AIChE",
    "american institute of chemical engineers": "AIChE",
    "optica": "Optica (OSA)",
    "osa": "Optica (OSA)",
    "optical society of america": "Optica (OSA)",
    "spie": "SPIE",
    "international society for optics and photonics": "SPIE",
    "eurasip": "EURASIP",
    "european association for signal processing": "EURASIP",
    "ifip": "IFIP",
    "international federation for information processing": "IFIP",
    "iscb": "ISCB",
    "international society for computational biology": "ISCB",
    "miccai": "MICCAI Society",
    "rsna": "RSNA",
    "radiological society of north america": "RSNA",
}

# ── Indexing Tiers (aligns with signals.py INDEXING_TIER_SCORES) ──────────────

TIER_1_INDEXING: set[str] = {
    "SCOPUS",
    "SCI",
    "SCIE",
    "WEB OF SCIENCE",
    "WOS",
    "IEEE",
    "IEEE XPLORE",
    "ACM",
    "ACM DIGITAL LIBRARY",
    "PUBMED",
    "MEDLINE",
}

TIER_2_INDEXING: set[str] = {
    "DBLP",
    "EI COMPENDEX",
    "COMPENDEX",
    "DOAJ",
    "SPRINGER",
    "ELSEVIER",
    "INSPEC",
    "EMBASE",
    "ERIC",
    "CORE A*",
    "CORE A",
}

TIER_3_INDEXING: set[str] = {
    "GOOGLE SCHOLAR",
    "CROSSREF",
    "SEMANTIC SCHOLAR",
    "WIKICFP",
    "CORE B",
    "CORE C",
    "INDEX COPERNICUS",
}

# ── Suspicious TLDs Frequently Abused for Scholarly Phishing ─────────────────

SUSPICIOUS_TLDS: set[str] = {
    ".top",
    ".xyz",
    ".click",
    ".loan",
    ".work",
    ".fit",
    ".rest",
    ".gq",
    ".cf",
    ".ml",
    ".tk",
    ".ga",
    ".buzz",
    ".cam",
    ".monster",
}

# ── Generic Consumer Free Email Domains ───────────────────────────────────────

FREE_EMAIL_DOMAINS: set[str] = {
    "gmail.com",
    "yahoo.com",
    "yahoo.co.uk",
    "yahoo.co.in",
    "hotmail.com",
    "outlook.com",
    "live.com",
    "msn.com",
    "163.com",
    "126.com",
    "qq.com",
    "rediffmail.com",
    "yandex.com",
    "mail.ru",
    "protonmail.com",
    "zoho.com",
}


# ── Lookup & Matching Helpers ─────────────────────────────────────────────────

_WORD_BOUNDARY_RE = re.compile(r"\b[a-z0-9&/.-]+\b")


def match_trusted_publisher(name: str | None) -> tuple[bool, str | None]:
    """
    Deterministically check if a publisher name matches a known verified academic publisher.

    Returns
    -------
    tuple[bool, str | None]
        (is_trusted, canonical_name)
    """
    if not name or not isinstance(name, str):
        return False, None

    clean = name.strip().lower()
    if clean in TRUSTED_ACADEMIC_PUBLISHERS:
        return True, TRUSTED_ACADEMIC_PUBLISHERS[clean]

    # Substring / token matching for prefix/suffixes (e.g. "IEEE Computer Society", "Springer Verlag Berlin")
    for key, canonical in TRUSTED_ACADEMIC_PUBLISHERS.items():
        pattern = rf"\b{re.escape(key)}\b"
        if re.search(pattern, clean):
            return True, canonical

    return False, None


def match_trusted_society(name: str | None) -> tuple[bool, str | None]:
    """
    Deterministically check if an organizer/society matches a verified scientific society.

    Returns
    -------
    tuple[bool, str | None]
        (is_trusted, canonical_society)
    """
    if not name or not isinstance(name, str):
        return False, None

    clean = name.strip().lower()
    if clean in TRUSTED_ACADEMIC_SOCIETIES:
        return True, TRUSTED_ACADEMIC_SOCIETIES[clean]

    for key, canonical in TRUSTED_ACADEMIC_SOCIETIES.items():
        pattern = rf"\b{re.escape(key)}\b"
        if re.search(pattern, clean):
            return True, canonical

    return False, None


def is_suspicious_tld(hostname: str | None) -> bool:
    """
    Check if a hostname ends with a frequently abused or untrusted TLD.
    """
    if not hostname or not isinstance(hostname, str):
        return False

    clean = hostname.strip().lower()
    for tld in SUSPICIOUS_TLDS:
        if clean.endswith(tld):
            return True

    return False


def is_free_email_domain(email_or_domain: str | None) -> bool:
    """
    Check if an email address or domain is a generic free consumer webmail service.
    """
    if not email_or_domain or not isinstance(email_or_domain, str):
        return False

    clean = email_or_domain.strip().lower()
    domain = clean.split("@")[-1] if "@" in clean else clean
    return domain in FREE_EMAIL_DOMAINS
