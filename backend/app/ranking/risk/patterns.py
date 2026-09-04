"""
Deterministic Regex Pattern Matchers for Phase 2.6B.

Provides bounded, contextual regex pattern groups to detect suspicious payment language,
unrealistic review speeds, bogus impact factor claims, and consumer webmail submissions.

Includes explicit false-positive safeguards for legitimate academic disclosures
(e.g., standard APCs, IEEE member fees, double-blind peer review).
"""
from __future__ import annotations

import re

# ── Suspicious Payment & Fee Patterns ─────────────────────────────────────────

# Wire transfer / non-traceable money demands
_PAYMENT_NON_TRACEABLE_RE = re.compile(
    r"\b(western\s+union|moneygram|pay\s+cash\s+on\s+arrival|remit\s+via\s+hawala|wire\s+transfer\s+only)\b",
    re.IGNORECASE,
)

# Guaranteed publication for money / pay-to-publish bribery
_PAYMENT_PAY_TO_PUBLISH_RE = re.compile(
    r"\b(guaranteed?\s+(?:publication|acceptance)\s+(?:upon|after|with)\s+(?:fee|payment)|"
    r"pay\b.{1,40}\b(?:guarantee\w*\s+publication|instant\s+acceptance)|"
    r"(?:fast-track|expedited)\s+fee\s+for\s+(?:same-day|24-hour|instant)\s+(?:publication|acceptance))\b",
    re.IGNORECASE,
)

# Urgent payment pressure
_PAYMENT_URGENT_DEMAND_RE = re.compile(
    r"\b(urgent\s+(?:fee|payment)\s+required\s+within\s+(?:24|48)\s*hours|"
    r"immediate\s+remittance\s+mandatory\s+for\s+acceptance)\b",
    re.IGNORECASE,
)

# Explicit False-Positive Safeguard for Legitimate Fees
_LEGITIMATE_FEE_RE = re.compile(
    r"\b(registration\s+fee|conference\s+registration|article\s+processing\s+charge|"
    r"apc|open\s+access\s+fee|ieee\s+member|acm\s+member|student\s+registration|"
    r"early\s+bird|page\s+charges?|publication\s+charge)\b",
    re.IGNORECASE,
)


# ── Suspicious Peer Review & Acceptance Claims ────────────────────────────────

# Unrealistic review speed (sub-48 hour peer review)
_REVIEW_UNREALISTIC_SPEED_RE = re.compile(
    r"\b((?:peer\s+)?review\s+(?:(?:is\s+|will\s+be\s+)?completed\s+)?(?:within|in)\s+(?:24|48)\s*(?:hours|hrs)|"
    r"(?:peer\s+)?review\s+(?:(?:is\s+|will\s+be\s+)?completed\s+)?in\s+[1-3]\s*days|"
    r"acceptance\s+(?:(?:is\s+|will\s+be\s+)?(?:given|notified|sent)\s+)?(?:within|in)\s+(?:24|48)\s*(?:hours|hrs)|"
    r"instant\s+(?:peer\s+review|acceptance\s+letter)|"
    r"same-day\s+(?:peer\s+)?review)\b",
    re.IGNORECASE,
)

# Unconditional acceptance guarantees
_REVIEW_GUARANTEED_ACCEPTANCE_RE = re.compile(
    r"\b(100%\s+acceptance\s+rate|acceptance\s+is\s+guaranteed|guaranteed\s+acceptance\s+rate|"
    r"no\s+rejection\s+policy|all\s+papers\s+accepted)\b",
    re.IGNORECASE,
)

# Explicit False-Positive Safeguard for Legitimate Review Policies
_LEGITIMATE_REVIEW_RE = re.compile(
    r"\b(double-blind\s+peer\s+review|single-blind\s+peer\s+review|rigorous\s+peer\s+review|"
    r"peer-reviewed\s+proceedings|international\s+program\s+committee|"
    r"review\s+process\s+takes\s+\d+\s*(?:weeks|months))\b",
    re.IGNORECASE,
)


# ── Suspicious Editorial & Metric Claims ──────────────────────────────────────

# Phony / vanity impact factor services
_EDITORIAL_FAKE_METRICS_RE = re.compile(
    r"\b(global\s+impact\s+factor|universal\s+impact\s+factor|general\s+impact\s+factor|"
    r"cosmos\s+impact\s+factor|international\s+scientific\s+indexing|isi\s+indexing\b(?!\s*thomson)|"
    r"scientific\s+journal\s+impact\s+factor|sjif\s+impact\s+factor|citefactor)\b",
    re.IGNORECASE,
)


