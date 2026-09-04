"""
Modular Risk & Trust Evidence Extractors for Phase 2.6B.

Each extractor focuses on a distinct dimension (Trust Registries, Domains/URLs,
Editorial/Review claims, Payment/Fees, and Metadata Completeness).

Enforces the core architectural rule:
  UNKNOWN != PREDATORY
Missing metadata decreases confidence but never generates negative risk evidence.
"""
from __future__ import annotations

from typing import Any

from app.ranking.risk.models import (
    EvidenceCategory,
    EvidenceConfidence,
    EvidenceProvenance,
    EvidenceSignal,
    EvidenceStrength,
    RiskEvidence,
)
from app.ranking.risk.normalizers import (
    extract_emails,
    is_ip_address_host,
    normalize_url,
    validate_doi,
    validate_issn,
)
from app.ranking.risk.patterns import (
    has_legitimate_fee_context,
    has_legitimate_review_context,
    scan_contact_patterns,
    scan_editorial_patterns,
    scan_payment_patterns,
    scan_review_patterns,
)
from app.ranking.risk.registries import (
    FREE_EMAIL_DOMAINS,
    TIER_1_INDEXING,
    TIER_2_INDEXING,
    is_free_email_domain,
    is_suspicious_tld,
    match_trusted_publisher,
    match_trusted_society,
)


