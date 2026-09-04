"""
Venue & Publisher Intelligence & Cross-Source Resolution Service for Phase 2.6D.

Provides deterministic resolution of academic entities:
  Opportunity -> Venue -> Publisher / Organizer -> Academic Identifiers -> External Research Sources

Key Architectural Invariants:
  1. UNKNOWN != PREDATORY: Missing identifiers, unindexed publishers, or DOAJ=False are neutral.
  2. Resolution Confidence != Risk Confidence: High resolution confidence indicates identity certainty, not safety.
  3. Organizer != Publisher: Scientific societies/organizers remain distinct from proceedings/journal publishers.
  4. Zero Network Calls: Resolution runs strictly offline using local registries, models, and pre-fetched data.
  5. Zero N+1 Queries: Batch resolution uses in-memory lookups against pre-fetched candidate mappings.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from app.ranking.risk.models import (
    EvidenceCategory,
    EvidenceConfidence,
    EvidenceProvenance,
    EvidenceSignal,
    EvidenceStrength,
    ResolutionStatus,
    ResolvedAcademicEntity,
    RiskEvidence,
)
from app.ranking.risk.normalizers import normalize_url, validate_doi, validate_issn
from app.ranking.risk.registries import (
    TRUSTED_ACADEMIC_PUBLISHERS,
    TRUSTED_ACADEMIC_SOCIETIES,
    match_trusted_publisher,
    match_trusted_society,
)
from app.ranking.venue_intelligence import (
    get_canonical_venue_key,
    normalize_issn,
    normalize_venue_name,
)

logger = logging.getLogger(__name__)

# ── Deterministic Academic Domain -> Publisher Mapping ────────────────────────

PUBLISHER_DOMAINS: dict[str, str] = {
    # IEEE & Societies
    "ieee.org": "IEEE",
    "computer.org": "IEEE",
    "ieeexplore.ieee.org": "IEEE",
    # ACM
    "acm.org": "ACM",
    "dl.acm.org": "ACM",
    # Springer / Nature Portfolio
    "springer.com": "Springer Nature",
    "link.springer.com": "Springer Nature",
    "springeropen.com": "Springer Nature",
    "nature.com": "Nature Portfolio",
    "biomedcentral.com": "BioMed Central",
    # Elsevier & Cell Press
    "elsevier.com": "Elsevier",
    "sciencedirect.com": "Elsevier",
    "cell.com": "Cell Press",
    # Wiley
    "wiley.com": "John Wiley & Sons",
    "onlinelibrary.wiley.com": "John Wiley & Sons",
    # University Presses
    "oup.com": "Oxford University Press",
    "academic.oup.com": "Oxford University Press",
    "cambridge.org": "Cambridge University Press",
    "mitpress.mit.edu": "MIT Press",
    # Taylor & Francis / Routledge / CRC
    "tandfonline.com": "Taylor & Francis",
    "taylorandfrancis.com": "Taylor & Francis",
    "routledge.com": "Taylor & Francis (Routledge)",
    "crcpress.com": "Taylor & Francis (CRC Press)",
    # SAGE
    "sagepub.com": "SAGE Publishing",
    "journals.sagepub.com": "SAGE Publishing",
    # Open Access Publishers
    "plos.org": "PLOS",
    "frontiersin.org": "Frontiers Media",
    "mdpi.com": "MDPI",
    "degruyter.com": "De Gruyter",
    # Physical / Chemical / Math Societies
    "iop.org": "IOP Publishing",
    "iopscience.iop.org": "IOP Publishing",
    "aip.org": "AIP Publishing",
    "pubs.aip.org": "AIP Publishing",
    "aps.org": "APS",
    "journals.aps.org": "APS",
    "acs.org": "ACS",
    "pubs.acs.org": "ACS",
    "ams.org": "AMS",
    "aaas.org": "AAAS",
    "science.org": "AAAS",
    # Medical & Professional
    "bmj.com": "BMJ Publishing",
    "emerald.com": "Emerald Publishing",
    "karger.com": "Karger Publishers",
    "wolterskluwer.com": "Wolters Kluwer",
    "lww.com": "Wolters Kluwer (LWW)",
    # Computing / AI Societies (as hosts/organizers)
    "aaai.org": "AAAI",
    "aclweb.org": "ACL",
    "usenix.org": "USENIX Association",
    "siam.org": "SIAM",
    "spie.org": "SPIE",
    "optica.org": "Optica (OSA)",
}

# ── Standard Academic Publisher DOI Prefixes ──────────────────────────────────

KNOWN_DOI_PREFIXES: dict[str, str] = {
    "10.1109": "IEEE",
    "10.1145": "ACM",
    "10.1007": "Springer Nature",
    "10.1038": "Nature Portfolio",
    "10.1186": "BioMed Central",
    "10.1016": "Elsevier",
    "10.1002": "John Wiley & Sons",
    "10.1093": "Oxford University Press",
    "10.1017": "Cambridge University Press",
    "10.1177": "SAGE Publishing",
    "10.1371": "PLOS",
    "10.3389": "Frontiers Media",
    "10.3390": "MDPI",
    "10.1088": "IOP Publishing",
    "10.1063": "AIP Publishing",
    "10.1103": "APS",
    "10.1021": "ACS",
    "10.1090": "AMS",
    "10.1126": "AAAS",
    "10.1136": "BMJ Publishing",
}

# ── Affiliated Imprints & Parent Publishing Groups ────────────────────────────

_KNOWN_AFFILIATED_PUBLISHERS: dict[str, set[str]] = {
    "springer nature": {"nature portfolio", "nature publishing group", "biomed central", "springer", "springer verlag", "springer-verlag"},
    "nature portfolio": {"springer nature", "springer", "nature publishing group"},
    "nature publishing group": {"springer nature", "nature portfolio", "springer"},
    "elsevier": {"cell press", "the lancet", "lancet"},
    "cell press": {"elsevier"},
    "taylor & francis": {"routledge", "crc press", "taylor and francis"},
    "routledge": {"taylor & francis", "taylor and francis"},
    "crc press": {"taylor & francis", "taylor and francis"},
    "wolters kluwer": {"lippincott williams & wilkins", "lww"},
    "ieee": {"ieee computer society", "institute of electrical and electronics engineers"},
    "acm": {"association for computing machinery"},
}


def _get_attr(obj: Any, field_name: str) -> Any:
    """Safely extract field from model or dict."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(field_name)
    return getattr(obj, field_name, None)