# ── Suspicious Contact & Submission Patterns ──────────────────────────────────

# Manuscript submission directed to consumer webmail
_CONTACT_FREE_MAIL_SUBMISSION_RE = re.compile(
    r"(?:submit|send\s+papers?|submissions?|editorial\s+office|send\s+manuscripts?)"
    r"[\s\S]{0,60}@"
    r"(?:gmail\.com|yahoo\.com|yahoo\.co\.in|hotmail\.com|163\.com|rediffmail\.com)",
    re.IGNORECASE,
)


# ── Pattern Matcher Functions ─────────────────────────────────────────────────


def scan_payment_patterns(text: str | None) -> list[tuple[str, str, str]]:
    """
    Scan text for suspicious payment language.

    Returns
    -------
    list[tuple[pattern_name, matched_substring, explanation]]
    """
    if not text or not isinstance(text, str):
        return []

    results: list[tuple[str, str, str]] = []

    m1 = _PAYMENT_NON_TRACEABLE_RE.search(text)
    if m1:
        results.append((
            "NON_TRACEABLE_PAYMENT",
            m1.group(0),
            "Non-traceable payment method requested (e.g. Western Union, cash on arrival).",
        ))

    m2 = _PAYMENT_PAY_TO_PUBLISH_RE.search(text)
    if m2:
        results.append((
            "PAY_FOR_GUARANTEED_PUBLICATION",
            m2.group(0),
            "Explicit promise of guaranteed publication or acceptance in exchange for fee payment.",
        ))

    m3 = _PAYMENT_URGENT_DEMAND_RE.search(text)
    if m3:
        results.append((
            "URGENT_PAYMENT_PRESSURE",
            m3.group(0),
            "Urgent payment pressure with short ultimatum deadline.",
        ))

    return results


def has_legitimate_fee_context(text: str | None) -> bool:
    """Return True if text contains standard, legitimate academic fee terminology."""
    if not text or not isinstance(text, str):
        return False
    return bool(_LEGITIMATE_FEE_RE.search(text))


def scan_review_patterns(text: str | None) -> list[tuple[str, str, str]]:
    """
    Scan text for suspicious peer-review promises.

    Returns
    -------
    list[tuple[pattern_name, matched_substring, explanation]]
    """
    if not text or not isinstance(text, str):
        return []

    results: list[tuple[str, str, str]] = []

    m1 = _REVIEW_UNREALISTIC_SPEED_RE.search(text)
    if m1:
        results.append((
            "UNREALISTIC_REVIEW_SPEED",
            m1.group(0),
            "Unrealistic sub-48-hour peer-review turnaround claimed.",
        ))

    m2 = _REVIEW_GUARANTEED_ACCEPTANCE_RE.search(text)
    if m2:
        results.append((
            "GUARANTEED_ACCEPTANCE",
            m2.group(0),
            "Unconditional or 100% acceptance rate promised without genuine editorial scrutiny.",
        ))

    return results


def has_legitimate_review_context(text: str | None) -> bool:
    """Return True if text describes standard legitimate peer-review procedures."""
    if not text or not isinstance(text, str):
        return False
    return bool(_LEGITIMATE_REVIEW_RE.search(text))


def scan_editorial_patterns(text: str | None) -> list[tuple[str, str, str]]:
    """
    Scan text for fraudulent metrics or fake indexing claims.

    Returns
    -------
    list[tuple[pattern_name, matched_substring, explanation]]
    """
    if not text or not isinstance(text, str):
        return []

    results: list[tuple[str, str, str]] = []

    m = _EDITORIAL_FAKE_METRICS_RE.search(text)
    if m:
        results.append((
            "BOGUS_METRIC_CLAIM",
            m.group(0),
            "Reference to known predatory or misleading vanity metric service (e.g. Global Impact Factor).",
        ))

    return results


def scan_contact_patterns(text: str | None) -> list[tuple[str, str, str]]:
    """
    Scan text for manuscript submission instructions pointing to free webmail.

    Returns
    -------
    list[tuple[pattern_name, matched_substring, explanation]]
    """
    if not text or not isinstance(text, str):
        return []

    results: list[tuple[str, str, str]] = []

    m = _CONTACT_FREE_MAIL_SUBMISSION_RE.search(text)
    if m:
        results.append((
            "FREE_MAIL_SUBMISSION",
            m.group(0),
            "Official manuscript submission directed to a free consumer webmail account.",
        ))

    return results
