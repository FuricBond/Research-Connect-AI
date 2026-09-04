"""
Deterministic Risk Explainability Layer for Phase 2.6F.

Exposes trust and risk analysis established across Phases 2.6B–2.6E in a deterministic,
transparent, provenance-backed, and academically conservative representation.

Phase 2.6C DeterministicRiskScoringEngine remains the SOLE composite risk scorer.
This module does NOT calculate or alter risk scores; it translates RiskAssessment and
underlying RiskEvidenceCollection into human- and machine-readable explanations.

Guarantees:
  1. UNKNOWN != PREDATORY (Missing metadata is neutral and documented as a limitation).
  2. Conservative, non-defamatory, academic wording.
  3. Strict provenance preservation for every evidence item.
  4. Mathematical score attribution reconciling gross negative, trust mitigation, and final score.
  5. Anti-correlation consolidation: single underlying facts are presented clearly with context.
  6. 100% offline, zero database queries, zero network calls, strictly deterministic.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from app.ranking.risk.engine import risk_evidence_extractor
from app.ranking.risk.models import (
    EvidenceCategory,
    EvidenceConfidence,
    EvidenceProvenance,
    EvidenceSignal,
    EvidenceStrength,
    ResolvedAcademicEntity,
    RiskAssessment,
    RiskEvidence,
    RiskEvidenceCollection,
    RiskLevel,
)
from app.ranking.risk.scoring import RiskScoringConfig, risk_scoring_engine


# ── Structured Evidence Item Explanation ──────────────────────────────────────


@dataclass(frozen=True)
class RiskEvidenceExplanation:
    """
    Structured, provenance-backed explanation for an atomic piece of risk or trust evidence.

    Attributes
    ----------
    signal:
        Standardized identifier of the signal (e.g. 'VERIFIED_PUBLISHER').
    category:
        Categorical classification ('POSITIVE_TRUST', 'NEGATIVE_SUSPICIOUS', 'NEUTRAL_UNKNOWN').
    strength:
        Impact level of this signal ('NONE', 'WEAK', 'MODERATE', 'STRONG').
    confidence:
        Observation reliability based on provenance and completeness ('LOW', 'MEDIUM', 'HIGH').
    provenance:
        Source origin of the evidence ('STATIC_TRUST_REGISTRY', 'GRAPH_ANALYSIS', etc.).
    source_field:
        Opportunity field or origin where evidence was detected (e.g. 'publisher').
    matched_value:
        Exact or normalized token/phrase matched.
    explanation:
        Clear, conservative human-readable description of the evidence.
    is_present:
        True if affirmative observation; False if representing missing metadata.
    contribution:
        Calculated effective score contribution in Phase 2.6C scoring formulation.
    severity:
        Visual severity classification ('HIGH', 'MODERATE', 'LOW', 'NEUTRAL', 'TRUST').
    evidence_type:
        Originating intelligence layer ('DIRECT_METADATA', 'VENUE_INTELLIGENCE', 'GRAPH_ANALYSIS').
    metadata:
        Additional structured attributes (e.g. pattern name, tier, cluster details).
    """

    signal: str
    category: str
    strength: str
    confidence: str
    provenance: str
    source_field: str
    matched_value: str | None = None
    explanation: str = ""
    is_present: bool = True
    contribution: float = 0.0
    severity: str = "NEUTRAL"
    evidence_type: str = "DIRECT_METADATA"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "signal": self.signal,
            "category": self.category,
            "strength": self.strength,
            "confidence": self.confidence,
            "provenance": self.provenance,
            "source_field": self.source_field,
            "matched_value": self.matched_value,
            "explanation": self.explanation,
            "is_present": self.is_present,
            "contribution": round(self.contribution, 4),
            "severity": self.severity,
            "evidence_type": self.evidence_type,
            "metadata": dict(self.metadata),
        }


# ── Canonical Risk Explanation Model ──────────────────────────────────────────


@dataclass(frozen=True)
class RiskExplanation:
    """
    Canonical deterministic risk explanation container derived strictly from
    RiskAssessment and RiskEvidenceCollection.
    """

    opportunity_id: str | None
    risk_score: float
    risk_level: str
    risk_confidence: float
    evidence_sufficiency: str
    is_predatory_flag: bool
    summary: str
    positive_trust_signals: list[RiskEvidenceExplanation] = field(default_factory=list)
    suspicious_signals: list[RiskEvidenceExplanation] = field(default_factory=list)
    neutral_signals: list[RiskEvidenceExplanation] = field(default_factory=list)
    graph_signals: list[RiskEvidenceExplanation] = field(default_factory=list)
    venue_signals: list[RiskEvidenceExplanation] = field(default_factory=list)
    publisher_signals: list[RiskEvidenceExplanation] = field(default_factory=list)
    evidence_items: list[RiskEvidenceExplanation] = field(default_factory=list)
    risk_reasons: list[str] = field(default_factory=list)
    provenance_summary: dict[str, int] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)
    gross_negative_score: float = 0.0
    trust_mitigation_score: float = 0.0
    resolved_entity: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "opportunity_id": self.opportunity_id,
            "risk_score": round(self.risk_score, 2),
            "risk_level": self.risk_level,
            "risk_confidence": round(self.risk_confidence, 2),
            "evidence_sufficiency": self.evidence_sufficiency,
            "is_predatory_flag": self.is_predatory_flag,
            "summary": self.summary,
            "positive_trust_signals": [s.to_dict() for s in self.positive_trust_signals],
            "suspicious_signals": [s.to_dict() for s in self.suspicious_signals],
            "neutral_signals": [s.to_dict() for s in self.neutral_signals],
            "graph_signals": [s.to_dict() for s in self.graph_signals],
            "venue_signals": [s.to_dict() for s in self.venue_signals],
            "publisher_signals": [s.to_dict() for s in self.publisher_signals],
            "evidence_items": [s.to_dict() for s in self.evidence_items],
            "risk_reasons": list(self.risk_reasons),
            "provenance_summary": dict(self.provenance_summary),
            "limitations": list(self.limitations),
            "gross_negative_score": round(self.gross_negative_score, 4),
            "trust_mitigation_score": round(self.trust_mitigation_score, 4),
            "resolved_entity": self.resolved_entity,
        }


# ── Risk Explainability Service ───────────────────────────────────────────────


class RiskExplainabilityService:
    """
    Deterministic explainability service for translating Phase 2.6C RiskAssessment
    and RiskEvidenceCollection into user-facing, provenance-backed explanations.
    """

    def __init__(self, scoring_config: RiskScoringConfig | None = None) -> None:
        self.config = scoring_config or RiskScoringConfig()

    def explain(
        self,
        assessment: RiskAssessment,
        opportunity: Any | None = None,
    ) -> RiskExplanation:
        """
        Generate deterministic RiskExplanation from RiskAssessment and underlying evidence.

        Parameters
        ----------
        assessment:
            RiskAssessment produced by Phase 2.6C scoring engine.
        opportunity:
            Optional original opportunity object (used if assessment lacks underlying evidence).

        Returns
        -------
        RiskExplanation
            Complete structured explainability container.
        """
        collection = assessment.evidence_collection
        if collection is None and opportunity is not None:
            collection = risk_evidence_extractor.extract(opportunity)

        if collection is None:
            # Fallback for bare assessment without underlying collection
            collection = RiskEvidenceCollection(opportunity_id=assessment.opportunity_id)

        # 1. Determine Evidence Sufficiency
        evidence_sufficiency = self._determine_sufficiency(assessment, collection)

        # 2. Build individual RiskEvidenceExplanation objects
        explained_items = self._build_evidence_explanations(collection)

        # 3. Categorize and sort signals deterministically
        positive_signals = sorted(
            [e for e in explained_items if e.category == EvidenceCategory.POSITIVE_TRUST.value],
            key=lambda x: (-x.contribution, x.signal, x.source_field, str(x.matched_value)),
        )
        suspicious_signals = sorted(
            [e for e in explained_items if e.category == EvidenceCategory.NEGATIVE_SUSPICIOUS.value],
            key=lambda x: (-x.contribution, x.signal, x.source_field, str(x.matched_value)),
        )
        neutral_signals = sorted(
            [e for e in explained_items if e.category == EvidenceCategory.NEUTRAL_UNKNOWN.value],
            key=lambda x: (x.signal, x.source_field, str(x.matched_value)),
        )

        # 4. Domain & Intelligence Sub-Lists
        graph_signals = sorted(
            [e for e in explained_items if e.evidence_type == "GRAPH_ANALYSIS"],
            key=lambda x: (-x.contribution, x.signal, x.source_field),
        )
        venue_signals = sorted(
            [
                e for e in explained_items
                if e.source_field in ("venue", "journal", "conference", "series_name")
                or e.signal in (
                    EvidenceSignal.VERIFIED_VENUE.value,
                    EvidenceSignal.VERIFIED_VENUE_IDENTITY.value,
                    EvidenceSignal.DOAJ_INDEXED.value,
                    EvidenceSignal.VALID_ISSN.value,
                    EvidenceSignal.VERIFIED_ISSN_L.value,
                    EvidenceSignal.VALID_DOI.value,
                    EvidenceSignal.VERIFIED_INDEXING.value,
                    EvidenceSignal.OPENALEX_METADATA_MATCH.value,
                    EvidenceSignal.CROSSREF_METADATA_MATCH.value,
                )
            ],
            key=lambda x: (-x.contribution, x.signal, x.source_field),
        )
        publisher_signals = sorted(
            [
                e for e in explained_items
                if e.source_field in ("publisher", "organizer")
                or e.signal in (
                    EvidenceSignal.VERIFIED_PUBLISHER.value,
                    EvidenceSignal.VERIFIED_PUBLISHER_IDENTITY.value,
                    EvidenceSignal.VERIFIED_SOCIETY.value,
                    EvidenceSignal.PUBLISHER_DOMAIN_MATCH.value,
                    EvidenceSignal.SUSPICIOUS_PUBLISHER_PATTERN.value,
                    EvidenceSignal.SUSPICIOUS_PUBLISHER_CLUSTER.value,
                    EvidenceSignal.HIGH_ORGANIZER_REUSE.value,
                    EvidenceSignal.SUSPICIOUS_ORGANIZER_CLUSTER.value,
                )
            ],
            key=lambda x: (-x.contribution, x.signal, x.source_field),
        )

        # 5. Provenance Summary (sorted alphabetically by key)
        prov_counts: dict[str, int] = {}
        for item in explained_items:
            prov_counts[item.provenance] = prov_counts.get(item.provenance, 0) + 1
        provenance_summary = {k: prov_counts[k] for k in sorted(prov_counts.keys())}

        # 6. Deduplicated & Consolidated Risk Reasons
        risk_reasons = self._consolidate_reasons(assessment, collection)

        # 7. Limitations & Neutrality Disclaimers (enforces UNKNOWN != PREDATORY)
        limitations = self._generate_limitations(assessment, collection)

        # 8. Deterministic Natural Language Summary
        summary = self._generate_summary(assessment, collection, positive_signals, suspicious_signals)

        # 9. Resolved Entity representation
        resolved_dict = collection.resolved_entity.to_dict() if collection.resolved_entity else None

        # 10. Complete deterministically ordered list of all items
        evidence_items = sorted(
            explained_items,
            key=lambda x: (
                0 if x.category == EvidenceCategory.NEGATIVE_SUSPICIOUS.value else (1 if x.category == EvidenceCategory.POSITIVE_TRUST.value else 2),
                -x.contribution,
                x.signal,
                x.source_field,
            ),
        )

        return RiskExplanation(
            opportunity_id=assessment.opportunity_id,
            risk_score=assessment.risk_score,
            risk_level=assessment.risk_level.value,
            risk_confidence=assessment.risk_confidence,
            evidence_sufficiency=evidence_sufficiency,
            is_predatory_flag=assessment.is_predatory_flag,
            summary=summary,
            positive_trust_signals=positive_signals,
            suspicious_signals=suspicious_signals,
            neutral_signals=neutral_signals,
            graph_signals=graph_signals,
            venue_signals=venue_signals,
            publisher_signals=publisher_signals,
            evidence_items=evidence_items,
            risk_reasons=risk_reasons,
            provenance_summary=provenance_summary,
            limitations=limitations,
            gross_negative_score=assessment.gross_negative_score,
            trust_mitigation_score=assessment.trust_mitigation_score,
            resolved_entity=resolved_dict,
        )

    def explain_batch(
        self,
        assessments: list[RiskAssessment],
        opportunities: list[Any] | None = None,
    ) -> list[RiskExplanation]:
        """Generate risk explanations for a batch of assessments deterministically."""
        opp_map: dict[str, Any] = {}
        if opportunities:
            for opp in opportunities:
                oid = getattr(opp, "id", None) or (opp.get("id") if isinstance(opp, dict) else None)
                if oid:
                    opp_map[str(oid)] = opp

        results: list[RiskExplanation] = []
        for a in assessments:
            matched_opp = opp_map.get(str(a.opportunity_id)) if a.opportunity_id else None
            results.append(self.explain(a, opportunity=matched_opp))
        return results

    def _determine_sufficiency(
        self,
        assessment: RiskAssessment,
        collection: RiskEvidenceCollection,
    ) -> str:
        """Categorize evidence sufficiency into SUFFICIENT, INSUFFICIENT, or MINIMAL."""
        if assessment.risk_level == RiskLevel.INSUFFICIENT_EVIDENCE:
            return "INSUFFICIENT"
        if assessment.risk_confidence < 0.35:
            return "MINIMAL"
        return "SUFFICIENT"

    def _build_evidence_explanations(
        self,
        collection: RiskEvidenceCollection,
    ) -> list[RiskEvidenceExplanation]:
        """Convert atomic RiskEvidence items into typed RiskEvidenceExplanation containers."""
        cfg = self.config
        explanations: list[RiskEvidenceExplanation] = []

        for item in collection.items:
            # 1. Compute effective base mathematical contribution
            contrib = 0.0
            str_mult = cfg.strength_multipliers.get(item.strength, 0.00)
            conf_mult = cfg.confidence_multipliers.get(item.confidence, 0.50)

            if item.category == EvidenceCategory.NEGATIVE_SUSPICIOUS and item.is_present:
                base_w = cfg.negative_signal_weights.get(item.signal, 0.30)
                contrib = round(base_w * str_mult * conf_mult, 4)
            elif item.category == EvidenceCategory.POSITIVE_TRUST and item.is_present:
                base_w = cfg.positive_signal_weights.get(item.signal, 0.20)
                contrib = round(base_w * str_mult * conf_mult, 4)

            # 2. Determine Severity
            severity = "NEUTRAL"
            if item.category == EvidenceCategory.POSITIVE_TRUST:
                severity = "TRUST"
            elif item.category == EvidenceCategory.NEGATIVE_SUSPICIOUS:
                if item.strength == EvidenceStrength.STRONG:
                    severity = "HIGH"
                elif item.strength == EvidenceStrength.MODERATE:
                    severity = "MODERATE"
                else:
                    severity = "LOW"

            # 3. Determine Evidence Type
            evidence_type = "DIRECT_METADATA"
            if item.provenance == EvidenceProvenance.GRAPH_ANALYSIS:
                evidence_type = "GRAPH_ANALYSIS"
            elif item.provenance in (
                EvidenceProvenance.STATIC_TRUST_REGISTRY,
                EvidenceProvenance.EXTERNAL_VERIFICATION,
            ) or item.signal in (
                EvidenceSignal.VERIFIED_VENUE_IDENTITY.value,
                EvidenceSignal.VERIFIED_PUBLISHER_IDENTITY.value,
                EvidenceSignal.OPENALEX_METADATA_MATCH.value,
                EvidenceSignal.CROSSREF_METADATA_MATCH.value,
                EvidenceSignal.PUBLISHER_DOMAIN_MATCH.value,
            ):
                evidence_type = "VENUE_INTELLIGENCE"

            # 4. Format Human-Readable Explanation with Provenance
            explanation_text = item.explanation
            if not explanation_text:
                explanation_text = self._format_default_explanation(item)

            explanations.append(
                RiskEvidenceExplanation(
                    signal=item.signal,
                    category=item.category.value,
                    strength=item.strength.value,
                    confidence=item.confidence.value,
                    provenance=item.provenance.value,
                    source_field=item.source_field,
                    matched_value=item.matched_value,
                    explanation=explanation_text,
                    is_present=item.is_present,
                    contribution=contrib,
                    severity=severity,
                    evidence_type=evidence_type,
                    metadata=dict(item.metadata),
                )
            )

        return explanations

    def _format_default_explanation(self, item: RiskEvidence) -> str:
        """Provide conservative fallback explanation based on signal name."""
        name = item.signal.replace("_", " ").title()
        if item.category == EvidenceCategory.POSITIVE_TRUST:
            return f"Verified academic trust indicator: {name}."
        elif item.category == EvidenceCategory.NEGATIVE_SUSPICIOUS:
            return f"Potential cautionary signal: {name} detected in {item.source_field}."
        return f"Neutral observation: {name} ({item.source_field})."

    def _consolidate_reasons(
        self,
        assessment: RiskAssessment,
        collection: RiskEvidenceCollection,
    ) -> list[str]:
        """
        Preserve deterministic reasons from RiskAssessment while consolidating
        correlated graph facts into single cohesive bullet points.
        """
        reasons = list(assessment.risk_reasons)

        # If multiple graph reuse signals exist, ensure anti-correlation note is present
        graph_negative = [
            e for e in collection.negative_evidence
            if e.provenance == EvidenceProvenance.GRAPH_ANALYSIS
        ]
        if len(graph_negative) > 1:
            note = "Correlated graph topology signals consolidated; anti-correlation limits applied."
            if note not in reasons:
                reasons.append(note)

        return reasons

    def _generate_limitations(
        self,
        assessment: RiskAssessment,
        collection: RiskEvidenceCollection,
    ) -> list[str]:
        """
        Generate conservative limitations and neutrality statements.
        Explicitly enforces: UNKNOWN != PREDATORY.
        """
        limitations: list[str] = []

        # 1. Missing metadata neutrality notice
        missing_items = [item for item in collection.items if not item.is_present]
        for item in missing_items:
            field_name = item.source_field.replace("_", " ")
            limitations.append(
                f"Field '{field_name}' was not provided or could not be verified. "
                f"Missing metadata is neutral and does not indicate predatory behavior."
            )

        # 2. Insufficient evidence disclaimer
        if assessment.risk_level == RiskLevel.INSUFFICIENT_EVIDENCE:
            limitations.append(
                "Limited bibliographic metadata available for this venue. "
                "ResearchConnect AI requires corroborated negative signals before assigning elevated risk."
            )

        # 3. Advisory disclaimer
        limitations.append(
            "Risk scores represent automated heuristic screening for academic publishing safety, "
            "not a definitive legal or accreditation determination."
        )

        return sorted(list(dict.fromkeys(limitations)))

    def _generate_summary(
        self,
        assessment: RiskAssessment,
        collection: RiskEvidenceCollection,
        positive_signals: list[RiskEvidenceExplanation],
        suspicious_signals: list[RiskEvidenceExplanation],
    ) -> str:
        """
        Generate deterministic, non-defamatory, academic synthesis of findings.
        """
        score = assessment.risk_score
        conf = assessment.risk_confidence
        level = assessment.risk_level

        if level == RiskLevel.HIGH_RISK:
            top_reasons = [s.signal.replace("_", " ").lower() for s in suspicious_signals[:2]]
            drivers = ", ".join(top_reasons) if top_reasons else "unverified editorial claims"
            return (
                f"Evaluated as High Risk (Score: {score:.2f}, Confidence: {conf:.2f}) "
                f"based on multiple corroborated suspicious indicators ({drivers}). "
                f"Trust mitigation is minimal."
            )

        elif level == RiskLevel.MODERATE_RISK:
            if assessment.trust_mitigation_score > 0:
                return (
                    f"Evaluated as Moderate Risk (Score: {score:.2f}, Confidence: {conf:.2f}). "
                    f"Cautionary indicators were observed, but risk is partially mitigated "
                    f"(-{assessment.trust_mitigation_score:.2f}) by recognized publishing credentials."
                )
            return (
                f"Evaluated as Moderate Risk (Score: {score:.2f}, Confidence: {conf:.2f}). "
                f"Cautionary indicators were observed in venue metadata or domain characteristics."
            )

        elif level == RiskLevel.INSUFFICIENT_EVIDENCE:
            return (
                f"Insufficient evidence available to establish verified trust or elevated risk "
                f"(Score: {score:.2f}, Confidence: {conf:.2f}). "
                f"Metadata is sparse; unverified status is strictly neutral and does not indicate predatory behavior."
            )

        else:
            # LOW_RISK
            if positive_signals:
                top_trust = [s.signal.replace("_", " ").lower() for s in positive_signals[:2]]
                trust_str = ", ".join(top_trust)
                return (
                    f"Verified Low Risk venue (Score: {score:.2f}, Confidence: {conf:.2f}) "
                    f"supported by affirmative trust evidence ({trust_str})."
                )
            return (
                f"Low Risk venue (Score: {score:.2f}, Confidence: {conf:.2f}) "
                f"exhibiting standard academic characteristics with zero suspicious indicators."
            )


# Global singleton
risk_explainability_service = RiskExplainabilityService()