def _get_field(obj: Any, field_name: str) -> Any:
    """Safely extract attribute from ORM model or dictionary."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(field_name)
    return getattr(obj, field_name, None)


class TrustEvidenceExtractor:
    """
    Extracts positive trust evidence from static academic publisher/society registries,
    verified indexing bodies, DOAJ inclusion, and validated ISSN/DOI.
    """

    def extract(self, opportunity: Any) -> list[RiskEvidence]:
        evidence_list: list[RiskEvidence] = []

        # 1. Publisher Registry Match
        publisher = _get_field(opportunity, "publisher")
        if publisher and isinstance(publisher, str) and publisher.strip():
            is_trusted, canon_name = match_trusted_publisher(publisher)
            if is_trusted and canon_name:
                evidence_list.append(
                    RiskEvidence(
                        signal=EvidenceSignal.VERIFIED_PUBLISHER.value,
                        category=EvidenceCategory.POSITIVE_TRUST,
                        strength=EvidenceStrength.STRONG,
                        confidence=EvidenceConfidence.HIGH,
                        provenance=EvidenceProvenance.STATIC_TRUST_REGISTRY,
                        source_field="opportunity.publisher",
                        matched_value=publisher.strip(),
                        explanation=f"Publisher matched verified global academic publisher: {canon_name}.",
                        metadata={"canonical_publisher": canon_name},
                    )
                )
            else:
                evidence_list.append(
                    RiskEvidence(
                        signal=EvidenceSignal.UNKNOWN_PUBLISHER.value,
                        category=EvidenceCategory.NEUTRAL_UNKNOWN,
                        strength=EvidenceStrength.NONE,
                        confidence=EvidenceConfidence.MEDIUM,
                        provenance=EvidenceProvenance.STATIC_TRUST_REGISTRY,
                        source_field="opportunity.publisher",
                        matched_value=publisher.strip(),
                        explanation=f"Publisher '{publisher.strip()}' is not in the static trusted publisher registry (neutral; not evidence of risk).",
                    )
                )
        else:
            evidence_list.append(
                RiskEvidence(
                    signal=EvidenceSignal.MISSING_METADATA.value,
                    category=EvidenceCategory.NEUTRAL_UNKNOWN,
                    strength=EvidenceStrength.NONE,
                    confidence=EvidenceConfidence.LOW,
                    provenance=EvidenceProvenance.NORMALIZED_METADATA,
                    source_field="opportunity.publisher",
                    is_present=False,
                    explanation="No publisher information provided in opportunity metadata.",
                )
            )

        # 2. Organizer / Society Registry Match
        organizer = _get_field(opportunity, "organizer")
        if organizer and isinstance(organizer, str) and organizer.strip():
            is_society, canon_society = match_trusted_society(organizer)
            if is_society and canon_society:
                evidence_list.append(
                    RiskEvidence(
                        signal=EvidenceSignal.VERIFIED_SOCIETY.value,
                        category=EvidenceCategory.POSITIVE_TRUST,
                        strength=EvidenceStrength.STRONG,
                        confidence=EvidenceConfidence.HIGH,
                        provenance=EvidenceProvenance.STATIC_TRUST_REGISTRY,
                        source_field="opportunity.organizer",
                        matched_value=organizer.strip(),
                        explanation=f"Organizer verified as recognized scientific society: {canon_society}.",
                        metadata={"canonical_society": canon_society},
                    )
                )

        # 3. Verified Indexing Services
        indexing = _get_field(opportunity, "indexing")
        if indexing and isinstance(indexing, (list, tuple, set)) and len(indexing) > 0:
            matched_tier1: list[str] = []
            matched_doaj: bool = False
            matched_tier2: list[str] = []

            for item in indexing:
                if not item or not isinstance(item, str):
                    continue
                clean_item = item.strip().upper()
                if clean_item in TIER_1_INDEXING:
                    matched_tier1.append(item.strip())
                elif clean_item == "DOAJ":
                    matched_doaj = True
                elif clean_item in TIER_2_INDEXING:
                    matched_tier2.append(item.strip())

            if matched_tier1:
                evidence_list.append(
                    RiskEvidence(
                        signal=EvidenceSignal.VERIFIED_INDEXING.value,
                        category=EvidenceCategory.POSITIVE_TRUST,
                        strength=EvidenceStrength.STRONG,
                        confidence=EvidenceConfidence.HIGH,
                        provenance=EvidenceProvenance.STATIC_TRUST_REGISTRY,
                        source_field="opportunity.indexing",
                        matched_value=", ".join(matched_tier1),
                        explanation=f"Opportunity is indexed in Tier 1 bibliographic databases: {', '.join(matched_tier1)}.",
                        metadata={"tier": 1, "matches": matched_tier1},
                    )
                )

            if matched_doaj:
                evidence_list.append(
                    RiskEvidence(
                        signal=EvidenceSignal.DOAJ_INDEXED.value,
                        category=EvidenceCategory.POSITIVE_TRUST,
                        strength=EvidenceStrength.STRONG,
                        confidence=EvidenceConfidence.HIGH,
                        provenance=EvidenceProvenance.STATIC_TRUST_REGISTRY,
                        source_field="opportunity.indexing",
                        matched_value="DOAJ",
                        explanation="Opportunity or parent venue is indexed in the Directory of Open Access Journals (DOAJ).",
                    )
                )
            elif matched_tier2 and not matched_tier1:
                evidence_list.append(
                    RiskEvidence(
                        signal=EvidenceSignal.VERIFIED_INDEXING.value,
                        category=EvidenceCategory.POSITIVE_TRUST,
                        strength=EvidenceStrength.MODERATE,
                        confidence=EvidenceConfidence.HIGH,
                        provenance=EvidenceProvenance.STATIC_TRUST_REGISTRY,
                        source_field="opportunity.indexing",
                        matched_value=", ".join(matched_tier2),
                        explanation=f"Opportunity is indexed in recognized academic indexing databases: {', '.join(matched_tier2)}.",
                        metadata={"tier": 2, "matches": matched_tier2},
                    )
                )
        else:
            evidence_list.append(
                RiskEvidence(
                    signal=EvidenceSignal.UNKNOWN_INDEXING.value,
                    category=EvidenceCategory.NEUTRAL_UNKNOWN,
                    strength=EvidenceStrength.NONE,
                    confidence=EvidenceConfidence.LOW,
                    provenance=EvidenceProvenance.NORMALIZED_METADATA,
                    source_field="opportunity.indexing",
                    is_present=False,
                    explanation="No indexing metadata provided (neutral default; not evidence of risk).",
                )
            )

        # 4. Valid ISSN / DOI Identifiers
        raw_issn = _get_field(opportunity, "issn") or _get_field(opportunity, "issn_l")
        if raw_issn:
            norm_issn = validate_issn(str(raw_issn))
            if norm_issn:
                evidence_list.append(
                    RiskEvidence(
                        signal=EvidenceSignal.VALID_ISSN.value,
                        category=EvidenceCategory.POSITIVE_TRUST,
                        strength=EvidenceStrength.MODERATE,
                        confidence=EvidenceConfidence.HIGH,
                        provenance=EvidenceProvenance.NORMALIZED_METADATA,
                        source_field="opportunity.issn",
                        matched_value=norm_issn,
                        explanation=f"Valid International Standard Serial Number verified: {norm_issn}.",
                    )
                )

        raw_doi = _get_field(opportunity, "doi")
        if raw_doi:
            norm_doi = validate_doi(str(raw_doi))
            if norm_doi:
                evidence_list.append(
                    RiskEvidence(
                        signal=EvidenceSignal.VALID_DOI.value,
                        category=EvidenceCategory.POSITIVE_TRUST,
                        strength=EvidenceStrength.MODERATE,
                        confidence=EvidenceConfidence.HIGH,
                        provenance=EvidenceProvenance.NORMALIZED_METADATA,
                        source_field="opportunity.doi",
                        matched_value=norm_doi,
                        explanation=f"Valid Digital Object Identifier verified: {norm_doi}.",
                    )
                )

        return evidence_list


class DomainEvidenceExtractor:
    """
    Analyzes website_url and submission_url for domain authenticity, IP hosts,
    and suspicious TLDs. Operates purely in-memory without network requests.
    """

    def extract(self, opportunity: Any) -> list[RiskEvidence]:
        evidence_list: list[RiskEvidence] = []
        website_url = _get_field(opportunity, "website_url")
        submission_url = _get_field(opportunity, "submission_url")

        # 1. Website URL Analysis
        if website_url and isinstance(website_url, str) and website_url.strip():
            url_meta = normalize_url(website_url)
            hostname = url_meta.get("hostname")

            if url_meta.get("is_ip") == "true":
                evidence_list.append(
                    RiskEvidence(
                        signal=EvidenceSignal.SUSPICIOUS_DOMAIN.value,
                        category=EvidenceCategory.NEGATIVE_SUSPICIOUS,
                        strength=EvidenceStrength.STRONG,
                        confidence=EvidenceConfidence.HIGH,
                        provenance=EvidenceProvenance.NORMALIZED_METADATA,
                        source_field="opportunity.website_url",
                        matched_value=hostname,
                        explanation=f"Opportunity website uses a raw IP address ({hostname}) rather than a registered domain name.",
                        metadata={"type": "raw_ip_host", "url": website_url},
                    )
                )
            elif is_suspicious_tld(hostname):
                evidence_list.append(
                    RiskEvidence(
                        signal=EvidenceSignal.SUSPICIOUS_DOMAIN.value,
                        category=EvidenceCategory.NEGATIVE_SUSPICIOUS,
                        strength=EvidenceStrength.MODERATE,
                        confidence=EvidenceConfidence.MEDIUM,
                        provenance=EvidenceProvenance.NORMALIZED_METADATA,
                        source_field="opportunity.website_url",
                        matched_value=hostname,
                        explanation=f"Opportunity website domain '{hostname}' uses a high-risk TLD frequently associated with conference phishing.",
                        metadata={"type": "suspicious_tld", "url": website_url},
                    )
                )
        else:
            evidence_list.append(
                RiskEvidence(
                    signal=EvidenceSignal.MISSING_METADATA.value,
                    category=EvidenceCategory.NEUTRAL_UNKNOWN,
                    strength=EvidenceStrength.NONE,
                    confidence=EvidenceConfidence.LOW,
                    provenance=EvidenceProvenance.NORMALIZED_METADATA,
                    source_field="opportunity.website_url",
                    is_present=False,
                    explanation="No official website URL provided (neutral; not evidence of risk).",
                )
            )

        # 2. Submission URL Analysis
        if submission_url and isinstance(submission_url, str) and submission_url.strip():
            sub_meta = normalize_url(submission_url)
            sub_host = sub_meta.get("hostname")

            if sub_meta.get("is_ip") == "true":
                evidence_list.append(
                    RiskEvidence(
                        signal=EvidenceSignal.SUSPICIOUS_DOMAIN.value,
                        category=EvidenceCategory.NEGATIVE_SUSPICIOUS,
                        strength=EvidenceStrength.STRONG,
                        confidence=EvidenceConfidence.HIGH,
                        provenance=EvidenceProvenance.NORMALIZED_METADATA,
                        source_field="opportunity.submission_url",
                        matched_value=sub_host,
                        explanation=f"Manuscript submission portal uses a raw IP address ({sub_host}).",
                        metadata={"type": "raw_ip_host", "url": submission_url},
                    )
                )

        return evidence_list


class EditorialReviewEvidenceExtractor:
    """
    Scans textual metadata (description, summary, title) for unrealistic peer review
    speed, guaranteed acceptance promises, fake impact factors, or webmail submissions.
    """

    def extract(self, opportunity: Any) -> list[RiskEvidence]:
        evidence_list: list[RiskEvidence] = []

        # Aggregate candidate text fields
        title = _get_field(opportunity, "title") or ""
        summary = _get_field(opportunity, "summary") or ""
        description = _get_field(opportunity, "description") or ""
        full_text = f"{title}\n{summary}\n{description}".strip()

        if not full_text:
            evidence_list.append(
                RiskEvidence(
                    signal=EvidenceSignal.UNKNOWN_EDITORIAL_PROCESS.value,
                    category=EvidenceCategory.NEUTRAL_UNKNOWN,
                    strength=EvidenceStrength.NONE,
                    confidence=EvidenceConfidence.LOW,
                    provenance=EvidenceProvenance.SCRAPED_METADATA,
                    source_field="opportunity.description",
                    is_present=False,
                    explanation="No textual description provided to evaluate editorial policies (neutral default).",
                )
            )
            return evidence_list

        # 1. Peer Review Patterns
        review_issues = scan_review_patterns(full_text)
        if review_issues:
            for pat_name, matched_str, reason in review_issues:
                evidence_list.append(
                    RiskEvidence(
                        signal=EvidenceSignal.SUSPICIOUS_REVIEW_CLAIM.value,
                        category=EvidenceCategory.NEGATIVE_SUSPICIOUS,
                        strength=EvidenceStrength.STRONG,
                        confidence=EvidenceConfidence.HIGH,
                        provenance=EvidenceProvenance.SCRAPED_METADATA,
                        source_field="opportunity.description",
                        matched_value=matched_str,
                        explanation=reason,
                        metadata={"pattern": pat_name},
                    )
                )
        elif has_legitimate_review_context(full_text):
            evidence_list.append(
                RiskEvidence(
                    signal=EvidenceSignal.TRANSPARENT_PEER_REVIEW.value,
                    category=EvidenceCategory.POSITIVE_TRUST,
                    strength=EvidenceStrength.WEAK,
                    confidence=EvidenceConfidence.MEDIUM,
                    provenance=EvidenceProvenance.SCRAPED_METADATA,
                    source_field="opportunity.description",
                    explanation="Legitimate peer-review process explicitly disclosed (e.g. double-blind review or international committee).",
                )
            )
        else:
            evidence_list.append(
                RiskEvidence(
                    signal=EvidenceSignal.UNKNOWN_EDITORIAL_PROCESS.value,
                    category=EvidenceCategory.NEUTRAL_UNKNOWN,
                    strength=EvidenceStrength.NONE,
                    confidence=EvidenceConfidence.LOW,
                    provenance=EvidenceProvenance.SCRAPED_METADATA,
                    source_field="opportunity.description",
                    is_present=False,
                    explanation="No explicit peer-review process details provided in description (neutral default).",
                )
            )

        # 2. Fake Metric / Vanity Impact Factor Claims
        editorial_issues = scan_editorial_patterns(full_text)
        for pat_name, matched_str, reason in editorial_issues:
            evidence_list.append(
                RiskEvidence(
                    signal=EvidenceSignal.SUSPICIOUS_EDITORIAL_CLAIM.value,
                    category=EvidenceCategory.NEGATIVE_SUSPICIOUS,
                    strength=EvidenceStrength.STRONG,
                    confidence=EvidenceConfidence.HIGH,
                    provenance=EvidenceProvenance.SCRAPED_METADATA,
                    source_field="opportunity.description",
                    matched_value=matched_str,
                    explanation=reason,
                    metadata={"pattern": pat_name},
                )
            )

        # 3. Submission to Consumer Webmail
        contact_issues = scan_contact_patterns(full_text)
        for pat_name, matched_str, reason in contact_issues:
            evidence_list.append(
                RiskEvidence(
                    signal=EvidenceSignal.SUSPICIOUS_CONTACT_PATTERN.value,
                    category=EvidenceCategory.NEGATIVE_SUSPICIOUS,
                    strength=EvidenceStrength.MODERATE,
                    confidence=EvidenceConfidence.MEDIUM,
                    provenance=EvidenceProvenance.SCRAPED_METADATA,
                    source_field="opportunity.description",
                    matched_value=matched_str,
                    explanation=reason,
                    metadata={"pattern": pat_name},
                )
            )

        return evidence_list


class PaymentFeeEvidenceExtractor:
    """
    Differentiates transparent, legitimate academic fees (APCs, conference registration)
    from predatory payment demands (Western Union, wire-only, pay-to-publish speedups).
    """

    def extract(self, opportunity: Any) -> list[RiskEvidence]:
        evidence_list: list[RiskEvidence] = []

        title = _get_field(opportunity, "title") or ""
        summary = _get_field(opportunity, "summary") or ""
        description = _get_field(opportunity, "description") or ""
        full_text = f"{title}\n{summary}\n{description}".strip()

        apc_or_fee = _get_field(opportunity, "apc_or_fee")

        # 1. Suspicious Payment Language Scan
        payment_issues = scan_payment_patterns(full_text)
        if payment_issues:
            for pat_name, matched_str, reason in payment_issues:
                evidence_list.append(
                    RiskEvidence(
                        signal=EvidenceSignal.SUSPICIOUS_PAYMENT_LANGUAGE.value,
                        category=EvidenceCategory.NEGATIVE_SUSPICIOUS,
                        strength=EvidenceStrength.STRONG,
                        confidence=EvidenceConfidence.HIGH,
                        provenance=EvidenceProvenance.SCRAPED_METADATA,
                        source_field="opportunity.description",
                        matched_value=matched_str,
                        explanation=reason,
                        metadata={"pattern": pat_name},
                    )
                )

        # 2. Transparent Fee Structure (Safe positive signal if no suspicious payment demands)
        has_legit_fee_dict = isinstance(apc_or_fee, dict) and bool(apc_or_fee.get("has_fee"))
        has_legit_fee_text = has_legitimate_fee_context(full_text)

        if (has_legit_fee_dict or has_legit_fee_text) and not payment_issues:
            evidence_list.append(
                RiskEvidence(
                    signal=EvidenceSignal.TRANSPARENT_FEE_STRUCTURE.value,
                    category=EvidenceCategory.POSITIVE_TRUST,
                    strength=EvidenceStrength.WEAK,
                    confidence=EvidenceConfidence.MEDIUM,
                    provenance=EvidenceProvenance.NORMALIZED_METADATA,
                    source_field="opportunity.apc_or_fee" if has_legit_fee_dict else "opportunity.description",
                    explanation="Standard academic fee or APC disclosed without suspicious payment methods.",
                )
            )
        elif not has_legit_fee_dict and not has_legit_fee_text and not payment_issues:
            evidence_list.append(
                RiskEvidence(
                    signal=EvidenceSignal.MISSING_METADATA.value,
                    category=EvidenceCategory.NEUTRAL_UNKNOWN,
                    strength=EvidenceStrength.NONE,
                    confidence=EvidenceConfidence.LOW,
                    provenance=EvidenceProvenance.NORMALIZED_METADATA,
                    source_field="opportunity.apc_or_fee",
                    is_present=False,
                    explanation="No fee or APC information specified (neutral default; not evidence of risk).",
                )
            )

        return evidence_list


class MetadataCompletenessExtractor:
    """
    Audits core metadata availability and computes a completeness ratio.
    Helps 2.6C determine overall evidence confidence without penalizing missing data.
    """

    CORE_FIELDS = (
        ("title", "opportunity.title"),
        ("publisher", "opportunity.publisher"),
        ("organizer", "opportunity.organizer"),
        ("website_url", "opportunity.website_url"),
        ("submission_deadline", "opportunity.submission_deadline"),
        ("indexing", "opportunity.indexing"),
    )

    def extract(self, opportunity: Any) -> tuple[list[RiskEvidence], float]:
        evidence_list: list[RiskEvidence] = []
        present_count = 0

        for field_key, source_field in self.CORE_FIELDS:
            val = _get_field(opportunity, field_key)
            has_val = False
            if val is not None:
                if isinstance(val, (str, list, dict, set, tuple)):
                    has_val = len(val) > 0
                else:
                    has_val = True

            if has_val:
                present_count += 1
            else:
                evidence_list.append(
                    RiskEvidence(
                        signal=EvidenceSignal.MISSING_METADATA.value,
                        category=EvidenceCategory.NEUTRAL_UNKNOWN,
                        strength=EvidenceStrength.NONE,
                        confidence=EvidenceConfidence.LOW,
                        provenance=EvidenceProvenance.NORMALIZED_METADATA,
                        source_field=source_field,
                        is_present=False,
                        explanation=f"Field '{field_key}' is not populated in opportunity metadata.",
                    )
                )

        completeness_score = present_count / len(self.CORE_FIELDS)
        return evidence_list, completeness_score