def _publishers_compatible(pub_a: str | None, pub_b: str | None) -> bool:
    """
    Check if two publisher strings refer to the same or compatible entity.
    E.g. 'IEEE' and 'IEEE Computer Society', or 'Springer' and 'Springer Nature'.
    """
    if not pub_a or not pub_b:
        return True

    clean_a = pub_a.strip().lower()
    clean_b = pub_b.strip().lower()

    if clean_a == clean_b:
        return True

    # Check canonical mapping
    _, canon_a = match_trusted_publisher(clean_a)
    _, canon_b = match_trusted_publisher(clean_b)
    canon_a_clean = (canon_a or clean_a).lower()
    canon_b_clean = (canon_b or clean_b).lower()

    if canon_a_clean == canon_b_clean:
        return True

    # Check affiliated publisher imprints
    if canon_a_clean in _KNOWN_AFFILIATED_PUBLISHERS and canon_b_clean in _KNOWN_AFFILIATED_PUBLISHERS[canon_a_clean]:
        return True
    if canon_b_clean in _KNOWN_AFFILIATED_PUBLISHERS and canon_a_clean in _KNOWN_AFFILIATED_PUBLISHERS[canon_b_clean]:
        return True

    # Substring / token containment
    if clean_a in clean_b or clean_b in clean_a:
        return True

    return False


