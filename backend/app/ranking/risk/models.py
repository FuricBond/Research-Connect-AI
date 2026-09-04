"""
Evidence Data Models for Phase 2.6B — Risk Evidence Extraction & Pattern Matchers.

Provides typed, structured, machine-readable containers for observable trust,
suspicious, and neutral signals.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EvidenceCategory(str, Enum):
    """Classification of the nature of the evidence."""

    POSITIVE_TRUST = "POSITIVE_TRUST"
    NEGATIVE_SUSPICIOUS = "NEGATIVE_SUSPICIOUS"
    NEUTRAL_UNKNOWN = "NEUTRAL_UNKNOWN"


class RiskLevel(str, Enum):
    """Categorical risk assessment level for Phase 2.6C."""

    LOW_RISK = "LOW_RISK"
    MODERATE_RISK = "MODERATE_RISK"
    HIGH_RISK = "HIGH_RISK"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class EvidenceStrength(str, Enum):
    """Weight or impact level of an individual evidence signal."""

    NONE = "NONE"
    WEAK = "WEAK"
    MODERATE = "MODERATE"
    STRONG = "STRONG"


class EvidenceConfidence(str, Enum):
    """Reliability of the observation based on provenance and metadata quality."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class EvidenceProvenance(str, Enum):
    """Origin of the extracted evidence."""

    SCRAPED_METADATA = "SCRAPED_METADATA"
    NORMALIZED_METADATA = "NORMALIZED_METADATA"
    STATIC_TRUST_REGISTRY = "STATIC_TRUST_REGISTRY"
    EXTERNAL_VERIFICATION = "EXTERNAL_VERIFICATION"
    GRAPH_ANALYSIS = "GRAPH_ANALYSIS"
    DERIVED = "DERIVED"
    UNKNOWN = "UNKNOWN"


class EvidenceSignal(str, Enum):
    """Controlled vocabulary of standardized evidence signals."""

    # ── Positive Trust Signals ────────────────────────────────────────────────
    VERIFIED_PUBLISHER = "VERIFIED_PUBLISHER"
    VERIFIED_SOCIETY = "VERIFIED_SOCIETY"
    VERIFIED_VENUE = "VERIFIED_VENUE"
    VERIFIED_VENUE_IDENTITY = "VERIFIED_VENUE_IDENTITY"
    VERIFIED_PUBLISHER_IDENTITY = "VERIFIED_PUBLISHER_IDENTITY"
    VERIFIED_ISSN_L = "VERIFIED_ISSN_L"
    DOAJ_INDEXED = "DOAJ_INDEXED"
    VALID_ISSN = "VALID_ISSN"
    VALID_DOI = "VALID_DOI"
    VERIFIED_INDEXING = "VERIFIED_INDEXING"
    OPENALEX_METADATA_MATCH = "OPENALEX_METADATA_MATCH"
    CROSSREF_METADATA_MATCH = "CROSSREF_METADATA_MATCH"
    PUBLISHER_DOMAIN_MATCH = "PUBLISHER_DOMAIN_MATCH"
    CONSISTENT_GRAPH_IDENTITY = "CONSISTENT_GRAPH_IDENTITY"
    TRANSPARENT_PEER_REVIEW = "TRANSPARENT_PEER_REVIEW"
    TRANSPARENT_FEE_STRUCTURE = "TRANSPARENT_FEE_STRUCTURE"

    # ── Negative / Suspicious Signals ─────────────────────────────────────────
    SUSPICIOUS_PAYMENT_LANGUAGE = "SUSPICIOUS_PAYMENT_LANGUAGE"
    SUSPICIOUS_REVIEW_CLAIM = "SUSPICIOUS_REVIEW_CLAIM"
    SUSPICIOUS_EDITORIAL_CLAIM = "SUSPICIOUS_EDITORIAL_CLAIM"
    SUSPICIOUS_DOMAIN = "SUSPICIOUS_DOMAIN"
    SUSPICIOUS_PUBLISHER_PATTERN = "SUSPICIOUS_PUBLISHER_PATTERN"
    SUSPICIOUS_CONTACT_PATTERN = "SUSPICIOUS_CONTACT_PATTERN"
    HIGH_ORGANIZER_REUSE = "HIGH_ORGANIZER_REUSE"
    HIGH_DOMAIN_REUSE = "HIGH_DOMAIN_REUSE"
    GRAPH_IDENTITY_CONFLICT = "GRAPH_IDENTITY_CONFLICT"
    SUSPICIOUS_ORGANIZER_CLUSTER = "SUSPICIOUS_ORGANIZER_CLUSTER"
    SUSPICIOUS_PUBLISHER_CLUSTER = "SUSPICIOUS_PUBLISHER_CLUSTER"
    UNVERIFIABLE_CLAIM = "UNVERIFIABLE_CLAIM"
    CONFLICTING_METADATA = "CONFLICTING_METADATA"

    # ── Neutral / Unknown Signals ─────────────────────────────────────────────
    UNKNOWN_PUBLISHER = "UNKNOWN_PUBLISHER"
    UNKNOWN_INDEXING = "UNKNOWN_INDEXING"
    UNKNOWN_EDITORIAL_PROCESS = "UNKNOWN_EDITORIAL_PROCESS"
    UNKNOWN_DOMAIN_REPUTATION = "UNKNOWN_DOMAIN_REPUTATION"
    MISSING_METADATA = "MISSING_METADATA"


