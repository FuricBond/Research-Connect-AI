"""
Unified Evidence Extraction Orchestrator for Phase 2.6B.

Coordinates modular extractors, deduplicates signals, and produces a structured
RiskEvidenceCollection. Operates strictly in-memory with zero network or database queries.
"""
from __future__ import annotations

from typing import Any
import uuid

from app.ranking.risk.extractors import (
    DomainEvidenceExtractor,
    EditorialReviewEvidenceExtractor,
    MetadataCompletenessExtractor,
    PaymentFeeEvidenceExtractor,
    TrustEvidenceExtractor,
    _get_field,
)
from app.ranking.risk.models import RiskEvidence, RiskEvidenceCollection


class RiskEvidenceExtractor:
    """
    Orchestrates deterministic extraction of trust, risk, and neutral evidence
    from academic opportunity metadata.
    """

    def __init__(self) -> None:
        self.trust_extractor = TrustEvidenceExtractor()
        self.domain_extractor = DomainEvidenceExtractor()
        self.editorial_extractor = EditorialReviewEvidenceExtractor()
        self.payment_extractor = PaymentFeeEvidenceExtractor()
        self.completeness_extractor = MetadataCompletenessExtractor()

    def extract(self, opportunity: Any) -> RiskEvidenceCollection:
        """
        Extract all observable evidence for a single opportunity.

        Parameters
        ----------
        opportunity:
            OpportunityModel instance, OpportunityRead schema, or dictionary.

        Returns
        -------
        RiskEvidenceCollection
            Deduplicated, structured collection of extracted evidence.
        """
        raw_id = _get_field(opportunity, "id")
        opp_id = str(raw_id) if raw_id is not None else None

        collection = RiskEvidenceCollection(opportunity_id=opp_id)

        # 1. Run all modular extractors
        trust_items = self.trust_extractor.extract(opportunity)
        domain_items = self.domain_extractor.extract(opportunity)
        editorial_items = self.editorial_extractor.extract(opportunity)
        payment_items = self.payment_extractor.extract(opportunity)
        completeness_items, completeness_score = self.completeness_extractor.extract(opportunity)

        # 2. Deduplicate and collect
        seen_keys: set[tuple[str, str, str | None]] = set()

        all_items: list[RiskEvidence] = (
            trust_items
            + domain_items
            + editorial_items
            + payment_items
            + completeness_items
        )

        for item in all_items:
            dedup_key = (item.signal, item.source_field, item.matched_value)
            if dedup_key not in seen_keys:
                seen_keys.add(dedup_key)
                collection.add(item)

        collection.metadata_completeness_score = completeness_score
        return collection

    def extract_batch(self, opportunities: list[Any]) -> list[RiskEvidenceCollection]:
        """
        Extract evidence for a batch of opportunities in-memory.

        Guarantees zero N+1 queries.
        """
        return [self.extract(opp) for opp in opportunities]


# Global singleton
risk_evidence_extractor = RiskEvidenceExtractor()