class VenuePublisherIntelligenceService:
    """
    Deterministic cross-source academic entity resolution engine.
    """

    def resolve_entity(
        self,
        opportunity: Any,
        source_record: Any | None = None,
    ) -> ResolvedAcademicEntity:
        """
        Resolve an academic opportunity to a structured academic entity.

        Parameters
        ----------
        opportunity:
            OpportunityModel, OpportunityRead, or dictionary.
        source_record:
            Optional pre-fetched ResearchSourceModel instance, dict, or None.

        Returns
        -------
        ResolvedAcademicEntity
            Deterministic resolution result with status, confidence, and metadata.
        """
        if opportunity is None:
            return ResolvedAcademicEntity(
                resolution_status=ResolutionStatus.UNRESOLVED,
                resolution_confidence=0.0,
            )

        # 1. Extract core attributes from opportunity
        opp_type_raw = _get_attr(opportunity, "opportunity_type") or "UNKNOWN"
        entity_type = "JOURNAL" if "JOURNAL" in str(opp_type_raw).upper() else (
            "CONFERENCE" if "CONFERENCE" in str(opp_type_raw).upper() else "UNKNOWN"
        )

        title = _get_attr(opportunity, "title")
        series_name = _get_attr(opportunity, "series_name")
        opp_publisher = _get_attr(opportunity, "publisher")
        opp_organizer = _get_attr(opportunity, "organizer")
        website_url = _get_attr(opportunity, "website_url")
        raw_issn = _get_attr(opportunity, "issn")
        raw_issn_l = _get_attr(opportunity, "issn_l")
        raw_doi = _get_attr(opportunity, "doi")
        raw_metadata = _get_attr(opportunity, "raw_metadata") or {}

        # 2. Identifier Resolution & Validation
        norm_issn = validate_issn(str(raw_issn)) if raw_issn else None
        norm_issn_l = validate_issn(str(raw_issn_l)) if raw_issn_l else None
        norm_doi = validate_doi(str(raw_doi)) if raw_doi else None

        # Linking ISSN precedence
        issn_l: str | None = norm_issn_l or norm_issn

        doi_prefix: str | None = None
        if norm_doi and norm_doi.startswith("10."):
            parts = norm_doi.split("/")
            if len(parts) >= 2:
                doi_prefix = parts[0]

        venue_name = normalize_venue_name(series_name) or normalize_venue_name(title)
        canon_key = get_canonical_venue_key(
            name=venue_name,
            issn_l=issn_l,
            issn_list=[norm_issn] if norm_issn else None,
        )

        # 3. Publisher & Organizer Separation & Normalization
        canon_publisher: str | None = None
        publisher_is_trusted = False
        if opp_publisher and isinstance(opp_publisher, str) and opp_publisher.strip():
            is_trusted, matched_canon = match_trusted_publisher(opp_publisher)
            publisher_is_trusted = is_trusted
            canon_publisher = matched_canon if is_trusted else opp_publisher.strip()

        canon_organizer: str | None = None
        organizer_is_trusted = False
        if opp_organizer and isinstance(opp_organizer, str) and opp_organizer.strip():
            is_society, matched_soc = match_trusted_society(opp_organizer)
            organizer_is_trusted = is_society
            canon_organizer = matched_soc if is_society else opp_organizer.strip()

        # 4. Domain Intelligence
        norm_url_data = normalize_url(website_url)
        domain = norm_url_data.get("domain")
        hostname = norm_url_data.get("hostname")

        domain_publisher: str | None = None
        domain_confirmed = False
        conflicts: list[str] = []

        if hostname and hostname in PUBLISHER_DOMAINS:
            domain_publisher = PUBLISHER_DOMAINS[hostname]
        elif domain and domain in PUBLISHER_DOMAINS:
            domain_publisher = PUBLISHER_DOMAINS[domain]

        if domain_publisher:
            if canon_publisher:
                if _publishers_compatible(canon_publisher, domain_publisher):
                    domain_confirmed = True
                else:
                    conflicts.append(
                        f"Domain publisher mismatch: domain '{domain}' belongs to '{domain_publisher}', "
                        f"but opportunity claims publisher '{canon_publisher}'."
                    )
            else:
                # Infer publisher from strong domain mapping if otherwise missing
                canon_publisher = domain_publisher
                domain_confirmed = True

        # 5. DOI Prefix Intelligence
        doi_confirmed = False
        if doi_prefix and doi_prefix in KNOWN_DOI_PREFIXES:
            doi_pub = KNOWN_DOI_PREFIXES[doi_prefix]
            if canon_publisher:
                if _publishers_compatible(canon_publisher, doi_pub):
                    doi_confirmed = True
                else:
                    conflicts.append(
                        f"DOI prefix mismatch: prefix '{doi_prefix}' belongs to '{doi_pub}', "
                        f"but opportunity claims publisher '{canon_publisher}'."
                    )
            else:
                canon_publisher = doi_pub
                doi_confirmed = True

        # 6. Cross-Source ResearchSource Enrichment (OpenAlex / DOAJ)
        matched_sources: list[str] = []
        openalex_id: str | None = None
        is_in_doaj: bool | None = None
        is_oa: bool | None = None
        works_count = 0
        cited_by_count = 0

        # If source_record is passed, inspect it
        target_source = source_record
        if target_source is None and hasattr(opportunity, "primary_source"):
            target_source = getattr(opportunity, "primary_source")

        if target_source is not None:
            src_name = _get_attr(target_source, "display_name")
            src_openalex = _get_attr(target_source, "openalex_id")
            src_issn_l = normalize_issn(_get_attr(target_source, "issn_l"))
            src_issns = _get_attr(target_source, "issn") or []
            src_host_org = _get_attr(target_source, "host_organization")
            src_doaj = bool(_get_attr(target_source, "is_in_doaj") or False)
            src_oa = bool(_get_attr(target_source, "is_oa") or False)
            src_works = _get_attr(target_source, "works_count") or 0
            src_cits = _get_attr(target_source, "cited_by_count") or 0

            if src_openalex:
                matched_sources.append("OpenAlex")
                openalex_id = str(src_openalex)

            if src_issn_l:
                if issn_l and issn_l != src_issn_l:
                    # Check alternative ISSN list
                    clean_issns = [normalize_issn(i) for i in src_issns if isinstance(i, str)]
                    if norm_issn not in clean_issns and norm_issn_l not in clean_issns:
                        conflicts.append(
                            f"ISSN discrepancy: opportunity ISSN '{issn_l}' differs from source Linking ISSN '{src_issn_l}'."
                        )
                issn_l = src_issn_l

            # Check DOAJ status
            is_in_doaj = src_doaj
            is_oa = src_oa
            works_count = max(0, int(src_works)) if isinstance(src_works, (int, float)) else 0
            cited_by_count = max(0, int(src_cits)) if isinstance(src_cits, (int, float)) else 0

            # Compare Host Organization
            if src_host_org and isinstance(src_host_org, str) and src_host_org.strip():
                if canon_publisher:
                    if not _publishers_compatible(canon_publisher, src_host_org):
                        conflicts.append(
                            f"Host organization discrepancy: opportunity publisher '{canon_publisher}' "
                            f"differs from external host '{src_host_org.strip()}'."
                        )
                else:
                    canon_publisher = src_host_org.strip()

            if src_name and not venue_name:
                venue_name = normalize_venue_name(src_name)

        # Crossref metadata from ingestion or container
        if isinstance(raw_metadata, dict):
            if "crossref" in raw_metadata or "crossref_container_title" in raw_metadata:
                matched_sources.append("Crossref")

        # 7. Resolution Confidence Computation
        # Confidence is strictly bounded [0.00, 1.00] and measures identity certainty, NOT risk
        confidence = 0.0

        if issn_l or norm_issn:
            confidence += 0.45
        if publisher_is_trusted:
            confidence += 0.20
        if domain_confirmed:
            confidence += 0.10
        if doi_confirmed:
            confidence += 0.10
        if organizer_is_trusted:
            confidence += 0.15
        if matched_sources:
            confidence += 0.20
        if canon_key and canon_key.startswith("issn:"):
            confidence += 0.10
        elif canon_key and canon_key.startswith("name:"):
            confidence += 0.05

        # Deduct for conflicts
        if conflicts:
            confidence = max(0.0, confidence - (0.25 * len(conflicts)))

        confidence = min(1.0, max(0.0, confidence))

        # Determine ResolutionStatus
        if confidence >= 0.75:
            res_status = ResolutionStatus.RESOLVED
        elif confidence >= 0.35:
            res_status = ResolutionStatus.PARTIALLY_RESOLVED
        else:
            res_status = ResolutionStatus.UNRESOLVED

        provenance = "STATIC_TRUST_REGISTRY" if (publisher_is_trusted and not matched_sources) else (
            "EXTERNAL_VERIFICATION" if matched_sources else "DERIVED"
        )

        return ResolvedAcademicEntity(
            entity_type=entity_type,
            canonical_name=venue_name,
            publisher=canon_publisher,
            organizer=canon_organizer,
            domain=domain,
            issn=norm_issn,
            issn_l=issn_l,
            doi_prefix=doi_prefix,
            openalex_id=openalex_id,
            is_in_doaj=is_in_doaj,
            is_oa=is_oa,
            works_count=works_count,
            cited_by_count=cited_by_count,
            resolution_status=res_status,
            resolution_confidence=confidence,
            matched_sources=matched_sources,
            conflicts=conflicts,
            provenance=provenance,
        )

    def extract_venue_evidence(
        self,
        entity: ResolvedAcademicEntity,
        opportunity: Any,
    ) -> list[RiskEvidence]:
        """
        Produce atomic, typed RiskEvidence items from a resolved academic entity.

        Enforces Missing Metadata Neutrality:
          DOAJ=False -> Neutral (No evidence created)
          Unresolved entity -> Neutral (No negative evidence created)
          Unknown publisher -> Neutral
        """
        evidence_list: list[RiskEvidence] = []

        # 1. Verified Venue Identity
        if entity.resolution_status == ResolutionStatus.RESOLVED and entity.canonical_name:
            evidence_list.append(
                RiskEvidence(
                    signal=EvidenceSignal.VERIFIED_VENUE_IDENTITY.value,
                    category=EvidenceCategory.POSITIVE_TRUST,
                    strength=EvidenceStrength.STRONG,
                    confidence=EvidenceConfidence.HIGH,
                    provenance=EvidenceProvenance.EXTERNAL_VERIFICATION if entity.matched_sources else EvidenceProvenance.DERIVED,
                    source_field="venue.identity",
                    matched_value=entity.canonical_name,
                    explanation=f"Academic venue identity deterministically resolved: '{entity.canonical_name}'.",
                    metadata={"confidence": round(entity.resolution_confidence, 4), "sources": entity.matched_sources},
                )
            )

        # 2. Verified Publisher Identity
        if entity.publisher:
            is_trusted, canon_pub = match_trusted_publisher(entity.publisher)
            if is_trusted and canon_pub:
                evidence_list.append(
                    RiskEvidence(
                        signal=EvidenceSignal.VERIFIED_PUBLISHER_IDENTITY.value,
                        category=EvidenceCategory.POSITIVE_TRUST,
                        strength=EvidenceStrength.STRONG,
                        confidence=EvidenceConfidence.HIGH,
                        provenance=EvidenceProvenance.STATIC_TRUST_REGISTRY,
                        source_field="venue.publisher",
                        matched_value=canon_pub,
                        explanation=f"Publisher resolved to verified global academic publisher: {canon_pub}.",
                        metadata={"canonical_publisher": canon_pub},
                    )
                )

        # 3. Verified Linking ISSN (ISSN-L)
        if entity.issn_l:
            evidence_list.append(
                RiskEvidence(
                    signal=EvidenceSignal.VERIFIED_ISSN_L.value,
                    category=EvidenceCategory.POSITIVE_TRUST,
                    strength=EvidenceStrength.MODERATE,
                    confidence=EvidenceConfidence.HIGH,
                    provenance=EvidenceProvenance.NORMALIZED_METADATA,
                    source_field="venue.issn_l",
                    matched_value=entity.issn_l,
                    explanation=f"Canonical Linking ISSN (ISSN-L) established: {entity.issn_l}.",
                )
            )

        # 4. Publisher Domain Match
        if entity.domain and entity.domain in PUBLISHER_DOMAINS:
            domain_pub = PUBLISHER_DOMAINS[entity.domain]
            if entity.publisher and _publishers_compatible(entity.publisher, domain_pub):
                evidence_list.append(
                    RiskEvidence(
                        signal=EvidenceSignal.PUBLISHER_DOMAIN_MATCH.value,
                        category=EvidenceCategory.POSITIVE_TRUST,
                        strength=EvidenceStrength.MODERATE,
                        confidence=EvidenceConfidence.HIGH,
                        provenance=EvidenceProvenance.STATIC_TRUST_REGISTRY,
                        source_field="venue.domain",
                        matched_value=entity.domain,
                        explanation=f"Opportunity domain '{entity.domain}' confirms academic publisher '{domain_pub}'.",
                        metadata={"domain": entity.domain, "publisher": domain_pub},
                    )
                )

        # 5. OpenAlex Source Match
        if "OpenAlex" in entity.matched_sources and entity.openalex_id:
            evidence_list.append(
                RiskEvidence(
                    signal=EvidenceSignal.OPENALEX_METADATA_MATCH.value,
                    category=EvidenceCategory.POSITIVE_TRUST,
                    strength=EvidenceStrength.MODERATE,
                    confidence=EvidenceConfidence.HIGH,
                    provenance=EvidenceProvenance.EXTERNAL_VERIFICATION,
                    source_field="research_sources.openalex_id",
                    matched_value=entity.openalex_id,
                    explanation=f"Linked to verified OpenAlex publication venue record ({entity.openalex_id}).",
                    metadata={
                        "openalex_id": entity.openalex_id,
                        "works_count": entity.works_count,
                        "cited_by_count": entity.cited_by_count,
                    },
                )
            )

        # 6. Crossref Metadata Match
        if "Crossref" in entity.matched_sources:
            evidence_list.append(
                RiskEvidence(
                    signal=EvidenceSignal.CROSSREF_METADATA_MATCH.value,
                    category=EvidenceCategory.POSITIVE_TRUST,
                    strength=EvidenceStrength.WEAK,
                    confidence=EvidenceConfidence.HIGH,
                    provenance=EvidenceProvenance.EXTERNAL_VERIFICATION,
                    source_field="raw_metadata.crossref",
                    matched_value="Crossref",
                    explanation="Opportunity publication metadata verified against Crossref bibliographic record.",
                )
            )

        # 7. DOAJ Evidence (Strictly Positive; DOAJ=False or None is Neutral)
        if entity.is_in_doaj is True:
            evidence_list.append(
                RiskEvidence(
                    signal=EvidenceSignal.DOAJ_INDEXED.value,
                    category=EvidenceCategory.POSITIVE_TRUST,
                    strength=EvidenceStrength.STRONG,
                    confidence=EvidenceConfidence.HIGH,
                    provenance=EvidenceProvenance.EXTERNAL_VERIFICATION,
                    source_field="research_sources.is_in_doaj",
                    matched_value="DOAJ",
                    explanation="Publication venue is actively indexed in the Directory of Open Access Journals (DOAJ).",
                )
            )

        # 8. Cross-Source Metadata Discrepancy / Conflicts (Cautionary, NOT auto-predatory)
        if entity.conflicts:
            joined_conflicts = " | ".join(entity.conflicts)
            evidence_list.append(
                RiskEvidence(
                    signal=EvidenceSignal.CONFLICTING_METADATA.value,
                    category=EvidenceCategory.NEGATIVE_SUSPICIOUS,
                    strength=EvidenceStrength.WEAK,
                    confidence=EvidenceConfidence.MEDIUM,
                    provenance=EvidenceProvenance.DERIVED,
                    source_field="cross_source.resolution",
                    matched_value=joined_conflicts,
                    explanation=f"Cross-source metadata discrepancies detected: {joined_conflicts}.",
                    metadata={"conflicts": entity.conflicts},
                )
            )

        return evidence_list

    def resolve_batch(
        self,
        opportunities: list[Any],
        source_records: dict[str, Any] | None = None,
    ) -> list[ResolvedAcademicEntity]:
        """
        Batch resolve opportunities in-memory with zero N+1 database queries.

        Parameters
        ----------
        opportunities:
            List of opportunities to resolve.
        source_records:
            Optional pre-fetched candidate mapping keyed by ISSN (e.g. '0028-0836')
            or canonical key (e.g. 'issn:0028-0836').
        """
        resolved: list[ResolvedAcademicEntity] = []
        source_dict = source_records or {}

        for opp in opportunities:
            # Check if matching source record exists in pre-fetched dictionary
            candidate_source: Any | None = None
            raw_issn = _get_attr(opp, "issn") or _get_attr(opp, "issn_l")
            norm_issn = validate_issn(str(raw_issn)) if raw_issn else None

            if norm_issn and norm_issn in source_dict:
                candidate_source = source_dict[norm_issn]
            elif norm_issn and f"issn:{norm_issn}" in source_dict:
                candidate_source = source_dict[f"issn:{norm_issn}"]
            else:
                title = _get_attr(opp, "series_name") or _get_attr(opp, "title")
                canon_key = get_canonical_venue_key(name=title, issn_l=norm_issn)
                if canon_key and canon_key in source_dict:
                    candidate_source = source_dict[canon_key]

            entity = self.resolve_entity(opp, source_record=candidate_source)
            resolved.append(entity)

        return resolved


# Global singleton instance
venue_publisher_intelligence_service = VenuePublisherIntelligenceService()