class ResolutionStatus(str, Enum):
    """Categorical entity resolution status for Phase 2.6D."""

    RESOLVED = "RESOLVED"
    PARTIALLY_RESOLVED = "PARTIALLY_RESOLVED"
    UNRESOLVED = "UNRESOLVED"


@dataclass
class ResolvedAcademicEntity:
    """
    Structured cross-source resolution result for a venue and its associated publisher/organizer.
    Phase 2.6D entity representation.
    """

    entity_type: str = "UNKNOWN"  # e.g. "JOURNAL", "CONFERENCE", "BOOK_SERIES", "REPOSITORY", "UNKNOWN"
    canonical_name: str | None = None
    publisher: str | None = None
    organizer: str | None = None
    domain: str | None = None
    issn: str | None = None
    issn_l: str | None = None
    doi_prefix: str | None = None
    openalex_id: str | None = None
    is_in_doaj: bool | None = None
    is_oa: bool | None = None
    works_count: int = 0
    cited_by_count: int = 0
    resolution_status: ResolutionStatus = ResolutionStatus.UNRESOLVED
    resolution_confidence: float = 0.0
    matched_sources: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    provenance: str = "DERIVED"

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "entity_type": self.entity_type,
            "canonical_name": self.canonical_name,
            "publisher": self.publisher,
            "organizer": self.organizer,
            "domain": self.domain,
            "issn": self.issn,
            "issn_l": self.issn_l,
            "doi_prefix": self.doi_prefix,
            "openalex_id": self.openalex_id,
            "is_in_doaj": self.is_in_doaj,
            "is_oa": self.is_oa,
            "works_count": self.works_count,
            "cited_by_count": self.cited_by_count,
            "resolution_status": self.resolution_status.value,
            "resolution_confidence": round(self.resolution_confidence, 4),
            "matched_sources": list(self.matched_sources),
            "conflicts": list(self.conflicts),
            "provenance": self.provenance,
        }


@dataclass(frozen=True)
class RiskEvidence:
    """
    A single atomic piece of observable evidence extracted from opportunity metadata.

    Attributes
    ----------
    signal:
        Standardized identifier of the signal (from EvidenceSignal or string).
    category:
        Nature of the evidence (POSITIVE_TRUST, NEGATIVE_SUSPICIOUS, NEUTRAL_UNKNOWN).
    strength:
        Impact level of this signal (NONE, WEAK, MODERATE, STRONG).
    confidence:
        Reliability of the observation (LOW, MEDIUM, HIGH).
    provenance:
        Source origin of the evidence (e.g. STATIC_TRUST_REGISTRY, SCRAPED_METADATA).
    source_field:
        Opportunity field or origin where evidence was detected (e.g. 'publisher').
    matched_value:
        Exact or normalized token/phrase matched.
    explanation:
        Clear human-readable description of why this evidence matters.
    is_present:
        True if signal was affirmatively observed. False if representing missing metadata.
    metadata:
        Additional arbitrary structured attributes (e.g. matched pattern, tier).
    """

    signal: str
    category: EvidenceCategory
    strength: EvidenceStrength
    confidence: EvidenceConfidence
    provenance: EvidenceProvenance
    source_field: str
    matched_value: str | None = None
    explanation: str = ""
    is_present: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "signal": self.signal,
            "category": self.category.value,
            "strength": self.strength.value,
            "confidence": self.confidence.value,
            "provenance": self.provenance.value,
            "source_field": self.source_field,
            "matched_value": self.matched_value,
            "explanation": self.explanation,
            "is_present": self.is_present,
            "metadata": dict(self.metadata),
        }


