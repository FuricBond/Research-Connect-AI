"""
Unified Evidence Extraction Orchestrator for Phase 2.6B & 2.6D.

Coordinates modular extractors, venue/publisher intelligence, deduplicates signals,
and produces a structured RiskEvidenceCollection with attached ResolvedAcademicEntity.
Operates strictly in-memory with zero network or database queries.
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
from app.ranking.risk.models import (
    EvidenceSignal,
    ResolvedAcademicEntity,
    RiskEvidence,
    RiskEvidenceCollection,
)
from app.ranking.risk.venue_intelligence import venue_publisher_intelligence_service


class RiskEvidenceExtractor:
    """
    Orchestrates deterministic extraction of trust, risk, and neutral evidence
    from academic opportunity metadata and resolves cross-source academic entities.
    """

    def __init__(self) -> None:
        self.trust_extractor = TrustEvidenceExtractor()
        self.domain_extractor = DomainEvidenceExtractor()
        self.editorial_extractor = EditorialReviewEvidenceExtractor()
        self.payment_extractor = PaymentFeeEvidenceExtractor()
        self.completeness_extractor = MetadataCompletenessExtractor()
        self.venue_service = venue_publisher_intelligence_service

    def extract(
        self,
        opportunity: Any,
        source_record: Any | None = None,
        resolved_entity: ResolvedAcademicEntity | None = None,
    ) -> RiskEvidenceCollection:
        """
        Extract all observable evidence for a single opportunity and resolve academic entity.

        Parameters
        ----------
        opportunity:
            OpportunityModel instance, OpportunityRead schema, or dictionary.
        source_record:
            Optional pre-fetched ResearchSourceModel or source metadata.
        resolved_entity:
            Optional pre-resolved academic entity for batch optimization.

        Returns
        -------
        RiskEvidenceCollection
            Deduplicated, structured collection of extracted evidence with resolved entity.
        """
        raw_id = _get_field(opportunity, "id")
        opp_id = str(raw_id) if raw_id is not None else None

        collection = RiskEvidenceCollection(opportunity_id=opp_id)

        # 1. Resolve Academic Entity via VenuePublisherIntelligenceService
        entity = resolved_entity
        if entity is None:
            entity = self.venue_service.resolve_entity(opportunity, source_record=source_record)

        collection.resolved_entity = entity

        # 2. Run all modular extractors and venue intelligence
        trust_items = self.trust_extractor.extract(opportunity)
        domain_items = self.domain_extractor.extract(opportunity)
        editorial_items = self.editorial_extractor.extract(opportunity)
        payment_items = self.payment_extractor.extract(opportunity)
        completeness_items, completeness_score = self.completeness_extractor.extract(opportunity)
        venue_items = self.venue_service.extract_venue_evidence(entity, opportunity)

        # 3. Deduplicate and collect
        seen_keys: set[tuple[str, str, str | None]] = set()
        seen_signals: set[str] = set()

        all_items: list[RiskEvidence] = (
            trust_items
            + domain_items
            + editorial_items
            + payment_items
            + completeness_items
            + venue_items
        )

        for item in all_items:
            # Enforce single occurrence for singular canonical signals like DOAJ_INDEXED
            if item.signal == EvidenceSignal.DOAJ_INDEXED.value:
                if item.signal in seen_signals:
                    continue
                seen_signals.add(item.signal)

            dedup_key = (item.signal, item.source_field, item.matched_value)
            if dedup_key not in seen_keys:
                seen_keys.add(dedup_key)
                collection.add(item)

        collection.metadata_completeness_score = completeness_score
        return collection

    def extract_batch(
        self,
        opportunities: list[Any],
        source_records: dict[str, Any] | None = None,
    ) -> list[RiskEvidenceCollection]:
        """
        Extract evidence for a batch of opportunities in-memory with pre-fetched source records.

        Guarantees zero N+1 queries.
        """
        resolved_entities = self.venue_service.resolve_batch(opportunities, source_records=source_records)
        return [
            self.extract(opp, resolved_entity=ent)
            for opp, ent in zip(opportunities, resolved_entities)
        ]


# Global singleton
risk_evidence_extractor = RiskEvidenceExtractor()