@dataclass
class RiskEvidenceCollection:
    """
    Aggregated container of all extracted evidence for a single opportunity.
    """

    opportunity_id: str | None = None
    items: list[RiskEvidence] = field(default_factory=list)
    metadata_completeness_score: float = 0.0
    resolved_entity: ResolvedAcademicEntity | None = None

    @property
    def positive_evidence(self) -> list[RiskEvidence]:
        """All positive trust evidence items."""
        return [
            item for item in self.items
            if item.category == EvidenceCategory.POSITIVE_TRUST and item.is_present
        ]

    @property
    def negative_evidence(self) -> list[RiskEvidence]:
        """All negative suspicious evidence items."""
        return [
            item for item in self.items
            if item.category == EvidenceCategory.NEGATIVE_SUSPICIOUS and item.is_present
        ]

    @property
    def neutral_evidence(self) -> list[RiskEvidence]:
        """All neutral or unknown evidence items (including missing metadata records)."""
        return [
            item for item in self.items
            if item.category == EvidenceCategory.NEUTRAL_UNKNOWN
        ]

    @property
    def has_suspicious_evidence(self) -> bool:
        """True if any affirmative negative/suspicious evidence exists."""
        return len(self.negative_evidence) > 0

    @property
    def has_trust_evidence(self) -> bool:
        """True if any affirmative positive trust evidence exists."""
        return len(self.positive_evidence) > 0

    @property
    def strong_suspicious_signals(self) -> list[RiskEvidence]:
        """Affirmative suspicious signals with STRONG strength."""
        return [
            item for item in self.negative_evidence
            if item.strength == EvidenceStrength.STRONG
        ]

    def add(self, evidence: RiskEvidence) -> None:
        """Add an evidence item to the collection."""
        self.items.append(evidence)

    def to_dict(self) -> dict[str, Any]:
        """Convert entire collection to JSON-serializable dictionary."""
        return {
            "opportunity_id": self.opportunity_id,
            "items": [item.to_dict() for item in self.items],
            "metadata_completeness_score": round(self.metadata_completeness_score, 4),
            "resolved_entity": self.resolved_entity.to_dict() if self.resolved_entity else None,
            "summary": self.summary(),
        }

    def summary(self) -> dict[str, Any]:
        """Generate high-level counts and status for explainability and diagnostics."""
        res_status = self.resolved_entity.resolution_status.value if self.resolved_entity else None
        res_conf = round(self.resolved_entity.resolution_confidence, 4) if self.resolved_entity else 0.0
        return {
            "total_signals": len(self.items),
            "positive_count": len(self.positive_evidence),
            "negative_count": len(self.negative_evidence),
            "neutral_count": len(self.neutral_evidence),
            "has_suspicious_evidence": self.has_suspicious_evidence,
            "has_trust_evidence": self.has_trust_evidence,
            "metadata_completeness_score": round(self.metadata_completeness_score, 4),
            "resolution_status": res_status,
            "resolution_confidence": res_conf,
        }


@dataclass(frozen=True)
class RiskAssessment:
    """
    Deterministic risk assessment produced by Phase 2.6C scoring engine.

    Attributes
    ----------
    opportunity_id:
        UUID string of the opportunity if present.
    risk_score:
        Calibrated numerical risk score in range [0.00, 1.00].
    risk_level:
        Categorical risk classification (LOW_RISK, MODERATE_RISK, HIGH_RISK, INSUFFICIENT_EVIDENCE).
    risk_confidence:
        Confidence in the assessment based on metadata availability and provenance in [0.00, 1.00].
    is_predatory_flag:
        Boolean flag indicating suspected predatory opportunity.
    risk_reasons:
        Deterministic, ordered human-readable justifications for the risk score.
    dominant_signals:
        Identifiers of top positive and negative signals driving the score.
    gross_negative_score:
        Gross suspicious score before trust mitigation.
    trust_mitigation_score:
        Positive trust score deducted from gross negative score.
    evidence_collection:
        Full underlying collection of extracted atomic evidence items.
    """

    opportunity_id: str | None
    risk_score: float
    risk_level: RiskLevel
    risk_confidence: float
    is_predatory_flag: bool
    risk_reasons: list[str] = field(default_factory=list)
    dominant_signals: list[str] = field(default_factory=list)
    gross_negative_score: float = 0.0
    trust_mitigation_score: float = 0.0
    evidence_collection: RiskEvidenceCollection | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert assessment to JSON-serializable dictionary."""
        return {
            "opportunity_id": self.opportunity_id,
            "risk_score": round(self.risk_score, 2),
            "risk_level": self.risk_level.value,
            "risk_confidence": round(self.risk_confidence, 2),
            "is_predatory_flag": self.is_predatory_flag,
            "risk_reasons": list(self.risk_reasons),
            "dominant_signals": list(self.dominant_signals),
            "gross_negative_score": round(self.gross_negative_score, 4),
            "trust_mitigation_score": round(self.trust_mitigation_score, 4),
            "evidence_summary": self.evidence_collection.summary() if self.evidence_collection else None,
        }
